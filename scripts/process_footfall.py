"""
process_footfall.py
===================
Reads monthly Footfall CSV exports from Locomizer and produces, for EACH
input file, two clean output files:

  <original_name>_totals.<ext>
       Rows where HOUR = 25, MOVEMENT_MODALITY = 'ALL', VISITATION_MODALITY = 'ALL'
       → one summary row per screen per day; used for KPIs and trend analysis.

  <original_name>_hourly.<ext>
       All remaining rows (specific hours, specific modalities).
       → granular data for Busiest Times charts and modality breakdowns.

  Example:
    IN  → 03_Mar25_Micromedia_Footfall.csv
    OUT → 03_Mar25_Micromedia_Footfall_totals.parquet
          03_Mar25_Micromedia_Footfall_hourly.parquet

Transformations applied to every file:
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
  Use "Get Data → Folder" in Power BI and point it at OUTPUT_DIR.
  Power BI auto-combines all Parquet files that share the same schema,
  so adding a new month requires zero changes to the .pbix file.

Data cleaning rule applied (per project spec):
  Totals filter → HOUR == 25  AND  MOVEMENT_MODALITY == 'ALL'
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
OUTPUT_TOTALS_DIR = os.path.join(OUTPUT_DIR, "totals")
OUTPUT_HOURLY_DIR = os.path.join(OUTPUT_DIR, "hourly")
os.makedirs(OUTPUT_TOTALS_DIR, exist_ok=True)
os.makedirs(OUTPUT_HOURLY_DIR, exist_ok=True)

# ── Output format ─────────────────────────────────────────────────────────────
# "parquet" → recommended for Power BI (smaller, faster, type-safe)
# "csv"     → Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# ── Filter constants (change here if Locomizer ever changes casing) ───────────
HOUR_TOTAL     = 25      # Locomizer sentinel: all-day total row
MODALITY_ALL   = "ALL"   # MOVEMENT_MODALITY value for the totals filter
VISITATION_ALL = "ALL"   # VISITATION_MODALITY value for the totals filter

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

# ── Logical column order for both output files ────────────────────────────────
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


def export_pair(df_totals, df_hourly, stem, fmt):
    """
    Export totals and hourly DataFrames using 'stem' as the base file name.
    fmt: "parquet" or "csv"
    Returns (path_totals, path_hourly).
    """
    ext         = ".parquet" if fmt == "parquet" else ".csv"
    path_totals = os.path.join(OUTPUT_TOTALS_DIR, f"{stem}_totals{ext}")
    path_hourly = os.path.join(OUTPUT_HOURLY_DIR, f"{stem}_hourly{ext}")

    if fmt == "parquet":
        # pyarrow preserves dtypes and date columns exactly as-is.
        # Power BI reads the DATE column as a clean Date (no time).
        df_totals.to_parquet(path_totals, index=False, engine="pyarrow")
        df_hourly.to_parquet(path_hourly, index=False, engine="pyarrow")
    else:
        # utf-8-sig BOM ensures the CSV opens correctly in Excel on Windows
        df_totals.to_csv(path_totals, index=False, encoding="utf-8-sig")
        df_hourly.to_csv(path_hourly, index=False, encoding="utf-8-sig")

    return path_totals, path_hourly


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
# Each file is loaded, validated, transformed, split, and exported independently.
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

    # Null check on columns used in the totals filter
    key_cols  = ["CODE", "HOUR", "MOVEMENT_MODALITY", "VISITATION_MODALITY",
                 "DAY", "MONTH", "YEAR"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}

    if any(v > 0 for v in null_hits.values()):
        print(f"  ⚠️  Nulls in key filter columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key filter columns. ✅")

    # ── 2c: Build DATE column (date-only, no timestamp) ───────────────────────
    nat_before = df[["DAY", "MONTH", "YEAR"]].isna().any(axis=1).sum()
    df = build_date_column(df)
    nat_after  = df["DATE"].isna().sum()

    sample_dates = [str(d) for d in df["DATE"].dropna().unique()[:3]]
    print(f"  [DATE]   DATE column built (date only). "
          f"NaT: {nat_after:,}  |  Sample: {sample_dates}")

    if nat_after > 0:
        print(f"  ⚠️  WARNING: {nat_after} rows have an invalid DATE (will appear as NaT).")

    # ── 2d: Split totals vs. hourly ────────────────────────────────────────────
    totals_mask = (
        (df["HOUR"]                == HOUR_TOTAL)     &
        (df["MOVEMENT_MODALITY"]   == MODALITY_ALL)   &
        (df["VISITATION_MODALITY"] == VISITATION_ALL)
    )

    df_totals = df[totals_mask].reset_index(drop=True)
    df_hourly = df[~totals_mask].reset_index(drop=True)
    del df   # free the original DataFrame; outputs are now independent copies

    split_sum   = len(df_totals) + len(df_hourly)
    split_check = "PASS" if split_sum == rows_raw else "FAIL"
    print(f"  [SPLIT]  {rows_raw:>8,} total  →  "
          f"{len(df_totals):>6,} totals  +  {len(df_hourly):>7,} hourly  [{split_check}]")

    if len(df_totals) == 0:
        print(f"  ⚠️  WARNING: totals split is empty — check HOUR_TOTAL / MODALITY_ALL constants.")
    else:
        # Sanity assertions: totals must contain exactly the three filter values
        assert set(df_totals["HOUR"].unique())                == {HOUR_TOTAL},     \
            "Unexpected HOUR in totals!"
        assert set(df_totals["MOVEMENT_MODALITY"].unique())   == {MODALITY_ALL},   \
            "Unexpected MOVEMENT_MODALITY in totals!"
        assert set(df_totals["VISITATION_MODALITY"].unique()) == {VISITATION_ALL}, \
            "Unexpected VISITATION_MODALITY in totals!"
        print(f"  [VERIFY] Filter values in totals confirmed. ✅")

    # ── 2e: Column reordering ──────────────────────────────────────────────────
    df_totals = apply_column_order(df_totals, "TOTALS")
    df_hourly = apply_column_order(df_hourly, "HOURLY")

    # ── 2f: Export pair ────────────────────────────────────────────────────────
    try:
        path_totals, path_hourly = export_pair(df_totals, df_hourly, stem, OUTPUT_FORMAT)

        size_t, mod_t = file_info(path_totals)
        size_h, mod_h = file_info(path_hourly)
        elapsed       = time.time() - t_start

        print(f"  [EXPORT] Totals → {os.path.basename(path_totals):<55} ({size_t:>7,.1f} KB)")
        print(f"           Hourly → {os.path.basename(path_hourly):<55} ({size_h:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":           filename,
            "status":         "OK",
            "rows_raw":       rows_raw,
            "rows_totals":    len(df_totals),
            "rows_hourly":    len(df_hourly),
            "date_min":       str(df_totals["DATE"].min()) if len(df_totals) > 0 else "N/A",
            "date_max":       str(df_totals["DATE"].max()) if len(df_totals) > 0 else "N/A",
            "screens":        df_totals["CODE"].nunique() if len(df_totals) > 0 else 0,
            "size_totals_kb": round(size_t, 1),
            "size_hourly_kb": round(size_h, 1),
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
print(f"\n  {'FILE':<46} {'STATUS':<8}  {'RAW':>8}  {'TOTALS':>7}  {'HOURLY':>8}  {'DATE RANGE':<23}  {'SCRNS':>5}  {'TIME':>5}")
print(f"  {'-'*46} {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*23}  {'-'*5}  {'-'*5}")

total_raw    = 0
total_totals = 0
total_hourly = 0
ok_count     = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count     += 1
        total_raw    += s["rows_raw"]
        total_totals += s["rows_totals"]
        total_hourly += s["rows_hourly"]
        date_range    = f"{s['date_min']} → {s['date_max']}"
        print(f"  {s['file']:<46} {'✅ OK':<8}  {s['rows_raw']:>8,}  "
              f"{s['rows_totals']:>7,}  {s['rows_hourly']:>8,}  "
              f"{date_range:<23}  {s['screens']:>5,}  {s['elapsed_s']:>4.1f}s")
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<46} ❌ {s['status']:<8}  {err}")

print(f"  {'─'*120}")
print(f"  {'TOTAL':<46} {'':>8}  {total_raw:>8,}  {total_totals:>7,}  {total_hourly:>8,}")
print(f"\n  Files OK          : {ok_count} / {len(footfall_files)}")
print(f"  Totals folder     : {OUTPUT_TOTALS_DIR}\n"
        f"  Hourly folder     : {OUTPUT_HOURLY_DIR}")
print(f"  Output format     : {OUTPUT_FORMAT.upper()}")
print(f"{'='*56}")
print("Process finished.")
# %%
import pandas as pd

df = pd.read_parquet(r"C:\Users\brafa\Documents\data-analyst\MicroMedia\micromedia-project\data\processed\footfall\totals\01_Jan25_Micromedia_Footfall_totals.parquet")

print(df.shape)
df.head(10)
# %%
