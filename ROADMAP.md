# Roadmap

## v1.0.0: one polished catalog

- [x] Catalog: 31 fictional products, 117 variations, 59 planned photos
- [x] Build script that writes the WooCommerce and Shopify CSVs from the catalog
- [x] Checks that mirror the importers' rules, run in CI on every push
- [x] Sample PDF for the downloadable product
- [ ] Generate the product photos with Gemini (`scripts/images.py`) and review them
- [ ] Release candidate: build with `--ref v1.0.0-rc.1` and tag it
- [ ] Import test on current WooCommerce and on a Shopify development store, then fix anything that fails
- [ ] Export one imported product from Shopify, to confirm the current column names
- [ ] Release v1.0.0: tag, GitHub release, and "tested with" versions in the README
- [ ] Share it: r/woocommerce, r/shopifydev, WooCommerce Community Slack, Shopify Community forums, and old "where can I find a sample CSV" threads

## v1.1: edge cases

- Files that are valid but awkward: UTF-8 and emoji in names, right-to-left text, `&` and quotes in attribute values, HTML-heavy descriptions, commas inside values
- Files that are broken on purpose, each documenting the error it should cause: duplicate SKUs, a variation before its parent, a dead image URL, a missing price

## v1.2: large files

- 1k, 10k and 100k-row versions that reuse the same images, for testing import speed and timeouts

## v1.3: beyond products

- Customer and order CSVs
- Shopify files with the newer column names, if the classic ones stop being accepted
