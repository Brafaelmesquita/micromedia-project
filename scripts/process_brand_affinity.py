"""
process_brand_affinity.py
=========================
Reads monthly Brand Affinity CSV exports from Locomizer and produces, for EACH
input file, one clean output file:

  <original_name>_clean.<ext>
       Granular hourly affinity data per screen, modality, and POI category,
       ready for Power BI affinity charts (over-/under-indexing analysis,
       category preference profiling, audience targeting selection).

  Example:
    IN  -> 02_Feb2025_Micromedia_BrandAffinity.csv
    OUT -> 02_Feb2025_Micromedia_BrandAffinity_clean.parquet

Transformations applied to every file:
  * DISPLAY NAME dropped -- CODE is already a clean 5-digit integer ID in
    Brand Affinity exports (unlike Demographics, no extraction needed).
    Screen names/addresses live in the master site list (joined on CODE).
  * CODE converted from int32 -> str BEFORE export. The int32 type is used
    during processing for the 5-digit range sanity check; the export uses
    str so that all three fact tables (Footfall, Demographics, Brand
    Affinity) share the same join-key dtype in the Power BI data model.
  * MOVEMENT_MODALITY and VISITATION_MODALITY normalised to Title Case.
    Brand Affinity already exports in Title Case, so this step is a no-op
    in practice; it is included for defensive consistency with the
    Footfall and Demographics pipelines (which DO need the conversion)
    and so a future Locomizer schema change would not break the dashboard
    silently.
  * TIME_INTERVAL_DESCRIPTION dropped -- it is a perfect 1-to-1 derivation
    of TIME_INTERVAL (1 -> "00.00-00.59", 2 -> "01.00-01.59", ..., 24 ->
    "23.00-23.59"). Power BI can rebuild the label from HOUR if needed.
  * BRAND_AFFINITY_PROFILING_TIME_INTERVAL dropped -- constant value '08_22'
    on every row of every file (the profiling window Locomizer uses to learn
    user affinities). Provides no analytical signal once it's known.
  * DAY_START / DAY_END dropped -- constant per file (always the first and
    last day of the month). YEAR_MONTH carries the period info; the day
    boundaries are derivable from the month.
  * TIME_INTERVAL (1-24) converted to HOUR (0-23) -- aligns with Footfall
    and Demographics where HOUR uses the 0-23 convention. Cross-dataset
    slicers in Power BI then share a single HOUR axis.
  * YEAR_MONTH period column built from MONTH + YEAR (no DAY in Brand
    Affinity exports -- each file is one full calendar month). Stored as
    "YYYY-MM" string for clean display in Power BI slicers. MONTH and YEAR
    integer columns are dropped after YEAR_MONTH is built -- the period
    information is fully captured in YEAR_MONTH and duplication is avoided.
  * Zero-data rows removed -- rows where BRAND_AFFINITY_INDEX,
    BRAND_AFFINITY_DWELL_TIME and PROPORTION_OF_TARGET_USERS are ALL zero
    are placeholder rows emitted by Locomizer when the panel is too small
    to produce reliable affinity scores. They carry no audience signal
    (verified: all three metrics are zero on exactly the same set of rows)
    and would distort Power BI averages and category rankings if kept.
  * Redundant catchment RADIUS collapsed (NEW in v1.4.0) -- from May 2026
    Locomizer briefly shipped both catchment radii (50 m + 183 m) per screen,
    duplicating every row. The two radii are byte-identical on all three
    metrics (verified: max abs diff = 0), so one row per
    (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY, VISITATION_MODALITY,
    BRAND_AFFINITY_CATEGORY_NAME) is kept. Single-radius months are untouched.
    See collapse_redundant_radius() and the v1.4.0 changelog entry.
  * Explicit column dtypes on load -- avoids pandas type inference, cuts
    memory usage significantly and speeds up read_csv on the 390K-row files.
  * Low-cardinality string columns stored as 'category' -- BRAND_AFFINITY_
    CATEGORY_NAME has 11 unique values repeated ~35K times each; the
    categorical dtype reduces memory ~30x on that column alone and speeds
    up groupby/filter in pandas.

Output format:
  Set OUTPUT_FORMAT = "parquet" for Power BI (recommended -- 10-20x faster
  load, 3-5x smaller files, data types preserved automatically).
  Set OUTPUT_FORMAT = "csv"     for Excel / legacy compatibility.

Power BI tip (Parquet):
  Use "Get Data -> Folder" in Power BI and point it at OUTPUT_DIR (data/processed/brand_affinity).
  Power BI auto-combines all Parquet files that share the same schema,
  so adding a new month requires zero changes to the .pbix file.

Schema notes:
  HOUR              -> 0-23 (converted from TIME_INTERVAL 1-24 on load).
  MOVEMENT_MODALITY -> All | Pedestrians | Non_Pedestrians.
  VISITATION_MODALITY -> All | Residents | Workers | Transient.
                      IMPORTANT: only 6 valid combinations exist in the data:
                      * MOVEMENT=All        with All / Residents / Workers / Transient
                      * Pedestrians         with VISITATION=All only
                      * Non_Pedestrians     with VISITATION=All only
                      -> Filter by VISITATION='All' for movement-mode analysis,
                         filter by MOVEMENT='All'  for visitation-segment analysis.
                      Unlike Footfall, the ALL+ALL row is KEPT here -- the
                      Brand Affinity INDEX is a normalized audience characteristic,
                      NOT a sum of segments. Removing it would erase the
                      "overall audience affinity" view.
  BRAND_AFFINITY_INDEX -> 0..16,000+ (national average = 100).
                      >100 = audience over-indexes for this POI category
                      <100 = audience under-indexes for this POI category
                      Values >>200 are common and represent strong affinity
                      hotspots; capping/winsorising should be done in Power BI
                      visuals, not in this preprocessing step (signal preserved).
  BRAND_AFFINITY_CATEGORY_NAME -> 11 POI categories (Airport, Bank, Drinks_Out,
                      Eating Places/Restaurants, Grocery stores, etc.).

Usage:
  python process_brand_affinity.py
  Drop new monthly CSVs into INPUT_DIR and re-run -- no code changes needed.

Version history:
  v1.5.0  2026-09-05  Output location simplified: cleaned Parquet files are now
                      written directly into data/processed/brand_affinity/ instead
                      of a nested "clean" subfolder. OUTPUT_CLEAN_DIR now equals
                      OUTPUT_DIR (variable name kept so the rest of the pipeline is
                      unchanged). Point Power BI's "Get Data -> Folder" at
                      data/processed/brand_affinity.
  v1.4.0  2026-09-04  FIX: collapse redundant catchment RADIUS (row-doubling).
                      In May 2026 Locomizer shipped BOTH catchment radii
                      (50 m + 183 m) for every screen -- 259 screens, every row
                      duplicated (820,512 rows vs ~408,672 in adjacent months);
                      before and after May each screen carries a single radius
                      (Mar/Apr/Jun/Jul 2026 and all of 2025). The two radii are
                      BYTE-IDENTICAL on all three metrics (INDEX / DWELL_TIME /
                      PROPORTION) -- normalised characteristics, so catchment
                      size does not change them -- verified on the May 2026
                      export: 410,256 (CODE,HOUR,MOVEMENT,VISITATION,CATEGORY)
                      keys, max abs diff = 0. The duplicate row therefore carries
                      no signal and only doubles row counts (and any SUM/COUNT);
                      the INDEX, being averaged, was numerically robust, but
                      shipping doubled rows is still wrong. New
                      collapse_redundant_radius() keeps ONE row per
                      (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY,
                      VISITATION_MODALITY, BRAND_AFFINITY_CATEGORY_NAME),
                      retaining the smallest available radius (lossless -- the
                      values are identical). Trigger: only >1-radius groups are
                      touched, so single-radius months pass through untouched.
                      Mirrors process_demographics.py v1.7.0; unlike
                      process_footfall.py the master is NOT consulted (footfall's
                      radii DIFFER ~4.3x and must pick the canonical one; here
                      they are identical, so either is correct). Runs after the
                      zero-row filter so IS_DEFAULT, the modality-shape report and
                      the export all reflect the de-duplicated data. RADIUS column
                      kept as-is (no dashboard measure uses it).
  v1.3.0  2026-07-26  FEATURE: canonical SITE_ID column. Micromedia is migrating
                      screen codes from the legacy MM ID scheme to NEW MM ID, and
                      Locomizer delivers monthly exports under either scheme. A new
                      SITE_ID column (from scripts/site_id_crosswalk.py, built by
                      build_master_sites.py) maps every CODE — old or new — onto
                      one canonical key, so the Power BI join no longer drops
                      whichever scheme a file used. CODE is preserved as the raw
                      as-delivered value. Codes absent from the master site list
                      are left unmapped (SITE_ID = CODE) and logged as orphans.
                      Resolution runs on the string CODE, so it sits AFTER the
                      int32 -> str conversion and BEFORE column reordering.
                      DOWNSTREAM NOTE: the Power BI relationship now joins
                      Brand_Affinity.SITE_ID -> Master_Sites.SITE_ID.
  v1.2.0  2026-05-14  Power BI cross-dataset alignment:
                      (1) CODE column converted from int32 -> str before export.
                          The int32 type is preserved during the sanity check
                          (5-digit range validation). All three fact tables
                          (Footfall, Demographics, Brand Affinity) now share
                          the same join-key dtype, simplifying the Power BI
                          relationship configuration.
                      (2) MOVEMENT_MODALITY and VISITATION_MODALITY casing
                          normalised to Title Case. Brand Affinity already
                          exports in Title Case, so the step is a no-op on
                          current data; included for defensive consistency
                          with the Footfall and Demographics pipelines (which
                          DO need the conversion) and so a future Locomizer
                          schema change cannot break the dashboard silently.
  v1.1.0  2025-05-14  Two improvements from post-delivery audit:
                      (1) IS_DEFAULT column added (int8: 1 = MOVEMENT='All' AND
                          VISITATION='All', 0 = segment view). Gives Power BI a
                          one-field filter for the correct default analysis view.
                          Without it, charts that don't filter by modality mix
                          3-6 segment rows per CODE/HOUR/CATEGORY and produce
                          INDEX averages 5-48 points off the correct value.
                      (2) Extra-column detection fixed: raw file header is now
                          read (nrows=0) before the main load so that any new
                          columns Locomizer adds to future exports are surfaced
                          in the log instead of being silently discarded by usecols.
                      (3) Zero-filter reinforced: now verifies that all three
                          metric columns are zero on exactly the same rows before
                          dropping (was relying on INDEX alone with a comment;
                          now the assertion is live in the code).
  v1.0.0  2025-05-14  Initial release -- based on process_demographics.py v1.4.0.
                      Transformations applied:
                        * DISPLAY NAME dropped (CODE is already clean)
                        * TIME_INTERVAL_DESCRIPTION dropped (derivable from HOUR)
                        * BRAND_AFFINITY_PROFILING_TIME_INTERVAL dropped (constant)
                        * DAY_START / DAY_END dropped (redundant with YEAR_MONTH)
                        * TIME_INTERVAL (1-24) -> HOUR (0-23) for cross-dataset alignment
                        * YEAR_MONTH period column built from MONTH + YEAR
                        * Zero-data rows filtered (~33% of input on Feb 2025,
                          ~37% on Mar 2025)
                        * Fully-zeroed screens flagged in log so users know which
                          screens disappear from Power BI for the period
                          (Feb 2025: 50254, 50255 / Mar 2025: 50022, 50254, 50255)
                        * Float32 + categorical dtypes for memory/storage gains
                          (64.5 MB CSV -> 2.1 MB parquet, ~30x smaller)
"""

# %% ---------------------------------------------------------------------------
# Imports & configuration
# ---------------------------------------------------------------------------

import os
import time
import glob

import pandas as pd

from site_id_crosswalk import Crosswalk

__version__ = "1.5.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Folders -------------------------------------------------------------------
INPUT_DIR        = os.path.join(BASE_DIR, "..", "data", "raw", "brand_affinity")
OUTPUT_DIR       = os.path.join(BASE_DIR, "..", "data", "processed", "brand_affinity")
OUTPUT_CLEAN_DIR = OUTPUT_DIR   # grava direto em brand_affinity/ (sem subpasta "clean")
os.makedirs(OUTPUT_CLEAN_DIR, exist_ok=True)

# Canonical SITE_ID crosswalk (built by build_master_sites.py). Loaded once.
# If the master site list is absent, SITE_ID mirrors CODE so the run still
# succeeds.
CROSSWALK, CROSSWALK_MSG = Crosswalk.load_or_none()

# -- Output format -------------------------------------------------------------
# "parquet" -> recommended for Power BI (smaller, faster, type-safe)
# "csv"     -> Excel / legacy compatibility
OUTPUT_FORMAT = "parquet"

# -- Columns to drop before export ---------------------------------------------
# Each column is removed for a specific, documented reason -- not "just in case".
# Removing them at preprocessing (rather than hiding in Power BI) means:
#   * smaller Parquet files       -> faster Power BI refresh
#   * smaller in-memory model     -> faster slicer/visual rendering
#   * no risk of user accidentally building a visual on a meaningless column
COLS_DROP = [
    # DISPLAY NAME -- the CODE column is already a clean 5-digit integer ID,
    # so the human-readable name is redundant here. The master site list is
    # the single source of truth for screen name, address, and coordinates.
    "DISPLAY NAME",

    # TIME_INTERVAL_DESCRIPTION -- perfect 1-to-1 mapping with TIME_INTERVAL
    # (verified: 1 -> "00.00-00.59" ... 24 -> "23.00-23.59"). Any visual that
    # needs the label can derive it from HOUR via FORMAT() in DAX.
    "TIME_INTERVAL_DESCRIPTION",

    # BRAND_AFFINITY_PROFILING_TIME_INTERVAL -- constant value '08_22' on every
    # row of every export (the profiling window Locomizer uses to learn the
    # user affinity profile). Provides no analytical signal once known.
    "BRAND_AFFINITY_PROFILING_TIME_INTERVAL",

    # DAY_START / DAY_END -- constant per file (always 1st and last day of
    # the month). YEAR_MONTH carries the period info; day boundaries are
    # derivable. Keeping them would duplicate the period across 3 columns.
    "DAY_START",
    "DAY_END",
]

# -- Zero-row filter -----------------------------------------------------------
# Locomizer emits placeholder rows where BRAND_AFFINITY_INDEX,
# BRAND_AFFINITY_DWELL_TIME and PROPORTION_OF_TARGET_USERS are ALL zero --
# these are screen/hour/modality/category combinations where the target panel
# was too small to compute a reliable affinity score.
# Verified on real data:
#   Feb 2025 export -> 129,384 zero rows out of 389,664 (33.2%)
#   Mar 2025 export -> 143,893 zero rows out of 389,664 (36.9%)
# The three metric columns flip to zero TOGETHER on the same rows (verified:
# all three counts match exactly), so filtering on INDEX alone is sufficient.
# A small numerical threshold (rather than == 0) protects against float jitter.
ZERO_ROW_THRESHOLD = 0.001   # BRAND_AFFINITY_INDEX below this -> row is empty

# -- TIME_INTERVAL -> HOUR conversion ------------------------------------------
# Brand Affinity uses TIME_INTERVAL 1..24 where 1 = midnight hour (00.00-00.59).
# Footfall and Demographics use HOUR 0..23 where 0 = midnight hour.
# We normalize to HOUR (0..23) for cross-dataset consistency in Power BI:
# a single HOUR slicer can then drive all three datasets simultaneously.
TIME_INTERVAL_OFFSET = 1   # HOUR = TIME_INTERVAL - 1

# -- Explicit dtype overrides for read_csv -------------------------------------
# Specifying dtypes skips pandas type-inference on load -- biggest speed-up
# for large CSVs. Rules:
#   int8     -> TIME_INTERVAL (1-24), MONTH (1-12) -- fit in -128..127
#   int16    -> RADIUS (~50-200), YEAR
#   int32    -> CODE (5-digit IDs, well below 2 billion)
#   float32  -> all metric columns (halves memory vs float64; precision is
#               more than sufficient for affinity indices and percentages)
#   category -> low-cardinality strings (3 movement types, 4 visitation types,
#               11 brand affinity categories)
DTYPE_MAP = {
    "CODE":                                   "int32",
    "DISPLAY NAME":                           str,        # dropped after load
    "RADIUS":                                 "int16",
    "TIME_INTERVAL":                          "int8",
    "TIME_INTERVAL_DESCRIPTION":              "category", # dropped after load
    "DAY_START":                              str,        # dropped after load
    "DAY_END":                                str,        # dropped after load
    "MONTH":                                  "int8",
    "YEAR":                                   "int16",
    "MOVEMENT_MODALITY":                      "category",
    "VISITATION_MODALITY":                    "category",
    "BRAND_AFFINITY_CATEGORY_NAME":           "category",
    "BRAND_AFFINITY_PROFILING_TIME_INTERVAL": "category", # dropped after load
    "BRAND_AFFINITY_DWELL_TIME":              "float32",
    "BRAND_AFFINITY_INDEX":                   "float32",
    "PROPORTION_OF_TARGET_USERS":             "float32",
}

# -- Expected columns (for schema validation) ----------------------------------
EXPECTED_COLUMNS = list(DTYPE_MAP.keys())

# -- Modality columns to normalise to Title Case ------------------------------
# Brand Affinity already exports in Title Case, so this is a no-op on current
# data. Included for defensive consistency with the Footfall and Demographics
# pipelines (which DO need the conversion -- they arrive UPPERCASE) and so
# that a future Locomizer schema change cannot silently desynchronise the
# three fact tables and break cross-table slicers in Power BI.
MODALITY_COLS = ["MOVEMENT_MODALITY", "VISITATION_MODALITY"]


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
        print(f"  OK Schema OK -- all {len(EXPECTED_COLUMNS)} expected columns present.")
    else:
        print(f"  WARNING  {len(missing)} column(s) MISSING from schema: {sorted(missing)}")

    if extra:
        print(f"  [INFO] {len(extra)} extra column(s) found (kept): {sorted(extra)}")

    return missing, extra


def standardize_modality_casing(df, columns):
    """
    Normalise modality column values to Title Case for cross-dataset
    consistency in Power BI. Locomizer's three exports use mixed casing:

      Footfall       -> UPPERCASE ('PEDESTRIANS', 'ALL', 'WORKERS', ...)
      Demographics   -> UPPERCASE ('ALL', 'PEDESTRIANS', 'NON_PEDESTRIANS')
      Brand Affinity -> Title Case ('Pedestrians', 'All', ...)

    Brand Affinity already arrives in Title Case so this function is a no-op
    on current data. It is kept here as a defensive measure: if Locomizer
    ever flips the Brand Affinity casing in a future export, the three
    fact tables would silently desynchronise and a single Power BI slicer
    would no longer filter all three simultaneously. Running this function
    unconditionally guarantees the output schema regardless of input casing.

    Title Case is chosen because:
      * Brand Affinity already uses it (no behaviour change on current data).
      * str.title() handles underscored compound words correctly
        ('NON_PEDESTRIANS' -> 'Non_Pedestrians').
      * Reads cleanly in chart labels and slicer UI.

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


def build_hour_column(df):
    """
    Convert TIME_INTERVAL (1-24) -> HOUR (0-23) for cross-dataset alignment.
    TIME_INTERVAL 1 = midnight hour 00.00-00.59 in Brand Affinity, but Footfall
    and Demographics use HOUR 0 for the same hour. We normalize here so that a
    single HOUR slicer in Power BI can drive all three datasets.

    The conversion is a simple offset subtraction; dtype stays int8.
    TIME_INTERVAL is dropped after the conversion -- HOUR fully replaces it.
    """
    df["HOUR"] = (df["TIME_INTERVAL"] - TIME_INTERVAL_OFFSET).astype("int8")
    df.drop(columns=["TIME_INTERVAL"], inplace=True)
    return df


def build_year_month_column(df):
    """
    Build a YEAR_MONTH string column (format "YYYY-MM") from the MONTH and YEAR
    integer columns. Brand Affinity exports are one calendar month per file, so
    YEAR_MONTH alone fully captures the period.

    "YYYY-MM" is chosen over a Period dtype because Power BI reads it as a plain
    text slicer without needing calendar table configuration. This matches the
    convention used in process_demographics.py for consistency across datasets.

    MONTH and YEAR are dropped after YEAR_MONTH is built -- the period
    information is fully captured in YEAR_MONTH and duplication serves no purpose.
    """
    df["YEAR_MONTH"] = (
        df["YEAR"].astype(str)
        + "-"
        + df["MONTH"].astype(str).str.zfill(2)
    )
    df.drop(columns=["YEAR", "MONTH"], inplace=True)
    return df


def collapse_redundant_radius(df):
    """
    Collapse Locomizer's duplicate catchment RADIUS (NEW in v1.4.0).

    In May 2026 Locomizer shipped every screen's Brand Affinity profile at TWO
    catchment radii (50 m and 183 m); before and after May each screen carries a
    single radius. The three affinity metrics (BRAND_AFFINITY_INDEX,
    BRAND_AFFINITY_DWELL_TIME, PROPORTION_OF_TARGET_USERS) are byte-for-byte
    identical across the two radii -- they are normalised characteristics of the
    audience, so catchment size does not change them (verified on the May 2026
    export: 410,256 (CODE, HOUR, MOVEMENT_MODALITY, VISITATION_MODALITY,
    BRAND_AFFINITY_CATEGORY_NAME) keys, max abs diff = 0). The second radius
    therefore carries no information and only doubles the row count (820,512 vs
    ~408,672 in adjacent months), inflating any SUM/COUNT.

    We keep ONE row per
      (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY, VISITATION_MODALITY,
       BRAND_AFFINITY_CATEGORY_NAME),
    retaining the smallest available radius for determinism (groups with both
    radii keep 50 m; groups carrying only one radius keep it -- nothing is
    dropped). Because the values are identical the choice is lossless. RADIUS is
    not used by any dashboard measure, so the column is kept as-is and only the
    duplicate rows are removed.

    Trigger: only groups carrying >1 radius are affected, so single-radius months
    (all of 2025, and Mar/Apr/Jun/Jul 2026) pass through untouched.

    Unlike process_footfall.py, the master `viewing.radius` is NOT consulted:
    footfall's two radii hold DIFFERENT audience counts (a 183 m catchment ~4.3x
    a 50 m one) so it must pick each screen's canonical radius, whereas here the
    radii are identical and either one is correct. This mirrors
    process_demographics.py v1.7.0.

    Must run AFTER build_hour_column and build_year_month_column so HOUR and
    YEAR_MONTH exist for the key.
    """
    key = ["CODE", "YEAR_MONTH", "HOUR",
           "MOVEMENT_MODALITY", "VISITATION_MODALITY",
           "BRAND_AFFINITY_CATEGORY_NAME"]
    missing = [c for c in key + ["RADIUS"] if c not in df.columns]
    if missing:
        raise ValueError(
            f"collapse_redundant_radius needs columns {missing}. "
            f"Run it after build_hour_column and build_year_month_column."
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
        print(f"  [DROP]   Removed {len(present)} column(s): {present}")
    return df


def filter_zero_rows(df):
    """
    Remove placeholder rows where BRAND_AFFINITY_INDEX is below the threshold.
    These are screen/hour/modality/category combinations for which Locomizer
    could not produce a reliable affinity score (panel too small). All three
    metric columns flip to zero together on these rows, so the INDEX filter
    is sufficient.

    Returns (df_filtered, n_removed).
    """
    rows_before = len(df)
    zero_mask = df["BRAND_AFFINITY_INDEX"] < ZERO_ROW_THRESHOLD
    n_removed = int(zero_mask.sum())
    df = df[~zero_mask].reset_index(drop=True)
    return df, n_removed


def add_site_id(df):
    """Stamp a canonical SITE_ID on every row via the id crosswalk.

    Unmatched CODEs (screens absent from the master site list) keep SITE_ID =
    CODE and are logged as orphans rather than dropped. Expects CODE as string.
    """
    if CROSSWALK is None:
        df["SITE_ID"] = df["CODE"].astype("string")
        print(f"  [SITE_ID] SKIPPED — {CROSSWALK_MSG}")
        return df

    df["SITE_ID"], matched = CROSSWALK.resolve_ids(df["CODE"])
    remapped = int((matched & (df["SITE_ID"] != df["CODE"].astype("string"))).sum())
    orphan_codes = sorted(df.loc[~matched, "CODE"].dropna().unique().tolist())
    n_screens = df["CODE"].nunique()
    print(f"  [SITE_ID] {n_screens - len(orphan_codes)}/{n_screens} screens "
          f"mapped to SITE_ID ({remapped:,} rows re-keyed to a NEW MM ID).")
    if orphan_codes:
        print(f"  [ORPHAN]  {len(orphan_codes)} CODE(s) not in master site list "
              f"(kept as-is): {orphan_codes[:10]}"
              + (" ..." if len(orphan_codes) > 10 else ""))
    return df


def build_column_order(df):
    """
    Return df with columns in a logical order:
      CODE -> SITE_ID -> time -> segment -> category -> metrics -> SOURCE_FILE.
    Any unexpected columns are appended at the end.
    """
    priority = [
        "CODE",                          # raw as-delivered identifier
        "SITE_ID",                       # canonical key (joins to site list)
        "YEAR_MONTH",                    # time period (YYYY-MM)
        "HOUR",                          # time of day (0-23)
        "RADIUS",                        # viewshed radius
        "MOVEMENT_MODALITY",             # segment filter (All / Pedestrians / Non_Pedestrians)
        "VISITATION_MODALITY",           # segment filter (All / Residents / Workers / Transient)
        "IS_DEFAULT",                    # 1 = All+All (overall audience); 0 = segment view
        "BRAND_AFFINITY_CATEGORY_NAME",  # POI category dimension
        "BRAND_AFFINITY_INDEX",          # PRIMARY metric (vs national average = 100)
        "BRAND_AFFINITY_DWELL_TIME",     # dwell time of target audience (%)
        "PROPORTION_OF_TARGET_USERS",    # % of users with positive affinity
        "SOURCE_FILE",                   # audit trail
    ]

    ordered = [c for c in priority if c in df.columns]

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
        # pyarrow preserves dtypes (including category and int8) and is the
        # smallest/fastest format for Power BI to consume.
        df_clean.to_parquet(path_clean, index=False, engine="pyarrow")
    else:
        # utf-8-sig BOM ensures the CSV opens correctly in Excel on Windows
        df_clean.to_csv(path_clean, index=False, encoding="utf-8-sig")

    return path_clean


def file_info(path):
    """Return (size_kb, last_modified_str) for a file."""
    stats = os.stat(path)
    return stats.st_size / 1024, time.ctime(stats.st_mtime)


# %% ---------------------------------------------------------------------------
# Step 1 -- Discover input files
# ---------------------------------------------------------------------------
# Scan INPUT_DIR for CSVs whose name contains 'brandaffinity' (case-insensitive,
# spaces and underscores stripped). Sorted alphabetically so monthly files
# process in chronological order (assuming the "MM_MonYYYY_..." naming pattern).

print(f"{'='*20} FILE DISCOVERY {'='*20}")
print(f"[DIR]    Scanning : {INPUT_DIR}")
print(f"[FORMAT] Output   : {OUTPUT_FORMAT.upper()}")
print(f"[VER]    Script   : v{__version__}")

all_csvs = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
brand_affinity_files = sorted(
    [f for f in all_csvs
     if "brandaffinity" in os.path.basename(f).lower().replace("_", "").replace(" ", "")]
)

if not brand_affinity_files:
    print(f"ERROR: No Brand Affinity CSV files found in {INPUT_DIR}")
    print("       Filenames must contain 'brandaffinity' "
          "(e.g. '02_Feb2025_Micromedia_BrandAffinity.csv')")
    raise SystemExit(1)

print(f"[FOUND]  {len(brand_affinity_files)} file(s) detected:")
for f in brand_affinity_files:
    print(f"         - {os.path.basename(f):60s} ({os.path.getsize(f)/1024:>8,.0f} KB)")
print(f"{'='*56}\n")


# %% ---------------------------------------------------------------------------
# Step 2 -- Per-file processing loop
# ---------------------------------------------------------------------------
# Each file is loaded, validated, transformed, and exported independently.
# Benefits:
#   * Only one month sits in RAM at a time -> lower peak memory usage.
#   * A single corrupt/missing file does not block the others.
#   * New months can be added to the folder without re-processing old ones.

global_summary = []   # collects one dict per file for the final report

for filepath in brand_affinity_files:
    filename = os.path.basename(filepath)
    stem     = os.path.splitext(filename)[0]   # e.g. "02_Feb2025_Micromedia_BrandAffinity"

    print(f"{'='*20} PROCESSING: {filename} {'='*20}")
    t_start = time.time()

    # -- 2a: Pre-check source header for unexpected new columns ---------------
    # usecols=EXPECTED_COLUMNS at load time causes pandas to silently discard
    # any column Locomizer may add in future exports. Reading only the header
    # first (nrows=0, fast) lets us surface those columns in the log BEFORE
    # they disappear, so we can decide whether to add them to DTYPE_MAP.
    try:
        raw_header = pd.read_csv(filepath, nrows=0).columns.tolist()
        new_cols = [c for c in raw_header if c not in EXPECTED_COLUMNS]
        if new_cols:
            print(f"  [NEW COLS] {len(new_cols)} column(s) in source not in EXPECTED_COLUMNS "
                  f"(ignored by usecols): {new_cols}")
            print(f"             Consider adding these to DTYPE_MAP if they carry analytical value.")
        else:
            print(f"  [PRE-SCHEMA] Source matches EXPECTED_COLUMNS ({len(raw_header)} cols). OK")
    except Exception as e:
        print(f"  [PRE-SCHEMA] Header pre-check skipped: {e}")

    # -- 2b: Load with optimised dtypes ----------------------------------------
    # Pass DTYPE_MAP at load time so pandas skips the type-inference scan.
    # usecols=EXPECTED_COLUMNS guards against schema drift (unexpected columns
    # in future exports are now flagged above BEFORE being discarded here).
    try:
        df = pd.read_csv(filepath, dtype=DTYPE_MAP, usecols=EXPECTED_COLUMNS)
    except Exception as e:
        print(f"  ERROR LOAD FAILED: {e}")
        global_summary.append({"file": filename, "status": "LOAD ERROR", "error": str(e)})
        print()
        continue

    df["SOURCE_FILE"] = filename   # audit trail -- which file this row came from
    rows_raw = len(df)
    print(f"  [LOAD]   {rows_raw:>10,} rows x {len(df.columns)} columns")

    # -- 2c: Schema validation -------------------------------------------------
    print(f"  [SCHEMA]")
    validate_schema(df, filename)

    # Null check on key filter columns (must run before they're transformed)
    key_cols  = ["CODE", "TIME_INTERVAL", "MONTH", "YEAR",
                 "MOVEMENT_MODALITY", "VISITATION_MODALITY",
                 "BRAND_AFFINITY_CATEGORY_NAME", "BRAND_AFFINITY_INDEX"]
    null_hits = {c: int(df[c].isna().sum()) for c in key_cols if c in df.columns}
    if any(v > 0 for v in null_hits.values()):
        print(f"  WARNING  Nulls in key columns: {null_hits}")
    else:
        print(f"  [NULLS]  No nulls in key columns. OK")

    # -- 2d: CODE sanity check (5-digit integer expected) ----------------------
    # Defensive: flag any CODEs outside the expected 5-digit range so they can
    # be reconciled against the master site list before reaching Power BI.
    bad_codes = df[(df["CODE"] < 10000) | (df["CODE"] > 99999)]["CODE"].unique()
    if len(bad_codes) > 0:
        print(f"  WARNING  {len(bad_codes)} CODE(s) outside 5-digit range: {sorted(bad_codes)[:10]}")
    else:
        print(f"  [CODE]   All {df['CODE'].nunique()} CODEs are valid 5-digit integers. OK")

    # -- 2e: Normalise modality casing (defensive — already Title Case) --------
    # Brand Affinity arrives in Title Case so this is a no-op on current data.
    # Run unconditionally for defensive consistency with the Footfall and
    # Demographics pipelines and to guard against a future Locomizer schema
    # change desynchronising the three fact tables (see helper docstring).
    df = standardize_modality_casing(df, MODALITY_COLS)
    print(f"  [CASE]   MOVEMENT_MODALITY  : {sorted(df['MOVEMENT_MODALITY'].unique().tolist())}")
    print(f"           VISITATION_MODALITY: {sorted(df['VISITATION_MODALITY'].unique().tolist())}")

    # -- 2f: Drop redundant columns (DISPLAY NAME, descriptions, constants) ----
    df = drop_columns(df, COLS_DROP)

    # -- 2g: Convert TIME_INTERVAL (1-24) -> HOUR (0-23) -----------------------
    df = build_hour_column(df)
    hour_min, hour_max = int(df["HOUR"].min()), int(df["HOUR"].max())
    print(f"  [HOUR]   TIME_INTERVAL -> HOUR conversion done. "
          f"Range: {hour_min}..{hour_max} (expected 0..23)")

    # -- 2h: Build YEAR_MONTH period column ------------------------------------
    df = build_year_month_column(df)
    sample_ym = df["YEAR_MONTH"].iloc[0] if len(df) > 0 else ""
    unique_ym = sorted(df["YEAR_MONTH"].unique().tolist())
    print(f"  [PERIOD] YEAR_MONTH column built. "
          f"Periods in file: {unique_ym}  |  Sample: '{sample_ym}'")

    # -- 2i: Filter zero-data rows ---------------------------------------------
    # Rows where INDEX, DWELL_TIME and PROPORTION are all zero simultaneously
    # are Locomizer placeholders (panel too small). We now ASSERT that all three
    # metrics agree before filtering -- if a future export breaks this assumption,
    # the divergence is logged and the analyst can investigate.
    dwell_zeros = int((df["BRAND_AFFINITY_DWELL_TIME"]      < ZERO_ROW_THRESHOLD).sum())
    prop_zeros  = int((df["PROPORTION_OF_TARGET_USERS"]     < ZERO_ROW_THRESHOLD).sum())
    idx_zeros   = int((df["BRAND_AFFINITY_INDEX"]           < ZERO_ROW_THRESHOLD).sum())
    if not (dwell_zeros == prop_zeros == idx_zeros):
        print(f"  WARNING  Zero-row counts diverge across metrics: "
              f"INDEX={idx_zeros:,}  DWELL={dwell_zeros:,}  PROP={prop_zeros:,}")
        print(f"           Filtering on INDEX only -- inspect diverging rows manually.")
    else:
        print(f"  [ZERO-CHECK] All three metrics agree: {idx_zeros:,} zero rows. OK")

    # Capture screens before filtering to detect full-screen data loss.
    screens_before = set(df["CODE"].unique())
    df, rows_zero = filter_zero_rows(df)
    print(f"  [FILTER] {rows_zero:,} zero-data rows removed "
          f"({rows_zero / rows_raw * 100:.1f}% of raw)  ->  {len(df):,} rows remain.")

    screens_after = set(df["CODE"].unique())
    fully_filtered_screens = sorted(int(c) for c in (screens_before - screens_after))
    if fully_filtered_screens:
        print(f"  WARNING  {len(fully_filtered_screens)} screen(s) had ALL rows zeroed "
              f"and are excluded from the output entirely:")
        print(f"           CODEs: {fully_filtered_screens}")
        print(f"           These screens will be absent from Power BI affinity visuals "
              f"for this period.")
    else:
        print(f"  [SCREENS] All {len(screens_after)} screens retained at least one row. OK")

    # -- 2i2: Collapse redundant catchment RADIUS (NEW in v1.4.0) --------------
    # From May 2026 Locomizer briefly shipped both catchment radii (50 m + 183 m)
    # per screen, duplicating every row. The two radii are byte-identical on all
    # three affinity metrics (verified: max abs diff = 0 on the May 2026 export),
    # so the duplicate carries no signal and only doubles the row count. Keep one
    # row per (CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY, VISITATION_MODALITY,
    # BRAND_AFFINITY_CATEGORY_NAME). Runs BEFORE IS_DEFAULT / the shape report /
    # export so every downstream count reflects the de-duplicated data. Single-
    # radius months pass through untouched (trigger: >1 radius in a group).
    df = collapse_redundant_radius(df)

    # -- 2j: Add IS_DEFAULT helper column --------------------------------------
    # IS_DEFAULT = 1 marks rows where MOVEMENT_MODALITY='All' AND
    # VISITATION_MODALITY='All'. This is the "overall audience" view --
    # the correct default for most Power BI affinity visuals.
    #
    # WHY this matters: the file contains 6 modality combinations. Without a
    # filter, a Power BI chart averages across all 6 rows per CODE/HOUR/CATEGORY,
    # producing INDEX averages 5-48 pts off from the correct overall-audience
    # value (verified on Feb 2025 data across all 11 categories).
    #
    # In Power BI: add IS_DEFAULT = 1 as a report-level filter or slicer before
    # building any affinity chart. Use IS_DEFAULT = 0 only when comparing
    # specific segments (Residents vs Transient; Pedestrians vs Non_Pedestrians).
    #
    # Stored as int8 (0/1) for full Parquet cross-tool compatibility.
    df["IS_DEFAULT"] = (
        (df["MOVEMENT_MODALITY"] == "All") &
        (df["VISITATION_MODALITY"] == "All")
    ).astype("int8")
    n_default = int(df["IS_DEFAULT"].sum())
    print(f"  [IS_DEFAULT] {n_default:,} rows = IS_DEFAULT=1 "
          f"({n_default / len(df) * 100:.1f}% = overall audience view)")

    # -- 2k: Report modality combinations and categories (sanity) --------------
    mov_vis = (df.groupby(["MOVEMENT_MODALITY", "VISITATION_MODALITY"], observed=True)
                 .size().reset_index(name="n"))
    print(f"  [SHAPE]  {len(mov_vis)} modality combos x "
          f"{df['BRAND_AFFINITY_CATEGORY_NAME'].nunique()} categories x "
          f"{df['CODE'].nunique()} screens")

    # -- 2l: Convert CODE int32 -> str (final dtype for Power BI join) ---------
    # Brand Affinity loads CODE as int32 so the 5-digit range sanity check in
    # step 2d works on a numeric type. We convert to str before the SITE_ID
    # crosswalk (string keys) and export, so the published Parquet has the same
    # join-key dtype as Footfall (str) and Demographics (str) -- one consistent
    # column type across all three fact tables means a single relationship-type
    # setting in the Power BI data model.
    df["CODE"] = df["CODE"].astype(str)
    print(f"  [CODE]   Converted int32 -> str. Sample: '{df['CODE'].iloc[0]}'")

    # -- 2m: Canonical SITE_ID (crosswalk old/new codes -> one key) ------------
    df = add_site_id(df)

    # -- 2n: Column reordering -------------------------------------------------
    df = build_column_order(df)
    print(f"  [ORDER]  Columns reordered. Final width: {len(df.columns)} columns.")

    # -- 2o: Export ------------------------------------------------------------
    try:
        path_clean = export_file(df, stem, OUTPUT_FORMAT)
        size_kb, _ = file_info(path_clean)
        elapsed    = time.time() - t_start

        print(f"  [EXPORT] {os.path.basename(path_clean):<65} ({size_kb:>7,.1f} KB)")
        print(f"  [TIME]   {elapsed:.1f}s")

        global_summary.append({
            "file":         filename,
            "status":       "OK",
            "rows_raw":     rows_raw,
            "rows_zero":    rows_zero,
            "rows_clean":   len(df),
            "screens":      df["CODE"].nunique(),
            "lost_screens": len(fully_filtered_screens),
            "categories":   df["BRAND_AFFINITY_CATEGORY_NAME"].nunique(),
            "periods":      ", ".join(unique_ym),
            "size_kb":      round(size_kb, 1),
            "elapsed_s":    round(elapsed, 1),
        })

    except Exception as e:
        print(f"  ERROR EXPORT FAILED: {e}")
        global_summary.append({"file": filename, "status": "EXPORT ERROR", "error": str(e)})

    print()   # blank line between files


# %% ---------------------------------------------------------------------------
# Step 3 -- Global summary
# ---------------------------------------------------------------------------
# One-glance report across all processed files.

print(f"{'='*20} GLOBAL SUMMARY {'='*20}")
print(f"\n  {'FILE':<50} {'STATUS':<8}  {'RAW':>8}  {'ZERO':>7}  {'CLEAN':>8}  "
      f"{'SCRNS':>5}  {'LOST':>4}  {'CATS':>4}  {'PERIOD':<8}  {'KB':>8}  {'TIME':>5}")
print(f"  {'-'*50} {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}  "
      f"{'-'*5}  {'-'*4}  {'-'*4}  {'-'*8}  {'-'*8}  {'-'*5}")

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
        lost_flag    = f"WARN {s['lost_screens']}" if s["lost_screens"] > 0 else "OK 0"
        print(
            f"  {s['file']:<50} {'OK':<8}  {s['rows_raw']:>8,}  "
            f"{s['rows_zero']:>7,}  {s['rows_clean']:>8,}  "
            f"{s['screens']:>5,}  {lost_flag:>4}  {s['categories']:>4,}  "
            f"{s['periods']:<8}  {s['size_kb']:>8,.1f}  {s['elapsed_s']:>4.1f}s"
        )
    else:
        err = s.get("error", "")
        print(f"  {s['file']:<50} ERROR {s['status']:<8}  {err}")

print(f"  {'-'*130}")
print(f"  {'TOTAL':<50} {'':>8}  {total_raw:>8,}  {total_zero:>7,}  {total_clean:>8,}")
print(f"\n  Files OK      : {ok_count} / {len(brand_affinity_files)}")
print(f"  Output folder : {OUTPUT_CLEAN_DIR}")
print(f"  Output format : {OUTPUT_FORMAT.upper()}")
print(f"{'='*56}")
print("Process finished.")
# %%