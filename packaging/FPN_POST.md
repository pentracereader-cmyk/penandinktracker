# Pen & Ink Tracker — a free, local, no-cloud collection tracker

Hi all — sharing a small app I built for tracking a fountain pen / ink /
paper collection. Posting it here in case it's useful to anyone else.

## What it is

A single-user app for cataloging your pens, inks, and paper: what you
own, condition, cost, where it's stored, ink currently loaded, swab
photos, "will sell" flags, and so on. It runs **entirely on your own
computer** — there's no cloud service, no account to create, and no
company (including me) on the other end collecting anything. Your
collection data lives in plain files next to the app, on your own
machine, full stop.

## Features

- Pens, inks, and paper collections with the fields you'd actually want
  to track (condition, cost, nib, ink loaded, storage location, etc.)
- Photos per item, plus an ink "swab wall"
- **Add via phone**: scan a QR code shown on the desktop app and your
  phone becomes a camera for that item — no app install, works over your
  own Wi-Fi
- Import/export of your collection data
- Optional AI auto-fill: type a pen or ink name and have it propose the
  spec fields and a product photo for you (uses your own free Google
  Gemini API key — entirely optional, everything else works without it)

## Download

Download here: https://drive.google.com/drive/folders/1hepe5sq8pxy20eskz5UZgi61eP90Eohr?usp=sharing

Two options in that folder:

- PenInkTracker-Setup-1.0.0.exe — Windows, standalone, no Python required
- PenInkTracker-1.0.0.zip — Windows / Mac / Linux, requires a free Python 3 install; also the source code

## Installing

Windows (easiest): download and run PenInkTracker-Setup-1.0.0.exe.
Windows/your antivirus may warn about it being from an unrecognized
publisher — that's a known false-positive pattern for this kind of
self-contained executable, not a sign anything's wrong (more detail in
the Disclaimer, linked below). Click through, and the app opens in your
browser automatically.

Windows / Mac / Linux (the zip):
1. Install Python 3 if you don't have it already (free, from
   https://www.python.org/downloads/ — on Windows, tick "Add python.exe
   to PATH" during install).
2. Download and unzip PenInkTracker-1.0.0.zip anywhere.
3. Double-click the launcher for your OS: Start on Windows.bat,
   start-mac.command, or start-linux.sh.
4. The first run asks a couple of quick questions (including the
   optional AI key — press Enter to skip it), then opens the app in your
   browser at http://localhost:3838.
5. Next time, just run the same launcher again.

## Using it from your phone

Open any pen or ink in the app and tap Add via phone — it shows a QR
code. Scan it with your phone's camera (same Wi-Fi network, no app
needed) and a simple one-button camera page opens; photos you take there
land straight into your collection on the desktop.

## Where your data lives, and backups

Everything is stored as plain files (pens.json, inks.json, papers.json,
a photos folder, etc.) right next to the app. Nothing is uploaded or
synced anywhere automatically. To back up, just copy those files
somewhere safe — a USB drive, another folder, your own cloud storage. To
restore, copy them back before starting the app.

## License, privacy, and disclaimer

This is free software, licensed under the GNU GPL v3.0. Full details:

License (GPL-3.0, GitHub repo): https://github.com/pentracereader-cmyk/pentracereader

Privacy policy: https://github.com/pentracereader-cmyk/pentracereader/wiki/Privacy-Policy-%E2%80%94-Pen-&-Ink-Tracker
Short version: nothing you enter is collected by me; the only thing that
ever leaves your computer is the optional AI lookup, which goes directly
from your machine to Google/Anthropic using your own key.

Disclaimer: https://github.com/pentracereader-cmyk/pentracereader/wiki/Disclaimer-%E2%80%90-Pen-n-Ink-Tracker
The standard "no warranty, back up your own data, verify AI suggestions
before relying on them" terms.

## Feedback / issues

Happy to hear bug reports or feature requests — reply here, or email
pentracereader@gmail.com.
