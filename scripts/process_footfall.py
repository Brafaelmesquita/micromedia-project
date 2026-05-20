"""
process_footfall.py
===================
Reads monthly Footfall CSV exports from Locomizer and produces, for each
input file, one Parquet (or CSV) file ready for Power BI ingestion.

  Example:  03_Mar25_Micromedia_Footfall.csv  ->  03_Mar25_Micromedia_Footfall.parquet

Transformations
---------------
  * DAY + MONTH + YEAR merged into a single DATE column (date only).
  * MOVEMENT_MODALITY / VISITATION_MODALITY normalised to Title Case
    ('PEDESTRIANS' -> 'Pedestrians'). Aligns Footfall with Demographics and
    Brand Affinity so a single Power BI slicer drives all three fact tables.
  * IS_GRAND_TOTAL (int8) flag added on every (All, All) row. Combined with
    HOUR it gives the dashboard a one-field filter for the right slice:
        IS_GRAND_TOTAL = 1 AND HOUR = 25  -> daily / monthly unique audience
        IS_GRAND_TOTAL = 1 AND HOUR < 25  -> hourly unique audience
        IS_GRAND_TOTAL = 0                -> segment breakdowns
  * No rows are removed. HOUR=25 sentinels are PRESERVED (see v3.1 changelog).

Power BI usage
--------------
The three audience KPIs come pre-computed by Locomizer as separate columns
and share the same row filter:

  Total Population  ->  EXTRAPOLATED_USERS_2                 (whole population)
  PaS               ->  EXTRAPOLATED_NUMBER_OF_USERS         (mobile-holding only)
  OTS               ->  EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS  (looking at the screen)

  Filter for all three:  IS_GRAND_TOTAL = 1 AND HOUR = 25

For segment breakdowns:
  Movement-mix donut         IS_GRAND_TOTAL = 0 AND VISITATION_MODALITY = 'All'
  Visitation-type donut      IS_GRAND_TOTAL = 0 AND MOVEMENT_MODALITY  = 'All'

Segment percentages are reliable; segment absolute volumes overcount by
40-50% because a panellist can be classified into more than one modality
within the same hour. Always show segments as share-of-total, not raw counts.

Why we keep (All, All) and HOUR=25 rows
---------------------------------------
Versions <= 2.x removed (All, All) on the assumption it equalled the sum of
the segment rows. Versions <= 3.0 kept (All, All) but still removed HOUR=25
on the assumption Power BI could sum HOUR 0..23 to get daily totals. Both
assumptions are wrong. Empirical check against Mar 2025 (243 screens, 320,286 rows):

  * Movement-segment sum > (All, All) in 37.7% of (CODE, DAY, HOUR) cells.
  * Visitation-segment sum > (All, All) in 15.8% of cells.
  * Summing HOUR 0..23 inflates daily Total Population 1.46x vs HOUR=25
    (people who stay 3h get counted 3x).
  * Naive whole-table SUM inflates Total Population 8.08x.

The (All, All) HOUR=25 row is therefore the ONLY source of a deduplicated
daily count. Keeping it is mandatory for the dashboard's day-level KPIs.

Full reproducible audit: docs/footfall_methodology/

Data model
----------
DISPLAY NAME, LATITUDE, LONGITUDE are dropped. The Master Sites dimension
table is the single source of truth, joined to this fact table via CODE.

Output format
-------------
OUTPUT_FORMAT = "parquet"  (recommended; ~5x smaller, ~15x faster in Power BI)
OUTPUT_FORMAT = "csv"      (Excel / legacy compatibility)

Usage
-----
  python process_footfall.py
  Drop new monthly CSVs into INPUT_DIR and re-run. No code changes needed.

Changelog
---------
  v3.1.0  2026-05-20  BEHAVIOUR CHANGE: stop removing HOUR=25 sentinel rows.
                      They are the only deduplicated daily totals Locomizer
                      provides; the dashboard needs them for day-level and
                      month-level KPIs. Power BI measures must now filter
                      HOUR=25 explicitly (see "Power BI usage" above).
                      Methodology empirically cross-validated against the
                      full Mar 2025 dataset (243 screens) -- refines the
                      single-screen probe from v3.0. Reproducible SQL audit
                      shipped under docs/footfall_methodology/.
  v3.0.0  2026-05-16  BREAKING: stop removing (All, All) rows; add
                      IS_GRAND_TOTAL flag. Segment-sum overcount measured at
                      41% (movement) / 49% (visitation) on a single-screen
                      probe (Feb 2025, screen 50004).
  v2.0.0  2026-05     Title-Case modality normalisation for cross-dataset
                      alignment in Power BI.
  v1.x.x              Initial pipeline.
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

__version__ = "3.1.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folders
INPUT_DIR  = os.path.join(BASE_DIR, "..", "data", "raw", "footfall")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "processed", "footfall")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Output format: "parquet" for Power BI, "csv" for Excel.
OUTPUT_FORMAT = "parquet"

# Sentinel value used by Locomizer to flag the all-day-total row.
# Kept for clarity in the IS_GRAND_TOTAL semantics; not used as a filter.
HOUR_TOTAL = 25

# Title-Case values matched by add_grand_total_flag().
MODALITY_ALL   = "All"
VISITATION_ALL = "All"

# Columns to standardise to Title Case. Footfall and Demographics arrive
# UPPERCASE from Locomizer; Brand Affinity arrives Title Case. Standardising
# here lets a single Power BI slicer drive all three datasets.
MODALITY_COLS = ["MOVEMENT_MODALITY", "VISITATION_MODALITY"]


# ── Explicit dtypes for read_csv ─────────────────────────────────────────────
# Skips pandas type inference (biggest single speed-up on large CSVs) and
# halves memory vs the default float64 / int64 inference.
DTYPE_MAP = {
    "CODE":                                           str,
    "RADIUS":                                         "int16",
    "HOUR":                                           "int8",
    "DAY":                                            "int8",
    "MONTH":                                          "int8",
    "YEAR":                                           "int16",
    "MOVEMENT_MODALITY":                              "category",
    "VISITATION_MODALITY":                            "category",
    "NUMBER_OF_USERS":                                "int32",
    "NUMBER_OF_SIGNALS":                              "int32",
    "DWELL_TIME":                                     "float32",
    "REACH":                                          "float32",
    "EXTRAPOLATED_NUMBER_OF_USERS":                   "float32",
    "EXTRAPOLATED_NUMBER_OF_SIGNALS":                 "float32",
    "EXTRAPOLATED_USERS_2":                           "float32",
    "EXTRAPOLATED_SIGNALS_2":                         "float32",
    "NUMBER_OF_EYE_CONTACTS":                         "int32",
    "NUMBER_OF_EYE_CONTACTS_WEIGHTED":                "int32",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS":            "float32",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED":   "float32",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED_2": "float32",
}

EXPECTED_COLUMNS = list(DTYPE_MAP.keys())

# Logical column order for the output file. IS_GRAND_TOTAL sits next to the
# modality columns it derives from.
COLS_ORDER = [
    "CODE",
    "DATE", "HOUR",
    "RADIUS",
    "MOVEMENT_MODALITY", "VISITATION_MODALITY",
    "IS_GRAND_TOTAL",
    "NUMBER_OF_USERS", "NUMBER_OF_SIGNALS",
    "DWELL_TIME", "REACH",
    "EXTRAPOLATED_NUMBER_OF_USERS", "EXTRAPOLATED_NUMBER_OF_SIGNALS",
    "EXTRAPOLATED_USERS_2", "EXTRAPOLATED_SIGNALS_2",
    "NUMBER_OF_EYE_CONTACTS", "NUMBER_OF_EYE_CONTACTS_WEIGHTED",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED_2",
    "SOURCE_FILE",
]


# %% ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def validate_schema(df, filename):
    """Warn on missing expected columns; note extras. Returns (missing, extra)."""
    actual   = set(df.columns)
    expected = set(EXPECTED_COLUMNS)
    missing  = expected - actual
    extra    = actual - expected - {"SOURCE_FILE"}

    if not missing:
        print(f"  ✅ Schema OK — all {len(EXPECTED_COLUMNS)} expected columns present.")
    else:
        print(f"  ⚠️  {len(missing)} column(s) MISSING from schema: {sorted(missing)}")

    if extra:
        print(f"  [INFO] {len(extra)} extra column(s) found (kept): {sorted(extra)}")

    return missing, extra


def standardize_modality_casing(df, columns):
    """
    Convert modality column values to Title Case so a single Power BI slicer
    can drive Footfall + Demographics + Brand Affinity at once. Idempotent.
    Uses .cat.rename_categories() to preserve the categorical dtype.
    """
    for col in columns:
        if col not in df.columns:
            continue
        if isinstance(df[col].dtype, pd.CategoricalDtype):
            df[col] = df[col].cat.rename_categories(
                {c: c.title() for c in df[col].cat.categories}
            )
        else:
            df[col] = df[col].astype(str).str.title().astype("category")
    return df


def build_date_column(df):
    """Merge DAY + MONTH + YEAR into a date-only DATE column; drop the source ints."""
    df["DATE"] = pd.to_datetime(
        df[["YEAR", "MONTH", "DAY"]].rename(
            columns={"YEAR": "year", "MONTH": "month", "DAY": "day"}
        ),
        errors="coerce",
    ).dt.date
    df.drop(columns=["DAY", "MONTH", "YEAR"], inplace=True)
    return df


def add_grand_total_flag(df):
    """
    Add IS_GRAND_TOTAL (int8, 0/1). Set to 1 on every (All, All) row regardless
    of HOUR. The flag marks deduplicated audience counts; combine with HOUR to
    pick the granularity:
        IS_GRAND_TOTAL=1 AND HOUR=25  -> daily / monthly unique audience
        IS_GRAND_TOTAL=1 AND HOUR<25  -> hourly unique audience
        IS_GRAND_TOTAL=0              -> segment breakdowns
    See module docstring for the empirical rationale.
    """
    df["IS_GRAND_TOTAL"] = (
        (df["MOVEMENT_MODALITY"] == MODALITY_ALL) &
        (df["VISITATION_MODALITY"] == VISITATION_ALL)
    ).astype("int8")
    return df


def apply_column_order(df, label):
    """Reorder columns to COLS_ORDER; append any unexpected extras at the end."""
    ordered  = [c for c in COLS_ORDER if c in df.columns]
    leftover = sorted([c for c in df.columns if c not in ordered])
    df = df[ordered + leftover]

    if leftover:
        print(f"  [{label}] {len(leftover)} unexpected column(s) appended: {leftover}")
    else:
        print(f"  [{label}] ✅ Column order applied.")
    return df


def export_file(df, stem, fmt):
    """Export df to OUTPUT_DIR/<stem>.<ext> in the requested format."""
    ext  = ".parquet" if fmt == "parquet" else ".csv"
    path = os.path.join(OUTPUT_DIR, f"{stem}{ext}")

    if fmt == "parquet":
        df.to_parquet(path, index=False, engine="pyarrow")
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")

    return path


def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 — Discover input files
# ---------------------------------------------------------------------------

print(f"{'='*20} FILE DISCOVERY (process_footfall v{__version__}) {'='*20}")
print(f"[DIR]    Scanning : {INPUT_DIR}")
print(f"[FORMAT] Output   : {OUTPUT_FORMAT.upper()}")

all_csvs       = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
footfall_files = sorted([f for f in all_csvs if "footfall" in os.path.basename(f).lower()])

if not footfall_files:
    print(f"❌ ERROR: No Footfall CSV files found in {INPUT_DIR}")
    print("         Filenames must contain 'footfall' (e.g. '03_Mar25_Micromedia_Footfall.csv')")
    raise SystemExit(1)

print(f"[FOUND]  {len(footfall_files)} file(s) detected:")
for f in footfall_files:
    print(f"         - {os.path.basename(f):55s} ({os.path.getsize(f)/1024:>8,.0f} KB)")
print(f"{'='*56}\n")


# %% ---------------------------------------------------------------------------
# Step 2 — Per-file processing loop
# ---------------------------------------------------------------------------

global_summary = []

for filepath in footfall_files:
    filename = os.path.basename(filepath)
    stem     = os.path.splitext(filename)[0]

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # 2a — Load with explicit dtypes
    try:
        df = pd.read_csv(filepath, dtype=DTYPE_MAP, usecols=EXPECTED_COLUMNS)
    except Exception as e:
        print(f"  ❌ LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename
    rows_raw = len(df)
    print(f"  [LOAD]   {rows_raw:>10,} rows × {len(df.columns)} columns")

    # 2b — Schema + null checks
    print(f"  [SCHEMA]")
    validate_schema(df, filename)
    key_cols  = ["CODE", "HOUR", "MOVEMENT_MODALITY", "VISITATION_MODALITY",
                 "DAY", "MONTH", "YEAR"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}
    if any(v > 0 for v in null_hits.values()):
        print(f"  ⚠️  Nulls in key filter columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key filter columns. ✅")

    # 2c — Build DATE
    df = build_date_column(df)
    nat_after = df["DATE"].isna().sum()
    sample_dates = [str(d) for d in df["DATE"].dropna().unique()[:3]]
    print(f"  [DATE]   DATE column built. NaT: {nat_after:,}  |  Sample: {sample_dates}")
    if nat_after > 0:
        print(f"  ⚠️  WARNING: {nat_after} rows have an invalid DATE (NaT).")

    # 2d — Title-Case modalities (must run before IS_GRAND_TOTAL).
    df = standardize_modality_casing(df, MODALITY_COLS)
    print(f"  [CASE]   MOVEMENT_MODALITY  : {sorted(df['MOVEMENT_MODALITY'].unique().tolist())}")
    print(f"           VISITATION_MODALITY: {sorted(df['VISITATION_MODALITY'].unique().tolist())}")

    # 2e — IS_GRAND_TOTAL flag
    df = add_grand_total_flag(df)
    n_grand        = int(df["IS_GRAND_TOTAL"].sum())
    n_grand_daily  = int(((df["IS_GRAND_TOTAL"] == 1) & (df["HOUR"] == HOUR_TOTAL)).sum())
    n_grand_hourly = n_grand - n_grand_daily
    print(f"  [FLAG]   IS_GRAND_TOTAL=1 on {n_grand:,} rows "
          f"({n_grand/len(df)*100:.1f}%) — {n_grand_daily:,} daily (HOUR=25), "
          f"{n_grand_hourly:,} hourly.")

    # 2f — Column order
    df = apply_column_order(df, "OUTPUT")

    # 2g — Export
    try:
        path    = export_file(df, stem, OUTPUT_FORMAT)
        size_kb = file_info(path)[0]
        elapsed = time.time() - t_start
        print(f"  [EXPORT] → {os.path.basename(path):<55} ({size_kb:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":           filename,
            "status":         "OK",
            "rows":           len(df),
            "grand_daily":    n_grand_daily,
            "grand_hourly":   n_grand_hourly,
            "date_min":       str(df["DATE"].min()),
            "date_max":       str(df["DATE"].max()),
            "screens":        df["CODE"].nunique(),
            "size_kb":        round(size_kb, 1),
            "elapsed_s":      round(elapsed, 1),
        })

    except Exception as e:
        print(f"  ❌ EXPORT FAILED: {e}")
        global_summary.append({"file": filename, "status": "EXPORT ERROR", "error": str(e)})

    print()


# %% ---------------------------------------------------------------------------
# Step 3 — Global summary
# ---------------------------------------------------------------------------

print(f"{'='*20} GLOBAL SUMMARY {'='*20}")
print(f"\n  {'FILE':<46} {'STATUS':<8}  {'ROWS':>8}  {'G.DAILY':>7}  {'G.HOURLY':>8}  {'DATE RANGE':<23}  {'SCRNS':>5}  {'TIME':>5}")
print(f"  {'-'*46} {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*23}  {'-'*5}  {'-'*5}")

total_rows = 0
ok_count   = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count   += 1
        total_rows += s["rows"]
        date_range  = f"{s['date_min']} → {s['date_max']}"
        print(f"  {s['file']:<46} {'✅ OK':<8}  {s['rows']:>8,}  "
              f"{s['grand_daily']:>7,}  {s['grand_hourly']:>8,}  "
              f"{date_range:<23}  {s['screens']:>5,}  {s['elapsed_s']:>4.1f}s")
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<46} ❌ {s['status']:<8}  {err}")

print(f"  {'─'*120}")
print(f"  {'TOTAL':<46} {'':>8}  {total_rows:>8,}")
print(f"\n  Files OK      : {ok_count} / {len(footfall_files)}")
print(f"  Output folder : {OUTPUT_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"  Script version: {__version__}")
print(f"{'='*56}")
print("Process finished.")