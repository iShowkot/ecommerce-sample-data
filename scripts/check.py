#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate the catalog, the generated CSVs and the images.

    python3 scripts/check.py                   # offline checks (CI runs this on every push)
    python3 scripts/check.py --require-images  # also fail when a catalog photo is missing
    python3 scripts/check.py --online          # also check that every URL in the CSVs loads

The CSV rules mirror what the WooCommerce and Shopify importers enforce, so a
file that passes here should import without row errors. Needs Python 3.9+ and
no third-party packages.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
PRICE = re.compile(r"^\d+\.\d{2}$")
SKU = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")
HANDLE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
IMAGE_SIZE = (1200, 1200)
MAX_IMAGE_BYTES = 300 * 1024
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TYPES = {"simple", "variable", "grouped", "external"}
PRODUCT_FIELDS = {
    "handle", "sku", "name", "type", "vendor", "category", "tags", "short_description", "description",
    "price", "sale_price", "sale_from", "sale_to", "tax_status", "stock", "backorders", "sold_individually",
    "featured", "status", "visibility", "virtual", "downloads", "weight_kg", "dimensions_cm", "shipping_class",
    "attributes", "options", "image_option", "defaults", "variant_rules", "photos", "upsells", "cross_sells",
    "children", "external_url", "button_text", "small", "notes",
}
RULE_FIELDS = {"when", "price", "sale_price", "stock", "weight_kg"}
SHOPIFY_MAX_VARIANTS = 100

errors: list[str] = []
warnings: list[str] = []


def error(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


# --- Catalog -------------------------------------------------------------------

def check_catalog(products: list[dict]) -> None:
    handles = [p["handle"] for p in products]
    by_handle = {p["handle"]: p for p in products}
    for handle in {h for h in handles if handles.count(h) > 1}:
        error(f"catalog: duplicate handle {handle}")

    skus: list[str] = []
    for p in products:
        where = f"catalog: {p['handle']}"
        if not HANDLE.match(p["handle"]):
            error(f"{where}: handle must be lowercase words joined by hyphens")
        if p["type"] not in TYPES:
            error(f"{where}: unknown type {p['type']!r}")
            continue
        unknown = set(p) - PRODUCT_FIELDS
        if unknown:
            error(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        for field in ("sku", "name", "vendor", "category", "tags", "short_description", "description", "photos"):
            if not p.get(field):
                error(f"{where}: missing {field}")
        for field in ("sale_from", "sale_to"):
            if field in p and not DATE.match(p[field]):
                error(f"{where}: {field} must look like 2025-01-31")
        if p.get("tax_status", "taxable") not in ("taxable", "none"):
            error(f"{where}: tax_status must be taxable or none")
        if p.get("status", "publish") not in ("publish", "draft"):
            error(f"{where}: status must be publish or draft")
        if p.get("visibility", "visible") not in ("visible", "hidden"):
            error(f"{where}: visibility must be visible or hidden")
        if p.get("backorders", "no") not in ("no", "notify", "yes"):
            error(f"{where}: backorders must be no, notify or yes")

        if p["type"] != "grouped":
            check_price(where, p.get("price"), p.get("sale_price"))
        elif "price" in p:
            error(f"{where}: grouped products take their prices from their children")

        if p["type"] == "variable":
            check_options(p, where)
            skus += [v["sku"] for v in build.variants(p)]
        elif p.get("options"):
            error(f"{where}: only variable products can have options")
        skus.append(p["sku"])

        check_photos(p, where)

        for key in ("children", "upsells", "cross_sells"):
            for handle in p.get(key, []):
                if handle not in by_handle:
                    error(f"{where}: {key} refers to unknown product {handle}")
        if p["type"] == "grouped":
            if not p.get("children"):
                error(f"{where}: grouped product needs children")
            for handle in p.get("children", []):
                child = by_handle.get(handle)
                if child and child["type"] == "grouped":
                    error(f"{where}: a grouped product cannot contain another grouped product")
                if child and p.get("small") and not child.get("small"):
                    error(f"{where}: is in the small files but its child {handle} is not")
        if p["type"] == "external" and not p.get("external_url"):
            error(f"{where}: external product needs external_url")
        for download in p.get("downloads", []):
            if not (ROOT / download["file"]).is_file():
                error(f"{where}: download file {download['file']} does not exist")
        if len(p.get("downloads", [])) > 1:
            error(f"{where}: the CSV has columns for one download only")

    for sku in {s for s in skus if skus.count(s) > 1}:
        error(f"catalog: duplicate SKU {sku}")
    for sku in skus:
        if not SKU.match(sku):
            error(f"catalog: SKU {sku} should use only A-Z, 0-9 and single hyphens")


def check_price(where: str, price, sale_price) -> None:
    if not price or not PRICE.match(price):
        error(f"{where}: price must look like 12.00")
        return
    if sale_price:
        if not PRICE.match(sale_price):
            error(f"{where}: sale price must look like 12.00")
        elif float(sale_price) >= float(price):
            error(f"{where}: sale price must be lower than the price")


def check_options(p: dict, where: str) -> None:
    options = p.get("options", [])
    if not options:
        error(f"{where}: variable product needs options")
        return
    attribute_count = len(options) + len(p.get("attributes", []))
    if len(options) > 3:
        error(f"{where}: Shopify allows at most 3 options")
    if attribute_count > build.MAX_ATTRIBUTES:
        error(f"{where}: {attribute_count} attributes, but the WooCommerce CSV has {build.MAX_ATTRIBUTES} attribute columns")
    values_by_name = {}
    for option in options:
        values = option["values"]
        values_by_name[option["name"]] = values
        if not values:
            error(f"{where}: option {option['name']} has no values")
        if len(set(values)) != len(values):
            error(f"{where}: option {option['name']} has duplicate values")
        if len({build.slug(v) for v in values}) != len(values):
            error(f"{where}: option {option['name']} has values that give the same SKU part")
        for value in values:
            if "," in value:
                error(f"{where}: option value {value!r} contains a comma")
    names = [o["name"] for o in options] + [a["name"] for a in p.get("attributes", [])]
    if len({n.lower() for n in names}) != len(names):
        error(f"{where}: attribute names must be unique")

    variant_count = 1
    for values in values_by_name.values():
        variant_count *= len(values)
    if variant_count > SHOPIFY_MAX_VARIANTS:
        error(f"{where}: {variant_count} variants, keep it at or under {SHOPIFY_MAX_VARIANTS}")

    for name, value in p.get("defaults", {}).items():
        if value not in values_by_name.get(name, []):
            error(f"{where}: default {name}={value} is not an option value")
    for rule in p.get("variant_rules", []):
        unknown = set(rule) - RULE_FIELDS
        if unknown:
            error(f"{where}: variant rule has unknown fields {sorted(unknown)}")
        for name, value in rule.get("when", {}).items():
            if value not in values_by_name.get(name, []):
                error(f"{where}: variant rule matches {name}={value}, which is not an option value")
        for field in ("price", "sale_price"):
            if field in rule and not PRICE.match(rule[field]):
                error(f"{where}: variant rule {field} must look like 12.00")

    image_option = p.get("image_option")
    if image_option:
        if image_option not in values_by_name:
            error(f"{where}: image_option {image_option} is not an option")
        else:
            photo_ids = {photo["id"] for photo in p.get("photos", [])}
            for value in values_by_name[image_option]:
                if build.slug(value) not in photo_ids:
                    error(f"{where}: no photo with id {build.slug(value)} for {image_option} {value}")


def check_photos(p: dict, where: str) -> None:
    seen: dict[str, dict] = {}
    for photo in p.get("photos", []):
        photo_id = photo.get("id", "")
        if not HANDLE.match(photo_id):
            error(f"{where}: photo id {photo_id!r} must be lowercase words joined by hyphens")
        if photo_id in seen:
            error(f"{where}: duplicate photo id {photo_id}")
        if "edit_of" in photo:
            base = seen.get(photo["edit_of"])
            if base is None:
                error(f"{where}: photo {photo_id} edits {photo['edit_of']}, which must be listed before it")
            elif "edit_of" in base:
                error(f"{where}: photo {photo_id} must edit an original photo, not another edit")
            if not photo.get("change"):
                error(f"{where}: photo {photo_id} needs a change description")
        elif not photo.get("prompt"):
            error(f"{where}: photo {photo_id} needs a prompt")
        seen[photo_id] = photo


# --- Generated files -----------------------------------------------------------

def built_ref() -> str:
    try:
        return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["ref"]
    except (OSError, KeyError, ValueError):
        return "main"


def check_up_to_date(ref: str) -> None:
    for path, content in build.render(ref).items():
        target = ROOT / path
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            error(f"{path}: out of date, run: python3 scripts/build.py --ref {ref}")


def read_csv(path: str) -> tuple[list[str], list[dict]]:
    text = (ROOT / path).read_text(encoding="utf-8")
    if text.startswith("﻿"):
        error(f"{path}: starts with a byte order mark")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), list(reader)


def split_list(cell: str) -> list[str]:
    # Same splitting as the WooCommerce importer: commas, with "\," for a literal comma.
    return [part.strip().replace("::comma::", ",") for part in cell.replace("\\,", "::comma::").split(",")] if cell else []


def local_path(url: str, ref: str) -> str | None:
    prefix = build.asset_url(ref, "")
    return url[len(prefix):] if url.startswith(prefix) else None


def check_asset_url(where: str, url: str, ref: str) -> None:
    path = local_path(url, ref)
    if path is None:
        error(f"{where}: URL {url} does not point at {build.asset_url(ref, '')}")
    elif not (ROOT / path).is_file():
        error(f"{where}: {path} does not exist in the repository")


def check_woocommerce_csv(path: str, ref: str) -> None:
    columns, rows = read_csv(path)
    units = build.IMPERIAL if "imperial" in path else build.METRIC
    if columns != build.woo_columns(units):
        error(f"{path}: columns differ from the expected WooCommerce header")
    if "ID" in columns:
        error(f"{path}: has an ID column; IDs only fit the store they came from, and WooCommerce 11.1+ refuses new variations with IDs when updating existing products")

    defined: dict[str, dict] = {}
    variation_counts: dict[str, int] = {}
    for number, row in enumerate(rows, start=2):
        where = f"{path}:{number}"
        sku = row["SKU"]
        if not sku:
            error(f"{where}: missing SKU")
        if sku in defined:
            error(f"{where}: duplicate SKU {sku}")
        product_type = split_list(row["Type"])[0] if row["Type"] else ""

        for url in split_list(row["Images"]):
            check_asset_url(where, url, ref)
        if row["Download 1 URL"]:
            check_asset_url(where, row["Download 1 URL"], ref)

        if product_type == "variation":
            parent = defined.get(row["Parent"])
            if parent is None or parent["type"] != "variable":
                error(f"{where}: parent {row['Parent']} must be a variable product on an earlier row")
            else:
                variation_counts[row["Parent"]] += 1
                check_variation_attributes(where, row, parent)
            if not row["Regular price"]:
                error(f"{where}: variation needs a regular price")
            if len(split_list(row["Images"])) > 1:
                error(f"{where}: a variation can have only one image")
        else:
            attributes = {}
            for i in range(1, build.MAX_ATTRIBUTES + 1):
                name = row[f"Attribute {i} name"]
                if name:
                    attributes[name] = {
                        "values": split_list(row[f"Attribute {i} value(s)"]),
                        "global": row[f"Attribute {i} global"],
                        "default": row[f"Attribute {i} default"],
                    }
            for name, attribute in attributes.items():
                if attribute["default"] and attribute["default"] not in attribute["values"]:
                    error(f"{where}: default {attribute['default']} is not a value of {name}")
            if product_type == "variable":
                variation_counts[sku] = 0
                if row["Regular price"]:
                    error(f"{where}: variable products take their prices from their variations")
            elif product_type in ("simple", "external") and not row["Regular price"]:
                error(f"{where}: missing regular price")
            defined[sku] = {"type": product_type, "attributes": attributes}

    for parent, count in variation_counts.items():
        if count == 0:
            error(f"{path}: variable product {parent} has no variations")
    for number, row in enumerate(rows, start=2):
        for column in ("Grouped products", "Upsells", "Cross-sells"):
            for related in split_list(row[column]):
                if related not in defined:
                    error(f"{path}:{number}: {column} refers to {related}, which this file does not define")


def check_variation_attributes(where: str, row: dict, parent: dict) -> None:
    seen = set()
    for i in range(1, build.MAX_ATTRIBUTES + 1):
        name = row[f"Attribute {i} name"]
        if not name:
            continue
        seen.add(name)
        attribute = parent["attributes"].get(name)
        if attribute is None:
            error(f"{where}: parent has no {name} attribute")
            continue
        if row[f"Attribute {i} global"] != attribute["global"]:
            error(f"{where}: {name} global flag differs from the parent row")
        value = row[f"Attribute {i} value(s)"].replace("\\,", ",")
        if value not in attribute["values"]:
            error(f"{where}: {value} is not one of the parent's {name} values")
    for name, attribute in parent["attributes"].items():
        if attribute["global"] == "1" and name not in seen:
            error(f"{where}: missing a value for the variation attribute {name}")


def check_shopify_csv(path: str, ref: str) -> None:
    columns, rows = read_csv(path)
    if columns != build.SHOPIFY_COLUMNS:
        error(f"{path}: columns differ from the expected Shopify header")

    products: dict[str, list[tuple[int, dict]]] = {}
    order: list[str] = []
    for number, row in enumerate(rows, start=2):
        handle = row["Handle"]
        if not handle:
            error(f"{path}:{number}: missing Handle")
            continue
        if handle in products and order[-1] != handle:
            error(f"{path}:{number}: rows for {handle} must be next to each other")
        if handle not in products:
            products[handle] = []
            order.append(handle)
        products[handle].append((number, row))

    skus = set()
    for handle, product_rows in products.items():
        first_number, first = product_rows[0]
        where = f"{path}:{first_number}"
        if not first["Title"]:
            error(f"{where}: first row of {handle} needs a Title")
        for column in ("Published", "Gift Card"):
            if first[column] not in ("TRUE", "FALSE"):
                error(f"{where}: {column} must be TRUE or FALSE")
        if first["Status"] not in ("active", "draft", "archived"):
            error(f"{where}: Status must be active, draft or archived")
        option_names = [first[f"Option{i} Name"] for i in range(1, 4) if first[f"Option{i} Name"]]

        images = []
        combos = set()
        for number, row in product_rows:
            where = f"{path}:{number}"
            if row["Image Src"]:
                check_asset_url(where, row["Image Src"], ref)
                images.append(row["Image Src"])
                if row["Image Position"] != str(len(images)):
                    error(f"{where}: Image Position should be {len(images)}")
            if not row["Variant SKU"]:
                if any(row[f"Option{i} Value"] for i in range(1, 4)):
                    error(f"{where}: option values without a Variant SKU")
                continue
            if row["Variant SKU"] in skus:
                error(f"{where}: duplicate Variant SKU {row['Variant SKU']}")
            skus.add(row["Variant SKU"])
            combo = tuple(row[f"Option{i} Value"] for i in range(1, len(option_names) + 1))
            if not all(combo):
                error(f"{where}: missing an option value")
            if combo in combos:
                error(f"{where}: repeats the option values {combo}")
            combos.add(combo)
            if not PRICE.match(row["Variant Price"]):
                error(f"{where}: Variant Price must look like 12.00")
            if row["Variant Compare At Price"] and float(row["Variant Compare At Price"]) <= float(row["Variant Price"]):
                error(f"{where}: Compare At Price must be higher than the price")
            if not row["Variant Grams"].isdigit():
                error(f"{where}: Variant Grams must be a whole number")
            for column in ("Variant Requires Shipping", "Variant Taxable"):
                if row[column] not in ("TRUE", "FALSE"):
                    error(f"{where}: {column} must be TRUE or FALSE")
            if row["Variant Inventory Policy"] not in ("deny", "continue"):
                error(f"{where}: Variant Inventory Policy must be deny or continue")
            if row["Variant Image"]:
                check_asset_url(where, row["Variant Image"], ref)
        for number, row in product_rows:
            if row["Variant Image"] and row["Variant Image"] not in images:
                error(f"{path}:{number}: Variant Image is not one of the product's images")
        if len(combos) > SHOPIFY_MAX_VARIANTS:
            error(f"{where}: more than {SHOPIFY_MAX_VARIANTS} variants")


# --- Images --------------------------------------------------------------------

def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG's frame header, or None if it isn't a JPEG."""
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        i += 2 + length
    return None


def check_images(products: list[dict], require: bool) -> None:
    expected = {}
    for p in products:
        for photo in p.get("photos", []):
            expected[build.photo_path(p, photo["id"])] = p["handle"]

    missing = [path for path in expected if not (ROOT / path).is_file()]
    if missing:
        message = f"images: {len(missing)} of {len(expected)} catalog photos are missing (run scripts/images.py)"
        error(message) if require else warn(message)

    for file in sorted((ROOT / "images").rglob("*")) if (ROOT / "images").is_dir() else []:
        if file.is_dir() or file.name == ".gitkeep":
            continue
        path = file.relative_to(ROOT).as_posix()
        if path not in expected:
            warn(f"{path}: not used by any product in the catalog")
            continue
        data = file.read_bytes()
        size = jpeg_size(data)
        if size is None:
            error(f"{path}: not a JPEG file")
        elif size != IMAGE_SIZE:
            error(f"{path}: is {size[0]}x{size[1]}, expected {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}")
        if len(data) > MAX_IMAGE_BYTES:
            error(f"{path}: {len(data) // 1024} KB, keep images under {MAX_IMAGE_BYTES // 1024} KB")


# --- Online --------------------------------------------------------------------

def url_status(url: str) -> tuple[str, str | None]:
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": "ecommerce-sample-data-check"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 200:
                    return url, None
        except urllib.error.HTTPError as e:
            if method == "GET":
                return url, f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            if method == "GET":
                return url, str(getattr(e, "reason", e))
    return url, "no 200 response"


def check_online(paths: list[str]) -> None:
    urls = set()
    for path in paths:
        _, rows = read_csv(path)
        for row in rows:
            for column in ("Images", "Image Src", "Variant Image", "Download 1 URL"):
                urls.update(split_list(row.get(column, "")) if column == "Images" else [row.get(column, "")])
    urls.discard("")
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    urls.update(f["url"] for f in manifest["files"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, problem in pool.map(url_status, sorted(urls)):
            if problem:
                error(f"online: {url} -> {problem}")
    print(f"checked {len(urls)} URLs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--require-images", action="store_true", help="fail when a catalog photo is missing")
    parser.add_argument("--online", action="store_true", help="check that every URL in the CSVs loads")
    args = parser.parse_args()

    products = build.load_catalog()
    ref = built_ref()
    check_catalog(products)
    check_images(products, args.require_images)
    if not errors:
        check_up_to_date(ref)
    woo_files = ["woocommerce/products.csv", "woocommerce/products-imperial.csv", "woocommerce/products-small.csv"]
    shopify_files = ["shopify/products.csv", "shopify/products-small.csv"]
    for path in woo_files:
        if (ROOT / path).is_file():
            check_woocommerce_csv(path, ref)
    for path in shopify_files:
        if (ROOT / path).is_file():
            check_shopify_csv(path, ref)
    if args.online:
        check_online(woo_files + shopify_files)

    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
