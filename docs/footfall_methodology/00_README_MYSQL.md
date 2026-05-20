# Footfall Methodology — SQL Demo Scripts (MySQL 8.0+)

These scripts show, against the raw Locomizer Footfall data, **what each filter does**
to the audience numbers. Run them in order against the `micromedia` schema in MySQL.

## Files (run in order)

| # | File | What it does |
|---|---|---|
| 0 | `00_setup_create_table.sql` | Creates the `footfall_raw` table in `micromedia` schema. |
| 0 | `00_setup_load_csv.sql` | Loads the Mar/2025 CSV via `LOAD DATA LOCAL INFILE`. Edit the path first. |
| 1 | `01_hour25_vs_sum_of_hours.sql` | Proves `HOUR=25` is NOT the sum of `HOUR 0..23`. |
| 2 | `02_movement_modality_overlap.sql` | Proves movement segments overlap (~38% of cells). |
| 3 | `03_visitation_modality_overlap.sql` | Proves visitation segments overlap (~16% of cells). |
| 4 | `04_month_wide_filter_comparison.sql` | The A/B/C/D filter comparison at month level, in one query. |
| 5 | `05_correct_kpi_methodology.sql` | The official query for Total Population, PaS, and OTS. |

## Step-by-step instructions

See `INSTRUCOES_PASSO_A_PASSO.md` for the full walk-through (Portuguese) on how
to load the data and run the scripts in MySQL Workbench.

## Headline result (Mar 2025, all 243 screens)

| KPI | Column | Filter | Value |
|---|---|---|---:|
| Total Population | `EXTRAPOLATED_USERS_2` | `MOV='ALL' AND VIS='ALL' AND HOUR=25` | 149,821,318 |
| PaS | `EXTRAPOLATED_NUMBER_OF_USERS` | same | 66,587,252 |
| OTS | `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS` | same | 28,102,238 |

Every wrong filter inflates these — script 04 proves it side by side.
