# Pen & Ink Tracker

A local-first tracker for fountain **pens, inks, and papers**. Runs entirely on
your machine — no cloud, no accounts. The full app works on your phone too
(scan the 📱 QR in the header), including taking photos straight into any record.

Highlights:
- **Three collections** — pens, inks, papers — each with filters, grid/list views,
  search, and photo galleries.
- **Swab wall** — the Inks tab has a 🎨 Wall view: a hue-sorted color wall built
  from your swab photos.
- **Photo types** — every photo is tagged 📷 Photo / 🎨 Swab / ✍ Writing sample
  (tap the label to retag). Cards and the wall pick the right kind automatically.
- **Currently inked** — track what's inked with what; the dashboard shows a
  live list and nudges you to flush pens inked 30+ days.
- **Import wizard (⇄)** — paste rows from Excel/Google Sheets (or a CSV),
  columns auto-match (with optional ✨ AI matching), review, import.
- **Exports (⇄)** — CSV per collection (valuation/insurance record) and
  ready-to-post **sale listing text** for pens marked Listed / Will Sell.
- **AI auto-fill & photo finder** — Gemini free tier researches any pen, ink,
  or paper and proposes fields + real product photos.
- **Installable (PWA)** — on the phone, "Add to Home Screen" gives a real app
  icon that opens full-screen.

## Running

Double-click **`Launch Pen Tracker.bat`** (in the parent folder), or:

```
python tracker/server.py
```

Then open **http://localhost:3838**. The server also prints a `http://<your-LAN-IP>:3838`
address — that's what the in-app QR codes point to so your phone can reach it.

> Runs on port **3838**, so it does not collide with the old Conway Stewart app (3737).
> Both can run at once.

## What's where

| File | Purpose | Who writes it |
|------|---------|---------------|
| `pens.json` | Your pen collection (67 imported from the Google Sheet) | the browser |
| `inks.json` | Your ink collection | the browser |
| `papers.json` | Your paper collection | the browser |
| `photos.json` | Which photos (and photo types) belong to which record | **the server only** |
| `photos/` | The actual image files | the server |
| `backups/` | Rotating snapshots (newest 20 per file) taken before every save | the server |
| `ink_catalog.json` | Seed reference catalog for add-form autocomplete: ~4,900 inks (110 brands), ~380 fountain pens (45 makes, with colorways), ~835 papers (78 brands, with size/gsm/ruling). Sources: Wilder Writes/inks-mcp (GPL-3.0), inkdb-data (share-alike), and public Shopify product feeds of makers (Ferris Wheel Press, Van Dieman's, Krishna) & retailers (Vanness, Goulet) — names only. Personal use; review licenses before redistribution. Rebuild: `python _source/build_catalog.py` | — |
| `catalog_learned.json` | Self-growing catalog — every successful AI fill (ink, pen, or paper) is cached here and feeds autocomplete | the server |
| `config.json` | Your AI API key (optional; never served to the browser) | you |
| `manifest.json`, `icon-*.png` | PWA install assets | — |
| `qrcode.min.js` | Offline QR generator (MIT, Kazuhiko Arase) | — |
| `_source/` | One-time migration script, icon generator, sheet snapshot | — |

Photos live in their own file owned solely by the server, so phone uploads can
never overwrite edits you're making on the desktop.

## Photos from your iPhone (QR hand-off)

1. Open any pen or ink → **Add via phone**.
2. Point your iPhone camera at the QR code (no app needed).
3. The phone opens a one-button camera page; every shot uploads straight here.
4. The desktop window shows the photo count climb live.

Requirements: phone and desktop on the **same Wi-Fi**. LAN uploads carry a
per-session token so other devices on the network can't push photos.

You can also use **Upload here** to add an image directly from the desktop.

## AI auto-fill

Default provider is **Google Gemini's free tier** (no `pip install` needed —
it's called over plain HTTPS from the standard library).

1. Get a free Gemini API key at https://aistudio.google.com/apikey (Google login).
2. Copy `config.example.json` to `config.json` and paste it into `gemini_api_key`
   (or set the `GEMINI_API_KEY` environment variable).
3. In **+ Add**, type the make + model (or ink brand + name) and click
   **✨ Auto-fill with AI**.
4. Gemini researches it with Google Search grounding, proposes field values and a
   few candidate photos. **Review and edit everything** before saving — kept
   photos are downloaded into your local library.

Config keys: `provider` (`gemini` default, or `anthropic`), `gemini_model`
(default `gemini-2.5-flash`), `enable_web_search` (default true).

**Switching to Claude:** set `provider` to `anthropic`, add `anthropic_api_key`,
and `pip install -r tracker/requirements.txt`. Note: a Claude **Pro/Max
subscription does not include API access** — the API is billed separately.

## Re-importing the sheet

`_source/migrate.py` parses `_source/pens.md` into `pens.json`. It's a one-time
import; running it again **overwrites** `pens.json`, so only use it for a fresh
re-import.
