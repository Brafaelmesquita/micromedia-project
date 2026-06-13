# Micromedia OOH Audience Analytics Dashboard

Interactive Power BI dashboard for analysing audience data across Micromedia
Ireland's digital Out-of-Home (OOH) billboard network. A Python pipeline cleans
the monthly Locomizer exports; Power BI consumes the processed files for pre- and
post-campaign reporting.

## Data

Provided monthly by Locomizer as CSV exports:

- **Footfall** — audience volume and movement profile per screen
- **Demographics** — age and gender distribution per screen
- **Brand Affinity** — affinity index for brand / POI categories per screen

Screens are joined to the **Master Site List** on `CODE` (Custom ID), the shared
key across all three datasets. Raw data files are not version-controlled (client
confidential).

## Project structure

```
micromedia-project/
├── data/
│   ├── raw/              ← Original Locomizer CSVs (not versioned)
│   └── processed/        ← Cleaned Parquet/CSV outputs for Power BI
├── scripts/
│   ├── build_master_sites.py      ← Master screen list (join key + metadata)
│   ├── process_footfall.py        ← Clean footfall data
│   ├── process_demographics.py    ← Clean demographics (wide + age-long)
│   └── process_brand_affinity.py  ← Clean brand affinity data
├── pbix/
│   └── MM_Dashbard__Final.pbip    ← Power BI project (report + semantic model)
├── docs/                          ← Methodology notes
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Pipeline (run order)

```bash
python scripts/build_master_sites.py      # Master screen list (join key)
python scripts/process_footfall.py        # Clean footfall
python scripts/process_demographics.py    # Clean demographics
python scripts/process_brand_affinity.py  # Clean brand affinity
```

Drop the new monthly CSVs into `data/raw/<dataset>/` and re-run — cleaned outputs
land in `data/processed/`. No code changes are needed to add a new month.

## Power BI dashboard

The `.pbip` lives under `pbix/` (text-based, so it diffs cleanly in git). Pages:

- **Campaign reporting** — pre- and post-campaign views (footfall / impressions,
  demographics, brand affinity) filtered by screen, date, time of day and
  movement type.
- **QA — Daily vs Hourly** and **QA — Inflation Trend** — internal data-quality
  monitors that validate Locomizer's all-day totals against the hourly sums.
  Not client-facing (hidden in the published app).

**Methodology:** always report from the **Daily** figure
(`IS_GRAND_TOTAL = 1 AND HOUR = 25`, the deduplicated all-day total). Hourly is
for validation only — see the in-report reading guide. Inflation = Hourly ÷ Daily
behaves predictably by metric (≈1.0 for signals, ≈1.5 for unique-person counts,
≈0.7–0.9 for reach/eye-contact metrics).

## Monthly refresh & publish

Data is delivered monthly, so refresh is manual:

1. Drop the new CSVs in `data/raw/` and run the pipeline (above).
2. Open the `.pbip` in Power BI Desktop → **Refresh** → **Publish** (overwrite).
3. The published **app** (Power BI Service, *MicroMedia-Audience* workspace)
   reflects the new data.

The dashboard is distributed to the company through a Power BI **app** — share the
app link, not the `.pbix`/`.pbip`.

## Versioning

Versioned with git. The `.pbip` format stores the report and semantic model as
text, so model and visual changes are reviewable in diffs. Raw data under
`data/raw/` is git-ignored (client confidential).