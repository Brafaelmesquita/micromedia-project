"""
process_footfall.py
===================
Reads monthly Footfall CSV exports from Locomizer and produces, for each
input file, one Parquet (or CSV) file ready for Power BI ingestion.

Output files are renamed to a YEAR-FIRST, zero-padded-month convention so
they sort chronologically in any file explorer (see "Output file naming"):

  Example:  03_Mar25_Micromedia_Footfall.csv  ->  2025_03_Mar_Micromedia_Footfall.parquet

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

Output file naming
------------------
Locomizer delivers files as MM_MonYY_... (e.g. 03_Mar25_...). Because the
month number leads, an alphabetical sort interleaves years (01_Jan25 sits
next to 01_Jan26). Output files are therefore renamed to:

  YYYY_MM[_Mon]_<rest>        e.g. 2025_03_Mar_Micromedia_Footfall.parquet

which sorts strictly by year then month. Controlled by:

  RENAME_OUTPUT_CHRONOLOGICAL = True   # turn the year-first rename on/off
  INCLUDE_MONTH_NAME_IN_STEM  = True   # keep the 'Mar' token for readability

The two-digit year in the source name is expanded to four digits (25 -> 2025)
and cross-checked against the actual DATE values in the data; a mismatch is
logged as a warning. If a source name does not match the expected pattern the
original stem is reused unchanged, so the pipeline never fails on an odd name.
The source CSVs in data/raw/ are left untouched (immutable landing zone).

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
  v3.3.0  2026-07-16  ROBUSTNESS: survive malformed source files.
                      (1) Blank-metric rows (a screen exported with CODE/DISPLAY
                          NAME but every measurement empty) no longer crash the
                          typed read. A safe-mode fallback drops them and logs
                          which screens were affected.
                      (2) Excel-truncation guard: warns loudly when a file sits
                          on Excel's 1,048,576-row limit (a CSV opened + saved in
                          Excel loses every row past that point).
  v3.2.0  2026-07-16  FEATURE: year-first output filenames. Processed files are
                      renamed MM_MonYY_... -> YYYY_MM_Mon_... so they sort
                      chronologically. Source CSVs are NOT touched. Parsed
                      period is cross-validated against the data's DATE column.
                      DOWNSTREAM NOTE: output filenames change, so any Power BI
                      query that references a processed file by its old name
                      must be repointed once (folder-based imports are safe).
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
import re
import time
import glob

import pandas as pd

__version__ = "3.3.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folders
INPUT_DIR  = os.path.join(BASE_DIR, "..", "data", "raw", "footfall")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "processed", "footfall")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Output format: "parquet" for Power BI, "csv" for Excel.
OUTPUT_FORMAT = "parquet"

# Output file naming.
#   RENAME_OUTPUT_CHRONOLOGICAL: rename MM_MonYY_... -> YYYY_MM[_Mon]_... so
#   processed files sort by year then month. Source CSVs are never renamed.
#   INCLUDE_MONTH_NAME_IN_STEM : keep the 'Mar' token (2025_03_Mar_...) for
#   readability; set False for a leaner 2025_03_... stem.
RENAME_OUTPUT_CHRONOLOGICAL = True
INCLUDE_MONTH_NAME_IN_STEM  = True

# Sentinel value used by Locomizer to flag the all-day-total row.
# Kept for clarity in the IS_GRAND_TOTAL semantics; not used as a filter.
HOUR_TOTAL = 25

# Excel silently drops every row past 1,048,576 (2^20) when a CSV is opened
# and re-saved. A file landing exactly on this boundary is almost certainly
# truncated, so we warn (see check_excel_truncation).
EXCEL_ROW_LIMIT = 1_048_576

# Title-Case values matched by add_grand_total_flag().
MODALITY_ALL   = "All"
VISITATION_ALL = "All"

# Month-abbreviation -> month-number map used to parse Locomizer filenames
# (e.g. '03_Mar25_Micromedia_Footfall.csv'). Case-insensitive lookup.
MONTH_ABBR_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches '<MM>_<Mon><YY>_<rest>' e.g. '03_Mar25_Micromedia_Footfall'.
# Groups: (month-number, month-abbr, 2-or-4-digit year, remainder).
FILENAME_PERIOD_RE = re.compile(r"^(\d{1,2})_([A-Za-z]{3})(\d{2,4})_(.+)$")

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

def parse_filename_period(filename):
    """
    Parse a Locomizer filename into its calendar period.

    'MM_MonYY_<rest>' -> (year4, month_num, 'Mon', '<rest>'), else None.
    e.g. '03_Mar25_Micromedia_Footfall.csv' -> (2025, 3, 'Mar', 'Micromedia_Footfall')

    The two-digit year is expanded as 2000 + YY. Returns None (rather than
    raising) on any name that does not match, so callers can fall back safely.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = FILENAME_PERIOD_RE.match(stem)
    if not m:
        return None

    _mm_str, mon_str, yy_str, rest = m.groups()
    month_num = MONTH_ABBR_TO_NUM.get(mon_str.lower())
    if month_num is None:
        return None

    yy    = int(yy_str)
    year4 = yy if yy > 100 else 2000 + yy
    return year4, month_num, mon_str.title(), rest


def build_output_stem(filename, include_month_name=True):
    """
    Build the year-first output stem from a source filename.

    '03_Mar25_Micromedia_Footfall.csv'
        include_month_name=True  -> ('2025_03_Mar_Micromedia_Footfall', (2025, 3))
        include_month_name=False -> ('2025_03_Micromedia_Footfall',     (2025, 3))

    Falls back to the original stem (and period=None) when the name does not
    match the expected pattern, guaranteeing the pipeline never fails on it.
    """
    original_stem = os.path.splitext(os.path.basename(filename))[0]
    parsed = parse_filename_period(filename)
    if parsed is None:
        return original_stem, None

    year4, month_num, mon_abbr, rest = parsed
    if include_month_name:
        stem = f"{year4}_{month_num:02d}_{mon_abbr}_{rest}"
    else:
        stem = f"{year4}_{month_num:02d}_{rest}"
    return stem, (year4, month_num)


def validate_period_against_data(df, parsed_period, label):
    """
    Cross-check the period parsed from the filename against the data itself.

    Uses the modal (most frequent) year/month of the DATE column so a few
    stray edge-of-month rows don't trigger a false alarm. Warns on mismatch;
    never raises. Returns True when they agree (or can't be checked).
    """
    if parsed_period is None or "DATE" not in df.columns:
        return True

    dates = pd.to_datetime(df["DATE"], errors="coerce").dropna()
    if dates.empty:
        return True

    data_year  = int(dates.dt.year.mode().iloc[0])
    data_month = int(dates.dt.month.mode().iloc[0])
    name_year, name_month = parsed_period

    if (data_year, data_month) != (name_year, name_month):
        print(f"  ⚠️  [{label}] Filename period {name_year}-{name_month:02d} "
              f"≠ data period {data_year}-{data_month:02d}. "
              f"Output named from the FILENAME; verify the source file.")
        return False

    print(f"  [PERIOD] Filename ↔ data agree: {data_year}-{data_month:02d}. ✅")
    return True


def coerce_expected_dtypes(df):
    """Cast columns to their DTYPE_MAP types where present. Best-effort: a
    column that still can't be cast is left as-is so the schema/null checks
    downstream surface the problem rather than crashing the run."""
    for col, dt in DTYPE_MAP.items():
        if col not in df.columns:
            continue
        try:
            df[col] = df[col].astype(dt)
        except (ValueError, TypeError):
            pass
    return df


def drop_empty_metric_rows(df):
    """
    Drop placeholder rows that carry an identifier but no data — e.g. a screen
    exported as '50104,50104 - HQ Laundrette,,,,,,...' with every metric blank.
    A row counts as empty when every column except CODE is null.
    Returns (clean_df, n_dropped, dropped_codes).
    """
    non_id     = [c for c in df.columns if c not in ("CODE", "SOURCE_FILE")]
    empty_mask = df[non_id].isna().all(axis=1)
    codes      = sorted(df.loc[empty_mask, "CODE"].dropna().unique().tolist())
    return df.loc[~empty_mask].copy(), int(empty_mask.sum()), codes


def load_footfall_csv(filepath):
    """
    Load one Footfall CSV robustly. Returns (df, n_empty_dropped, dropped_codes).

    Fast path: typed read (dtype=DTYPE_MAP) — what every clean file uses.
    Fallback: if the typed read raises because an integer column contains blank
    cells (source placeholder rows), re-read untyped, drop the empty rows, then
    cast to the expected dtypes. The fast files pay no penalty.
    """
    try:
        df = pd.read_csv(filepath, dtype=DTYPE_MAP, usecols=EXPECTED_COLUMNS)
        return df, 0, []
    except (ValueError, TypeError):
        df = pd.read_csv(filepath, dtype={"CODE": str}, usecols=EXPECTED_COLUMNS)
        df, n_dropped, codes = drop_empty_metric_rows(df)
        df = coerce_expected_dtypes(df)
        print(f"  [CLEAN]  Typed read hit blank metric cells — recovered in safe mode.")
        print(f"           Dropped {n_dropped:,} empty row(s) from screen(s): {codes}")
        return df, n_dropped, codes


def check_excel_truncation(n_rows_raw):
    """
    Warn if the file looks truncated at Excel's worksheet limit (2^20 rows).
    Returns True when a likely truncation is detected.
    """
    if n_rows_raw >= EXCEL_ROW_LIMIT - 1:
        print(f"  ⚠️  [TRUNCATION] {n_rows_raw:,} rows ≈ Excel's {EXCEL_ROW_LIMIT:,}-row "
              f"limit.")
        print(f"       This CSV was almost certainly opened + saved in Excel, which "
              f"DROPS every row past the limit.")
        print(f"       Data is likely MISSING — re-export from Locomizer and never "
              f"open the raw CSV in Excel.")
        return True
    return False


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

    # Decide the output stem up front (source file is never renamed).
    if RENAME_OUTPUT_CHRONOLOGICAL:
        out_stem, parsed_period = build_output_stem(filename, INCLUDE_MONTH_NAME_IN_STEM)
    else:
        out_stem, parsed_period = stem, None

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # 2a — Load (robust: fast typed read, safe fallback for blank-metric rows)
    try:
        df, n_empty_dropped, dropped_codes = load_footfall_csv(filepath)
    except Exception as e:
        print(f"  ❌ LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename
    rows_raw = len(df) + n_empty_dropped
    note = f"  ({n_empty_dropped:,} empty rows dropped)" if n_empty_dropped else ""
    print(f"  [LOAD]   {len(df):>10,} rows × {len(df.columns)} columns{note}")

    # Guard against files silently truncated at Excel's 2^20-row limit.
    truncated = check_excel_truncation(rows_raw)

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

    # Cross-check the period parsed from the filename against the actual data.
    if RENAME_OUTPUT_CHRONOLOGICAL:
        validate_period_against_data(df, parsed_period, "RENAME")

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

    # 2g — Export (year-first filename)
    try:
        path    = export_file(df, out_stem, OUTPUT_FORMAT)
        size_kb = file_info(path)[0]
        elapsed = time.time() - t_start
        if out_stem != stem:
            print(f"  [RENAME] {stem}  →  {out_stem}")
        print(f"  [EXPORT] → {os.path.basename(path):<55} ({size_kb:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":           filename,
            "output":         os.path.basename(path),
            "status":         "OK",
            "rows":           len(df),
            "empty_dropped":  n_empty_dropped,
            "truncated":      truncated,
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
print(f"\n  {'OUTPUT FILE':<46} {'STATUS':<8}  {'ROWS':>8}  {'G.DAILY':>7}  {'G.HOURLY':>8}  {'DATE RANGE':<23}  {'SCRNS':>5}  {'TIME':>5}")
print(f"  {'-'*46} {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*23}  {'-'*5}  {'-'*5}")

total_rows = 0
ok_count   = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count   += 1
        total_rows += s["rows"]
        date_range  = f"{s['date_min']} → {s['date_max']}"
        print(f"  {s.get('output', s['file']):<46} {'✅ OK':<8}  {s['rows']:>8,}  "
              f"{s['grand_daily']:>7,}  {s['grand_hourly']:>8,}  "
              f"{date_range:<23}  {s['screens']:>5,}  {s['elapsed_s']:>4.1f}s")
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<46} ❌ {s['status']:<8}  {err}")

print(f"  {'─'*120}")
print(f"  {'TOTAL':<46} {'':>8}  {total_rows:>8,}")

# Data-quality notes: surface anything that needs a human's attention.
dq_notes = []
for s in global_summary:
    if s.get("status") != "OK":
        continue
    if s.get("empty_dropped"):
        dq_notes.append(f"  • {s['output']}: dropped {s['empty_dropped']:,} empty "
                        f"placeholder row(s).")
    if s.get("truncated"):
        dq_notes.append(f"  • {s['output']}: ⚠️  LIKELY TRUNCATED at Excel's row "
                        f"limit — data may be missing. Re-export from Locomizer.")
if dq_notes:
    print(f"\n  {'DATA-QUALITY NOTES':<46}")
    print(f"  {'-'*46}")
    for line in dq_notes:
        print(line)

print(f"\n  Files OK      : {ok_count} / {len(footfall_files)}")
print(f"  Output folder : {OUTPUT_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"  Script version: {__version__}")
print(f"{'='*56}")
print("Process finished.")