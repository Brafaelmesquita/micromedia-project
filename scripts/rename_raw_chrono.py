"""
rename_raw_chrono.py
====================
One-shot utility that standardises EVERY raw Locomizer CSV to a single
year-first, chronologically sortable name — regardless of the (many and
inconsistent) names the provider ships:

    03_Mar25_Micromedia_Footfall.csv                                 ┐
    Audience_Filtering_and_Prediction_demographics_11_2025_IRL.csv   ├─► YYYY_MM_Mon_Micromedia_<Dataset>.csv
    Audience_Profiles_Brand_Affinity_IRL_2026-05_...csv              ┘

    e.g.  ->  2025_03_Mar_Micromedia_Footfall.csv
          ->  2025_11_Nov_Micromedia_Demographics.csv
          ->  2026_05_May_Micromedia_BrandAffinity.csv

Why content-based instead of parsing the filename
-------------------------------------------------
Locomizer delivers each dataset under a different convention, sometimes with
junk like '_IRL' or a ' (1)' duplicate-download suffix. Writing a regex per
convention is fragile — the next export may invent another one. Instead we
read the period straight from the data (every dataset has integer MONTH and
YEAR columns) and rebuild a clean, canonical name. The source name can be any
mess; the result is always the same.

This also makes renaming the single source of truth for naming: the three
processing scripts just reuse the raw stem, so once the raw files are
standardised, every processed .parquet is year-first automatically.

    IMPORTANT: after renaming, clear data/processed/<dataset>/ (including the
    clean/ and age_long/ subfolders) and reprocess, so outputs pick up the new
    names — old parquets won't auto-delete.

Safety
------
  * DRY_RUN = True by default: prints the plan, changes nothing.
  * Files already in YYYY_MM_Mon_... form are skipped WITHOUT being read (fast,
    idempotent).
  * Never overwrites an existing target — a collision (e.g. a ' (1)' duplicate
    resolving to the same period) is reported, not applied.
  * A file whose MONTH/YEAR can't be read is left untouched and flagged.

Usage
-----
  python rename_raw_chrono.py          # dry run: shows what WOULD happen
  # review the plan, then set DRY_RUN = False and re-run to apply.
"""

import os
import re
import csv

import pandas as pd

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_BASE = os.path.join(BASE_DIR, "..", "data", "raw")

# subfolder -> canonical dataset suffix for the standardised name.
# Each suffix still satisfies the processing scripts' glob filters
# ("footfall", "demograph", "brandaffinity").
DATASETS = {
    "footfall":       "Micromedia_Footfall",
    "demographics":   "Micromedia_Demographics",
    "brand_affinity": "Micromedia_BrandAffinity",
}

DRY_RUN = False

MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# A file already in the target convention: YYYY_MM_Mon_...
ALREADY_STD_RE = re.compile(r"^\d{4}_\d{2}_[A-Za-z]{3}_")

def sniff_dialect(filepath):
    """
    Return (encoding, delimiter) for a Locomizer CSV. Some exports ship
    comma/UTF-8, others TAB/UTF-8-SIG (and a few ';'). Falls back to comma.
    """
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            with open(filepath, "r", encoding=enc, newline="") as fh:
                sample = fh.read(8192)
        except (UnicodeError, UnicodeDecodeError):
            continue
        if not sample.strip():
            continue
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delim = max(",;\t|", key=sample.splitlines()[0].count)
        return enc, delim
    return "utf-8", ","

def read_period(filepath):
    """(year, month) from the file's own MONTH/YEAR columns, dialect-aware."""
    enc, delim = sniff_dialect(filepath)
    try:
        df = pd.read_csv(filepath, sep=delim, encoding=enc, usecols=["YEAR", "MONTH"])
    except (ValueError, KeyError, pd.errors.ParserError):
        return None

    yr = pd.to_numeric(df["YEAR"],  errors="coerce").dropna()
    mo = pd.to_numeric(df["MONTH"], errors="coerce").dropna()
    if yr.empty or mo.empty:
        return None

    year  = int(yr.mode().iloc[0])
    month = int(mo.mode().iloc[0])
    if not (1 <= month <= 12):
        return None
    return year, month


def build_target(year, month, suffix):
    """'2025_03_Mar_Micromedia_Footfall.csv' from (2025, 3, 'Micromedia_Footfall')."""
    return f"{year}_{month:02d}_{MONTH_ABBR[month]}_{suffix}.csv"


def rename_one_folder(folder, suffix):
    """Plan/apply renames in one raw subfolder. Returns count tuple."""
    print(f"\n[DIR] {folder}")
    if not os.path.isdir(folder):
        print("  ⚠️  Folder not found — skipped.")
        return 0, 0, 0, 0

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".csv"))
    planned = skipped_std = skipped_exists = skipped_unreadable = 0

    for fname in files:
        if ALREADY_STD_RE.match(fname):
            skipped_std += 1
            continue  # already standardised — don't even open it

        period = read_period(os.path.join(folder, fname))
        if period is None:
            print(f"  [SKIP ] can't read MONTH/YEAR : {fname}")
            skipped_unreadable += 1
            continue

        new_name = build_target(period[0], period[1], suffix)
        if new_name == fname:
            skipped_std += 1
            continue

        target = os.path.join(folder, new_name)
        if os.path.exists(target):
            print(f"  [SKIP ] target exists (dup?)  : {fname}  ->  {new_name}")
            skipped_exists += 1
            continue

        src = os.path.join(folder, fname)
        enc, delim = sniff_dialect(src)
        with open(src, "rb") as fh:
            has_bom = fh.read(3) == b"\xef\xbb\xbf"
        canonical = (delim == "," and enc == "utf-8-sig" and not has_bom)
        action = "RENAME" if canonical else "TRANSCODE"
        note   = "" if canonical else f"  ({delim!r}/{enc}{'+BOM' if has_bom else ''} -> ','/utf-8)"

        print(f"  [{'PLAN ' if DRY_RUN else action}] {fname}  ->  {new_name}{note}")
        planned += 1
        if DRY_RUN:
            continue

        if canonical:
            os.rename(src, target)
        else:
            # Stream-transcode (TAB/other -> comma/UTF-8) with the csv module:
            # constant memory, exact values, correct re-quoting. Write to a
            # .partial file and only atomically swap into place on success, so an
            # interrupted run can never leave a truncated *.csv in the glob path.
            tmp = target + ".partial"
            with open(src, "r", encoding=enc, newline="") as fin, \
                 open(tmp, "w", encoding="utf-8", newline="") as fout:
                writer = csv.writer(fout)
                for row in csv.reader(fin, delimiter=delim):
                    writer.writerow(row)
            os.replace(tmp, target)                       # atomic promote
            os.remove(src) 

    return planned, skipped_std, skipped_exists, skipped_unreadable


def main():
    mode = "DRY RUN (no changes)" if DRY_RUN else "APPLYING CHANGES"
    print(f"{'='*20} rename_raw_chrono — {mode} {'='*20}")

    tot_plan = tot_std = tot_exists = tot_unread = 0
    for sub, suffix in DATASETS.items():
        p, s, e, u = rename_one_folder(os.path.join(RAW_BASE, sub), suffix)
        tot_plan += p; tot_std += s; tot_exists += e; tot_unread += u

    print(f"\n{'-'*66}")
    print(f"  {'Would rename' if DRY_RUN else 'Renamed'}   : {tot_plan}")
    print(f"  Already standard : {tot_std}")
    print(f"  Skipped (dup)    : {tot_exists}")
    print(f"  Skipped (unread) : {tot_unread}")
    if DRY_RUN and tot_plan:
        print("\n  Review the plan above, then set DRY_RUN = False and re-run to apply.")
    if not DRY_RUN and tot_plan:
        print("\n  ⚠️  Now CLEAR data/processed/<dataset>/ and reprocess so outputs "
              "pick up the new names (old parquets won't auto-delete).")
    print(f"{'='*66}")


if __name__ == "__main__":
    main()