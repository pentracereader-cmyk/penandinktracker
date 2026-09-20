# Pen & Ink Tracker — Downloads

There are two ways to install Pen & Ink Tracker, depending on your computer.
Download either file from the
[Releases page](https://github.com/pentracereader-cmyk/penandinktracker/releases/latest)
(under **Assets**).

| File | Platform | What it is |
|------|----------|------------|
| `PenInkTracker-Setup-1.0.0.exe` | **Windows** | A standalone installer/app. No Python required. |
| `PenInkTracker-1.0.0.zip` | **Mac, Linux, or Windows** | The app's source, plus a double-click launcher for each OS. Requires Python 3 (free). |

There is currently no standalone `.app`/`.dmg` installer for Mac — use the
zip instead. It only takes a couple of extra minutes and works
identically once installed.

## Installing on a Mac

1. Download **`PenInkTracker-1.0.0.zip`** and double-click it to unzip
   (or unzip it anywhere you like, e.g. your Desktop).
2. If you don't already have Python 3, install it (free) from
   https://www.python.org/downloads/macos/ — run the installer, then
   you're set. (Macs usually already have it; if you're not sure, just
   try step 3 first.)
3. Open the unzipped `PenInkTracker` folder and double-click
   **`start-mac.command`**.
   - macOS will likely warn that it's from an unidentified developer the
     first time. Right-click (or Control-click) `start-mac.command` and
     choose **Open**, then confirm **Open** in the dialog. You only need
     to do this once.
4. A Terminal window opens and asks a couple of quick first-run
   questions (an optional AI key — you can skip it), then your browser
   opens the app automatically at `http://localhost:3838`.
5. Next time, just double-click `start-mac.command` again — the
   first-run questions only appear once. Keep the Terminal window open
   while you use the app; closing it stops the server.

Full details — using it from your phone, where your data is stored,
backups, and troubleshooting — are in the `README.md` **inside the zip**,
alongside the app itself once you unzip it.

## Installing on Windows

Double-click **`PenInkTracker-Setup-1.0.0.exe`** and follow the prompts.
No Python install needed. (Windows SmartScreen may warn about an
unrecognized publisher on first run — this build isn't code-signed yet;
choose **More info → Run anyway** if you trust the source.)

Alternatively, `PenInkTracker-1.0.0.zip` also works on
Windows via `Start on Windows.bat`, if you'd rather not run a standalone
`.exe`.

## Installing on Linux

Use `PenInkTracker-1.0.0.zip`. Unzip it, open a terminal in that folder,
and run `./start-linux.sh` (Python 3 required).
