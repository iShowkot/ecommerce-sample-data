#!/usr/bin/env python3
"""Build the platform CSV files and manifest.json from catalog/products.json.

    python3 scripts/build.py               # URLs point at the main branch
    python3 scripts/build.py --ref v1.0.0  # URLs pinned to a release tag

A CSV only references images that exist under images/, so every file imports
cleanly even while some photos are still missing. Needs Python 3.9+ and no
third-party packages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "iShowkot/ecommerce-sample-data"
MAX_ATTRIBUTES = 3

WOO_COLUMNS = [
    "Type", "SKU", "Name", "Published", "Is featured?", "Visibility in catalog",
    "Short description", "Description", "Date sale price starts", "Date sale price ends",
    "Tax status", "Tax class", "In stock?", "Stock", "Backorders allowed?", "Sold individually?",
    "Weight ({w})", "Length ({d})", "Width ({d})", "Height ({d})", "Allow customer reviews?",
    "Sale price", "Regular price", "Categories", "Tags", "Shipping class", "Images",
    "Download limit", "Download expiry days", "Parent", "Grouped products", "Upsells",
    "Cross-sells", "External URL", "Button text", "Position",
]
WOO_ATTRIBUTE_COLUMNS = ["name", "value(s)", "visible", "global", "default"]
WOO_DOWNLOAD_COLUMNS = ["Download 1 name", "Download 1 URL"]

SHOPIFY_COLUMNS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value", "Option3 Name", "Option3 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker", "Variant Inventory Qty",
    "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
    "Variant Compare At Price", "Variant Requires Shipping", "Variant Taxable",
    "Image Src", "Image Position", "Image Alt Text", "Gift Card", "SEO Title", "SEO Description",
    "Variant Image", "Variant Weight Unit", "Status",
]

# (weight unit, dimension unit, kg multiplier, cm divisor)
METRIC = ("kg", "cm", 1.0, 1.0)
IMPERIAL = ("lbs", "in", 2.20462, 2.54)


def load_catalog() -> list[dict]:
    return json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))["products"]


def slug(text: str) -> str:
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def asset_url(ref: str, path: str) -> str:
    return f"https://cdn.jsdelivr.net/gh/{REPO}@{ref}/{path}"


def raw_url(ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}"


def num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def flag(value) -> str:
    return "1" if value else "0"


def platforms(product: dict) -> list[str]:
    if product["type"] in ("grouped", "external"):
        return ["woocommerce"]
    return ["woocommerce", "shopify"]


def photo_path(product: dict, photo_id: str) -> str:
    return f"images/{product['handle']}/{photo_id}.jpg"


def photo_alt(product: dict, photo: dict) -> str:
    option = product.get("image_option")
    if option:
        for value in next(o["values"] for o in product["options"] if o["name"] == option):
            if slug(value) == photo["id"]:
                return f"{product['name']} - {value}"
    if photo.get("alt"):
        return f"{product['name']} - {photo['alt']}"
    return product["name"]


def photos(product: dict) -> list[tuple[str, str]]:
    """(path, alt text) for each catalog photo that exists on disk, in catalog order."""
    found = []
    for photo in product.get("photos", []):
        path = photo_path(product, photo["id"])
        if (ROOT / path).is_file():
            found.append((path, photo_alt(product, photo)))
    return found


def default_stock(sku: str) -> int:
    # Stable pseudo-random stock between 4 and 60, so rebuilds don't churn the CSVs.
    return int(hashlib.sha1(sku.encode()).hexdigest(), 16) % 57 + 4


def variants(product: dict) -> list[dict]:
    options = product.get("options", [])
    names = [o["name"] for o in options]
    result = []
    for combo in itertools.product(*(o["values"] for o in options)):
        values = dict(zip(names, combo))
        sku = "-".join([product["sku"], *(slug(v).upper() for v in combo)])
        variant = {
            "values": values,
            "sku": sku,
            "price": product["price"],
            "sale_price": product.get("sale_price", ""),
            "stock": default_stock(sku),
            "weight_kg": None,
        }
        for rule in product.get("variant_rules", []):
            if all(values[k] == v for k, v in rule["when"].items()):
                variant.update({k: v for k, v in rule.items() if k != "when"})
        result.append(variant)
    return result


def variant_photo(product: dict, variant: dict) -> str | None:
    option = product.get("image_option")
    if not option:
        return None
    path = photo_path(product, slug(variant["values"][option]))
    return path if (ROOT / path).is_file() else None


def to_csv(columns: list[str], rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return out.getvalue()


# --- WooCommerce -------------------------------------------------------------

def woo_columns(units) -> list[str]:
    weight_unit, dimension_unit = units[0], units[1]
    columns = [c.format(w=weight_unit, d=dimension_unit) for c in WOO_COLUMNS]
    for i in range(1, MAX_ATTRIBUTES + 1):
        columns += [f"Attribute {i} {suffix}" for suffix in WOO_ATTRIBUTE_COLUMNS]
    return columns + WOO_DOWNLOAD_COLUMNS


def woo_measurements(weight_kg, dimensions_cm, units) -> dict:
    weight_unit, dimension_unit, kg_factor, cm_divisor = units
    row = {}
    if weight_kg is not None:
        row[f"Weight ({weight_unit})"] = num(round(weight_kg * kg_factor, 2))
    if dimensions_cm:
        for label, value in zip(("Length", "Width", "Height"), dimensions_cm):
            row[f"{label} ({dimension_unit})"] = num(round(value / cm_divisor, 1))
    return row


def woo_type(product: dict) -> str:
    parts = [product["type"]]
    if product.get("downloads"):
        parts.append("downloadable")
    if product.get("virtual"):
        parts.append("virtual")
    return ", ".join(parts)


def woo_escape(value: str) -> str:
    # The importer splits list cells on commas; a literal comma is written as "\,".
    return value.replace(",", "\\,")


def woo_stock(stock, backorders: str) -> dict:
    allowed = {"no": "0", "yes": "1", "notify": "notify"}[backorders]
    if stock is None:
        return {"In stock?": "1", "Stock": "", "Backorders allowed?": allowed}
    if stock > 0:
        status = "1"
    else:
        status = "backorder" if backorders != "no" else "0"
    return {"In stock?": status, "Stock": str(stock), "Backorders allowed?": allowed}


def woo_rows(products: list[dict], ref: str, units) -> list[dict]:
    sku_of = {p["handle"]: p["sku"] for p in products}

    def related(handles: list[str]) -> str:
        # Only link products that are in the same file. A SKU the file never
        # defines would leave an "Import placeholder" product behind in the store.
        return ", ".join(sku_of[h] for h in handles if h in sku_of)

    rows = []
    for p in products:
        variable = p["type"] == "variable"
        has_price = p["type"] in ("simple", "external")
        row = {
            "Type": woo_type(p),
            "SKU": p["sku"],
            "Name": p["name"],
            "Published": "-1" if p.get("status") == "draft" else "1",
            "Is featured?": flag(p.get("featured")),
            "Visibility in catalog": p.get("visibility", "visible"),
            "Short description": p["short_description"],
            "Description": p["description"],
            "Date sale price starts": p.get("sale_from", ""),
            "Date sale price ends": p.get("sale_to", ""),
            "Tax status": p.get("tax_status", "taxable"),
            "Sold individually?": flag(p.get("sold_individually")),
            "Allow customer reviews?": "1",
            "Sale price": p.get("sale_price", "") if has_price else "",
            "Regular price": p["price"] if has_price else "",
            "Categories": p["category"],
            "Tags": ", ".join(woo_escape(t) for t in p["tags"]),
            "Shipping class": p.get("shipping_class", ""),
            "Images": ", ".join(asset_url(ref, path) for path, _ in photos(p)),
            "Grouped products": related(p.get("children", [])),
            "Upsells": related(p.get("upsells", [])),
            "Cross-sells": related(p.get("cross_sells", [])),
            "External URL": p.get("external_url", ""),
            "Button text": p.get("button_text", ""),
            "Position": "0",
        }
        row.update(woo_stock(None if variable else p.get("stock"), p.get("backorders", "no")))
        row.update(woo_measurements(p.get("weight_kg"), p.get("dimensions_cm"), units))

        attributes = [
            (o["name"], o["values"], "1", p.get("defaults", {}).get(o["name"], ""))
            for o in p.get("options", [])
        ] + [(a["name"], a["values"], "0", "") for a in p.get("attributes", [])]
        for i, (name, values, is_global, default) in enumerate(attributes, start=1):
            row[f"Attribute {i} name"] = name
            row[f"Attribute {i} value(s)"] = ", ".join(woo_escape(v) for v in values)
            row[f"Attribute {i} visible"] = "1"
            row[f"Attribute {i} global"] = is_global
            row[f"Attribute {i} default"] = default

        for download in p.get("downloads", []):
            row["Download 1 name"] = download["name"]
            row["Download 1 URL"] = asset_url(ref, download["file"])
        rows.append(row)

        if not variable:
            continue
        for position, v in enumerate(variants(p), start=1):
            image = variant_photo(p, v)
            variation = {
                "Type": "variation",
                "SKU": v["sku"],
                "Name": f"{p['name']} - {', '.join(v['values'].values())}",
                "Published": "1",
                "Is featured?": "0",
                "Visibility in catalog": "visible",
                "Tax status": "taxable",
                "Tax class": "parent",
                "Sold individually?": "0",
                "Allow customer reviews?": "0",
                "Sale price": v["sale_price"],
                "Regular price": v["price"],
                "Images": asset_url(ref, image) if image else "",
                "Parent": p["sku"],
                "Position": str(position),
            }
            variation.update(woo_stock(v["stock"], "no"))
            variation.update(woo_measurements(v["weight_kg"], None, units))
            for i, (name, value) in enumerate(v["values"].items(), start=1):
                variation[f"Attribute {i} name"] = name
                variation[f"Attribute {i} value(s)"] = woo_escape(value)
                variation[f"Attribute {i} global"] = "1"
            rows.append(variation)
    return rows


# --- Shopify -----------------------------------------------------------------

def shopify_rows(products: list[dict], ref: str) -> list[dict]:
    rows = []
    for p in products:
        if "shopify" not in platforms(p):
            continue
        if p["type"] == "variable":
            product_variants = variants(p)
        else:
            product_variants = [{
                "values": {"Title": "Default Title"},
                "sku": p["sku"],
                "price": p["price"],
                "sale_price": p.get("sale_price", ""),
                "stock": p.get("stock"),
                "weight_kg": None,
            }]
        tracked = not p.get("virtual")
        backorders = p.get("backorders", "no") != "no"
        product_rows = []
        for index, v in enumerate(product_variants):
            row = {"Handle": p["handle"]}
            if index == 0:
                listed = p.get("status") != "draft" and p.get("visibility", "visible") == "visible"
                row.update({
                    "Title": p["name"],
                    "Body (HTML)": p["description"],
                    "Vendor": p["vendor"],
                    "Type": p["category"].split(">")[-1].strip(),
                    "Tags": ", ".join(p["tags"]),
                    "Published": "TRUE" if listed else "FALSE",
                    "Gift Card": "FALSE",
                    "SEO Title": p["name"],
                    "SEO Description": p["short_description"],
                    "Status": "draft" if p.get("status") == "draft" else "active",
                })
            for i, (name, value) in enumerate(v["values"].items(), start=1):
                if index == 0:
                    row[f"Option{i} Name"] = name
                row[f"Option{i} Value"] = value

            weight_kg = v["weight_kg"] if v["weight_kg"] is not None else p.get("weight_kg") or 0
            grams = round(weight_kg * 1000)
            on_sale = bool(v["sale_price"])
            stock = v["stock"] if tracked else None
            image = variant_photo(p, v)
            row.update({
                "Variant SKU": v["sku"],
                "Variant Grams": str(grams),
                "Variant Inventory Tracker": "shopify" if stock is not None else "",
                "Variant Inventory Qty": str(stock) if stock is not None else "",
                "Variant Inventory Policy": "continue" if backorders else "deny",
                "Variant Fulfillment Service": "manual",
                "Variant Price": v["sale_price"] if on_sale else v["price"],
                "Variant Compare At Price": v["price"] if on_sale else "",
                "Variant Requires Shipping": "FALSE" if p.get("virtual") else "TRUE",
                "Variant Taxable": "FALSE" if p.get("tax_status") == "none" else "TRUE",
                "Variant Image": asset_url(ref, image) if image else "",
                "Variant Weight Unit": "kg" if grams >= 1000 else "g",
            })
            product_rows.append(row)

        # Product images fill the Image columns from the first row down, then
        # continue on image-only rows, the same layout as a Shopify export.
        for position, (path, alt) in enumerate(photos(p), start=1):
            if position > len(product_rows):
                product_rows.append({"Handle": p["handle"]})
            product_rows[position - 1].update({
                "Image Src": asset_url(ref, path),
                "Image Position": str(position),
                "Image Alt Text": alt,
            })
        rows += product_rows
    return rows


# --- Output ------------------------------------------------------------------

def version_for(ref: str) -> str:
    match = re.fullmatch(r"v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)", ref)
    return match.group(1) if match else "unreleased"


def render(ref: str) -> dict[str, str]:
    """Return {repo-relative path: file content} for every generated file."""
    products = load_catalog()
    small = [p for p in products if p.get("small")]
    shopify_products = [p for p in products if "shopify" in platforms(p)]

    outputs = {
        "woocommerce/products.csv": (woo_columns(METRIC), woo_rows(products, ref, METRIC), products),
        "woocommerce/products-imperial.csv": (woo_columns(IMPERIAL), woo_rows(products, ref, IMPERIAL), products),
        "woocommerce/products-small.csv": (woo_columns(METRIC), woo_rows(small, ref, METRIC), small),
        "shopify/products.csv": (SHOPIFY_COLUMNS, shopify_rows(products, ref), shopify_products),
        "shopify/products-small.csv": (
            SHOPIFY_COLUMNS, shopify_rows(small, ref), [p for p in small if "shopify" in platforms(p)]
        ),
    }
    descriptions = {
        "woocommerce/products.csv": "Full catalog for WooCommerce, metric units (kg, cm).",
        "woocommerce/products-imperial.csv": "Full catalog for WooCommerce, imperial units (lbs, in).",
        "woocommerce/products-small.csv": "{products} products for a quick WooCommerce test, metric units.",
        "shopify/products.csv": "Full catalog for Shopify. Grouped and external products are WooCommerce-only, so they are left out.",
        "shopify/products-small.csv": "{products} products for a quick Shopify test.",
    }
    files = {path: to_csv(columns, rows) for path, (columns, rows, _) in outputs.items()}

    manifest_files = []
    for path, (columns, rows, included) in outputs.items():
        manifest_files.append({
            "path": path,
            "platform": path.split("/")[0],
            "description": descriptions[path].format(products=len(included)),
            "products": len(included),
            "variations": sum(len(variants(p)) for p in included if p["type"] == "variable"),
            "rows": len(rows),
            "url": asset_url(ref, path),
            "raw_url": raw_url(ref, path),
        })

    expected_photos = sum(len(p.get("photos", [])) for p in products)
    available_photos = sum(len(photos(p)) for p in products)
    manifest = {
        "name": "ecommerce-sample-data",
        "description": "Import-ready sample product CSVs for WooCommerce and Shopify, with product photos and matching images for each variant.",
        "repository": f"https://github.com/{REPO}",
        "license": "CC0-1.0",
        "version": version_for(ref),
        "ref": ref,
        "asset_base_url": asset_url(ref, ""),
        "images": {"expected": expected_photos, "available": available_photos},
        "files": manifest_files,
        "products": [
            {
                "handle": p["handle"],
                "name": p["name"],
                "type": p["type"],
                "sku": p["sku"],
                "category": p["category"],
                "platforms": platforms(p),
                "variations": len(variants(p)) if p["type"] == "variable" else 0,
                "images": {"expected": len(p.get("photos", [])), "available": len(photos(p))},
                "tests": p.get("notes", []),
            }
            for p in products
        ],
    }
    files["manifest.json"] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="main", help="git branch or tag that image and file URLs point at (default: main)")
    args = parser.parse_args()

    for path, content in render(args.ref).items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
