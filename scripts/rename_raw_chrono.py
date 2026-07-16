"""
rename_raw_chrono.py
====================
OPTIONAL one-shot utility. Renames the raw Locomizer CSVs in place from
Locomizer's 'MM_MonYY_...' convention to a year-first, chronologically
sortable convention:

    03_Mar25_Micromedia_Footfall.csv  ->  2025_03_Mar_Micromedia_Footfall.csv

Why this is a SEPARATE script (and not part of process_footfall.py)
-------------------------------------------------------------------
The raw/ folder is the landing zone: the copies exactly as the data provider
delivered them. Best practice is to keep it immutable for provenance and
reproducibility, and to impose your own naming convention on the PROCESSED
output only (process_footfall.py already does that). Renaming raw files is a
one-off convenience, not part of the repeatable pipeline, so it lives on its
own and defaults to a DRY RUN.

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
RAW_DIR  = os.path.join(BASE_DIR, "..", "data", "raw", "footfall")

DRY_RUN                 = True   # <- flip to False to actually rename
INCLUDE_MONTH_NAME      = True   # 2025_03_Mar_...  (False -> 2025_03_...)
FILENAME_FILTER         = "footfall"   # only touch files whose name contains this

MONTH_ABBR_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
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


def main():
    mode = "DRY RUN (no changes)" if DRY_RUN else "APPLYING CHANGES"
    print(f"{'='*20} rename_raw_chrono — {mode} {'='*20}")
    print(f"[DIR] {RAW_DIR}\n")

    if not os.path.isdir(RAW_DIR):
        print(f"❌ Directory not found: {RAW_DIR}")
        raise SystemExit(1)

    files = sorted(
        f for f in os.listdir(RAW_DIR)
        if f.lower().endswith(".csv") and FILENAME_FILTER in f.lower()
    )

    planned, skipped_nomatch, skipped_exists = 0, 0, 0

    for fname in files:
        new_name = build_new_name(fname)

        if new_name is None:
            print(f"  [SKIP ] no pattern match : {fname}")
            skipped_nomatch += 1
            continue
        if new_name == fname:
            continue  # already in the target convention

        target = os.path.join(RAW_DIR, new_name)
        if os.path.exists(target):
            print(f"  [SKIP ] target exists    : {fname}  ->  {new_name}")
            skipped_exists += 1
            continue

        print(f"  [{'PLAN ' if DRY_RUN else 'RENAME'}] {fname}  ->  {new_name}")
        planned += 1
        if not DRY_RUN:
            os.rename(os.path.join(RAW_DIR, fname), target)

    print(f"\n  {'Would rename' if DRY_RUN else 'Renamed'} : {planned}")
    print(f"  Skipped (no match) : {skipped_nomatch}")
    print(f"  Skipped (exists)   : {skipped_exists}")
    if DRY_RUN and planned:
        print("\n  Review the plan above, then set DRY_RUN = False and re-run to apply.")
    print(f"{'='*66}")


if __name__ == "__main__":
    main()