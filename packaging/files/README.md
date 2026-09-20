# Pen & Ink Tracker

A local tracker for your fountain pen, ink, and paper collection. It runs
entirely on your own computer — there is no cloud service, no account, and
no company on the other end. Your collection data is stored in plain files
next to the app and is never uploaded anywhere.

## Install and run

You need Python 3 installed (free, from python.org). Everything else is
included in this download — no other software is required.

### Windows

1. Unzip this folder anywhere (e.g. your Desktop).
2. Double-click **`Start on Windows.bat`**.
3. The first time, a terminal window will ask you a couple of quick
   questions, then your browser will open the app automatically.

### Mac

1. Unzip this folder anywhere.
2. Double-click **`start-mac.command`**. (If macOS warns that it's from an
   unidentified developer, right-click it and choose **Open** once to
   approve it.)
3. Answer the first-run questions in the Terminal window that opens, then
   your browser will open the app automatically.

### Linux

1. Unzip this folder anywhere.
2. Open a terminal in that folder and run `./start-linux.sh` (or
   double-click it if your file manager runs `.sh` files directly).
3. Answer the first-run questions, then open the URL it prints
   (`http://localhost:3838`) in your browser.

Next time, just run the same launcher again — the first-run questions only
appear once.

## The optional AI key — what you get and what you lose

Pens, inks, papers, photos, the swab wall, imports, exports, and the phone
hand-off all work fully **without** any API key.

The one optional extra is **AI auto-fill**: typing a pen or ink name and
having the app research and propose the fields and product photos for you.
That feature uses **Google Gemini's free tier**. If you want it:

1. Get a free key (takes about a minute) at
   https://aistudio.google.com/apikey — sign in with any Google account.
2. Paste it in when the first-run setup asks, or add it later by copying
   `config.example.json` to `config.json` and pasting the key in.

If you skip this, everything else in the app works exactly the same — you
just fill in pen/ink/paper details by hand instead of having AI propose
them.

## Using it on your phone

The desktop app and your phone just need to be on the **same Wi-Fi
network** — no app to install on the phone.

1. On the desktop, open any pen or ink and tap **Add via phone**.
2. Scan the QR code with your phone's camera (no app needed).
3. A simple one-button camera page opens on the phone; every photo you
   take uploads straight into your collection.
4. The desktop screen updates live as photos come in.

## Where your data lives, and backing it up

Everything is stored as plain files in the same folder as the app:

| File | What it holds |
|------|----------------|
| `pens.json` | Your pen collection |
| `inks.json` | Your ink collection |
| `papers.json` | Your paper collection |
| `photos.json` | Which photos belong to which record |
| `photos/` | The actual photo files |
| `catalog_learned.json` | Details the AI has already looked up, cached for next time |
| `config.json` | Your AI key, if you added one (never shared with the app's UI or anyone else) |

To back up your collection, copy those files (and the `photos/` folder) to
a USB drive, external disk, or your own cloud storage folder. To restore,
copy them back into the app folder before starting the app.

## Troubleshooting

- **"Python was not found"** — install it from
  https://www.python.org/downloads/ (any recent Python 3 version), then
  run the launcher again. On Windows, make sure to tick "Add python.exe to
  PATH" during install.
- **"Address already in use" / port already in use** — you already have a
  copy of the app running (check for an existing browser tab or terminal
  window). Close it, or set the environment variable `PI_PORT` to a
  different number before starting the app again.
- **My phone can't connect** — double-check the phone and computer are on
  the *same* Wi-Fi network (not one on Wi-Fi and one on mobile data), and
  that your computer's firewall isn't blocking incoming connections on
  port 3838.
- **I closed the terminal window and the app stopped** — that's expected;
  the terminal window running the launcher needs to stay open while you
  use the app. Just run the launcher again to restart it.

## License, privacy, and disclaimer

Pen & Ink Tracker is free software licensed under the **GNU GPL v3.0** —
see `LICENSE` for the full terms and `CREDITS.md` for where the bundled
ink catalog data comes from. See `PRIVACY.md` for what happens to your
data (short version: nothing leaves your computer unless you turn on the
optional AI feature with your own key), and `DISCLAIMER.md` for the
no-warranty / use-at-your-own-risk terms this software is provided under.
