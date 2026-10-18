# Format notes

The rules these files follow, and why. The WooCommerce rules come from reading the importer's source code in the [WooCommerce repository](https://github.com/woocommerce/woocommerce/tree/trunk/plugins/woocommerce/includes/import). They're useful if you're writing your own CSVs too.

## WooCommerce

**No `ID` column.** IDs only mean something in the store a file was exported from. On a normal import WooCommerce works around them with placeholder products. With **Update existing products** ticked, though, WooCommerce 11.1 and later refuse a new variation whose row has an ID ("A new variation cannot be created for a row that specifies an ID"), and they require every new variation to have a SKU or GTIN. Matching on SKUs alone works in both modes. The sample file bundled with WooCommerce still uses IDs.

**Leave "Update existing products" unticked on the first import.** With it ticked, rows whose SKU isn't in the store yet are skipped ("No matching product exists to update"). Tick it only to re-import over products you've already imported.

**Parents come before their variations.** A variation's `Parent` must be the SKU of a `variable` product that's already been imported, either earlier in the same file or in an earlier import.

**Variation values must match the parent.** Each variation's attribute value has to be one of the values listed on its parent row, otherwise the row is refused. The `Attribute N global` flag must be the same on both rows: `1` means a shared attribute such as `pa_color`. A variation row sets one value for each variation attribute (`Color = Navy`), and the parent lists all of them (`Black, White, Navy`).

**Weight and size headers include the unit**, like `Weight (kg)` and `Length (cm)`. The importer only maps them automatically when the unit matches the store's settings. That's why there's a separate imperial file with `Weight (lbs)` and `Length (in)`.

**One failed image fails the whole row.** Images are downloaded during the import, and if a URL is dead the product is skipped. That's why old sample files with broken image links import badly. Here the images live in this repo, and each release's CSVs point at that release's tag, so the URLs keep working.

**Related products must be in the same file.** `Upsells`, `Cross-sells` and `Grouped products` take SKUs. If a SKU isn't defined anywhere, the importer creates an empty "Import placeholder" product for it. The small files drop links to products they don't include.

**List cells are split on commas.** `Images`, `Tags`, `Categories` and attribute values are comma-separated. Write `\,` for a literal comma. Categories use `>` for nesting, like `Clothing > T-shirts`.

**Status values:** `Published` is `1` (published), `0` (private), `-1` (draft) or `2` (pending review). `Visibility in catalog` is `visible`, `catalog`, `search` or `hidden`.

**Downloadable files from another domain** are allowed only after that folder is approved. WooCommerce approves it automatically when an administrator runs the import.

## Shopify

**One product, several rows.** Rows with the same `Handle` form one product. Product fields such as Title, Body, Vendor, Tags, Published and Status go on the first row only. The other rows carry variant data and images.

**Options:** up to three per product (`Option1`–`Option3`). The option names go on the first row, and the values on every variant row. A product without options uses `Option1 Name = Title` and `Option1 Value = Default Title`.

**Sale prices:** Shopify has no sale-price field. A variant on sale has `Variant Price` set to the sale price and `Variant Compare At Price` set to the regular price.

**Images:** `Image Src` and `Image Position` list the product's images from the first row down, and continue on image-only rows if there are more images than variants. This matches the layout of a Shopify export. A `Variant Image` must be one of the product's own images.

**Weight:** `Variant Grams` is always in grams. `Variant Weight Unit` only sets the unit shown in the admin.

**Published vs Status:** `Status` is `active`, `draft` or `archived`. `Published` controls whether an active product appears in the online store. The draft art print has `Status = draft`, and the hidden spare lid is active but unpublished.

**Column names:** the files use Shopify's classic names (`Handle`, `Body (HTML)`, `Variant Price`, `Image Src`, `Variant Image`). Shopify's current template uses newer names (`URL handle`, `Description`, `Price`, `Product image URL`), and its importer accepts both.
