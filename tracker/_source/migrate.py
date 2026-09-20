#!/usr/bin/env python3
"""
One-time migration: parse the pens.md table (exported verbatim from the
Pen_Inventory Google Sheet) into tracker/pens.json using the new schema.

Run:  python tracker/_source/migrate.py
"""
import json
import os
import re
import string
import random
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "pens.md")
OUT = os.path.join(HERE, "..", "pens.json")

# Header label -> internal field name
COLMAP = {
    "Make": "make",
    "Model": "model",
    "Material / Color": "material_color",
    "Paid ($)": "paid",
    "Source": "source",
    "eBay or Pen_Swap Seller": "seller",
    "Date Acquired": "date_acquired",
    "Nib / Grind": "nib_grind",
    "Nib Material": "nib_material",
    "Nibmeister": "nibmeister",
    "Status": "status",
    "Weight": "weight",
    "Fits Hand": "fits_hand",
    "Notes": "notes",
    "Est. Value (Private, mid $)": "est_value",
    "Unrealized vs Paid": "unrealized",
}


def gen_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=13))


def unescape(s: str) -> str:
    # Markdown export escaped these; restore the literal characters.
    return s.replace("\\_", "_").replace("\\|", "|").replace("\\-", "-").strip()


def clean_money(s: str):
    """'$390' -> 390.0 ; '($70)' -> -70.0 ; '' / '-' -> None"""
    s = s.strip()
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[(),$\s]", "", s)
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def clean_date(s: str):
    """'6/8/2026' -> '2026-06-08' (ISO). Leave unparseable as-is."""
    s = s.strip()
    if not s:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def parse_rows():
    with open(SRC, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]

    header = [unescape(c) for c in lines[0].strip("|").split("|")]
    fields = [COLMAP.get(h.strip(), h.strip()) for h in header]

    pens = []
    # lines[1] is the |:-:| separator; data starts at lines[2]
    for ln in lines[2:]:
        # The user uses a literal " || " inside Notes; protect it from the
        # column splitter, then restore it afterwards.
        protected = ln.strip().strip("|").replace(" || ", " ‖ ")
        cells = protected.split("|")
        if len(cells) != len(fields):
            raise ValueError(f"Column count mismatch ({len(cells)} vs {len(fields)}):\n{ln}")
        cells = [unescape(c).replace("‖", "||") for c in cells]
        rec = dict(zip(fields, cells))

        pen = {
            "id": gen_id(),
            "make": rec["make"],
            "model": rec["model"],
            "material_color": rec["material_color"],
            "paid": clean_money(rec["paid"]),
            "source": rec["source"],
            "seller": rec["seller"],
            "date_acquired": clean_date(rec["date_acquired"]),
            "nib_grind": rec["nib_grind"],
            "nib_material": rec["nib_material"],
            "nibmeister": rec["nibmeister"].replace("—", "").strip(),
            "status": rec["status"],
            "weight": rec["weight"],
            "fits_hand": rec["fits_hand"],
            "notes": rec["notes"],
            "est_value": clean_money(rec["est_value"]),
            # unrealized is derived (est_value - paid); we recompute, but keep
            # the sheet's original for reference / sanity check.
            "unrealized_sheet": clean_money(rec["unrealized"]),
            "photos": [],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        pens.append(pen)
    return pens


def main():
    pens = parse_rows()

    # Sanity check: recomputed unrealized should match the sheet where both exist.
    mismatches = []
    for p in pens:
        if p["paid"] is not None and p["est_value"] is not None and p["unrealized_sheet"] is not None:
            calc = round(p["est_value"] - p["paid"], 2)
            if abs(calc - p["unrealized_sheet"]) > 0.5:
                mismatches.append((p["make"], p["model"], calc, p["unrealized_sheet"]))

    out_path = os.path.abspath(OUT)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pens, f, indent=2, ensure_ascii=False)

    print(f"Imported {len(pens)} pens -> {out_path}")
    statuses = {}
    for p in pens:
        statuses[p["status"]] = statuses.get(p["status"], 0) + 1
    print("Status counts:", dict(sorted(statuses.items())))
    total_paid = sum(p["paid"] or 0 for p in pens)
    print(f"Total paid: ${total_paid:,.0f}")
    if mismatches:
        print(f"\n[!] {len(mismatches)} unrealized mismatches (calc vs sheet):")
        for m in mismatches:
            print("   ", m)
    else:
        print("Unrealized check: all rows consistent.")


if __name__ == "__main__":
    main()
