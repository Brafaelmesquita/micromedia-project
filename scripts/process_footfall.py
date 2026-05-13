"""
process_footfall.py
===================
Reads monthly Footfall CSV exports from Locomizer and produces, for EACH
input file, one clean output file:

  <original_name>_detail.<ext>
       All rows EXCEPT HOUR = 25 AND MOVEMENT_MODALITY = 'ALL'
                               AND VISITATION_MODALITY = 'ALL'.
       → granular data for all Busiest Times charts, modality breakdowns,
         and KPI calculations in Power BI.
       → all-day total rows (HOUR = 25) are excluded because Power BI
         aggregates the granular rows directly, avoiding redundancy.

  Example:
    IN  → 03_Mar25_Micromedia_Footfall.csv
    OUT → 03_Mar25_Micromedia_Footfall_detail.parquet

Transformations applied to every file:
  • HOUR = 25 / ALL / ALL rows stripped before export (handled by Power BI).
  • DAY + MONTH + YEAR merged into a single DATE column (date only, no time).
  • Explicit column dtypes on load — avoids pandas type inference, cuts
    memory usage by ~40% and speeds up read_csv on large files.
  • Low-cardinality string columns stored as 'category' — faster groupby /
    filter in pandas and smaller file size in Parquet.

Output format:
  Set OUTPUT_FORMAT = "parquet" for Power BI (recommended — 10-20x faster
  load, 3-5x smaller files, data types preserved automatically).
  Set OUTPUT_FORMAT = "csv"     for Excel / legacy compatibility.

Power BI tip (Parquet):
  Use "Get Data → Folder" in Power BI and point it at OUTPUT_DETAIL_DIR.
  Power BI auto-combines all Parquet files that share the same schema,
  so adding a new month requires zero changes to the .pbix file.

Row exclusion rule (per project spec):
  Excluded → HOUR == 25  AND  MOVEMENT_MODALITY == 'ALL'
                          AND  VISITATION_MODALITY == 'ALL'
  Note: schema spec says 'All' but real Locomizer exports use 'ALL'.
  Verified against 03_Mar25_Micromedia_Footfall.csv.

Usage:
  python process_footfall.py
  Drop new monthly CSVs into INPUT_DIR and re-run — no code changes needed.
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Folders ────────────────────────────────────────────────────────────────────
INPUT_DIR         = os.path.join(BASE_DIR, "..", "data", "raw", "footfall")
OUTPUT_DIR        = os.path.join(BASE_DIR, "..", "data", "processed", "footfall")
OUTPUT_DETAIL_DIR = os.path.join(OUTPUT_DIR, "detail")
os.makedirs(OUTPUT_DETAIL_DIR, exist_ok=True)

# ── Output format ─────────────────────────────────────────────────────────────
# "parquet" → recommended for Power BI (smaller, faster, type-safe)
# "csv"     → Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# ── Exclusion filter constants (rows matching ALL THREE are dropped) ───────────
# Change here if Locomizer ever changes casing.
HOUR_TOTAL     = 25      # Locomizer sentinel: all-day total row
MODALITY_ALL   = "ALL"   # MOVEMENT_MODALITY value of the all-day row
VISITATION_ALL = "ALL"   # VISITATION_MODALITY value of the all-day row

# ── Optimised dtypes for read_csv ─────────────────────────────────────────────
# Specifying dtypes skips pandas type-inference, which is the biggest single
# speed-up for large CSVs. Rules:
#   int8   → HOUR, DAY, MONTH (max 31, fits −128..127)
#   int16  → YEAR, RADIUS
#   int32  → count columns (values stay well below 2 billion)
#   float32→ all ratio/extrapolation columns (halves memory vs float64;
#             precision is more than sufficient for audience percentages)
#   category → low-cardinality strings (5 movement types, 4 visitation types,
#               ~243 screen names) — speeds up groupby/filter significantly
DTYPE_MAP = {
    "CODE":                                           str,
    "DISPLAY NAME":                                   "category",
    "RADIUS":                                         "int16",
    "LATITUDE":                                       "float32",
    "LONGITUDE":                                      "float32",
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

# ── Expected columns (derived from DTYPE_MAP keys) ────────────────────────────
EXPECTED_COLUMNS = list(DTYPE_MAP.keys())

# ── Logical column order for the output file ──────────────────────────────────
COLS_ORDER = [
    "CODE", "DISPLAY NAME",                          # Identifiers
    "DATE", "HOUR",                                  # Time (DATE = date only, no timestamp)
    "RADIUS", "LATITUDE", "LONGITUDE",               # Geography
    "MOVEMENT_MODALITY", "VISITATION_MODALITY",      # Segment filters
    "NUMBER_OF_USERS", "NUMBER_OF_SIGNALS",          # Raw panel metrics
    "DWELL_TIME", "REACH",
    "EXTRAPOLATED_NUMBER_OF_USERS", "EXTRAPOLATED_NUMBER_OF_SIGNALS",
    "EXTRAPOLATED_USERS_2", "EXTRAPOLATED_SIGNALS_2",
    "NUMBER_OF_EYE_CONTACTS", "NUMBER_OF_EYE_CONTACTS_WEIGHTED",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED",
    "EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED_2",
    "SOURCE_FILE",                                   # Audit trail
]


# %% ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def validate_schema(df, filename):
    """
    Check that all expected columns are present.
    Missing columns are flagged with a warning; extra columns are noted but kept.
    Returns (missing_cols, extra_cols).
    """
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


def build_date_column(df):
    """
    Merge DAY + MONTH + YEAR into a single DATE column stored as Python
    date objects (YYYY-MM-DD). Drop the three source integer columns.

    Using .dt.date strips the time component entirely so Power BI and Excel
    display clean dates without the redundant '00:00:00' suffix.
    """
    df["DATE"] = pd.to_datetime(
        df[["YEAR", "MONTH", "DAY"]].rename(
            columns={"YEAR": "year", "MONTH": "month", "DAY": "day"}
        ),
        errors="coerce",   # invalid date combos become NaT instead of crashing
    ).dt.date              # strip time → clean YYYY-MM-DD

    df.drop(columns=["DAY", "MONTH", "YEAR"], inplace=True)
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


def export_file(df_detail, stem, fmt):
    """
    Export the detail DataFrame using 'stem' as the base file name.
    fmt: "parquet" or "csv"
    Returns path_detail.
    """
    ext         = ".parquet" if fmt == "parquet" else ".csv"
    path_detail = os.path.join(OUTPUT_DETAIL_DIR, f"{stem}_detail{ext}")

    if fmt == "parquet":
        # pyarrow preserves dtypes and date columns exactly as-is.
        # Power BI reads the DATE column as a clean Date (no time).
        df_detail.to_parquet(path_detail, index=False, engine="pyarrow")
    else:
        # utf-8-sig BOM ensures the CSV opens correctly in Excel on Windows
        df_detail.to_csv(path_detail, index=False, encoding="utf-8-sig")

    return path_detail


def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 — Discover input files
# ---------------------------------------------------------------------------
# Scan INPUT_DIR for CSVs whose name contains 'footfall' (case-insensitive).
# Sorted alphabetically so monthly files process in chronological order.

print(f"{'='*20} FILE DISCOVERY {'='*20}")
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
# Each file is loaded, validated, transformed, filtered, and exported independently.
# Benefits of per-file processing:
#   • Only one month sits in RAM at a time → lower peak memory usage.
#   • A single corrupt/missing file does not block the others.
#   • New months can be added to the folder without re-processing old ones.

global_summary = []   # collects one dict per file for the final report

for filepath in footfall_files:
    filename = os.path.basename(filepath)
    stem     = os.path.splitext(filename)[0]   # e.g. "03_Mar25_Micromedia_Footfall"

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # ── 2a: Load with optimised dtypes ────────────────────────────────────────
    # Pass DTYPE_MAP at load time so pandas skips the type-inference scan.
    # Unknown columns (not in DTYPE_MAP) use default inference — safe fallback.
    try:
        df = pd.read_csv(filepath, dtype=DTYPE_MAP)
    except Exception as e:
        print(f"  ❌ LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename   # audit trail — which file this row came from
    rows_raw = len(df)
    print(f"  [LOAD]   {rows_raw:>10,} rows × {len(df.columns)} columns")

    # ── 2b: Schema validation ──────────────────────────────────────────────────
    print(f"  [SCHEMA]")
    validate_schema(df, filename)

    # Null check on key filter columns
    key_cols  = ["CODE", "HOUR", "MOVEMENT_MODALITY", "VISITATION_MODALITY",
                 "DAY", "MONTH", "YEAR"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}

    if any(v > 0 for v in null_hits.values()):
        print(f"  ⚠️  Nulls in key filter columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key filter columns. ✅")

    # ── 2c: Build DATE column (date-only, no timestamp) ───────────────────────
    df = build_date_column(df)
    nat_after = df["DATE"].isna().sum()

    sample_dates = [str(d) for d in df["DATE"].dropna().unique()[:3]]
    print(f"  [DATE]   DATE column built (date only). "
          f"NaT: {nat_after:,}  |  Sample: {sample_dates}")

    if nat_after > 0:
        print(f"  ⚠️  WARNING: {nat_after} rows have an invalid DATE (will appear as NaT).")

    # ── 2d: Exclude all-day total rows ────────────────────────────────────────
    # Rows where HOUR=25 AND MOVEMENT_MODALITY=ALL AND VISITATION_MODALITY=ALL
    # are Locomizer's pre-computed all-day summaries. They are excluded here
    # because Power BI aggregates the granular detail rows directly.
    exclusion_mask = (
        (df["HOUR"]                == HOUR_TOTAL)     &
        (df["MOVEMENT_MODALITY"]   == MODALITY_ALL)   &
        (df["VISITATION_MODALITY"] == VISITATION_ALL)
    )

    rows_excluded = int(exclusion_mask.sum())
    df_detail     = df[~exclusion_mask].reset_index(drop=True)
    del df   # free the original DataFrame

    print(f"  [FILTER] {rows_raw:>8,} raw rows  →  "
          f"{rows_excluded:>6,} excluded (HOUR=25/ALL/ALL)  →  "
          f"{len(df_detail):>7,} kept  ✅")

    # ── 2e: Column reordering ──────────────────────────────────────────────────
    df_detail = apply_column_order(df_detail, "DETAIL")

    # ── 2f: Export ────────────────────────────────────────────────────────────
    try:
        path_detail  = export_file(df_detail, stem, OUTPUT_FORMAT)
        size_d, _    = file_info(path_detail)
        elapsed      = time.time() - t_start

        print(f"  [EXPORT] {os.path.basename(path_detail):<60} ({size_d:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":           filename,
            "status":         "OK",
            "rows_raw":       rows_raw,
            "rows_excluded":  rows_excluded,
            "rows_detail":    len(df_detail),
            "date_min":       str(df_detail["DATE"].min()),
            "date_max":       str(df_detail["DATE"].max()),
            "screens":        df_detail["CODE"].nunique(),
            "size_detail_kb": round(size_d, 1),
            "elapsed_s":      round(elapsed, 1),
        })

    except Exception as e:
        print(f"  ❌ EXPORT FAILED: {e}")
        global_summary.append({"file": filename, "status": "EXPORT ERROR", "error": str(e)})

    print()   # blank line between files


# %% ---------------------------------------------------------------------------
# Step 3 — Global summary
# ---------------------------------------------------------------------------
# One-glance report across all processed files.

print(f"{'='*20} GLOBAL SUMMARY {'='*20}")
print(f"\n  {'FILE':<46} {'STATUS':<8}  {'RAW':>8}  {'EXCLUDED':>8}  {'DETAIL':>8}  {'DATE RANGE':<23}  {'SCRNS':>5}  {'TIME':>5}")
print(f"  {'-'*46} {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*23}  {'-'*5}  {'-'*5}")

total_raw      = 0
total_excluded = 0
total_detail   = 0
ok_count       = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count       += 1
        total_raw      += s["rows_raw"]
        total_excluded += s["rows_excluded"]
        total_detail   += s["rows_detail"]
        date_range      = f"{s['date_min']} → {s['date_max']}"
        print(f"  {s['file']:<46} {'✅ OK':<8}  {s['rows_raw']:>8,}  "
              f"{s['rows_excluded']:>8,}  {s['rows_detail']:>8,}  "
              f"{date_range:<23}  {s['screens']:>5,}  {s['elapsed_s']:>4.1f}s")
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<46} ❌ {s['status']:<8}  {err}")

print(f"  {'─'*120}")
print(f"  {'TOTAL':<46} {'':>8}  {total_raw:>8,}  {total_excluded:>8,}  {total_detail:>8,}")
print(f"\n  Files OK      : {ok_count} / {len(footfall_files)}")
print(f"  Detail folder : {OUTPUT_DETAIL_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"{'='*56}")
print("Process finished.")
# %%