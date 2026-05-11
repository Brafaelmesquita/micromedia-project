"""
build_master_sites.py
=====================
Merges three source files into one unified Master Site database:

1. Master_Site_List.xlsx               -> source of truth (active + inactive)
2. Locomizer_Master_V3_-_Azimuth.xlsx  -> adds Lat/Lng, azimuth, asset settings
3. MasterList-PowerBI_Template.csv     -> adds 'Display' label; drops 'Sum Campaigns 2025'

Join keys:
  Master MM ID  ==  Locomizer Custom ID  ==  PowerBI Display ID

Output: data/processed/master_sites_unified.csv
"""

# %% ---------------------------------------------------------------------------
# Imports & file paths
# ---------------------------------------------------------------------------
# Load external dependencies and resolve all paths relative to this script.

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MASTER_XLSX    = os.path.join(BASE_DIR, "..", "data", "raw", "sites", "Master Site List.xlsx")
LOCOMIZER_XLSX = os.path.join(BASE_DIR, "..", "data", "raw", "sites", "Locomizer Master V3 - Azimuth.xlsx")
POWERBI_CSV    = os.path.join(BASE_DIR, "..", "data", "raw", "sites", "MasterList-PowerBI Template.csv")
OUTPUT_CSV     = os.path.join(BASE_DIR, "..", "data", "processed", "master_sites_unified.csv")

paths_to_verify = {
    "Master XLSX": MASTER_XLSX,
    "Locomizer XLSX": LOCOMIZER_XLSX,
    "PowerBI CSV": POWERBI_CSV
}

print(f"{'='*20} PATH VERIFICATION {'='*20}")
for name, path in paths_to_verify.items():
    exists = "EXISTS" if os.path.exists(path) else "NOT FOUND"
    print(f"[{exists}] {name}: {path}")

print(f"[OUTPUT TARGET] Output will be saved to: {OUTPUT_CSV}")
print(f"{'='*59}\n")

# %% ---------------------------------------------------------------------------
# Load Master Site List (active + inactive)
# ---------------------------------------------------------------------------
# Read both sheets from the Master Site List workbook and tag them so we can
# keep track of active vs inactive screens after concatenation.

# Active screens
active = pd.read_excel(MASTER_XLSX, sheet_name="MasterList")
active["is_active"] = True

# Inactive screens
inactive = pd.read_excel(MASTER_XLSX, sheet_name="Inactive Screens")
inactive["is_active"] = False

print(f"{'='*20} DATA LOAD VERIFICATION {'='*20}")

# Function to generate a summary for each dataframe
for df_name, df in [("Active Sites", active), ("Inactive Sites", inactive)]:
    row_count = len(df)
    col_count = len(df.columns)
    status_check = df["is_active"].unique()
    
    print(f"Loaded '{df_name}':")
    print(f" - Dimensions: {row_count} rows x {col_count} columns")
    print(f" - 'is_active' flag verification: {status_check}")
    
    if row_count > 0:
        # Show a snippet of the first few Site IDs or Names to confirm data integrity
        # Adjust 'Site ID' to your actual column name if different
        example_col = df.columns[0] 
        print(f" - Sample {example_col}s: {df[example_col].head(3).tolist()}...")
    else:
        print(" ! WARNING: DataFrame is empty.")
    print("-" * 30)

print(f"Total rows to concatenate: {len(active) + len(inactive)}")
print(f"{'='*60}\n")

# %% ---------------------------------------------------------------------------
# Build base DataFrame from Master list
# ---------------------------------------------------------------------------
# Concatenate active and inactive into a single base DataFrame.
# Drop Excel artefact columns and standardise MM ID as nullable integer.

base = pd.concat([active, inactive], ignore_index=True)
base = base.loc[:, ~base.columns.str.startswith("Unnamed")]
base["MM ID"] = pd.to_numeric(base["MM ID"], errors="coerce").astype("Int64")

# Capture counts before concatenation for verification
count_active = len(active)
count_inactive = len(inactive)

print(f"{'='*20} CONCATENATION & CLEANING {'='*20}")

# 1. Verify Concatenation Math
expected_total = count_active + count_inactive
actual_total = len(base)
math_check = "PASS" if expected_total == actual_total else "FAIL"

print(f"[CONCAT] {count_active} (active) + {count_inactive} (inactive) = {actual_total} total rows")
print(f"         Integrity Check: {math_check}")

# 2. Verify Column Dropping
unnamed_cols = [c for c in base.columns if "Unnamed" in c]
print(f"[CLEAN]  Unnamed columns remaining: {len(unnamed_cols)}")

# 3. Verify Data Type Conversion
mm_id_dtype = base["MM ID"].dtype
null_mm_ids = base["MM ID"].isna().sum()
print(f"[TYPE]   'MM ID' converted to: {mm_id_dtype}")
print(f"         'MM ID' Nulls/Coerced: {null_mm_ids} (out of {actual_total} rows)")

# 4. Preview Final Structure
print(f"[SHAPE]  Final Base DataFrame: {base.shape[0]} rows x {base.shape[1]} columns")
print(f"{'='*60}\n")

# %% ---------------------------------------------------------------------------
#  Load & prepare Locomizer data
# ---------------------------------------------------------------------------
# Read Locomizer sheet. Before merging, drop columns that are either already
# present in the master or are not needed in the unified output, then rename
# all remaining columns (except the join key) with the _loco suffix so their
# origin is unambiguous in the final dataset.
 
# Columns to drop from the Locomizer sheet before merging.
# These are either redundant with master columns or explicitly excluded.
LOCO_COLS_TO_EXCLUDE = [
    "Display Name",
    "Panel",
    "Network",         # uppercase variant present in some sheet versions
    "network_name",
    "Address",
    "Image",
    "adunit_name",
    "network",          # lowercase variant present in some sheet versions
    "asset.image_url",
    "# asset.image_url", # alternate header form found in some exports
    "# Panel",           # alternate header form found in some exports
]
 
df_loco = pd.read_excel(LOCOMIZER_XLSX, sheet_name="Micromedia_Locomizer 2024 V3")
df_loco["Custom ID"] = pd.to_numeric(df_loco["Custom ID"], errors="coerce").astype("Int64")
 
# Drop excluded columns (silently skip any that are absent in this export)
cols_to_drop = [c for c in LOCO_COLS_TO_EXCLUDE if c in df_loco.columns]
df_loco = df_loco.drop(columns=cols_to_drop)
 
# Add _loco suffix to every column except the join key (Custom ID).
# This clearly marks Locomizer-sourced fields throughout the pipeline.
df_loco = df_loco.rename(columns={
    col: f"{col}_loco"
    for col in df_loco.columns
    if col != "Custom ID"
})
 
print(f"{'='*20} LOCOMIZER PREPARATION {'='*20}")
print(f"[EXCLUDE] Dropped {len(cols_to_drop)} column(s): {cols_to_drop}")
loco_cols_kept = [c for c in df_loco.columns if c != "Custom ID"]
print(f"[RENAME]  {len(loco_cols_kept)} column(s) renamed with '_loco' suffix.")
print(f"[SAMPLE]  First 5 renamed columns: {loco_cols_kept[:5]}")
print(f"{'='*60}\n")

# %% ---------------------------------------------------------------------------
# Merge Locomizer data onto base
# ---------------------------------------------------------------------------
# Left-join so all master records are preserved. Because all Locomizer columns
# have been pre-renamed with _loco, pandas will not create _x / _y variants.
 
# Record row count before merge
rows_before = len(base)
 
base = pd.merge(
    base,
    df_loco,
    left_on="MM ID",
    right_on="Custom ID",
    how="left",
    indicator=True  # Temporary column to track the merge source
)
 
# --- Confirmation Block ---
print(f"{'='*20} MERGE VERIFICATION: LOCOMIZER {'='*20}")
 
# 1. Check Merge Success Rate
merge_counts = base["_merge"].value_counts()
matched = merge_counts.get("both", 0)
left_only = merge_counts.get("left_only", 0)
match_percentage = (matched / rows_before) * 100
 
print(f"[MERGE] Source records: {rows_before}")
print(f"[MERGE] Successful matches: {matched} ({match_percentage:.1f}%)")
print(f"[MERGE] Unmatched records: {left_only}")
 
# 2. Key Consistency Check
null_loco_keys = df_loco["Custom ID"].isna().sum()
if null_loco_keys > 0:
    print(f"[WARN]  Locomizer 'Custom ID' has {null_loco_keys} null/invalid keys.")
 
# 3. Data Integrity
rows_after = len(base)
if rows_after > rows_before:
    print(f"[WARN]  Row count increased from {rows_before} to {rows_after}!")
    print("        (This suggests duplicate keys in the Locomizer file)")
else:
    print(f"[INFO]  Row count stable at {rows_after}.")
 
# Cleanup: Remove the indicator column and the now-redundant join key
base.drop(columns=["_merge", "Custom ID"], inplace=True)
print(f"[CLEAN] Temporary merge columns dropped.")
print(f"{'='*62}\n")
 

# %% ---------------------------------------------------------------------------
# Handle Locomizer-driven duplicates
# ---------------------------------------------------------------------------
# Locomizer may contain multiple rows per MM ID (e.g. multiple azimuth entries).
# Keep the first row per MM ID so the master table stays one row per screen.

# Capture stats before dropping
total_before = len(base)
duplicate_mask = base.duplicated(subset=["MM ID"], keep=False)
duplicados = base[duplicate_mask]
num_affected_ids = duplicados["MM ID"].nunique()
num_duplicate_rows = len(duplicados)
 
# Perform the drop
base = base.drop_duplicates(subset=["MM ID"], keep="first")
total_after = len(base)
 
# --- Confirmation Block ---
print(f"{'='*20} DUPLICATE RESOLUTION {'='*20}")
 
if num_duplicate_rows > 0:
    print(f"[IDENTIFIED] Found {num_duplicate_rows} rows associated with {num_affected_ids} unique MM IDs.")
    print(f"[ACTION]     Dropped {total_before - total_after} redundant rows.")
    
    # Validation: Check if duplicates still exist
    still_has_dupes = base.duplicated(subset=["MM ID"]).any()
    print(f"[VERIFY]     Remaining duplicates for 'MM ID': {still_has_dupes}")
    
    # Optional: Show which IDs were duplicated (first 5)
    example_ids = duplicados["MM ID"].unique()[:5].tolist()
    print(f"[SAMPLES]    Example IDs that had duplicates: {example_ids}")
else:
    print("[INFO] No duplicates found. No rows were dropped.")
 
print(f"[FINAL] Total unique screens in base: {total_after}")
print(f"{'='*62}\n")

# %% ---------------------------------------------------------------------------
# Load & prepare PowerBI template
# ---------------------------------------------------------------------------
# Read the PowerBI template which contributes the human-readable 'Display' label.
# Note: Using sep=None and encoding='utf-8-sig' to prevent header errors.
df_display_labels = pd.read_csv(POWERBI_CSV, sep=None, engine='python', encoding='utf-8-sig')
df_display_labels.columns = df_display_labels.columns.str.strip()

# Convert ID and capture count before/after deduplication
df_display_labels["Display ID"] = pd.to_numeric(df_display_labels["Display ID"], errors="coerce").astype("Int64")

initial_label_count = len(df_display_labels)
df_display_labels = df_display_labels.drop_duplicates(subset=["Display ID"])
final_label_count = len(df_display_labels)

# --- Audit Logic: Identify IDs in PBI missing from Master ---
master_ids = set(base["MM ID"].dropna())
pbi_ids = set(df_display_labels["Display ID"].dropna())
orphaned_in_pbi = pbi_ids - master_ids

# --- Confirmation Block ---
print(f"{'='*20} LABEL TEMPLATE PREPARATION {'='*20}")
print(f"[LOAD] Source: {os.path.basename(POWERBI_CSV)}")

# 1. Verify cleaning
dropped_labels = initial_label_count - final_label_count
print(f"[CLEAN] Deduplication complete:")
print(f"        - Initial rows: {initial_label_count}")
print(f"        - Duplicates removed: {dropped_labels}")
print(f"        - Unique labels available: {final_label_count}")

# 2. Audit Summary
print(f"[AUDIT] ID Consistency Check:")
if not orphaned_in_pbi:
    print("        ✅ PASS: All IDs in PBI Template exist in Master Base.")
else:
    print(f"        ⚠️ WARN: {len(orphaned_in_pbi)} IDs in PBI are MISSING from Master (Orphans).")

# 3. Content Check
if "Display" in df_display_labels.columns:
    sample_labels = df_display_labels["Display"].dropna().head(3).tolist()
    print(f"[CHECK] Found 'Display' column. Sample values: {sample_labels}")
else:
    print(f"[WARN] Column 'Display' not found! Available columns: {list(df_display_labels.columns)}")

print(f"{'='*60}\n")

# %% ---------------------------------------------------------------------------
# Merge Display Labels onto base & Export Audit Report
# ---------------------------------------------------------------------------
rows_before_merge = len(base)

# Definir a coluna de interesse e renomeá-la com o sufixo _pbi
# Cria um DataFrame temporário apenas com ID e a coluna de soma de campanhas
df_pbi_to_merge = df_display_labels[["Display ID", "Sum Campaigns 2025"]].copy()
df_pbi_to_merge = df_pbi_to_merge.rename(columns={"Sum Campaigns 2025": "Sum Campaigns 2025_pbi"})

base = pd.merge(
    base,
    df_pbi_to_merge,
    left_on="MM ID",
    right_on="Display ID",
    how="left",
    indicator="_merge_labels"
)

# --- Audit Export Logic ---
# 1. Sites in Master that did NOT find a match in the PowerBI Template
missing_labels_df = base[base["_merge_labels"] == "left_only"].copy()

# 2. Sites in PowerBI Template that do NOT exist in the Master Base
orphaned_labels_df = df_display_labels[df_display_labels["Display ID"].isin(orphaned_in_pbi)].copy()

AUDIT_PATH = os.path.join(BASE_DIR, "..", "data", "processed", "pbi_audit_report.xlsx")
with pd.ExcelWriter(AUDIT_PATH) as writer:
    missing_labels_df.to_excel(writer, sheet_name="Master_Missing_Labels", index=False)
    orphaned_labels_df.to_excel(writer, sheet_name="PBI_Orphans_Not_In_Master", index=False)

# --- Confirmation Block ---
print(f"{'='*20} MERGE VERIFICATION: POWER BI DATA {'='*20}")

# 1. Match Rate Analysis
label_stats = base["_merge_labels"].value_counts()
matches = label_stats.get("both", 0)
missing = label_stats.get("left_only", 0)
match_pct = (matches / rows_before_merge) * 100

print(f"[MERGE] Base records: {rows_before_merge}")
print(f"[MERGE] Successfully matched: {matches} ({match_pct:.1f}%)")
print(f"[MERGE] Sites missing PBI data: {missing} (Added to audit report)")

# 2. Column Check
if "Sum Campaigns 2025_pbi" in base.columns:
    print(f"[CHECK] Column 'Sum Campaigns 2025_pbi' successfully added.")

# 3. Export Notification
print(f"[AUDIT] Audit report generated: {os.path.basename(AUDIT_PATH)}")

# 4. Row Integrity
if len(base) == rows_before_merge:
    print(f"[VERIFY] Row count check: PASS (Count remains {len(base)})")
else:
    print(f"[WARN] Row count mismatch!")

# Cleanup
base.drop(columns=["_merge_labels", "Display ID"], inplace=True)
print(f"[CLEAN] Temporary merge indicator and redundant 'Display ID' dropped.")
print(f"{'='*62}\n")


# %% ---------------------------------------------------------------------------
# Column ordering
# ---------------------------------------------------------------------------
# Reorder columns into a logical thematic layout using the finalized column names.

COLS_ORDER = [
    # -- Identifiers --
    "MM ID", 
    "NEW MM ID", 
    "Xibo ID_loco",
    "Display Name",

    # -- Location & GIS --
    "Address", 
    "County", 
    "Postcode", 
    "City_loco",
    "Postal Code_loco",
    "Latitude_loco", 
    "Longitude_loco", 
    "azimuth_loco",

    # -- Screen Specs (Locomizer & Master Sourced) --
    "Network", 
    "Display Type_loco",
    "Display Facing",
    "Orientation_loco", 
    "Screen Size_loco",
    "Resolution_loco", 
    "slot.w_loco", 
    "slot.h_loco",
    "viewing.angle.FROM_loco", 
    "viewing.angle.TO_loco", 
    "viewing.radius_loco",
    "asset.name_loco",
    "asset.setting_loco",
    "venue.name_loco",

    # -- Operational & Business Logic --
    "is_active", 
    "Owner_loco",
    "PROOH", 
    "On-Trade", 
    "Restaurant",
    "Alcohol App.", 
    "Diageo - Approved",
    "Sum Campaigns 2025_pbi"  # Updated with PBI suffix
]

# Filter list to only include columns that actually exist in the dataframe
existing_ordered = [c for c in COLS_ORDER if c in base.columns]

# Catch any columns that might have been missed in the COLS_ORDER list
remaining = sorted([c for c in base.columns if c not in existing_ordered])

# Apply the new order
base = base[existing_ordered + remaining]

# --- Confirmation Block ---
print(f"{'='*20} COLUMN REORDERING: FINAL PASS {'='*20}")

# 1. Check for expected columns that weren't found
missing_from_list = [c for c in COLS_ORDER if c not in base.columns]
if missing_from_list:
    print(f"[NOTE] {len(missing_from_list)} defined columns were not found (skipped).")
    # print(f"       Missing: {missing_from_list}")

# 2. Check for "Leftovers"
if not remaining:
    print("✅ SUCCESS: All columns are accounted for in the thematic order.")
else:
    print(f"[INFO] {len(remaining)} unexpected columns moved to the end.")
    print(f"       Leftovers: {remaining}")

# 3. Layout Preview
print(f"\n[LAYOUT] Final Column sequence:")
print(f"    START: {base.columns[:4].tolist()}")
print(f"    END  : {base.columns[-3:].tolist()}")

print(f"\n[SHAPE] Final Dimensions: {base.shape[0]} rows x {base.shape[1]} columns.")
print(f"{'='*60}\n")

#%%
base

# %% ---------------------------------------------------------------------------
# Boolean / flag columns: inspection & safe normalisation
# ---------------------------------------------------------------------------
# Inspect current data types and value distributions, then coerce
# specific flag columns into clean nullable integer form (0/1 with NA).

# Added 'Restaurant' to the list as it is often a binary category in site lists
cols_alvo = ["is_active", "PROOH", "On-Trade", "Alcohol App.", "Diageo - Approved"]

print(f"{'='*20} INITIAL FLAG INSPECTION {'='*20}")
for col in cols_alvo:
    if col in base.columns:
        print(f"\nColumn: {col}")
        print(f" - Current dtype: {base[col].dtype}")
        print(f" - Unique values: {base[col].unique()[:5]}")
        print(f" - Null count: {base[col].isna().sum()}")
    else:
        print(f"\n[SKIP] Column '{col}' not found in DataFrame.")

# %% ---------------------------------------------------------------------------
# Helper: clean flag-like columns to nullable Int64
# ---------------------------------------------------------------------------

def clean_to_int(df, column_name):
    """
    Normalizes mixed-type columns (bool, string, float) into 0, 1, or <NA>.
    """
    if column_name in df.columns:
        # Convert to string and clean for mapping
        # We handle actual booleans and floats by converting to string first
        temp = df[column_name].astype(str).str.strip().str.lower()

        # Explicit mapping to catch various formats from Excel/CSV
        mapping = {
            "true": 1, "1": 1, "1.0": 1, "yes": 1, "y": 1, "active": 1,
            "false": 0, "0": 0, "0.0": 0, "no": 0, "n": 0, "inactive": 0,
            "nan": None, "none": None, "": None, "nat": None
        }

        df[column_name] = temp.map(mapping)
        
        # Cast to nullable Int64 (allows 0, 1, and NaN without converting to float)
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce").astype("Int64")
        
        # --- Confirmation Logic ---
        counts = df[column_name].value_counts(dropna=False)
        ones = counts.get(1, 0)
        zeros = counts.get(0, 0)
        # Handle different ways pandas represents nulls in value_counts
        nulls = len(df) - (ones + zeros)
        
        print(f"[FLAG] {column_name:.<20} | 1s: {ones:<5} | 0s: {zeros:<5} | Nulls: {nulls:<5}")
    return df

print(f"\n{'='*20} FLAG COLUMN NORMALIZATION {'='*20}")

# Applying to the verified column list
for col in cols_alvo:
    base = clean_to_int(base, col)

print(f"{'='*60}\n")


# %% ---------------------------------------------------------------------------
# Final export
# ---------------------------------------------------------------------------
# Export the unified master dataset to CSV for downstream consumption.

import os
import time

# Perform the export
base.to_csv(OUTPUT_CSV, index=False)

# --- Final Confirmation Block ---
print(f"{'='*20} FINAL EXPORT VERIFICATION {'='*20}")

if os.path.exists(OUTPUT_CSV):
    # Get file metadata
    file_stats = os.stat(OUTPUT_CSV)
    file_size_kb = file_stats.st_size / 1024
    last_modified = time.ctime(file_stats.st_mtime)
    
    print(f"[SUCCESS] File saved successfully.")
    print(f"[PATH]    {OUTPUT_CSV}")
    print(f"[SIZE]    {file_size_kb:.2f} KB")
    print(f"[STAMP]   Generated on: {last_modified}")
    
    # Final Integrity Snapshot
    rows, cols = base.shape
    print(f"[DATA]    Final Dimensions: {rows} rows x {cols} columns")
    
    # Check for critical errors (e.g., exporting an empty file)
    if rows == 0:
        print("⚠️ WARNING: The exported file is EMPTY (0 rows).")
    if file_size_kb < 1:
        print("⚠️ WARNING: The file size is unexpectedly small.")
        
else:
    print(f"❌ ERROR: File was NOT created at {OUTPUT_CSV}")

print(f"{'='*60}\n")
print("Process finished with success.")
