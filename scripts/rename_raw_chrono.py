"""
rename_raw_chrono.py
====================
OPTIONAL one-shot utility. Renames the raw Locomizer CSVs in place from
Locomizer's 'MM_MonYY[YY]_...' convention to a year-first, chronologically
sortable convention, across ALL raw datasets (footfall, demographics,
brand_affinity):

    03_Mar25_Micromedia_Footfall.csv        ->  2025_03_Mar_Micromedia_Footfall.csv
    12_Dec2024_Micromedia_Demographics.csv  ->  2024_12_Dec_Micromedia_Demographics.csv
    02_Feb2025_Micromedia_BrandAffinity.csv ->  2025_02_Feb_Micromedia_BrandAffinity.csv

Both 2-digit (25) and 4-digit (2025) source years are handled.

Why renaming raw is enough for the whole pipeline
-------------------------------------------------
process_demographics.py and process_brand_affinity.py build their output name
straight from the raw filename stem (stem -> stem_clean.parquet), and
process_footfall.py keeps an already-year-first stem unchanged via its
fallback. So renaming the raw files makes EVERY processed output year-first
too — no edits to the three processing scripts are needed.

    IMPORTANT: after renaming, clear data/processed/<dataset>/ and reprocess,
    otherwise the old-named parquets linger next to the new ones and a
    folder-based Power BI import would read both.

Why this is a SEPARATE script (not part of the processing scripts)
------------------------------------------------------------------
The raw/ folder is the landing zone — copies exactly as the provider delivered
them. Renaming is a one-off convenience, so it lives on its own and defaults
to a DRY RUN.

Safety
------
  * DRY_RUN = True by default: prints the plan, changes nothing.
  * Never overwrites an existing target (skips and warns).
  * Files that don't match the pattern are left untouched.
  * Set DRY_RUN = False only after you've reviewed the planned renames.

Usage
-----
  python rename_raw_chrono.py          # dry run: shows what WOULD happen
  # review the output, then set DRY_RUN = False and run again to apply.
"""

import os
import re

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_BASE = os.path.join(BASE_DIR, "..", "data", "raw")

# Every raw dataset that follows the MM_MonYY[YY]_... convention.
RAW_SUBDIRS = ["footfall", "demographics", "brand_affinity"]

DRY_RUN            = True   # <- flip to False to actually rename
INCLUDE_MONTH_NAME = True   # 2025_03_Mar_...  (False -> 2025_03_...)

MONTH_ABBR_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Matches '<MM>_<Mon><YY or YYYY>_<rest>'.
FILENAME_PERIOD_RE = re.compile(r"^(\d{1,2})_([A-Za-z]{3})(\d{2,4})_(.+)$")


def build_new_name(filename):
    """Return the year-first filename, or None if the name doesn't match."""
    stem, ext = os.path.splitext(filename)
    m = FILENAME_PERIOD_RE.match(stem)
    if not m:
        return None
    _mm, mon, yy, rest = m.groups()
    month_num = MONTH_ABBR_TO_NUM.get(mon.lower())
    if month_num is None:
        return None
    yy = int(yy)
    year4 = yy if yy > 100 else 2000 + yy
    if INCLUDE_MONTH_NAME:
        new_stem = f"{year4}_{month_num:02d}_{mon.title()}_{rest}"
    else:
        new_stem = f"{year4}_{month_num:02d}_{rest}"
    return f"{new_stem}{ext}"


def rename_one_folder(folder):
    """Plan/apply renames in a single raw subfolder. Returns counts."""
    print(f"\n[DIR] {folder}")
    if not os.path.isdir(folder):
        print("  ⚠️  Folder not found — skipped.")
        return 0, 0, 0

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".csv"))
    planned, skipped_nomatch, skipped_exists = 0, 0, 0

    for fname in files:
        new_name = build_new_name(fname)

        if new_name is None:
            print(f"  [SKIP ] no pattern match : {fname}")
            skipped_nomatch += 1
            continue
        if new_name == fname:
            continue  # already in the target convention

        target = os.path.join(folder, new_name)
        if os.path.exists(target):
            print(f"  [SKIP ] target exists    : {fname}  ->  {new_name}")
            skipped_exists += 1
            continue

        print(f"  [{'PLAN ' if DRY_RUN else 'RENAME'}] {fname}  ->  {new_name}")
        planned += 1
        if not DRY_RUN:
            os.rename(os.path.join(folder, fname), target)

    return planned, skipped_nomatch, skipped_exists


def main():
    mode = "DRY RUN (no changes)" if DRY_RUN else "APPLYING CHANGES"
    print(f"{'='*20} rename_raw_chrono — {mode} {'='*20}")

    total_planned, total_nomatch, total_exists = 0, 0, 0
    for sub in RAW_SUBDIRS:
        p, nm, ex = rename_one_folder(os.path.join(RAW_BASE, sub))
        total_planned  += p
        total_nomatch  += nm
        total_exists   += ex

    print(f"\n{'-'*66}")
    print(f"  {'Would rename' if DRY_RUN else 'Renamed'} : {total_planned}")
    print(f"  Skipped (no match) : {total_nomatch}")
    print(f"  Skipped (exists)   : {total_exists}")
    if DRY_RUN and total_planned:
        print("\n  Review the plan above, then set DRY_RUN = False and re-run to apply.")
    if not DRY_RUN and total_planned:
        print("\n  ⚠️  Now CLEAR data/processed/<dataset>/ and reprocess so the "
              "outputs pick up the new names (old parquets won't auto-delete).")
    print(f"{'='*66}")


if __name__ == "__main__":
    main()