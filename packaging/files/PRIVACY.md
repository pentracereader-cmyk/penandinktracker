# Privacy Policy — Pen & Ink Tracker

_Last updated: 2026-09-18_

Pen & Ink Tracker is a local application. This policy explains, plainly,
what happens to your data.

## The short version

**Nothing you enter into this app is collected by its developer.** There
is no account, no analytics, no crash reporting, and no server this app
talks to that the developer operates or has access to. Your pen, ink, and
paper collection — including any photos — is stored as plain files on
your own computer, next to the app, and stays there unless you copy it
somewhere yourself.

## What the app stores, and where

Everything lives in plain JSON files and a `photos/` folder in the same
directory as the app: `pens.json`, `inks.json`, `papers.json`,
`photos.json`, `catalog_learned.json`, and any photos you add. Nothing is
uploaded, synced, or backed up automatically. If you want a backup, copy
those files yourself (see the README).

## The optional AI feature

The app has one optional feature, "Auto-fill with AI," that looks up a
pen or ink by name. If you choose to use it, you supply your **own** API
key for Google Gemini (or, optionally, Anthropic's Claude). When you use
this feature:

- The text you type (a pen/ink name) and, if applicable, an image are
  sent **directly from your computer** to Google's or Anthropic's API —
  never through any server operated by this app's developer.
- That exchange is governed by **Google's** or **Anthropic's** own privacy
  policy and terms, not this one, since your own account and key are
  being used.
- If you never add an API key, this feature is simply unavailable, and no
  data of any kind leaves your computer through the app.

## The phone hand-off feature

"Add via phone" opens a small web page on your phone, on your own local
Wi-Fi network, so you can take a photo and have it land directly in the
app running on your computer. This traffic stays on your local network —
it does not go through the internet or through the developer.

## Data from other people (e.g. importing a marketplace listing)

If you use an import feature that reads a public listing (for example, a
pen or ink someone is selling), any details of that listing — including a
seller's username, if shown on the listing — are copied into **your own**
local `pens.json`/`inks.json` file, the same as any other field you'd type
in by hand. That data is not sent anywhere by this app beyond your own
files, and again may hit the AI provider above if you use auto-fill on it.

## Children's privacy

This app is not directed at children and does not knowingly collect any
information from anyone, since it does not collect information at all.

## Changes to this policy

If this policy changes, the updated version will be posted in this same
repository with a new "last updated" date.

## Contact

Questions about this policy can be raised as an issue in this GitHub
repository, or by email at pentracereader@gmail.com.
