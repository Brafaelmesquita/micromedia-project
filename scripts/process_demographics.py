"""
process_demographics.py
=======================
Reads monthly Demographics CSV exports from Locomizer and produces, for EACH
input file, one clean output file:

  <original_name>_clean.<ext>
       All rows with demographic reach values, fully cleaned and typed.
       -> granular hourly data per screen and movement modality, ready for
         Power BI demographic charts (age/gender, social grade, consumer segments).

  Example:
    IN  -> 12_Dec2024_Micromedia_Demographics.csv
    OUT -> 12_Dec2024_Micromedia_Demographics_clean.parquet

Transformations applied to every file:
  * MM_ID extracted from DISPLAY NAME (first 5 characters = Micromedia site ID).
    DISPLAY NAME column is then dropped -- the site list is the single source of
    truth for name, address, and coordinates.
  * LATITUDE / LONGITUDE dropped -- sourced from the master site list to avoid
    duplication and stale coordinate data in the analytics layer.
  * Zero-data rows removed -- rows where all reach values are 0 are placeholder
    rows emitted by Locomizer when the panel is too small. They carry no audience
    information and distort Power BI averages if kept.
  * YEAR_MONTH period column built from MONTH + YEAR (no DAY in demographics
    exports) -- stored as "YYYY-MM" string for clean display in Power BI slicers.
    MONTH and YEAR integer columns are dropped after YEAR_MONTH is built -- the
    period information is fully captured in YEAR_MONTH and duplication is avoided.
  * Explicit column dtypes on load -- avoids pandas type inference, cuts memory
    usage significantly and speeds up read_csv on wide files (142 columns).
  * Low-cardinality string columns stored as 'category' -- faster groupby /
    filter in pandas and smaller file size in Parquet.

Output format:
  Set OUTPUT_FORMAT = "parquet" for Power BI (recommended -- 10-20x faster
  load, 3-5x smaller files, data types preserved automatically).
  Set OUTPUT_FORMAT = "csv"     for Excel / legacy compatibility.

Power BI tip (Parquet):
  Use "Get Data -> Folder" in Power BI and point it at OUTPUT_CLEAN_DIR.
  Power BI auto-combines all Parquet files that share the same schema,
  so adding a new month requires zero changes to the .pbix file.

Schema notes:
  HOUR              -> 0-23 (no sentinel row 25 as in Footfall; all rows are hourly).
  MOVEMENT_MODALITY -> ALL | PEDESTRIANS | NON_PEDESTRIANS.
                      IMPORTANT: each modality row is an INDEPENDENT demographic
                      profile where all reach columns sum to 100%. ALL is a
                      weighted profile of the combined audience -- NOT the arithmetic
                      sum of PEDESTRIANS + NON_PEDESTRIANS. Use MOVEMENT_MODALITY
                      as a filter/slicer, never aggregate across modalities.
  All T1_*, T9_*, T13_*, T14_* columns -> percentage values (0-100),
  stored as float32.

Usage:
  python process_demographics.py
  Drop new monthly CSVs into INPUT_DIR and re-run -- no code changes needed.

Version history:
  v1.4.0  2025-05-13  Two new steps:
                      (1) Zero-row filter: drop rows where all reach data = 0
                          (placeholder rows emitted by Locomizer when panel is
                          too small). Removes 947 rows / 5.3% in Dec 2024 and
                          2,162 rows / 12.0% in Mar 2026.
                      (2) MM_ID validation: flag screens whose DISPLAY NAME does
                          not start with a 5-digit code -- these will not join to
                          the site list and require manual resolution.
                      Global summary updated to report raw / zero / clean row
                      counts and invalid MM_ID count per file.
  v1.3.0  2025-05-13  Drop all 35 _T_ age-total columns -- verified as exact
                      sums of their _M_ + _F_ counterparts (max diff = 0.0)
                      across all rows in both exports. Includes T1_1AGETT_REACH
                      (previously kept as sentinel; now confirmed redundant and
                      removed). Grand-total integrity check removed from
                      validate_schema accordingly. Final width: 103 columns.
  v1.2.0  2025-05-13  Drop T1_1AGETM_REACH and T1_1AGETF_REACH -- verified as
                      exact sums (max diff = 0.0) of their 34 respective age
                      group columns across all rows in Dec 2024 and Mar 2026
                      exports. Redundant; Power BI can derive via SUM() if needed.
  v1.1.0  2025-05-13  Drop YEAR and MONTH after YEAR_MONTH is built to avoid
                      redundant columns. Add MOVEMENT_MODALITY semantic note
                      (ALL != PED + NON_PED; each row is an independent 100%
                      profile -- verified against Dec 2024 export).
  v1.0.0  2025-05-13  Initial release -- based on process_footfall.py.
                      Transformations applied:
                        * MM_ID extracted from DISPLAY NAME (first 5 digits)
                        * LATITUDE / LONGITUDE dropped (sourced from site list)
                        * YEAR_MONTH period column built from MONTH + YEAR
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

__version__ = "1.4.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Folders -------------------------------------------------------------------
INPUT_DIR        = os.path.join(BASE_DIR, "..", "data", "raw", "demographics")
OUTPUT_DIR       = os.path.join(BASE_DIR, "..", "data", "processed", "demographics")
OUTPUT_CLEAN_DIR = os.path.join(OUTPUT_DIR, "clean")
os.makedirs(OUTPUT_CLEAN_DIR, exist_ok=True)

# -- Output format -------------------------------------------------------------
# "parquet" -> recommended for Power BI (smaller, faster, type-safe)
# "csv"     -> Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# -- Columns to drop before export ---------------------------------------------
# LATITUDE / LONGITUDE are redundant -- the master site list (joined on MM_ID)
# is the authoritative source for screen coordinates.
COLS_DROP = ["LATITUDE", "LONGITUDE"]

# -- Redundant summary columns to drop -----------------------------------------
# All verified as exact sums of their _M_ + _F_ counterparts (max diff = 0.0
# across all rows in Dec 2024 and Mar 2026 exports).
#
# Group 1 -- gender totals (v1.2.0):
#   T1_1AGETM_REACH = sum of all 34 individual male   age columns (_M_REACH)
#   T1_1AGETF_REACH = sum of all 34 individual female age columns (_F_REACH)
#
# Group 2 -- per-band age totals and grand total (v1.3.0):
#   T1_1AGE{band}T_REACH = _M_ + _F_ for every age band (individual years 0-19,
#                           5-yr bands 20-24 ... 80-84, 85+, and grand total)
#
# Removing all 37 avoids double-counting in Power BI and reduces file width
# by 37 columns. Any total can be recreated as a DAX measure (e.g.
# [Age 25-29 Total] = [T1_1AGE25_29M_REACH] + [T1_1AGE25_29F_REACH]).
COLS_REDUNDANT = [
    # Gender totals
    "T1_1AGETM_REACH", "T1_1AGETF_REACH",
    # Per-band totals -- individual years 0-19
    "T1_1AGE0T_REACH",  "T1_1AGE1T_REACH",  "T1_1AGE2T_REACH",  "T1_1AGE3T_REACH",
    "T1_1AGE4T_REACH",  "T1_1AGE5T_REACH",  "T1_1AGE6T_REACH",  "T1_1AGE7T_REACH",
    "T1_1AGE8T_REACH",  "T1_1AGE9T_REACH",  "T1_1AGE10T_REACH", "T1_1AGE11T_REACH",
    "T1_1AGE12T_REACH", "T1_1AGE13T_REACH", "T1_1AGE14T_REACH", "T1_1AGE15T_REACH",
    "T1_1AGE16T_REACH", "T1_1AGE17T_REACH", "T1_1AGE18T_REACH", "T1_1AGE19T_REACH",
    # Per-band totals -- 5-year bands
    "T1_1AGE20_24T_REACH", "T1_1AGE25_29T_REACH", "T1_1AGE30_34T_REACH",
    "T1_1AGE35_39T_REACH", "T1_1AGE40_44T_REACH", "T1_1AGE45_49T_REACH",
    "T1_1AGE50_54T_REACH", "T1_1AGE55_59T_REACH", "T1_1AGE60_64T_REACH",
    "T1_1AGE65_69T_REACH", "T1_1AGE70_74T_REACH", "T1_1AGE75_79T_REACH",
    "T1_1AGE80_84T_REACH", "T1_1AGEGE_85T_REACH",
    # Grand total (always = 100.0; confirmed = AGETM + AGETF)
    "T1_1AGETT_REACH",
]

# -- MM_ID extraction ----------------------------------------------------------
# Locomizer formats DISPLAY NAME as "<5-digit-ID> - <Screen Name>".
# We extract the first 5 characters as MM_ID (the Micromedia Custom ID / CODE)
# and discard the rest.  The full name is available in the site list via MM_ID.
MM_ID_LENGTH = 5

# -- MM_ID validation pattern --------------------------------------------------
# Valid MM_IDs are exactly 5 numeric digits (e.g. "50001").
# Screens whose DISPLAY NAME does not start with 5 digits (e.g.
# "Dorset St. - Red Parrott - Drumcondra") produce invalid MM_IDs that will
# NOT join to the site list. These are flagged in the log -- no automatic fix
# is possible without the master site list.
MM_ID_PATTERN = r"^\d{5}$"

# -- Zero-row filter -----------------------------------------------------------
# Locomizer emits placeholder rows (all reach values = 0) for screen/hour/
# modality combinations where the panel was too small to generate reliable data.
# Verified in Dec 2024 (947 rows, 5.3%) and Mar 2026 (2,162 rows, 12.0%):
#   * Every column in T1_*M_REACH AND T1_*F_REACH is 0.0
#   * T9_, T13_, T14_ groups are also entirely 0.0 on those same rows
# Detection: sum of all T1_*M_REACH columns < threshold -> row is empty.
# Using the M columns is sufficient because M and F are always both zero together.
ZERO_ROW_THRESHOLD = 0.01   # sum of all male age reach cols below this -> drop

# -- Explicit dtype overrides for non-demographic columns ----------------------
# Specifying dtypes skips pandas type-inference on load -- biggest speed-up
# for wide CSVs. Rules:
#   int8     -> HOUR, MONTH (max 31/23, fits -128..127)
#   int16    -> YEAR, RADIUS
#   float32  -> all reach percentage columns (halves memory vs float64;
#               precision is more than sufficient for audience percentages)
#   category -> low-cardinality strings (3 movement types, ~243 screen names)
DTYPE_MAP_BASE = {
    "DISPLAY NAME":      str,       # processed -> MM_ID then dropped
    "LATITUDE":          "float32", # dropped after load
    "LONGITUDE":         "float32", # dropped after load
    "RADIUS":            "int16",
    "MONTH":             "int8",
    "HOUR":              "int8",
    "YEAR":              "int16",
    "MOVEMENT_MODALITY": "category",
}

# All T1_*, T9_*, T13_*, T14_* reach columns are float32.
# They are discovered dynamically from each file header to avoid listing
# all 134 column names here (see _build_full_dtype_map()).
REACH_DTYPE = "float32"

# -- Expected non-demographic base columns (for schema validation) --------------
EXPECTED_BASE_COLUMNS = list(DTYPE_MAP_BASE.keys())


# %% ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_full_dtype_map(filepath):
    """
    Read only the header row (nrows=0) to discover all column names, then
    merge DTYPE_MAP_BASE with float32 for every demographic reach column.
    This avoids hardcoding all 134 reach column names while still giving
    pandas explicit dtypes at load time.
    """
    header = pd.read_csv(filepath, nrows=0)
    dtype_map = dict(DTYPE_MAP_BASE)  # start with base overrides
    for col in header.columns:
        if col not in dtype_map:
            dtype_map[col] = REACH_DTYPE
    return dtype_map


def validate_schema(df, filename):
    """
    Check that all expected non-demographic base columns are present.
    Missing base columns are flagged with a warning; extra columns noted but kept.
    Also checks that at least one T1_ reach column is present.
    Returns (missing_cols, extra_cols).
    """
    actual   = set(df.columns)
    expected = set(EXPECTED_BASE_COLUMNS)
    missing  = expected - actual
    extra    = actual - expected - {"SOURCE_FILE"}

    # Check at least some demographic reach columns exist
    reach_cols = [c for c in df.columns if c.startswith(("T1_", "T9_", "T13_", "T14_"))]

    if not missing:
        print(f"  OK Base schema OK -- all {len(EXPECTED_BASE_COLUMNS)} expected base columns present.")
    else:
        print(f"  WARNING  {len(missing)} base column(s) MISSING: {sorted(missing)}")

    if reach_cols:
        print(f"  OK Demographic reach columns found: {len(reach_cols)}")
    else:
        print(f"  WARNING: No demographic reach columns (T1_/T9_/T13_/T14_) found!")

    if extra - set(c for c in extra if c.startswith(("T1_", "T9_", "T13_", "T14_"))):
        non_reach_extra = extra - set(reach_cols)
        if non_reach_extra:
            print(f"  [INFO] Unexpected non-reach column(s) found (kept): {sorted(non_reach_extra)}")

    return missing, extra


def extract_mm_id(df):
    """
    Extract the first MM_ID_LENGTH characters from DISPLAY NAME as MM_ID.
    Drop DISPLAY NAME afterwards -- the full screen name lives in the site list.

    Example:
        "50001 - Tower Records - Dawson Street" -> MM_ID = "50001"
    """
    df["MM_ID"] = df["DISPLAY NAME"].str[:MM_ID_LENGTH].str.strip()
    df.drop(columns=["DISPLAY NAME"], inplace=True)
    return df


def build_year_month_column(df):
    """
    Build a YEAR_MONTH string column (format "YYYY-MM") from the MONTH and YEAR
    integer columns.  Demographics exports do not include a DAY field, so a full
    calendar date cannot be constructed.

    "YYYY-MM" is chosen over a Period dtype because Power BI reads it as a plain
    text slicer without needing calendar table configuration.

    Note on naming: YEAR_MONTH is intentionally kept distinct from the DATE
    column used in Footfall (which is YYYY-MM-DD).  Naming both DATE would create
    a type mismatch in the Power BI data model (date vs text).

    MONTH and YEAR are dropped after YEAR_MONTH is built -- the period information
    is fully captured in YEAR_MONTH and duplication serves no purpose.
    """
    df["YEAR_MONTH"] = (
        df["YEAR"].astype(str)
        + "-"
        + df["MONTH"].astype(str).str.zfill(2)
    )
    df.drop(columns=["YEAR", "MONTH"], inplace=True)
    return df


def drop_columns(df, cols):
    """Drop a list of columns, ignoring any that are not present."""
    present = [c for c in cols if c in df.columns]
    absent  = [c for c in cols if c not in df.columns]
    if absent:
        print(f"  [INFO] Columns to drop not found (skipped): {absent}")
    df.drop(columns=present, inplace=True)
    if present:
        print(f"  [DROP]   Removed {len(present)} column(s)")
    return df


def build_column_order(df):
    """
    Return df with columns in a logical order:
      MM_ID -> time -> segment -> all reach columns -> SOURCE_FILE.
    Any unexpected columns are appended at the end.
    """
    priority = [
        "MM_ID",             # identifier (joins to site list)
        "YEAR_MONTH",        # time period (YYYY-MM)
        "HOUR",              # time of day (0-23)
        "RADIUS",            # viewshed radius
        "MOVEMENT_MODALITY", # segment filter (ALL / PEDESTRIANS / NON_PEDESTRIANS)
    ]

    # Collect demographic reach groups in schema order
    reach_groups = ["T1_", "T9_", "T13_", "T14_"]
    reach_cols   = []
    for prefix in reach_groups:
        reach_cols += [c for c in df.columns if c.startswith(prefix)]

    tail = ["SOURCE_FILE"]

    ordered = (
        [c for c in priority if c in df.columns]
        + reach_cols
        + [c for c in tail   if c in df.columns]
    )

    # Append any column not yet captured
    already = set(ordered)
    extras  = [c for c in df.columns if c not in already]
    if extras:
        print(f"  [INFO] {len(extras)} extra column(s) appended at end: {extras}")
    ordered += extras

    return df[ordered]


def export_file(df_clean, stem, fmt):
    """Write the cleaned DataFrame to OUTPUT_CLEAN_DIR in the requested format."""
    ext        = "parquet" if fmt == "parquet" else "csv"
    name_clean = f"{stem}_clean.{ext}"
    path_clean = os.path.join(OUTPUT_CLEAN_DIR, name_clean)

    if fmt == "parquet":
        df_clean.to_parquet(path_clean, index=False)
    else:
        df_clean.to_csv(path_clean, index=False, encoding="utf-8-sig")

    return path_clean


def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 -- Discover input files
# ---------------------------------------------------------------------------
# Scan INPUT_DIR for CSVs whose name contains 'demograph' (case-insensitive).
# Sorted alphabetically so monthly files process in chronological order.

print(f"{'='*20} FILE DISCOVERY {'='*20}")
print(f"[DIR]    Scanning : {INPUT_DIR}")
print(f"[FORMAT] Output   : {OUTPUT_FORMAT.upper()}")
print(f"[VER]    Script   : v{__version__}")

all_csvs           = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
demographics_files = sorted(
    [f for f in all_csvs if "demograph" in os.path.basename(f).lower()]
)

if not demographics_files:
    print(f"ERROR: No Demographics CSV files found in {INPUT_DIR}")
    print("       Filenames must contain 'demograph' (e.g. '12_Dec2024_Micromedia_Demographics.csv')")
    raise SystemExit(1)

print(f"[FOUND]  {len(demographics_files)} file(s) detected:")
for f in demographics_files:
    print(f"         - {os.path.basename(f):60s} ({os.path.getsize(f)/1024:>8,.0f} KB)")
print(f"{'='*56}\n")


# %% ---------------------------------------------------------------------------
# Step 2 -- Per-file processing loop
# ---------------------------------------------------------------------------
# Each file is loaded, validated, transformed, and exported independently.
# Benefits:
#   * Only one month sits in RAM at a time -> lower peak memory on wide files.
#   * A single corrupt/missing file does not block the others.
#   * New months can be added to the folder without re-processing old ones.

global_summary = []   # collects one dict per file for the final report

for filepath in demographics_files:
    filename = os.path.basename(filepath)
    stem     = os.path.splitext(filename)[0]

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # -- 2a: Build full dtype map from file header, then load ------------------
    try:
        dtype_map = _build_full_dtype_map(filepath)
        df = pd.read_csv(filepath, dtype=dtype_map)
        # Copy immediately to defragment the wide DataFrame (142 columns).
        # Without this, subsequent column adds/drops trigger pandas
        # PerformanceWarning on highly fragmented frames.
        df = df.copy()
    except Exception as e:
        print(f"  ERROR LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename   # audit trail
    rows_raw = len(df)
    print(f"  [LOAD]   {rows_raw:>10,} rows x {len(df.columns)} columns")

    # -- 2b: Schema validation -------------------------------------------------
    print(f"  [SCHEMA]")
    validate_schema(df, filename)

    # Null check on key columns (must run before MONTH/YEAR are dropped)
    key_cols  = ["DISPLAY NAME", "HOUR", "MONTH", "YEAR", "MOVEMENT_MODALITY"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}
    if any(v > 0 for v in null_hits.values()):
        print(f"  WARNING  Nulls in key columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key columns. OK")

    # -- 2c: Extract MM_ID from DISPLAY NAME -----------------------------------
    # Capture invalid DISPLAY NAMEs before the column is dropped.
    invalid_display_names = (
        df["DISPLAY NAME"][
            ~df["DISPLAY NAME"].str[:MM_ID_LENGTH].str.strip().str.match(MM_ID_PATTERN)
        ].unique().tolist()
    )
    sample_display = df["DISPLAY NAME"].iloc[0] if len(df) > 0 else ""
    df = extract_mm_id(df)
    sample_mm_id = df["MM_ID"].iloc[0] if len(df) > 0 else ""
    print(f"  [MM_ID]  Extracted from DISPLAY NAME "
          f"('{sample_display}' -> '{sample_mm_id}'). "
          f"Unique screens: {df['MM_ID'].nunique()}")

    # MM_ID validation -- flag screens that won't join to the site list
    if invalid_display_names:
        invalid_count = df[~df["MM_ID"].str.match(MM_ID_PATTERN)]["MM_ID"].nunique()
        print(f"  WARNING  {invalid_count} screen(s) with INVALID MM_ID (will NOT join to site list):")
        for name in invalid_display_names:
            extracted = name[:MM_ID_LENGTH].strip()
            print(f"       DISPLAY NAME: '{name}'  ->  MM_ID: '{extracted}'")
        print(f"       Action required: map these screens manually to their 5-digit site codes.")
    else:
        print(f"  [MM_ID]  All MM_IDs are valid 5-digit codes. OK")

    # -- 2d: Drop LATITUDE / LONGITUDE -----------------------------------------
    df = drop_columns(df, COLS_DROP)

    # -- 2e: Filter out zero-data rows -----------------------------------------
    # Rows where all reach values = 0 are placeholder rows emitted by Locomizer
    # when the panel size is too small to produce reliable data. They carry no
    # audience information and would distort Power BI averages if kept.
    # Detection: sum of all T1_*M_REACH columns below ZERO_ROW_THRESHOLD.
    # (M and F are always both zero on the same rows -- using M alone is enough.)
    m_cols    = [c for c in df.columns if c.startswith("T1_1AGE") and c.endswith("M_REACH")]
    zero_mask = df[m_cols].sum(axis=1) < ZERO_ROW_THRESHOLD
    rows_zero = int(zero_mask.sum())
    df        = df[~zero_mask].reset_index(drop=True)
    print(f"  [FILTER] {rows_zero:,} zero-data rows removed "
          f"({rows_zero / rows_raw * 100:.1f}% of raw)  ->  {len(df):,} rows remain.")

    # -- 2f: Drop all redundant _T_ summary columns (37 total) -----------------
    # Includes gender totals (AGETM, AGETF), per-band age totals (AGE{band}T),
    # and grand total (AGETT). All verified as exact M+F sums (max diff = 0.0).
    df = drop_columns(df, COLS_REDUNDANT)

    # -- 2g: Build YEAR_MONTH period column ------------------------------------
    df = build_year_month_column(df)
    sample_ym = df["YEAR_MONTH"].iloc[0] if len(df) > 0 else ""
    unique_ym  = sorted(df["YEAR_MONTH"].unique().tolist())
    print(f"  [PERIOD] YEAR_MONTH column built. "
          f"Periods in file: {unique_ym}  |  Sample: '{sample_ym}'")

    # -- 2h: Column reordering -------------------------------------------------
    df = build_column_order(df)
    print(f"  [ORDER]  Columns reordered. Final width: {len(df.columns)} columns.")

    # -- 2i: Export ------------------------------------------------------------
    try:
        path_clean = export_file(df, stem, OUTPUT_FORMAT)
        size_kb, _ = file_info(path_clean)
        elapsed    = time.time() - t_start

        print(f"  [EXPORT] {os.path.basename(path_clean):<65} ({size_kb:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":        filename,
            "status":      "OK",
            "rows_raw":    rows_raw,
            "rows_zero":   rows_zero,
            "rows_clean":  len(df),
            "screens":     df["MM_ID"].nunique(),
            "invalid_ids": len(invalid_display_names),
            "periods":     ", ".join(unique_ym),
            "size_kb":     round(size_kb, 1),
            "elapsed_s":   round(elapsed, 1),
        })

    except Exception as e:
        print(f"  ERROR EXPORT FAILED: {e}")
        global_summary.append({"file": filename, "status": "EXPORT ERROR", "error": str(e)})

    print()   # blank line between files


# %% ---------------------------------------------------------------------------
# Step 3 -- Global summary
# ---------------------------------------------------------------------------

print(f"{'='*20} GLOBAL SUMMARY {'='*20}")
print(f"\n  {'FILE':<50} {'STATUS':<8}  {'RAW':>7}  {'ZERO':>6}  {'CLEAN':>7}  "
      f"{'INV_ID':>6}  {'SCRNS':>5}  {'PERIOD':<8}  {'KB':>7}  {'TIME':>5}")
print(f"  {'-'*50} {'-'*8}  {'-'*7}  {'-'*6}  {'-'*7}  "
      f"{'-'*6}  {'-'*5}  {'-'*8}  {'-'*7}  {'-'*5}")

total_raw   = 0
total_zero  = 0
total_clean = 0
ok_count    = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count    += 1
        total_raw   += s["rows_raw"]
        total_zero  += s["rows_zero"]
        total_clean += s["rows_clean"]
        inv_flag     = f"WARN {s['invalid_ids']}" if s["invalid_ids"] > 0 else "OK   0"
        print(
            f"  {s['file']:<50} {'OK':<8}  {s['rows_raw']:>7,}  "
            f"{s['rows_zero']:>6,}  {s['rows_clean']:>7,}  {inv_flag:>6}  "
            f"{s['screens']:>5,}  {s['periods']:<8}  "
            f"{s['size_kb']:>7,.1f}  {s['elapsed_s']:>4.1f}s"
        )
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<50} ERROR {s['status']:<8}  {err}")

print(f"  {'─'*120}")
print(f"  {'TOTAL':<50} {'':>8}  {total_raw:>7,}  {total_zero:>6,}  {total_clean:>7,}")
print(f"\n  Files OK      : {ok_count} / {len(demographics_files)}")
print(f"  Clean folder  : {OUTPUT_CLEAN_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"{'='*56}")
print("Process finished.")
# %%