#!/usr/bin/env python3
"""
One-off: ingest the 15 swatched inks from the uploaded swatch-book photos.
Crops each swatch card into its own swab image and writes inks.json + photos.json.
"""
import os
import json
import random
import string
from datetime import datetime, timezone
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PHOTOS = os.path.join(ROOT, "photos")
UP = os.environ.get("SWAB_UPLOAD_DIR", os.path.join(ROOT, "uploads"))  # folder of source swab images
os.makedirs(PHOTOS, exist_ok=True)

NOW = datetime.now(timezone.utc).isoformat()


def gid():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=13))


# (photo file, column 0/1/2, record)
def B(**k):
    d = dict(shimmer=False, type="Bottle", status="Keep")
    d.update(k)
    return d
INKS = [
 ("1383f3ca-IMG_4023.jpeg", 0, B(brand="J. Herbin", name="Perle Noire",
    color_match="Black", sheen="None", shading="None",
    notes="Classic French black; well-behaved and safe for vintage pens.")),
 ("1383f3ca-IMG_4023.jpeg", 1, B(brand="Pelikan", name="4001 Brilliant Black",
    color_match="Black", sheen="None", shading="None",
    notes="Workhorse black, on the dry side, very well-behaved.")),
 ("1383f3ca-IMG_4023.jpeg", 2, B(brand="Pilot Iroshizuku", name="take-sumi (Bamboo Charcoal)",
    color_match="Black", sheen="None", shading="Moderate",
    notes="Warm charcoal black; smooth, well-lubricated premium ink.")),

 ("457b94ae-IMG_4024.jpeg", 0, B(brand="Barock (Octopus Fluids)", name="Jade",
    color_match="Green", sheen="None", shading="Moderate",
    notes="Turquoise/jade from the German Barock 1910 line (reissued GDR ink); "
          "great flow, nice shading, light sheen.")),
 ("457b94ae-IMG_4024.jpeg", 1, B(brand="Montblanc", name="Homage to the Great Gatsby (Green)",
    color_match="Green", sheen="None", shading="Moderate",
    notes="Deep green inspired by the green light at the end of Daisy's dock; special edition.")),
 ("457b94ae-IMG_4024.jpeg", 2, B(brand="Montblanc", name="Irish Green",
    color_match="Green", sheen="None", shading="Moderate",
    notes="Bright, vivid grass green; well-lubricated.")),

 ("21267973-IMG_4027.jpeg", 0, B(brand="Pelikan", name="4001 Royal Blue (Königsblau)",
    color_match="Blue", sheen="None", shading="Moderate",
    notes="Washable royal-blue workhorse.")),
 ("21267973-IMG_4027.jpeg", 1, B(brand="Conklin", name="Israel 75th Anniversary — Blue Diamond (LE 1948)",
    color_match="Blue", sheen="None", shading="None",
    notes="Brilliant blue inspired by Israel's flag; limited edition of 1948. "
          "This is the bottle that came with my Conklin Israel 75th Anniversary pen.")),
 ("21267973-IMG_4027.jpeg", 2, B(brand="Pilot Iroshizuku", name="kon-peki (Deep Azure)",
    color_match="Blue", sheen="None", shading="Moderate",
    notes="Iconic bright cerulean; very subtle red sheen possible on coated paper.")),

 ("cc71b6cf-IMG_4026.jpeg", 0, B(brand="Pilot Iroshizuku", name="shin-kai (Deep Sea)",
    color_match="Blue", sheen="Red", shading="Strong",
    notes="Grey blue-black with a notable copper/red sheen and heavy shading.")),
 ("cc71b6cf-IMG_4026.jpeg", 1, B(brand="Waterman", name="Serenity Blue",
    color_match="Blue", sheen="None", shading="Moderate",
    notes="Bright, easy, well-behaved standard blue (formerly Florida Blue).")),
 ("cc71b6cf-IMG_4026.jpeg", 2, B(brand="Waterman", name="Inspired Blue",
    color_match="Blue", sheen="None", shading="Moderate",
    notes="Vivid mid-blue; well-behaved everyday ink.")),

 ("0e52137f-IMG_4025.jpeg", 0, B(brand="J. Herbin (1670)", name="Emerald of Chivor",
    color_match="Green", sheen="Red", shimmer=True, shading="Strong",
    notes="Iconic teal-green with GOLD shimmer and a pink/red sheen. Best in broad/stub "
          "nibs on coated paper; keep OUT of vintage sac fillers (particles clog).")),
 ("0e52137f-IMG_4025.jpeg", 1, B(brand="Tom's Studio", name="03 Neptune",
    color_match="Blue", sheen="Pink", shading="Moderate",
    notes="Medium teal with a subtle pink sheen and light shading; British-made.")),
 ("0e52137f-IMG_4025.jpeg", 2, B(brand="Kobe (Nagasawa)", name="California Teal Blue (CA Pen Show 2026)",
    color_match="Blue", sheen="None", shading="Moderate",
    notes="Nagasawa Kobe INK Monogatari, made by Sailor; California Pen Show 2026 exclusive; "
          "teal-blue inspired by SoCal shorelines.")),
]

# horizontal thirds (with gaps to avoid neighbor bleed); vertical band centered on the swatch
COLS = [(0.010, 0.325), (0.340, 0.660), (0.675, 0.990)]
BAND = (0.20, 0.68)

_img_cache = {}
def load(fname):
    # NOTE: these files carry EXIF orientation 6, but the raw landscape pixels are
    # already the correct viewing orientation (cards left-to-right). Do NOT transpose.
    if fname not in _img_cache:
        _img_cache[fname] = Image.open(os.path.join(UP, fname)).convert("RGB")
    return _img_cache[fname]


def crop_swab(fname, col, out_path):
    im = load(fname)
    w, h = im.size
    x0, x1 = COLS[col]
    box = (int(w * x0), int(h * BAND[0]), int(w * x1), int(h * BAND[1]))
    c = im.crop(box)
    c.thumbnail((1000, 1000), Image.LANCZOS)
    c.save(out_path, "JPEG", quality=85)


def main():
    inks, photos = [], {}
    for fname, col, rec in INKS:
        iid = gid()
        rec = dict(rec)
        rec.update(id=iid, photos=[], added_at=NOW)
        inks.append(rec)
        img_name = f"ink_{iid}_swab.jpg"
        crop_swab(fname, col, os.path.join(PHOTOS, img_name))
        photos[f"ink:{iid}"] = [{"url": f"photos/{img_name}", "tag": "swab"}]

    with open(os.path.join(ROOT, "inks.json"), "w", encoding="utf-8") as f:
        json.dump(inks, f, indent=2, ensure_ascii=False)

    # merge into existing photos.json (keep any pen/paper photos)
    pf = os.path.join(ROOT, "photos.json")
    existing = {}
    if os.path.exists(pf):
        try:
            existing = json.load(open(pf, encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(photos)
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"Ingested {len(inks)} inks with swab crops.")
    from collections import Counter
    print("By color:", dict(Counter(i["color_match"] for i in inks)))
    print("Shimmer:", sum(1 for i in inks if i["shimmer"]),
          "| With sheen:", sum(1 for i in inks if i["sheen"] != "None"))


if __name__ == "__main__":
    main()
