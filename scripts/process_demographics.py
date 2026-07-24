"""
process_demographics.py
=======================
Reads monthly Demographics CSV exports from Locomizer and produces, for EACH
input file, TWO clean output files:

  <original_name>_clean.<ext>
       All rows with demographic reach values, fully cleaned and typed (WIDE
       format -- one column per age*gender slot).
       -> granular hourly data per screen and movement modality, ready for
         Power BI demographic charts (age/gender, social grade, consumer segments).

  <original_name>_age_long.<ext>
       Same data restricted to the age/gender breakdown, reshaped into LONG
       format (one row per CODE x YEAR_MONTH x HOUR x MODALITY x AGE_BRACKET
       x GENDER). Granular 1-year and 5-year age columns are aggregated into
       7 marketing-friendly buckets.
       -> ready for Power BI Matrix visuals with AGE_BRACKET on the column
         axis. See docs/powerbi_demographics_heatmap_setup.md.

  Example:
    IN  -> 12_Dec2024_Micromedia_Demographics.csv
    OUT -> 12_Dec2024_Micromedia_Demographics_clean.parquet
           12_Dec2024_Micromedia_Demographics_age_long.parquet

Transformations applied to every file (wide cleaning, unchanged from v1.5.0):
  * CODE extracted from DISPLAY NAME (first 5 characters = Micromedia site ID).
    DISPLAY NAME column is then dropped -- the site list is the single source
    of truth for name, address, and coordinates.
  * MOVEMENT_MODALITY values normalised to Title Case ('PEDESTRIANS' ->
    'Pedestrians', 'NON_PEDESTRIANS' -> 'Non_Pedestrians').
  * LATITUDE / LONGITUDE dropped -- sourced from the master site list.
  * Zero-data rows removed -- placeholder rows where all reach values are 0.
  * YEAR_MONTH period column built from MONTH + YEAR -- stored as "YYYY-MM"
    string for clean display in Power BI slicers. MONTH and YEAR dropped.
  * Explicit column dtypes on load -- avoids pandas type inference.
  * Low-cardinality string columns stored as 'category'.
  * Redundant catchment RADIUS collapsed (NEW in v1.7.0) -- Locomizer ships a
    duplicate 50 m / 183 m profile for some screen/hours; the rows are identical
    across every reach column, so only one is kept. Prevents 2x over-counting.

Long-format export (NEW in v1.6.0):
  * All T1_1AGE*M_REACH and T1_1AGE*F_REACH columns unpivoted to rows.
  * Each source column mapped to one of 7 brackets via AGE_BRACKET_MAP
    (Under 18, 18-24, 25-34, 35-44, 45-54, 55-64, 65+).
  * REACH_PCT summed within each bracket (multiple source columns -> 1 row).
  * AGE_BRACKET stored as ORDERED categorical so Power BI sorts the column
    axis correctly without a separate sort-by column.
  * Output schema: CODE, YEAR_MONTH, HOUR, RADIUS, MOVEMENT_MODALITY,
                    AGE_BRACKET, GENDER, REACH_PCT, SOURCE_FILE.

Output format:
  Set OUTPUT_FORMAT = "parquet" for Power BI (recommended).
  Set OUTPUT_FORMAT = "csv"     for Excel / legacy compatibility.

Power BI tip (Parquet):
  Use "Get Data -> Folder" in Power BI and point it at OUTPUT_AGE_LONG_DIR
  for the heatmap page; point it at OUTPUT_CLEAN_DIR for analyses that need
  the full granular columns (specific years of age, social grade, consumer
  segments). Power BI auto-combines all Parquet files that share the same
  schema, so adding a new month requires zero changes to the .pbix file.

Schema notes (wide format):
  HOUR              -> 0-23 (no sentinel row 25 as in Footfall).
  MOVEMENT_MODALITY -> All | Pedestrians | Non_Pedestrians.
                      Each modality row is an INDEPENDENT 100% profile --
                      never aggregate across modalities.
  All T1_*, T9_*, T13_*, T14_* columns -> percentage values (0-100), float32.

Usage:
  python process_demographics.py
  Drop new monthly CSVs into INPUT_DIR and re-run -- no code changes needed.

Version history:
  v1.7.0  2026-07-24  FIX: collapse redundant catchment RADIUS (audience 2x bug).
                      (1) Locomizer exports each demographic profile at TWO
                          catchment radii (50 m and 183 m) for ~6.5% of
                          (CODE, YEAR_MONTH, HOUR, MODALITY) groups. Every one
                          of the 97 reach columns is byte-for-byte identical
                          across the two radii -- verified max abs diff = 0.0
                          over all 18 monthly exports (36,284 duplicated rows in
                          the wide file). The second radius therefore carries no
                          information; it only DOUBLES any sum over the table.
                      (2) Symptom this fixes: the Power BI Matrix "Who they are
                          -- hourly audience by age & gender" showed Male and
                          Female EACH reproducing ~100% of Total Population, so
                          age/gender columns summed to 2.00x Total. Root cause
                          was the duplicated radius rows, not the DAX measure.
                      (3) Added collapse_redundant_radius(): keeps ONE row per
                          (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY), retaining
                          the smallest available radius for determinism. Runs
                          after YEAR_MONTH is built, so BOTH the wide _clean and
                          the age_long exports are corrected at source. A naive
                          fixed-radius filter (RADIUS = 50) was rejected because
                          262,712 groups carry only ONE radius and it is not
                          always 50 -- that would zero-out screens carrying only
                          the 183 m profile.
                      (4) RADIUS column is KEPT (schema unchanged) -- no measure
                          references it, so only the duplicate ROWS are removed.
                      Validation: after re-run, sum of REACH_PCT per group = 100
                          (was 200 where duplicated); age breakdown reconciles to
                          Total Population (Hourly).
  v1.6.0  2026-05-21  NEW: age-long format export for Power BI Matrix.
                      (1) Added AGE_BRACKET_MAP (35 -> 7 mapping) and
                          AGE_BRACKET_ORDER constants. Brackets chosen to
                          match OOH ad-targeting conventions and the heatmap
                          page in the dashboard (Under 18, 18-24, 25-34,
                          35-44, 45-54, 55-64, 65+). Under-18 grouped because
                          minors are not addressable OOH targets. 65+ folds
                          five sparse 5-yr bands together.
                      (2) Added build_age_long_format() helper -- unpivots all
                          T1_1AGE*M_REACH / T1_1AGE*F_REACH columns, maps each
                          to a bracket, sums REACH_PCT within bracket.
                      (3) Added OUTPUT_AGE_LONG_DIR. New step 2k exports the
                          long-format Parquet alongside the wide _clean file.
                          Original wide export is unchanged for backwards
                          compatibility with existing analyses.
                      (4) AGE_BRACKET stored as ordered Categorical so Power
                          BI sorts the column axis correctly without needing
                          a 'Sort by column' configuration.
                      (5) Global summary updated to report long-format row
                          count and file size per input file.
                      Validation: schema-drift guard raises ValueError if
                      Locomizer adds an age column the map does not cover.
  v1.5.0  2026-05-14  Power BI cross-dataset alignment:
                      (1) MM_ID renamed to CODE so all three fact tables
                          share the same join-key name.
                      (2) MOVEMENT_MODALITY values normalised to Title Case.
                      (3) Internal constants renamed for clarity.
  v1.4.0  2025-05-13  Zero-row filter and MM_ID validation.
  v1.3.0  2025-05-13  Drop all 35 _T_ age-total columns (verified redundant).
  v1.2.0  2025-05-13  Drop T1_1AGETM_REACH and T1_1AGETF_REACH (redundant).
  v1.1.0  2025-05-13  Drop YEAR and MONTH after YEAR_MONTH is built.
  v1.0.0  2025-05-13  Initial release.
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

__version__ = "1.7.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Folders -------------------------------------------------------------------
INPUT_DIR           = os.path.join(BASE_DIR, "..", "data", "raw", "demographics")
OUTPUT_DIR          = os.path.join(BASE_DIR, "..", "data", "processed", "demographics")
OUTPUT_CLEAN_DIR    = os.path.join(OUTPUT_DIR, "clean")
OUTPUT_AGE_LONG_DIR = os.path.join(OUTPUT_DIR, "age_long")
os.makedirs(OUTPUT_CLEAN_DIR,    exist_ok=True)
os.makedirs(OUTPUT_AGE_LONG_DIR, exist_ok=True)

# -- Output format -------------------------------------------------------------
# "parquet" -> recommended for Power BI (smaller, faster, type-safe)
# "csv"     -> Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# -- Columns to drop before export ---------------------------------------------
# LATITUDE / LONGITUDE are redundant -- the master site list (joined on CODE)
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
#   T1_1AGE{band}T_REACH = _M_ + _F_ for every age band.
#
# Removing all 37 avoids double-counting in Power BI and reduces file width
# by 37 columns. Any total can be recreated as a DAX measure.
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

# -- CODE extraction -----------------------------------------------------------
# Locomizer formats DISPLAY NAME as "<5-digit-ID> - <Screen Name>".
# We extract the first 5 characters as CODE (the Micromedia site identifier).
CODE_LENGTH = 5

# -- CODE validation pattern ---------------------------------------------------
# Valid CODEs are exactly 5 numeric digits (e.g. "50001").
CODE_PATTERN = r"^\d{5}$"

# -- Zero-row filter -----------------------------------------------------------
# Locomizer placeholder rows (all reach values = 0) -- panel was too small.
# Detection: sum of all T1_*M_REACH columns < threshold -> row is empty.
ZERO_ROW_THRESHOLD = 0.01

# -- Explicit dtype overrides for non-demographic columns ----------------------
DTYPE_MAP_BASE = {
    "DISPLAY NAME":      str,
    "LATITUDE":          "float32",
    "LONGITUDE":         "float32",
    "RADIUS":            "int16",
    "MONTH":             "int8",
    "HOUR":              "int8",
    "YEAR":              "int16",
    "MOVEMENT_MODALITY": "category",
}

REACH_DTYPE = "float32"

EXPECTED_BASE_COLUMNS = list(DTYPE_MAP_BASE.keys())

MODALITY_COLS = ["MOVEMENT_MODALITY"]


# -- Age-bracket mapping for long-format export (NEW in v1.6.0) ----------------
# Maps each granular age-prefix in the source CSV (the column name minus its
# 'M_REACH' / 'F_REACH' suffix) to one of 7 marketing-friendly brackets used
# on the Power BI heatmap's column axis.
#
# Why these specific brackets:
#   * Match the standard OOH/Out-of-Home media planning convention.
#   * Under 18 grouped -- minors are NOT addressable for OOH ad targeting,
#     so subdividing ages 0-17 adds no analytical value but multiplies the
#     row count of the long file by 7x.
#   * 65+ folds five 5-yr bands together -- panel data is sparse beyond 65,
#     and most OOH campaigns treat 65+ as a single segment.
#
# Schema-drift guard: if Locomizer ever ships an age column with a prefix
# not in this map, build_age_long_format() raises ValueError. Adding the
# new prefix here is then the only required change.
AGE_BRACKET_MAP = {
    # Under 18 -- ages 0 through 17 (individual year columns)
    "T1_1AGE0":  "Under 18", "T1_1AGE1":  "Under 18", "T1_1AGE2":  "Under 18",
    "T1_1AGE3":  "Under 18", "T1_1AGE4":  "Under 18", "T1_1AGE5":  "Under 18",
    "T1_1AGE6":  "Under 18", "T1_1AGE7":  "Under 18", "T1_1AGE8":  "Under 18",
    "T1_1AGE9":  "Under 18", "T1_1AGE10": "Under 18", "T1_1AGE11": "Under 18",
    "T1_1AGE12": "Under 18", "T1_1AGE13": "Under 18", "T1_1AGE14": "Under 18",
    "T1_1AGE15": "Under 18", "T1_1AGE16": "Under 18", "T1_1AGE17": "Under 18",
    # 18-24 -- ages 18, 19 (individual years) + 5-yr band 20-24
    "T1_1AGE18": "18-24", "T1_1AGE19": "18-24", "T1_1AGE20_24": "18-24",
    # 25-34 -- two 5-yr bands
    "T1_1AGE25_29": "25-34", "T1_1AGE30_34": "25-34",
    # 35-44 -- two 5-yr bands
    "T1_1AGE35_39": "35-44", "T1_1AGE40_44": "35-44",
    # 45-54 -- two 5-yr bands
    "T1_1AGE45_49": "45-54", "T1_1AGE50_54": "45-54",
    # 55-64 -- two 5-yr bands
    "T1_1AGE55_59": "55-64", "T1_1AGE60_64": "55-64",
    # 65+ -- five 5-yr bands collapsed (sparse data beyond 65)
    "T1_1AGE65_69": "65+", "T1_1AGE70_74": "65+", "T1_1AGE75_79": "65+",
    "T1_1AGE80_84": "65+", "T1_1AGEGE_85": "65+",
}

# Bracket display order for Power BI Matrix column axis. Stored as ordered
# Categorical in the output so Power BI sorts the column axis automatically.
AGE_BRACKET_ORDER = [
    "Under 18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+",
]


# %% ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_full_dtype_map(filepath):
    """
    Read only the header row (nrows=0) to discover all column names, then
    merge DTYPE_MAP_BASE with float32 for every demographic reach column.
    """
    header = pd.read_csv(filepath, nrows=0)
    dtype_map = dict(DTYPE_MAP_BASE)
    for col in header.columns:
        if col not in dtype_map:
            dtype_map[col] = REACH_DTYPE
    return dtype_map


def validate_schema(df, filename):
    """Check that all expected non-demographic base columns are present."""
    actual   = set(df.columns)
    expected = set(EXPECTED_BASE_COLUMNS)
    missing  = expected - actual
    extra    = actual - expected - {"SOURCE_FILE"}

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


def extract_code(df):
    """Extract the first CODE_LENGTH characters from DISPLAY NAME as CODE."""
    df["CODE"] = df["DISPLAY NAME"].str[:CODE_LENGTH].str.strip()
    df.drop(columns=["DISPLAY NAME"], inplace=True)
    return df


def standardize_modality_casing(df, columns):
    """Normalise modality column values to Title Case for cross-dataset consistency."""
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


def build_year_month_column(df):
    """Build a YEAR_MONTH string column (format "YYYY-MM") from MONTH and YEAR."""
    df["YEAR_MONTH"] = (
        df["YEAR"].astype(str)
        + "-"
        + df["MONTH"].astype(str).str.zfill(2)
    )
    df.drop(columns=["YEAR", "MONTH"], inplace=True)
    return df


def collapse_redundant_radius(df):
    """
    Collapse Locomizer's duplicate catchment RADIUS (NEW in v1.7.0).

    Locomizer exports each demographic profile at TWO catchment radii (50 m and
    183 m) for a subset of screen/hours. Every reach column is byte-for-byte
    identical across the two radii (verified: max abs diff = 0.0 across all 97
    reach columns and all 18 monthly exports), so the second radius carries no
    information -- it only doubles any sum over the table and is what made the
    age/gender Matrix report 2.00x Total Population.

    We keep ONE row per (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY), retaining
    the smallest available radius for determinism (so groups with both radii
    keep 50 m; groups carrying only 183 m keep 183 m -- nothing is dropped).
    RADIUS is not used by any dashboard measure, so the column is kept as-is and
    only the duplicate rows are removed.

    Must run AFTER build_year_month_column so YEAR_MONTH exists for the key.
    """
    key = ["CODE", "YEAR_MONTH", "HOUR", "MOVEMENT_MODALITY"]
    missing = [c for c in key + ["RADIUS"] if c not in df.columns]
    if missing:
        raise ValueError(
            f"collapse_redundant_radius needs columns {missing}. "
            f"Run it after CODE extraction and build_year_month_column."
        )

    before   = len(df)
    dup_keys = int((df.groupby(key, observed=True)["RADIUS"].transform("nunique") > 1).sum())

    df = (
        df.sort_values("RADIUS", kind="stable")
          .drop_duplicates(subset=key, keep="first")
          .reset_index(drop=True)
    )

    removed = before - len(df)
    # Post-condition: every key must now be unique.
    assert not df.duplicated(subset=key).any(), \
        "collapse_redundant_radius: duplicate keys remain after collapse."

    print(f"  [RADIUS] Collapsed redundant catchment radius: "
          f"{removed:,} duplicate row(s) removed "
          f"({dup_keys:,} rows were in 2-radius groups)  ->  {len(df):,} rows remain.")
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
    """Return df with columns in a logical order."""
    priority = [
        "CODE",
        "YEAR_MONTH",
        "HOUR",
        "RADIUS",
        "MOVEMENT_MODALITY",
    ]

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

    already = set(ordered)
    extras  = [c for c in df.columns if c not in already]
    if extras:
        print(f"  [INFO] {len(extras)} extra column(s) appended at end: {extras}")
    ordered += extras

    return df[ordered]


def build_age_long_format(df_wide):
    """
    Unpivot the wide age/gender reach columns into long format ready for Power
    BI Matrix visuals.

    Power BI's Matrix needs ONE column on its column axis -- it cannot put 14
    separate columns (7 brackets x 2 genders) as side-by-side axis entries
    when each is a different field. The wide format works for KPIs and DAX
    measures but not for a visual that wants `AGE_BRACKET` on the column axis
    and `GENDER` as a filter or secondary group.

    What this function does:
      1. Melts all T1_1AGE*M_REACH and T1_1AGE*F_REACH columns to long format.
      2. Maps each granular age column to one of 7 buckets via AGE_BRACKET_MAP.
      3. Sums REACH_PCT within each bucket (multiple source columns -> one row).
         Example: REACH for "Under 18" is the sum of ages 0..17 for that
         (CODE, HOUR, YEAR_MONTH, MODALITY, GENDER).
      4. Stores AGE_BRACKET as ORDERED Categorical so Power BI sorts the
         column axis correctly without a sort-by-column setup.

    Output schema (one row per CODE x YEAR_MONTH x HOUR x MODALITY x BRACKET x GENDER):
      CODE                 str
      YEAR_MONTH           str
      HOUR                 int8 (0-23)
      RADIUS               int16
      MOVEMENT_MODALITY    category (All / Pedestrians / Non_Pedestrians)
      AGE_BRACKET          ordered category (Under 18, 18-24, ..., 65+)
      GENDER               category (M / F)
      REACH_PCT            float32 (0-100)
      SOURCE_FILE          str

    Note: This is a SEPARATE export. The wide _clean.parquet still ships
    unchanged for backwards compatibility and for analyses that need granular
    columns (specific-year-of-age targeting, social grade, consumer segments).

    Raises ValueError if any age column prefix is not in AGE_BRACKET_MAP --
    signals that Locomizer added a new age bracket to the schema.
    """
    id_cols = ["CODE", "YEAR_MONTH", "HOUR", "RADIUS",
               "MOVEMENT_MODALITY", "SOURCE_FILE"]

    # Sanity-check id columns are all present
    missing_ids = [c for c in id_cols if c not in df_wide.columns]
    if missing_ids:
        raise ValueError(
            f"Long-format export requires these columns in the wide DataFrame: "
            f"{missing_ids}. Did the wide cleaning steps run?"
        )

    # Identify M and F age columns (the _T_ columns were already dropped earlier)
    m_cols = [c for c in df_wide.columns
              if c.startswith("T1_1AGE") and c.endswith("M_REACH")]
    f_cols = [c for c in df_wide.columns
              if c.startswith("T1_1AGE") and c.endswith("F_REACH")]

    if not m_cols or not f_cols:
        raise ValueError(
            "No T1_1AGE*M_REACH / T1_1AGE*F_REACH columns found. The long-format "
            "export requires the wide cleaning steps to have run first."
        )

    def _melt_one_gender(cols, gender):
        sub = df_wide[id_cols + cols].melt(
            id_vars=id_cols,
            var_name="AGE_COL",
            value_name="REACH_PCT",
        )
        suffix = f"{gender}_REACH"
        sub["AGE_PREFIX"] = sub["AGE_COL"].str.removesuffix(suffix)
        sub["GENDER"] = gender
        sub.drop(columns=["AGE_COL"], inplace=True)
        return sub

    df_m = _melt_one_gender(m_cols, "M")
    df_f = _melt_one_gender(f_cols, "F")
    df_long = pd.concat([df_m, df_f], ignore_index=True)

    # Map granular column prefixes to 7-bucket brackets
    df_long["AGE_BRACKET"] = df_long["AGE_PREFIX"].map(AGE_BRACKET_MAP)

    # Schema-drift guard: any column not in the map is an error, not a warning
    unmapped = df_long[df_long["AGE_BRACKET"].isna()]["AGE_PREFIX"].unique().tolist()
    if unmapped:
        raise ValueError(
            f"{len(unmapped)} age column prefix(es) not in AGE_BRACKET_MAP -- "
            f"Locomizer schema may have changed. Add these prefixes to the map: "
            f"{sorted(unmapped)}"
        )

    df_long.drop(columns=["AGE_PREFIX"], inplace=True)

    # Sum percentages within each bracket (e.g. ages 0..17 -> "Under 18")
    df_long = df_long.groupby(
        id_cols + ["AGE_BRACKET", "GENDER"],
        as_index=False,
        observed=True,
    )["REACH_PCT"].sum()

    # Optimise dtypes for Parquet / Power BI
    df_long["AGE_BRACKET"] = pd.Categorical(
        df_long["AGE_BRACKET"],
        categories=AGE_BRACKET_ORDER,
        ordered=True,
    )
    df_long["GENDER"]    = df_long["GENDER"].astype("category")
    df_long["REACH_PCT"] = df_long["REACH_PCT"].astype("float32")

    # Final column order
    df_long = df_long[[
        "CODE", "YEAR_MONTH", "HOUR", "RADIUS",
        "MOVEMENT_MODALITY", "AGE_BRACKET", "GENDER",
        "REACH_PCT", "SOURCE_FILE",
    ]]

    return df_long


def export_file(df_clean, stem, fmt):
    """Write the cleaned WIDE DataFrame to OUTPUT_CLEAN_DIR."""
    ext        = "parquet" if fmt == "parquet" else "csv"
    name_clean = f"{stem}_clean.{ext}"
    path_clean = os.path.join(OUTPUT_CLEAN_DIR, name_clean)

    if fmt == "parquet":
        df_clean.to_parquet(path_clean, index=False)
    else:
        df_clean.to_csv(path_clean, index=False, encoding="utf-8-sig")

    return path_clean


def export_age_long_file(df_long, stem, fmt):
    """Write the LONG-format age DataFrame to OUTPUT_AGE_LONG_DIR."""
    ext       = "parquet" if fmt == "parquet" else "csv"
    name_long = f"{stem}_age_long.{ext}"
    path_long = os.path.join(OUTPUT_AGE_LONG_DIR, name_long)

    if fmt == "parquet":
        df_long.to_parquet(path_long, index=False)
    else:
        df_long.to_csv(path_long, index=False, encoding="utf-8-sig")

    return path_long


def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 -- Discover input files
# ---------------------------------------------------------------------------

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

global_summary = []

for filepath in demographics_files:
    filename = os.path.basename(filepath)
    stem     = os.path.splitext(filename)[0]

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # -- 2a: Load with explicit dtypes -----------------------------------------
    try:
        dtype_map = _build_full_dtype_map(filepath)
        df = pd.read_csv(filepath, dtype=dtype_map)
        df = df.copy()  # defragment after wide load (142 columns)
    except Exception as e:
        print(f"  ERROR LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename
    rows_raw = len(df)
    print(f"  [LOAD]   {rows_raw:>10,} rows x {len(df.columns)} columns")

    # -- 2b: Schema validation -------------------------------------------------
    print(f"  [SCHEMA]")
    validate_schema(df, filename)

    key_cols  = ["DISPLAY NAME", "HOUR", "MONTH", "YEAR", "MOVEMENT_MODALITY"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}
    if any(v > 0 for v in null_hits.values()):
        print(f"  WARNING  Nulls in key columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key columns. OK")

    # -- 2c: Extract CODE from DISPLAY NAME ------------------------------------
    invalid_display_names = (
        df["DISPLAY NAME"][
            ~df["DISPLAY NAME"].str[:CODE_LENGTH].str.strip().str.match(CODE_PATTERN)
        ].unique().tolist()
    )
    sample_display = df["DISPLAY NAME"].iloc[0] if len(df) > 0 else ""
    df = extract_code(df)
    sample_code = df["CODE"].iloc[0] if len(df) > 0 else ""
    print(f"  [CODE]   Extracted from DISPLAY NAME "
          f"('{sample_display}' -> '{sample_code}'). "
          f"Unique screens: {df['CODE'].nunique()}")

    if invalid_display_names:
        invalid_count = df[~df["CODE"].str.match(CODE_PATTERN)]["CODE"].nunique()
        print(f"  WARNING  {invalid_count} screen(s) with INVALID CODE (will NOT join to site list):")
        for name in invalid_display_names:
            extracted = name[:CODE_LENGTH].strip()
            print(f"       DISPLAY NAME: '{name}'  ->  CODE: '{extracted}'")
        print(f"       Action required: map these screens manually to their 5-digit site codes.")
    else:
        print(f"  [CODE]   All CODEs are valid 5-digit codes. OK")

    # -- 2d: Normalise modality casing -----------------------------------------
    df = standardize_modality_casing(df, MODALITY_COLS)
    print(f"  [CASE]   MOVEMENT_MODALITY: {sorted(df['MOVEMENT_MODALITY'].unique().tolist())}")

    # -- 2e: Drop LATITUDE / LONGITUDE -----------------------------------------
    df = drop_columns(df, COLS_DROP)

    # -- 2f: Filter out zero-data rows -----------------------------------------
    m_cols    = [c for c in df.columns if c.startswith("T1_1AGE") and c.endswith("M_REACH")]
    zero_mask = df[m_cols].sum(axis=1) < ZERO_ROW_THRESHOLD
    rows_zero = int(zero_mask.sum())
    df        = df[~zero_mask].reset_index(drop=True)
    print(f"  [FILTER] {rows_zero:,} zero-data rows removed "
          f"({rows_zero / rows_raw * 100:.1f}% of raw)  ->  {len(df):,} rows remain.")

    # -- 2g: Drop all redundant _T_ summary columns (37 total) -----------------
    df = drop_columns(df, COLS_REDUNDANT)

    # -- 2h: Build YEAR_MONTH period column ------------------------------------
    df = build_year_month_column(df)
    sample_ym = df["YEAR_MONTH"].iloc[0] if len(df) > 0 else ""
    unique_ym  = sorted(df["YEAR_MONTH"].unique().tolist())
    print(f"  [PERIOD] YEAR_MONTH column built. "
          f"Periods in file: {unique_ym}  |  Sample: '{sample_ym}'")

    # -- 2h+: Collapse redundant catchment RADIUS (NEW in v1.7.0) --------------
    # Removes Locomizer's duplicate 50 m / 183 m profile rows before export so
    # BOTH the wide _clean and the age_long files are de-duplicated at source.
    # This is the fix for the age/gender Matrix reporting 2x Total Population.
    df = collapse_redundant_radius(df)

    # -- 2i: Column reordering -------------------------------------------------
    df = build_column_order(df)
    print(f"  [ORDER]  Columns reordered. Final width: {len(df.columns)} columns.")

    # -- 2j: Export WIDE _clean file -------------------------------------------
    path_clean = None
    size_kb_clean = 0
    try:
        path_clean = export_file(df, stem, OUTPUT_FORMAT)
        size_kb_clean, _ = file_info(path_clean)
        print(f"  [EXPORT] {os.path.basename(path_clean):<65} ({size_kb_clean:>7,.1f} KB)")
    except Exception as e:
        print(f"  ERROR EXPORT (wide) FAILED: {e}")
        global_summary.append({"file": filename, "status": "EXPORT ERROR", "error": str(e)})
        print()
        continue

    # -- 2k: Build and export LONG-format age file (NEW in v1.6.0) -------------
    # Generates the second output file used by Power BI Matrix visuals.
    # See docs/powerbi_demographics_heatmap_setup.md for the consuming pages.
    rows_long      = 0
    size_kb_long   = 0
    path_long      = None
    try:
        df_age_long = build_age_long_format(df)
        path_long   = export_age_long_file(df_age_long, stem, OUTPUT_FORMAT)
        size_kb_long, _ = file_info(path_long)
        rows_long       = len(df_age_long)

        # Sanity numbers: per (CODE, HOUR, YEAR_MONTH, MODALITY) we expect
        # 7 brackets * 2 genders = 14 rows. Useful as a one-glance check.
        modalities = df_age_long["MOVEMENT_MODALITY"].nunique()
        screens    = df_age_long["CODE"].nunique()
        hours      = df_age_long["HOUR"].nunique()
        periods    = df_age_long["YEAR_MONTH"].nunique()
        expected   = screens * hours * periods * modalities * 7 * 2
        match_flag = "OK" if rows_long <= expected else "WARN"

        print(f"  [LONG]   {os.path.basename(path_long):<65} ({size_kb_long:>7,.1f} KB)")
        print(f"           {rows_long:>10,} rows  "
              f"({screens} screens x {hours} hours x {periods} periods x "
              f"{modalities} modalities x 7 brackets x 2 genders, "
              f"upper bound {expected:,}) -- {match_flag}")
    except Exception as e:
        print(f"  ERROR EXPORT (long) FAILED: {e}")
        global_summary.append({
            "file": filename, "status": "LONG EXPORT ERROR", "error": str(e),
        })
        print()
        continue

    elapsed = time.time() - t_start
    print(f"  [TIME]   {elapsed:.1f}s")

    global_summary.append({
        "file":         filename,
        "status":       "OK",
        "rows_raw":     rows_raw,
        "rows_zero":    rows_zero,
        "rows_clean":   len(df),
        "rows_long":    rows_long,
        "screens":      df["CODE"].nunique(),
        "invalid_ids":  len(invalid_display_names),
        "periods":      ", ".join(unique_ym),
        "size_kb":      round(size_kb_clean, 1),
        "size_kb_long": round(size_kb_long, 1),
        "elapsed_s":    round(elapsed, 1),
    })

    print()


# %% ---------------------------------------------------------------------------
# Step 3 -- Global summary
# ---------------------------------------------------------------------------

print(f"{'='*20} GLOBAL SUMMARY {'='*20}")
print(f"\n  {'FILE':<50} {'STATUS':<8}  {'RAW':>7}  {'ZERO':>6}  {'CLEAN':>7}  "
      f"{'LONG':>8}  {'INV_ID':>6}  {'SCRNS':>5}  {'KB-W':>6}  {'KB-L':>6}  {'TIME':>5}")
print(f"  {'-'*50} {'-'*8}  {'-'*7}  {'-'*6}  {'-'*7}  "
      f"{'-'*8}  {'-'*6}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*5}")

total_raw   = 0
total_zero  = 0
total_clean = 0
total_long  = 0
ok_count    = 0

for s in global_summary:
    if s["status"] == "OK":
        ok_count    += 1
        total_raw   += s["rows_raw"]
        total_zero  += s["rows_zero"]
        total_clean += s["rows_clean"]
        total_long  += s["rows_long"]
        inv_flag     = f"W{s['invalid_ids']}" if s["invalid_ids"] > 0 else "OK"
        print(
            f"  {s['file']:<50} {'OK':<8}  {s['rows_raw']:>7,}  "
            f"{s['rows_zero']:>6,}  {s['rows_clean']:>7,}  {s['rows_long']:>8,}  "
            f"{inv_flag:>6}  {s['screens']:>5,}  "
            f"{s['size_kb']:>6,.1f}  {s['size_kb_long']:>6,.1f}  {s['elapsed_s']:>4.1f}s"
        )
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<50} ERROR {s['status']:<8}  {err}")

print(f"  {'-'*125}")
print(f"  {'TOTAL':<50} {'':>8}  {total_raw:>7,}  {total_zero:>6,}  "
      f"{total_clean:>7,}  {total_long:>8,}")
print(f"\n  Files OK         : {ok_count} / {len(demographics_files)}")
print(f"  Clean folder     : {OUTPUT_CLEAN_DIR}")
print(f"  Age-long folder  : {OUTPUT_AGE_LONG_DIR}")
print(f"  Output format    : {OUTPUT_FORMAT.upper()}")
print(f"{'='*56}")
print("Process finished.")
# %%