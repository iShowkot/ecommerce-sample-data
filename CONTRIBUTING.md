# Contributing

Thanks for helping. This is an open-source project, and every report of a file that does or doesn't import cleanly makes it more useful to the next person.

## Ways to help

- **Report an import problem.** [Open an issue](https://github.com/iShowkot/ecommerce-sample-data/issues/new/choose) with your platform and version, the file you used, and the importer's error message.
- **Report a clean import.** Tell us which platform version you tested and it worked. These reports go into the "tested with" list in the README.
- **Suggest products or edge cases** that would help you test, for example a product type, an option combination or an awkward value.
- **Improve the catalog, scripts or docs** with a pull request.

## Ground rules for the catalog

- **Brands and products must be fictional.** No real brand names, trademarks, logos or product names.
- **Images** must come from `scripts/images.py` or be your own photos that you release under CC0. Don't add stock photos or pictures found online.
- **SKUs** start with `ESD-` and use only capital letters, numbers and hyphens.
- **Prices** are written with two decimals, like `24.00`, and have no currency symbol.

## Development

You need Python 3.9 or newer. `build.py` and `check.py` use only the standard library.

```sh
python3 scripts/build.py   # regenerate the CSVs and manifest.json from the catalog
python3 scripts/check.py   # validate everything, as CI does
```

Never edit the CSVs by hand. Change `catalog/products.json` and rebuild, then commit the catalog and the generated files together. CI fails if they're out of date.

To generate photos you also need Pillow (`pip install pillow`) and a Gemini API key in `GEMINI_API_KEY`:

```sh
python3 scripts/images.py --only your-product-handle
```

## Adding a product

Add an entry to `catalog/products.json`. The existing products are good examples.

| Field | Required | Notes |
|---|---|---|
| `handle` | yes | Lowercase words joined by hyphens. Used as the Shopify handle and the image folder name. |
| `sku` | yes | Parent SKU. Variation SKUs are made from it plus the option values. |
| `name`, `vendor`, `category`, `tags` | yes | `category` uses `>` for nesting, like `Clothing > T-shirts`. |
| `type` | yes | `simple`, `variable`, `grouped` or `external`. Grouped and external products are WooCommerce-only. |
| `short_description`, `description` | yes | The description can use simple HTML. |
| `price` | yes, except grouped | Plus optional `sale_price`, `sale_from` and `sale_to`. |
| `options` | variable only | Up to 3, each with a `name` and `values`. |
| `image_option` | no | The option whose values each get their own photo, usually `Color`. |
| `variant_rules` | no | Change `price`, `sale_price`, `stock` or `weight_kg` for variations that match `when`. |
| `photos` | yes | The first has a `prompt`. Color variants use `edit_of` and `change` so they show the same product. Each photo `id` must be the option value written in lowercase with hyphens, like `heather-grey`. |
| `notes` | no | What the product tests. These are listed in `manifest.json`. |

Other optional fields: `stock`, `backorders`, `featured`, `status`, `visibility`, `virtual`, `downloads`, `tax_status`, `sold_individually`, `weight_kg`, `dimensions_cm`, `shipping_class`, `attributes`, `defaults`, `upsells`, `cross_sells`, `children`, `external_url`, `button_text` and `small`. `scripts/check.py` explains anything it doesn't accept.

## Pull requests

- Keep each pull request to one change.
- Make sure `python3 scripts/check.py` passes.
- If you tested an import, say which platform and version.

## License of contributions

By contributing, you agree that your contribution is released under the project's licenses: [CC0 1.0](LICENSE) for data (the catalog, CSVs, images and docs) and [MIT](LICENSE-CODE) for code (`scripts/` and `.github/`).

## Code of conduct

Everyone taking part is expected to follow the [code of conduct](CODE_OF_CONDUCT.md).
