# Ecommerce Sample Data

Open-source sample product data for **WooCommerce** and **Shopify**: import-ready CSVs with real-looking product photos and a matching image for every variant. Free to use for anything.

[![check](https://github.com/iShowkot/ecommerce-sample-data/actions/workflows/check.yml/badge.svg)](https://github.com/iShowkot/ecommerce-sample-data/actions/workflows/check.yml)
[![Data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-blue)](LICENSE)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue)](LICENSE-CODE)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

> **Status: almost ready for v1.0.0.** The CSVs and all 59 product photos are done and pass validation. Next up: import tests on current WooCommerce and Shopify, then the first release. See the [roadmap](ROADMAP.md).

![All 59 product photos in the catalog](docs/preview.jpg)

## Download

| File | Platform | Products | Variations | Use it for |
|---|---|---:|---:|---|
| [`woocommerce/products.csv`](https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/woocommerce/products.csv) | WooCommerce | 31 | 117 | The full catalog, weights in kg and sizes in cm |
| [`woocommerce/products-imperial.csv`](https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/woocommerce/products-imperial.csv) | WooCommerce | 31 | 117 | The full catalog for stores set to lbs and inches |
| [`woocommerce/products-small.csv`](https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/woocommerce/products-small.csv) | WooCommerce | 8 | 38 | A quick test |
| [`shopify/products.csv`](https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/shopify/products.csv) | Shopify | 29 | 117 | The full catalog |
| [`shopify/products-small.csv`](https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/shopify/products-small.csv) | Shopify | 7 | 38 | A quick test |

Right-click a link and choose "Save link as", or use `curl -O <link>`.

## What's inside

The same fictional catalog is in both formats, so you can also use it to test migrations between the two platforms.

| Category | Products | What they cover |
|---|---|---|
| Clothing | T-shirt (5 colors × 5 sizes), hoodie, beanie, socks, linen shirt | Color × size, an image per color, sale and out-of-stock variations, a default variation |
| Shoes | Trail sneaker (3 colors × 6 sizes), slide sandal | Many variations, numeric and range sizes |
| Bags & accessories | Backpack, wallet, sunglasses, tote, enamel pins | Images chosen by "Frame Color", a scheduled sale, a one-per-order product |
| Home & kitchen | Mug, candle, cushion cover, French press, cutting board, spare lid | A scent option, price by size, a gallery image, backorders, a hidden product |
| Beauty | Face serum, lip balm trio | Price and weight that change by size |
| Electronics | Headphones, phone case, USB-C cable | Three options on one product (Shopify's maximum) |
| Food & drink | Coffee beans (bag size × grind), tea sampler | Options that aren't color or size |
| Digital & services | E-book with a real PDF download, gift wrapping | Downloadable, virtual and non-taxable products |
| Other | Art print, yoga mat | Draft status, a shipping class |
| WooCommerce only | Breakfast set, ceramic vase | Grouped and external products |

[`manifest.json`](manifest.json) lists every product with what it tests.

All SKUs start with `ESD-`, so they won't clash with products already in your store.

## Import into WooCommerce

1. Go to **Products → Import**, choose the file and click **Continue**.
2. On the mapping screen every column maps automatically. Click **Run the importer**.

Good to know:

- **Units:** WooCommerce maps the weight and size columns by unit name. Use `products.csv` for a store set to kg and cm, or `products-imperial.csv` for lbs and inches. Otherwise those columns are skipped.
- **Import as an administrator.** The e-book's download link is outside your site, and WooCommerce only approves outside download folders automatically for administrators.
- **Leave "Update existing products" unticked the first time.** With it ticked, WooCommerce skips every product that isn't in the store yet.
- **Importing again** skips every row, because the SKUs already exist. That's when you tick **Update existing products** to overwrite them.
- Images are downloaded during the import, so the full file takes a minute or two.

## Import into Shopify

1. Go to **Products → Import**, add the file, and click **Upload and preview**, then **Import products**.

Good to know:

- The files use Shopify's classic column names (`Handle`, `Body (HTML)`, `Variant Price`, `Image Src`). Shopify's importer still accepts them alongside its newer names.
- **Product category** is left empty on purpose. Shopify's category list changes over time, and an outdated value can fail the row. Each product has a **Type** and **Tags** instead.
- Shopify has no grouped or external products, so those two are only in the WooCommerce files.
- Stock quantities go to your default location.

## Use it from code or an AI agent

- [`manifest.json`](manifest.json) lists every file with its product count and download URLs.
- Raw file URLs follow one pattern:
  `https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/shopify/products.csv`
- After v1.0.0, replace `main` with the release tag, e.g. `v1.0.0`. A tagged file never changes, and its image URLs are pinned to the same tag.

```sh
curl -sO https://raw.githubusercontent.com/iShowkot/ecommerce-sample-data/main/woocommerce/products-small.csv
```

## How it's built

Everything is generated from one file, [`catalog/products.json`](catalog/products.json), so the WooCommerce and Shopify versions never drift apart.

```sh
python3 scripts/build.py      # writes the CSVs and manifest.json from the catalog
python3 scripts/check.py      # checks them against the importers' rules (CI runs this)
python3 scripts/images.py     # generates the product photos with Gemini (needs GEMINI_API_KEY)
```

`build.py` and `check.py` need only Python 3.9+. `images.py` also needs Pillow. Images are hosted in this repo and served through the jsDelivr CDN.

The v1 photos were generated with Figma AI (Gemini 3.1 Flash Image) from the prompts in the catalog, then resized and compressed with `python3 scripts/images.py --from-raw`.

[docs/format-notes.md](docs/format-notes.md) explains the importer rules the files follow, like why there's no `ID` column and why parents come before variations.

## License

This is an open-source project with two licenses:

| What | License | In short |
|---|---|---|
| Data: the catalog, CSVs, images, sample files and docs | [CC0 1.0](LICENSE) | Public domain. Use it for anything, no credit needed. |
| Code: `scripts/` and `.github/` | [MIT](LICENSE-CODE) | Use, change and share it. Keep the license notice if you redistribute the code. |

All brands and products are fictional. The product photos are AI-generated and are CC0 like the rest of the data.

## Contributing

Contributions are welcome, and you don't need to write code to help:

- **Found a file that doesn't import cleanly?** [Open an issue](https://github.com/iShowkot/ecommerce-sample-data/issues/new/choose) with your platform, its version and the error message.
- **Imported a file without problems?** Tell us your platform version, so we can list it as tested.
- **Want a product type or edge case added?** Open a request.

To change the catalog or the scripts, see [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
