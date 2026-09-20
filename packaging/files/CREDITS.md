# Credits

Pen & Ink Tracker is built on top of two open, community-maintained ink
reference datasets. Their licenses determine the license of this whole
package (see `LICENSE`).

## Ink catalog sources

The bundled `ink_catalog.json` (the seed reference list used for add-form
autocomplete) is a derived compilation from:

- **Wilder Writes / ewilderj — `inks-mcp`** (GPL-3.0)
  Author: Edd Wilder-James.
  Fields used: scanned/measured RGB swatch values for ink colors.

- **Pomax — `inkdb-data`** (share-alike license)
  Fields used: ink brand/line/name metadata and complementary color data.

- **Public Shopify product feeds** of ink and pen retailers and makers,
  including Ferris Wheel Press, Van Diemen's Ink, Krishna Inks, Vanness Pen
  Shop, Goulet Pens, and Taccia. Only product names, brand names, and sizes
  were taken from these public storefront feeds — this is factual product
  data (names of things for sale), not creative or copyrightable expression.

No proprietary or paid data source is included.

## Why this package is GPL-3.0

Because `ink_catalog.json` incorporates GPL-3.0-licensed data from
`inks-mcp`, and because that project's license and the share-alike terms of
`inkdb-data` require derivative works to be distributed under compatible
copyleft terms, the combined work — this application, including its code
and bundled catalog — is licensed under the **GNU General Public License
v3.0**. See `LICENSE` for the full text.

## Other bundled components

- **qrcode.min.js** — offline QR code generator, MIT License, © Kazuhiko
  Arase. Used to render the in-app "scan to open on your phone" codes with
  no network dependency.

## Rebuilding the catalog

The catalog is rebuilt from source snapshots by a script that is **not**
included in this distribution (it lives in the developer's working copy at
`_source/build_catalog.py`) so that only the compiled `ink_catalog.json`
result — not the raw scraped/cached retailer data — is redistributed.
