# Pen & Ink Tracker

A local-first tracker for your fountain **pen, ink, and paper** collection. It
runs entirely on your own computer: no cloud service, no account, and no
company on the other end. Your collection is stored as plain files next to the
app and is never uploaded anywhere.

- **Three collections**: pens, inks, and papers, with search, filters, grid/list
  views, and photo galleries.
- **Swab wall**: a hue-sorted color wall built from your ink swab photos.
- **Phone photos**: scan a QR code from the desktop app and take photos straight
  into any record. No phone app to install.
- **Currently inked**: track which pen has which ink, with a nudge to flush pens
  that have been inked for 30+ days.
- **Import and export**: paste rows from Excel or Google Sheets, export CSVs for
  valuation or insurance, and generate sale-listing text.
- **Optional AI auto-fill**: uses your own free Google Gemini key to research a
  pen, ink, or paper and propose fields and product photos. Everything else works
  without a key.

## Download

Get the latest build from the **[Releases page](../../releases/latest)**:

| File | Platform | Notes |
|------|----------|-------|
| `PenInkTracker-Setup-1.0.0.exe` | Windows | Standalone, no Python needed. Not code-signed, so Windows SmartScreen may warn on first run: choose **More info → Run anyway**. |
| `PenInkTracker-1.0.0.zip` | Windows, Mac, Linux | Needs [Python 3](https://www.python.org/downloads/) (free). Unzip and double-click the launcher for your OS. |

Install and troubleshooting details are in [`dist/README.md`](dist/README.md)
and in the `README.md` inside the zip.

## Run from source

```
python tracker/server.py
```

Then open <http://localhost:3838>. The server also prints a LAN address, which is
what the in-app QR codes point to so your phone can reach it. Set `PI_PORT` to
use a different port.

The app runs on the Python standard library alone. `pip install -r
tracker/requirements.txt` is only needed if you switch the AI provider to
Anthropic.

## AI key (optional)

Copy `tracker/config.example.json` to `tracker/config.json` and add a key. The
default provider is Google Gemini's free tier
(<https://aistudio.google.com/apikey>). `config.json` is git-ignored and is never
served to the browser.

## Building the release files

```
python packaging/build.py        # stages a clean copy and builds the zip
python packaging/build_exe.py    # Windows .exe (needs: pip install pyinstaller)
```

The build scripts stage the app with empty starting data and hard-fail if any
personal data or API key would end up in the package. Output goes to `dist/`,
which is git-ignored; publish the results as GitHub Release assets.

## Privacy, credits, and license

- [`packaging/files/PRIVACY.md`](packaging/files/PRIVACY.md): nothing leaves your
  computer unless you turn on the optional AI feature with your own key.
- [`packaging/files/CREDITS.md`](packaging/files/CREDITS.md): where the bundled
  ink catalog data comes from.
- [`packaging/files/DISCLAIMER.md`](packaging/files/DISCLAIMER.md): no warranty;
  back up your own data.

Pen & Ink Tracker is free software licensed under the **GNU General Public
License v3.0**. See [`LICENSE`](LICENSE).
