#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the catalog's product photos with the Gemini API.

    export GEMINI_API_KEY=...                          # from Google AI Studio
    python3 scripts/images.py                          # generate every missing photo
    python3 scripts/images.py --only classic-crew-tee  # one product (repeatable)
    python3 scripts/images.py --only classic-crew-tee --limit 1  # just its first photo
    python3 scripts/images.py --only classic-crew-tee --force   # regenerate it
    python3 scripts/images.py --dry-run                # print the prompts, no API calls
    python3 scripts/images.py --list-models            # image models your key can use
    python3 scripts/images.py --sheet                  # rebuild docs/preview.jpg only
    python3 scripts/images.py --from-raw               # finish images made with another tool

Each product's first photo is generated from its prompt. A photo with
"edit_of" is made by sending that first photo back with an edit instruction,
so every color variant shows the same product from the same angle. With
--no-edit, every photo is generated from its own prompt instead.

To use another image tool, save its output as build/raw/<handle>/<id>.png
(any image format works) and run --from-raw. Each photo's full prompt is
its catalog prompt followed by STYLE, or CLOSEUP_STYLE when it's a close-up.

The key is read from GEMINI_API_KEY, or GOOGLE_API_KEY. With neither set the
script still tries, which works where the environment adds the key itself.

Raw API output is kept in build/raw/ (not committed). Final images are
1200x1200 JPEGs in images/<handle>/<id>.jpg. Afterwards, run
scripts/build.py and scripts/check.py. Needs Pillow (pip install pillow).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

try:
    from PIL import Image
except ImportError:
    sys.exit("This script needs Pillow: pip install pillow")

ROOT = build.ROOT
API = "https://generativelanguage.googleapis.com/v1beta"
# First match wins. Override with --model.
PREFERRED_MODELS = ("gemini-3.1-flash-image", "gemini-2.5-flash-image", "gemini-3-pro-image")
SIZE = 1200
MAX_BYTES = 250 * 1024
BACKGROUND = (241, 239, 236)

STYLE = (
    "Professional e-commerce product photograph. Show only what is described, centered, "
    "filling about 75% of a square frame. Soft, even studio lighting with a subtle natural "
    "shadow underneath. Seamless plain light warm-grey background (#F1EFEC). Photorealistic, "
    "sharp focus, true-to-life colors. No text, no letters, no numbers, no logos, no brand "
    "marks, no watermark, no people, no hands."
)
CLOSEUP_STYLE = (
    "Professional e-commerce detail photograph. A close-up that fills the entire square frame "
    "edge to edge, with no border and no background visible. Soft, even studio lighting. "
    "Photorealistic, sharp focus, true-to-life colors. No text, no letters, no numbers, no logos, "
    "no brand marks, no watermark, no people, no hands."
)
EDIT = (
    "Edit this product photo. {change} Keep everything else exactly the same: the product's "
    "shape, details, angle, framing, lighting, shadow and background. No text or logos."
)

# Some models reject an image-only response or the aspect-ratio setting.
# After a 400 error the script falls back to the plainer request below.
compatible_config = False


def api_request(url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-goog-api-key"] = key
    request = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            detail = e.read().decode(errors="replace")[:300]
            raise SystemExit(
                f"The Gemini API refused the request (HTTP {e.code}). Check that GEMINI_API_KEY is set "
                f"and the key is valid.\n{detail}"
            )
        raise


def image_models(key: str) -> list[str]:
    listing = api_request(f"{API}/models?pageSize=1000", key)
    return sorted(
        m["name"].removeprefix("models/")
        for m in listing.get("models", [])
        if "image" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", [])
    )


def pick_model(key: str) -> str:
    available = image_models(key)
    for preferred in PREFERRED_MODELS:
        for model in available:
            if model == preferred or model.startswith(preferred + "-"):
                return model
    sys.exit(f"No preferred image model is available to this key. Available: {', '.join(available) or 'none'}. Use --model.")


def generate(model: str, key: str, prompt: str, base_image: bytes | None = None) -> bytes:
    global compatible_config
    parts = [{"text": prompt}]
    if base_image is not None:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(base_image).decode()}})

    for attempt in range(5):
        if compatible_config:
            config = {"responseModalities": ["TEXT", "IMAGE"]}
        else:
            config = {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        try:
            response = api_request(f"{API}/models/{model}:generateContent", key, body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:2000]
            if e.code == 400 and not compatible_config:
                compatible_config = True
                continue
            if e.code == 429 and "limit: 0" in detail:
                raise SystemExit(
                    f"The Gemini API has no quota for {model} on this key's project. Image models have no "
                    "free tier: turn on billing for the project in Google AI Studio, then run again."
                )
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                wait = 5 * 3 ** attempt
                print(f"    HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise SystemExit(f"Gemini API error {e.code}: {detail}")

        candidate = (response.get("candidates") or [{}])[0]
        texts = []
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
            if part.get("text"):
                texts.append(part["text"])
        reason = candidate.get("finishReason", "no image returned")
        print(f"    no image ({reason}) {' '.join(texts)[:200]}")
        if attempt < 4:
            time.sleep(3)
    raise SystemExit("Gave up after 5 attempts without an image.")


def finish(raw: bytes) -> bytes:
    """Center-crop to a square, resize to SIZE and compress under MAX_BYTES."""
    image = Image.open(io.BytesIO(raw))
    if image.mode != "RGB":
        flattened = Image.new("RGB", image.size, BACKGROUND)
        flattened.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image = flattened
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS)
    for quality in range(88, 55, -4):
        out = io.BytesIO()
        image.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if out.tell() <= MAX_BYTES:
            break
    return out.getvalue()


def full_prompt(photo: dict) -> str:
    return f"{photo['prompt']}. {CLOSEUP_STYLE if photo.get('closeup') else STYLE}"


def finish_raw(products: list[dict], force: bool) -> None:
    made = 0
    for product in products:
        for photo in product.get("photos", []):
            target = ROOT / build.photo_path(product, photo["id"])
            if target.is_file() and not force:
                continue
            raws = sorted((ROOT / "build" / "raw" / product["handle"]).glob(f"{photo['id']}.*"))
            if not raws:
                print(f"no raw image for {target.relative_to(ROOT)}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(finish(raws[0].read_bytes()))
            made += 1
    sheet = contact_sheet()
    print(f"finished {made} photo(s)" + (f", wrote {sheet.relative_to(ROOT)}" if sheet else ""))
    print("next: python3 scripts/build.py && python3 scripts/check.py")


def contact_sheet() -> Path | None:
    files = []
    for product in build.load_catalog():
        for photo in product.get("photos", []):
            path = ROOT / build.photo_path(product, photo["id"])
            if path.is_file():
                files.append(path)
    if not files:
        return None
    columns, thumb, gap = 8, 220, 10
    rows = -(-len(files) // columns)
    sheet = Image.new("RGB", (columns * (thumb + gap) + gap, rows * (thumb + gap) + gap), (255, 255, 255))
    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB").resize((thumb, thumb), Image.LANCZOS)
        row, column = divmod(index, columns)
        sheet.paste(image, (gap + column * (thumb + gap), gap + row * (thumb + gap)))
    target = ROOT / "docs" / "preview.jpg"
    target.parent.mkdir(exist_ok=True)
    sheet.save(target, "JPEG", quality=82, optimize=True, progressive=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", metavar="HANDLE", help="limit to these product handles")
    parser.add_argument("--force", action="store_true", help="regenerate photos that already exist")
    parser.add_argument("--limit", type=int, metavar="N", help="stop after generating N photos")
    parser.add_argument("--model", help="Gemini model to use (default: the first available of %s)" % ", ".join(PREFERRED_MODELS))
    parser.add_argument("--dry-run", action="store_true", help="print the prompts without calling the API")
    parser.add_argument("--list-models", action="store_true", help="list image models available to your key")
    parser.add_argument("--sheet", action="store_true", help="only rebuild docs/preview.jpg from existing images")
    parser.add_argument("--no-edit", action="store_true", help="generate every photo from its own prompt, without edits")
    parser.add_argument("--from-raw", action="store_true", help="finish images saved in build/raw/ instead of generating")
    args = parser.parse_args()

    if args.sheet:
        target = contact_sheet()
        print(f"wrote {target.relative_to(ROOT)}" if target else "no images yet")
        return

    products = build.load_catalog()
    if args.only:
        unknown = set(args.only) - {p["handle"] for p in products}
        if unknown:
            sys.exit(f"Unknown handle(s): {', '.join(sorted(unknown))}")
        products = [p for p in products if p["handle"] in args.only]

    if args.from_raw:
        finish_raw(products, args.force)
        return

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not args.dry_run and not key:
        print("No GEMINI_API_KEY or GOOGLE_API_KEY set, trying without one (create a key at https://aistudio.google.com/apikey)")
    if args.list_models:
        print("\n".join(image_models(key)))
        return
    model = args.model or ("(dry run)" if args.dry_run else pick_model(key))
    print(f"model: {model}")

    made = 0
    for product in products:
        for photo in product.get("photos", []):
            if args.limit is not None and made >= args.limit:
                break
            target = ROOT / build.photo_path(product, photo["id"])
            if target.is_file() and not args.force:
                continue
            if "edit_of" in photo and not args.no_edit:
                prompt = EDIT.format(change=photo["change"])
                base_path = ROOT / build.photo_path(product, photo["edit_of"])
            else:
                prompt = full_prompt(photo)
                base_path = None
            label = target.relative_to(ROOT)
            if args.dry_run:
                print(f"{label}\n    {'edit of ' + photo['edit_of'] + ': ' if base_path else ''}{prompt}")
                made += 1
                continue
            if base_path is not None and not base_path.is_file():
                print(f"skip {label}: its base photo {base_path.relative_to(ROOT)} is missing")
                continue

            print(f"generating {label}")
            raw = generate(model, key, prompt, base_path.read_bytes() if base_path else None)
            raw_path = ROOT / "build" / "raw" / product["handle"] / f"{photo['id']}.bin"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(raw)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(finish(raw))
            made += 1

    if not args.dry_run:
        target = contact_sheet()
        print(f"generated {made} photo(s)" + (f", wrote {target.relative_to(ROOT)}" if target else ""))
        print("next: python3 scripts/build.py && python3 scripts/check.py")


if __name__ == "__main__":
    main()
