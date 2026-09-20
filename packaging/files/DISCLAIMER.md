# Disclaimer

Pen & Ink Tracker is licensed under the **GNU General Public License
v3.0** (see `LICENSE`), which already includes a warranty and liability
disclaimer in Sections 15–17. This page restates that in plain language
and adds a few points specific to this app. It doesn't replace the
license — `LICENSE` is the legal text that governs your use of the
software.

## No warranty

This software is provided **"as is,"** without warranty of any kind,
express or implied — including, without limitation, warranties of
merchantability, fitness for a particular purpose, or non-infringement.
It's a free hobby project, not a commercial product with a support
contract behind it.

## No liability

To the fullest extent permitted by law, the author is not liable for any
damages arising from the use of this software — including but not
limited to data loss, lost time, or any indirect, incidental, or
consequential damages — even if advised of the possibility of such
damages.

## Back up your own data

Your collection data lives in plain files next to the app (see
`README.md`). Nothing is backed up automatically or stored anywhere else.
**You are responsible for backing up your own data.** Corrupted files,
accidental deletion, or a failed disk are not the app's responsibility to
recover from.

## Third-party AI features

The optional "Auto-fill with AI" feature uses your own API key with
Google Gemini (or, optionally, Anthropic). Any usage, cost, rate limits,
accuracy, or data handling for those API calls are governed entirely by
**that provider's own terms** — not by this project. AI-generated
suggestions (names, specs, valuations, images) can be wrong; verify
anything that matters before relying on it, especially before buying,
selling, or insuring an item based on it.

## Third-party names and data

Pen and ink brand names, model names, and manufacturer names that appear
in the bundled catalog or that you enter yourself are the property of
their respective owners. This project is **not affiliated with, endorsed
by, or sponsored by** any pen or ink manufacturer or retailer named in
the app. See `CREDITS.md` for the catalog's data sources.

## Antivirus warnings on the Windows installer

The standalone `.exe` is built with PyInstaller, which packages a Python
interpreter into a single self-extracting file — a pattern also used by
some malware, so antivirus tools occasionally flag freshly-built
PyInstaller executables as suspicious even when nothing is wrong. This is
a known, widely-documented false-positive pattern for this tool, not an
indication that the file is unsafe. If your AV flags it, that's a
reflection of the packaging tool's reputation, not a claim being made
about the app's safety. The plain `.zip` distribution (source + Python)
avoids this entirely, if you'd rather not deal with it.

## Use at your own risk

By downloading and running this software, you accept the terms above and
in `LICENSE`. If you don't agree with them, don't use the software.
