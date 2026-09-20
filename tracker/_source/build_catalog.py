#!/usr/bin/env python3
"""
Build ink_catalog.json — the seed reference catalog for add-ink autocomplete.

Sources (both share-alike; credit kept in the output file — revisit licensing
before ever redistributing this app commercially):
  - inks-mcp / Wilder Writes (Edd Wilder-James), GPL-3.0 — 502 inks w/ scanned RGB
    https://github.com/ewilderj/inks-mcp
  - inkdb-data (Pomax), share-and-share-alike — 356 inks w/ RGB
    https://github.com/Pomax/inkdb-data

Run:  python tracker/_source/build_catalog.py
"""
import colorsys
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "ink_catalog.json")

SRC = {
    "ink-colors.json": "https://raw.githubusercontent.com/ewilderj/inks-mcp/main/data/ink-colors.json",
    "search.json": "https://raw.githubusercontent.com/ewilderj/inks-mcp/main/data/search.json",
    "inkdata.js": "https://raw.githubusercontent.com/Pomax/inkdb-data/master/data/inkdata.js",
}

# Manufacturers whose own stores expose the standard public Shopify product feed
# (/products.json — published intentionally for integrations). Product names are
# facts; we take names only, no images or copy.
SHOPIFY_SOURCES = [
    {"brand": "Ferris Wheel Press", "domain": "ferriswheelpress.com",
     "types": ("writing ink", "calligraphy ink")},
    {"brand": "Van Dieman's", "domain": "vandiemansink.com.au",
     "types": ("bottled ink", "shimmer liquid")},
    # Krishna's store is ink-only but leaves product_type empty -> accept all ("*")
    {"brand": "Krishna Inks", "domain": "krishnainks.com", "types": ("*",)},
    # Taccia dropped: product_type values are meaningless (A/B/C) on a mixed store.
]

# Retailers that stock the major brands (Diamine, Pilot, Sailor, ...) which don't
# publish feeds themselves. brand=None -> use each product's `vendor` field.
# "exact" type matching avoids junk like "Ink Stamp" matching substring "ink".
RETAILER_SOURCES = [
    {"brand": None, "domain": "vanness1938.com",
     "types": ("ink",), "exact": True, "max_pages": 60},
    {"brand": None, "domain": "www.gouletpens.com",
     "types": ("bottled ink", "ink samples"), "exact": True, "max_pages": 60},
]


def fetch(name, url):
    cache = os.path.join(HERE, "cache_" + name)
    if not os.path.exists(cache):
        print("downloading", name)
        req = urllib.request.Request(url, headers={"User-Agent": "PenTracker catalog build"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r, open(cache, "wb") as f:
                    f.write(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    wait = 45 * (attempt + 1)
                    print(f"  rate-limited; waiting {wait}s…")
                    time.sleep(wait)
                    continue
                raise
        time.sleep(2)  # be polite between page downloads
    return open(cache, encoding="utf-8").read()


def color_family(r, g, b):
    """Map an RGB swatch to the tracker's 8 color families."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    hue = h * 360
    if l < 0.16 or (s < 0.12 and l < 0.30):
        return "Black"
    if s < 0.12:                      # desaturated but not dark = grey
        return "Grey"
    # browns: dark / desaturated warm hues
    if 10 <= hue < 65 and (l < 0.42 or s < 0.45):
        return "Brown"
    if hue < 14 or hue >= 340:
        return "Red"
    if hue < 40:
        return "Orange"
    if hue < 68:
        return "Yellow"
    if hue < 165:
        return "Green"
    if hue < 262:
        return "Blue"
    return "Purple"


def norm(s):
    return " ".join(str(s or "").split()).strip()


import re


def clean_title(brand, title):
    """Shopify product title -> ink name: strip brand prefix, volumes, boilerplate."""
    t = norm(title)
    if brand:
        t = re.sub(r"^" + re.escape(brand) + r"\s*[-–—|:]?\s*", "", t, flags=re.I)
    t = re.sub(r"\b\d+(\.\d+)?\s?[mM][lL]\b", "", t)           # 38ml / 20 ML / 4.5ml
    t = re.sub(r"\((\s*)\)", "", t)                            # emptied parens
    t = re.sub(r"\b(bottled ink|ink samples?|fountain pen ink|ink bottle|fp ink|bottled?)\b",
               "", t, flags=re.I)
    t = t.replace(" | ", " — ")
    t = re.sub(r"\s+inks?$", "", norm(t), flags=re.I)          # trailing bare "Ink"
    t = re.sub(r"\s*[-–—|:]\s*$", "", norm(t))
    t = re.sub(r"^\s*[-–—|:]\s*", "", t)
    return norm(t)


# Not fountain pen ink even when a store types it as "Ink"
JUNK_RE = re.compile(
    r"refill|cartridge|converter|\bempty\b|gel pen|ballpoint|rollerball|fineliner|"
    r"mixing kit|diluter|wetter|sample (set|pack)|tester|gift card|stamp|blotter|"
    r"syringe|pipette|\bnib\b|pen wrap|notebook", re.I)

# ── pens & papers from the same cached feeds ─────────────────────────────────
import glob

PEN_TYPES = {"fountain pens", "fountain pen"}
PAPER_TYPES = {"paper", "notebooks", "notebook", "notepads"}
PEN_JUNK = re.compile(
    r"converter|refill|\bnibs?\b|nib unit|case\b|sleeve|pouch|holder|stand|"
    r"pen roll|wrap|parts|sticker|\bink\b|gift set|display|tray", re.I)
PAPER_JUNK = re.compile(
    r"clip|accessor|blotter|cover\b|folio|holder|band\b|sticker|stamp|wax|"
    r"envelope|pen\b|pencil", re.I)
SIZE_RE = re.compile(r"\b(A[3-7]|B[5-7]|Passport|Pocket|Letter|Legal)\b", re.I)
GSM_RE = re.compile(r"\b(\d{2,3})\s?gsm\b", re.I)
RULING_RE = re.compile(r"\b(Lined|Ruled|Dot(?:ted)?|Grid|Graph|Blank|Plain)\b", re.I)
RULING_MAP = {"lined": "Lined", "ruled": "Lined", "dot": "Dot", "dotted": "Dot",
              "grid": "Grid", "graph": "Grid", "blank": "Blank", "plain": "Blank"}


def extract_pens_papers():
    """Mine fountain pens and FP-friendly paper out of the cached store feeds."""
    pens, papers = {}, {}
    for path in sorted(glob.glob(os.path.join(HERE, "cache_shopify_*.json"))):
        try:
            products = json.load(open(path, encoding="utf-8")).get("products", [])
        except (json.JSONDecodeError, OSError):
            continue
        for p in products:
            t = str(p.get("product_type") or "").strip().lower()
            vendor = norm(p.get("vendor", ""))
            title = norm(p.get("title", ""))
            if not vendor or not title:
                continue
            base = re.sub(r"^" + re.escape(vendor) + r"\s*[-–—|:]?\s*", "", title, flags=re.I)

            if t in PEN_TYPES or (t == "pen" and re.search(r"fountain", title, re.I)):
                if PEN_JUNK.search(title):
                    continue
                name = re.sub(r"\bfountain( pens?)?\b", "", base, flags=re.I)
                color = None
                if " - " in name:
                    name, color = name.rsplit(" - ", 1)
                name = norm(re.sub(r"\s*[-–—|:]\s*$", "", norm(name)))
                if len(name) < 2:
                    continue
                e = pens.setdefault((vendor.lower(), name.lower()),
                                    {"make": vendor, "model": name, "colors": []})
                color = norm(color or "")
                if color and color not in e["colors"] and len(e["colors"]) < 12:
                    e["colors"].append(color)

            elif t in PAPER_TYPES:
                if PAPER_JUNK.search(title):
                    continue
                name, variant = (base.rsplit(" - ", 1) if " - " in base else (base, ""))
                name = norm(name)
                if len(name) < 2:
                    continue
                k = (vendor.lower(), name.lower())
                if k in papers:
                    continue
                e = {"brand": vendor, "name": name}
                m = SIZE_RE.search(title)
                if m:
                    s = m.group(1)
                    e["size"] = s.upper() if len(s) == 2 else s.title()
                m = GSM_RE.search(title)
                if m:
                    e["gsm"] = int(m.group(1))
                m = RULING_RE.search(variant or title)
                if m:
                    e["ruling"] = RULING_MAP[m.group(1).lower()]
                papers[k] = e
    return (sorted(pens.values(), key=lambda x: (x["make"].lower(), x["model"].lower())),
            sorted(papers.values(), key=lambda x: (x["brand"].lower(), x["name"].lower())))


def shopify_inks(src):
    """Yield (brand, name) from a store's public product feed (paginated)."""
    out = []
    for page in range(1, src.get("max_pages", 8) + 1):
        url = f"https://{src['domain']}/products.json?limit=250&page={page}"
        cache = f"shopify_{src['domain'].replace('.', '_')}_p{page}.json"
        try:
            raw = fetch(cache, url)
            products = json.loads(raw).get("products", [])
        except Exception as e:  # noqa: BLE001 — a dead feed shouldn't kill the build
            print(f"  [warn] {src['domain']} page {page}: {e}")
            break
        if not products:
            break
        for p in products:
            ptype = str(p.get("product_type", "")).lower().strip()
            if "*" not in src["types"]:
                ok = (ptype in src["types"]) if src.get("exact") \
                    else any(t in ptype for t in src["types"])
                if not ok:
                    continue
            brand = src["brand"] or norm(p.get("vendor", ""))
            if not brand or JUNK_RE.search(str(p.get("title", ""))):
                continue
            name = clean_title(brand, p.get("title", ""))
            if name and len(name) > 1:
                out.append((brand, name))
    return out


def key(brand, name):
    return (norm(brand).lower(), norm(name).lower())


def main():
    entries, seen = [], set()

    # --- Wilder Writes (inks-mcp): search.json names + ink-colors.json RGB ---
    colors = {e["ink_id"]: e.get("rgb") for e in json.loads(fetch("ink-colors.json", SRC["ink-colors.json"]))}
    for e in json.loads(fetch("search.json", SRC["search.json"])):
        name = norm(e.get("name"))
        full = norm(e.get("fullname"))
        brand = norm(full[: -len(name)]) if name and full.lower().endswith(name.lower()) else norm(e.get("maker", "").replace("-", " ").title())
        if not brand or not name:
            continue
        k = key(brand, name)
        if k in seen:
            continue
        seen.add(k)
        rgb = colors.get(e.get("ink_id"))
        ent = {"brand": brand, "name": name, "src": "wilderwrites"}
        if rgb:
            ent["hex"] = "#%02x%02x%02x" % tuple(rgb)
            ent["color"] = color_family(*rgb)
        entries.append(ent)

    # --- inkdb-data ---
    raw = fetch("inkdata.js", SRC["inkdata.js"])
    data = json.loads(raw.replace("module.exports = ", "", 1).rstrip().rstrip(";"))
    for e in data:
        brand = norm(e.get("company"))
        name = norm((e.get("inkline") or "") + " " + (e.get("inkname") or ""))
        if not brand or not name:
            continue
        k = key(brand, name)
        if k in seen:
            continue
        seen.add(k)
        ent = {"brand": brand, "name": name, "src": "inkdb"}
        cols = e.get("colorInformation", {}).get("colors") or []
        if cols:
            c = cols[0]
            ent["hex"] = "#%02x%02x%02x" % (c["r"], c["g"], c["b"])
            ent["color"] = color_family(c["r"], c["g"], c["b"])
        entries.append(ent)

    # --- manufacturer + retailer Shopify feeds (names only; no color data) ---
    for src in SHOPIFY_SOURCES + RETAILER_SOURCES:
        added = 0
        for brand, name in shopify_inks(src):
            k = key(brand, name)
            if k in seen:
                continue
            seen.add(k)
            entries.append({"brand": brand, "name": name, "src": src["domain"]})
            added += 1
        print(f"  {src['brand'] or src['domain']}: +{added}")

    entries.sort(key=lambda x: (x["brand"].lower(), x["name"].lower()))
    cat_pens, cat_papers = extract_pens_papers()
    out = {
        "_credit": ("Seed data: Wilder Writes / inks-mcp (Edd Wilder-James, GPL-3.0, "
                    "github.com/ewilderj/inks-mcp); inkdb-data (Pomax, share-alike, "
                    "github.com/Pomax/inkdb-data); ink names from public Shopify product feeds "
                    "of manufacturers (Ferris Wheel Press, Van Dieman's, Krishna) and retailers "
                    "(Vanness Pens, Goulet Pens). Names are facts; no images or copy taken. "
                    "Personal use; review licenses before redistribution."),
        "inks": entries,
        "pens": cat_pens,
        "papers": cat_papers,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    from collections import Counter
    print(f"wrote {OUT}: {len(entries)} inks ({len({e['brand'] for e in entries})} brands), "
          f"{len(cat_pens)} pens ({len({p['make'] for p in cat_pens})} makes), "
          f"{len(cat_papers)} papers ({len({p['brand'] for p in cat_papers})} brands)")
    print("ink families:", dict(Counter(e.get("color", "?") for e in entries)))


if __name__ == "__main__":
    main()
