"""
process_footfall.py
===================
Reads monthly Footfall CSV exports from Locomizer and produces, for EACH
input file, one clean output file:

  <original_name>.<ext>
       All rows except HOUR = 25 (all-day totals are excluded — Power BI
       handles aggregations directly from the hourly granular data).

  Example:
    IN  → 03_Mar25_Micromedia_Footfall.csv
    OUT → 03_Mar25_Micromedia_Footfall.parquet


Transformations applied to every file:
  • HOUR = 25 rows removed (all-day sentinel totals — Power BI aggregates from hourly data).
  • DAY + MONTH + YEAR merged into a single DATE column (date only, no time).
  • MOVEMENT_MODALITY and VISITATION_MODALITY values normalised to Title
    Case ('PEDESTRIANS' → 'Pedestrians', 'CAR_CITY' → 'Car_City', etc.) so
    a single Power BI slicer can drive Footfall, Demographics and Brand
    Affinity simultaneously. Without this, Locomizer's mixed casing across
    the three exports breaks cross-table filtering silently.
  • IS_GRAND_TOTAL flag (int8, 0/1) added — marks the (All, All) row that
    contains the true unique-user count for each (CODE, DATE, HOUR) cell.
    Power BI measures use this flag to pick the correct denominator (see
    "Measure usage" below).
  • Explicit column dtypes on load — avoids pandas type inference, cuts
    memory usage by ~40% and speeds up read_csv on large files.
  • Low-cardinality string columns stored as 'category' — faster groupby /
    filter in pandas and smaller file size in Parquet.

═══════════════════════════════════════════════════════════════════════════════
⚠️  v3.0 BREAKING CHANGE — (All, All) rows are now KEPT, not removed
═══════════════════════════════════════════════════════════════════════════════
Versions ≤ 2.x removed every row where MOVEMENT='All' AND VISITATION='All',
on the documented assumption that this row was the exact arithmetic sum of
its modality decompositions and therefore redundant.

Empirical verification against Feb 2025 data (screen 50004) disproved that
assumption for both raw-panel and extrapolated metrics:

   For NUMBER_OF_USERS (panel-level), the equality (All,All) = Σ segments
   holds in only 10.9% of (day, hour) cells. In 89.1% of cells the sum of
   movement segments STRICTLY EXCEEDS (All, All), because Locomizer's
   classification is not mutually exclusive within an hour: the same
   panellist can appear in both PEDESTRIANS and CAR_CITY rows (e.g. they
   parked, then walked). Visitation segments behave the same way
   (Resident ∩ Transient overlap).

   For EXTRAPOLATED_NUMBER_OF_USERS, the (All,All) row was 41% LOWER
   than the movement-segment sum and 49% lower than the visitation-
   segment sum. Every previous PaS / Total-Population KPI built on
   segment-summation was therefore inflated by ~40-50%.

Consequence: the (All, All) row is the ONLY source of a deduplicated
unique-user count. Removing it silently corrupted every audience-volume
KPI in the dashboard. v3.0 preserves the row and exposes it via the new
IS_GRAND_TOTAL flag.

Measure usage in Power BI after v3.0:

   ✅ Unique audience volume       — filter IS_GRAND_TOTAL = 1
                                     (covers PaS, Total Population KPI cards,
                                      daily trend line, screen ranking)

   ✅ Movement-mode breakdown      — filter IS_GRAND_TOTAL = 0
                                     AND VISITATION_MODALITY = 'All'
                                     (movement-share donut, etc.)

   ✅ Visitation-type breakdown    — filter IS_GRAND_TOTAL = 0
                                     AND MOVEMENT_MODALITY  = 'All'
                                     (Residents/Workers/Transient donut)

   ⚠️ When using segment breakdowns for percentages they are reliable; the
      absolute values overcount by 40-50% due to user multi-classification.
      Always normalise to share-of-total when displaying segment volumes.

   ❌ DO NOT use a naked SUM over the whole table without an IS_GRAND_TOTAL
      filter — that triple-counts (grand-total row + movement segments +
      visitation segments).
═══════════════════════════════════════════════════════════════════════════════

Output format:
  Set OUTPUT_FORMAT = "parquet" for Power BI (recommended — 10-20x faster
  load, 3-5x smaller files, data types preserved automatically).
  Set OUTPUT_FORMAT = "csv"     for Excel / legacy compatibility.

Power BI tip (Parquet):
  Use "Get Data → Folder" in Power BI and point it at OUTPUT_DIR.
  Power BI auto-combines all Parquet files that share the same schema,
  so adding a new month requires zero changes to the .pbix file.

Power BI data model note:
  DISPLAY NAME, LATITUDE, and LONGITUDE are intentionally excluded from this
  table. They are stored in the Master Sites dimension table and joined to this
  fact table via CODE (5-digit screen identifier). This follows a star schema:

      Master Sites (dimension) ──── CODE ────► Footfall (fact)
                                         also ► Demographics (fact)
                                         also ► Brand Affinity (fact)

  Power BI relationships to configure:
    Master Sites[CODE] → Footfall[CODE]          (many-to-one)
    Master Sites[CODE] → Demographics[CODE]      (many-to-one)
    Master Sites[CODE] → Brand Affinity[CODE]    (many-to-one)

Data cleaning rules applied:
  • HOUR == 25                               removed — all-day total sentinel rows;
                                             Power BI handles aggregations from hourly data.
  • MOVEMENT=All AND VISITATION=All          KEPT (v3.0+) — true unique-user count;
                                             flagged via IS_GRAND_TOTAL = 1.
  • MOVEMENT=All AND VISITATION ≠ All        KEPT — these are the only rows that carry
                                             RESIDENTS / WORKERS / TRANSIENT segmentation.
  • Individual MOVEMENT + VISITATION=All     KEPT — movement mode breakdown.

  Data structure (verified against real data):
    Individual movements (CAR_CITY etc.) → only appear with VISITATION=ALL
    MOVEMENT=ALL                          → appears with ALL + RESIDENTS + WORKERS + TRANSIENT
    → Three orthogonal slices share the same table; use IS_GRAND_TOTAL to disambiguate.

Usage:
  python process_footfall.py
  Drop new monthly CSVs into INPUT_DIR and re-run — no code changes needed.

Changelog:
  v3.0.0  2026-05-16  BREAKING: stop removing (All, All) rows; add IS_GRAND_TOTAL
                      flag column. Documented over-counting findings (89% of
                      hourly cells violate the A=B=C equality the previous
                      cleaning rule assumed). See module docstring for details.
                      Downstream DAX measures must be updated — see
                      "Measure usage in Power BI after v3.0" above.
  v2.0.0  2026-05    Title-Case modality normalisation for cross-dataset alignment.
  v1.x.x              Initial pipeline.
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

__version__ = "3.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Folders ────────────────────────────────────────────────────────────────────
INPUT_DIR  = os.path.join(BASE_DIR, "..", "data", "raw", "footfall")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "processed", "footfall")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Output format ─────────────────────────────────────────────────────────────
# "parquet" → recommended for Power BI (smaller, faster, type-safe)
# "csv"     → Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# ── Filter constants ─────────────────────────────────────────────────────────
# Applied AFTER modality casing standardisation, so values are in Title Case.
HOUR_TOTAL     = 25    # Locomizer sentinel: all-day total row → removed
MODALITY_ALL   = "All" # Used to identify and FLAG (not remove) the grand-total row:
VISITATION_ALL = "All" #   MOVEMENT=All + VISITATION=All  → IS_GRAND_TOTAL = 1  (KEPT v3.0+)
                       #   MOVEMENT=All + VISITATION≠All → IS_GRAND_TOTAL = 0  (visitation segments)
                       #   Individual MOVEMENT + VISITATION=All → IS_GRAND_TOTAL = 0  (movement segments)

# ── Modality columns to normalise to Title Case ──────────────────────────────
# Locomizer's Footfall export uses UPPERCASE for these columns
# ('PEDESTRIANS', 'ALL', 'WORKERS', ...). Brand Affinity uses Title Case
# ('Pedestrians', 'All', ...). Demographics also uses UPPERCASE. We standardise
# all three datasets to Title Case here so a single Power BI slicer drives
# every fact table at once.
MODALITY_COLS = ["MOVEMENT_MODALITY", "VISITATION_MODALITY"]


# ── Optimised dtypes for read_csv ─────────────────────────────────────────────
# Specifying dtypes skips pandas type-inference, which is the biggest single
# speed-up for large CSVs. Rules:
#   int8   → HOUR, DAY, MONTH (max 31, fits −128..127)
#   int16  → YEAR, RADIUS
#   int32  → count columns (values stay well below 2 billion)
#   float32→ all ratio/extrapolation columns (halves memory vs float64;
#             precision is more than sufficient for audience percentages)
#   category → low-cardinality strings (5 movement types, 4 visitation types)
#             — speeds up groupby/filter significantly
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

# ── Expected columns (derived from DTYPE_MAP keys) ────────────────────────────
EXPECTED_COLUMNS = list(DTYPE_MAP.keys())

# ── Logical column order for the output file ──────────────────────────────────
# IS_GRAND_TOTAL sits right next to the modality columns it derives from,
# so anyone inspecting the parquet sees the semantic relationship at a glance.
COLS_ORDER = [
    "CODE",                                          # Identifier
    "DATE", "HOUR",                                  # Time (DATE = date only, no timestamp)
    "RADIUS",                                        # Geography
    "MOVEMENT_MODALITY", "VISITATION_MODALITY",      # Segment filters
    "IS_GRAND_TOTAL",                                # (v3.0) flag: 1 = unique-user grand total
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


def standardize_modality_casing(df, columns):
    """
    Normalise modality column values to Title Case for cross-dataset
    consistency in Power BI. Locomizer's three exports use mixed casing:

      Footfall       → UPPERCASE ('PEDESTRIANS', 'ALL', 'WORKERS', ...)
      Demographics   → UPPERCASE ('ALL', 'PEDESTRIANS', 'NON_PEDESTRIANS')
      Brand Affinity → Title Case ('Pedestrians', 'All', ...)

    Without normalisation, a single Power BI slicer on Movement/Visitation
    Modality cannot filter all three fact tables simultaneously because the
    string values do not match across tables — the slicer would silently
    return empty for two of the three datasets.

    Title Case is chosen because:
      • Brand Affinity already uses it (minimal change to that pipeline).
      • str.title() handles underscored compound words correctly
        ('CAR_CITY' → 'Car_City', 'NON_PEDESTRIANS' → 'Non_Pedestrians').
      • Reads cleanly in chart labels and slicer UI.

    Idempotent: re-applying to already-Title-Cased values is a no-op.
    Uses .cat.rename_categories() so the categorical dtype is preserved
    (no string array reallocation).
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


def add_grand_total_flag(df):
    """
    Add the IS_GRAND_TOTAL int8 column.

    Rationale (full evidence in the module docstring): the (All, All) row is
    the only source of a true deduplicated unique-user count, because
    Locomizer's modality classifications overlap within an hour (a panellist
    can be counted as both PEDESTRIAN and CAR_CITY in the same hour, and as
    both WORKER and TRANSIENT). Summing the segment rows overcounts unique
    users by 40-50% on extrapolated metrics. The flag exposes this row
    explicitly so Power BI measures can pick the right slice with a single
    boolean filter instead of a compound (movement = 'All' AND visitation =
    'All') condition.

    Power BI usage:
        Unique-user measures        → filter IS_GRAND_TOTAL = 1
        Segment-breakdown measures  → filter IS_GRAND_TOTAL = 0
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
    """
    Export a single DataFrame using 'stem' as the base file name.
    fmt: "parquet" or "csv"
    Returns the output path.
    """
    ext  = ".parquet" if fmt == "parquet" else ".csv"
    path = os.path.join(OUTPUT_DIR, f"{stem}{ext}")


    if fmt == "parquet":
        # pyarrow preserves dtypes and date columns exactly as-is.
        # Power BI reads the DATE column as a clean Date (no time).
        df.to_parquet(path, index=False, engine="pyarrow")
    else:
        # utf-8-sig BOM ensures the CSV opens correctly in Excel on Windows
        df.to_csv(path, index=False, encoding="utf-8-sig")

    return path



def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 — Discover input files
# ---------------------------------------------------------------------------
# Scan INPUT_DIR for CSVs whose name contains 'footfall' (case-insensitive).
# Sorted alphabetically so monthly files process in chronological order.

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
        df = pd.read_csv(filepath, dtype=DTYPE_MAP, usecols=EXPECTED_COLUMNS)
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

    # ── 2d: Normalise modality casing (UPPERCASE → Title Case) ────────────────
    # Required BEFORE the IS_GRAND_TOTAL flag is computed below, because the
    # flag matches on Title Case 'All'. Also required for cross-dataset
    # alignment in Power BI (see helper docstring).
    df = standardize_modality_casing(df, MODALITY_COLS)
    print(f"  [CASE]   MOVEMENT_MODALITY  : {sorted(df['MOVEMENT_MODALITY'].unique().tolist())}")
    print(f"           VISITATION_MODALITY: {sorted(df['VISITATION_MODALITY'].unique().tolist())}")

    # ── 2e: Add IS_GRAND_TOTAL flag (v3.0) ────────────────────────────────────
    # Replaces the previous "remove (All, All) row" rule. The row is now KEPT
    # and flagged so Power BI measures can select the right slice explicitly.
    df = add_grand_total_flag(df)
    n_grand = int(df["IS_GRAND_TOTAL"].sum())
    print(f"  [FLAG]   IS_GRAND_TOTAL added — {n_grand:,} rows flagged "
          f"({n_grand/len(df)*100:.1f}% of file).")

    # ── 2f: Remove HOUR=25 sentinel rows ──────────────────────────────────────
    # The only filter that survives in v3.0. (All, All) rows are no longer
    # removed — they are the true unique-user count and are kept under the
    # IS_GRAND_TOTAL=1 flag.
    rows_before = len(df)
    df = df[df["HOUR"] != HOUR_TOTAL].reset_index(drop=True)
    rows_removed = rows_before - len(df)
    pct_removed  = rows_removed / rows_before * 100
    print(f"  [FILTER] Removed {rows_removed:,} HOUR=25 rows ({pct_removed:.1f}%) "
          f"→ {len(df):,} rows remaining")

    # ── 2g: Column reordering ──────────────────────────────────────────────────
    df = apply_column_order(df, "OUTPUT")

    # ── 2h: Export single file ─────────────────────────────────────────────────
    try:
        path    = export_file(df, stem, OUTPUT_FORMAT)
        size_kb = file_info(path)[0]
        elapsed = time.time() - t_start

        print(f"  [EXPORT] → {os.path.basename(path):<55} ({size_kb:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":       filename,
            "status":     "OK",
            "rows_raw":   rows_raw,
            "rows_out":   len(df),
            "removed":    rows_removed,
            "grand_rows": n_grand,
            "date_min":   str(df["DATE"].min()),
            "date_max":   str(df["DATE"].max()),
            "screens":    df["CODE"].nunique(),
            "size_kb":    round(size_kb, 1),
            "elapsed_s":  round(elapsed, 1),
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
print(f"\n  {'FILE':<46} {'STATUS':<8}  {'RAW':>8}  {'OUTPUT':>8}  {'H=25 REM':>9}  {'GRAND':>7}  {'DATE RANGE':<23}  {'SCRNS':>5}  {'TIME':>5}")
print(f"  {'-'*46} {'-'*8}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*7}  {'-'*23}  {'-'*5}  {'-'*5}")

total_raw  = 0
total_out  = 0
ok_count   = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count   += 1
        total_raw  += s["rows_raw"]
        total_out  += s["rows_out"]
        date_range  = f"{s['date_min']} → {s['date_max']}"
        print(f"  {s['file']:<46} {'✅ OK':<8}  {s['rows_raw']:>8,}  "
              f"{s['rows_out']:>8,}  {s['removed']:>9,}  {s['grand_rows']:>7,}  "
              f"{date_range:<23}  {s['screens']:>5,}  {s['elapsed_s']:>4.1f}s")
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<46} ❌ {s['status']:<8}  {err}")

print(f"  {'─'*130}")
print(f"  {'TOTAL':<46} {'':>8}  {total_raw:>8,}  {total_out:>8,}")
print(f"\n  Files OK      : {ok_count} / {len(footfall_files)}")
print(f"  Output folder : {OUTPUT_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"  Script version: {__version__}")
print(f"{'='*56}")
print("Process finished.")