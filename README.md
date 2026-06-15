# Micromedia OOH Audience Analytics Dashboard

Interactive Power BI dashboard for analysing audience data across Micromedia
Ireland's digital Out-of-Home (OOH) billboard network. A Python pipeline cleans
the monthly Locomizer exports; Power BI consumes the processed files for pre- and
post-campaign reporting.

## Data

Provided monthly by Locomizer as CSV exports:

- **Footfall** — audience volume and movement profile per screen
- **Demographics** — age, gender, social grade, occupation and industry
  distribution per screen
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

- **Pre-Campaign — "Who you'll reach"** — proposed-audience profile to support
  sales, across two pages:
  - audience impact trend over the selected dates and headline KPIs
    (footfall / impressions);
  - gender split and age profile;
  - visitation mix (residents / workers / transient visitors) and movement mix
    (how they travel);
  - social grade / occupation / industry profile (family selectable);
  - brand-affinity index by brand / POI category (baseline 100).

  Filterable by screen, network, city, date range and time of day.
- **Post-Campaign reporting** — the same semantic model filtered to the delivered
  screens and campaign dates, reporting actual impressions, demographics and
  brand affinity.
- **QA — Daily vs Hourly** and **QA — Inflation Trend** — internal data-quality
  monitors that validate Locomizer's all-day totals against the hourly sums.
  Not client-facing (hidden in the published app).

**Methodology:** always report from the **Daily** figure
(`IS_GRAND_TOTAL = 1 AND HOUR = 25`, the deduplicated all-day total). Hourly is
for validation only — see the in-report reading guide. Inflation = Hourly ÷ Daily
behaves predictably by metric (≈1.0 for signals, ≈1.5 for unique-person counts,
≈0.7–0.9 for reach/eye-contact metrics).

Demographic composition (age, gender, social grade, occupation, industry) is
**audience-weighted by footfall**, so multi-screen profiles reflect where the
audience actually is rather than a simple per-screen average; each profile family
sums to ~100%. For movement and visitation, **"All" is the deduplicated unique
total — not the sum of the segments** (the same person can travel differently on
different days), so segment views are shown as relative mix and never summed back
to "All".

## Semantic model notes

- Profile visuals are driven by long-format demographic tables:
  `Demographics_AgeLong` (age × gender, from the Python pipeline) and
  `Demographics_ClassLong` (social grade / occupation / industry, unpivoted in
  Power Query with a `BREAKDOWN` / `SEGMENT` structure).
- Monthly demographic tables join the date `Calendar` on a `YEAR_MONTH` text key
  (`YYYY-MM`); the relationship is many-to-many, single-direction.
- Movement is modelled in two tiers: a fine-grained `dim_Movement` for the
  footfall travel chart, and a coarse `dim_Movement_Group`
  (Pedestrians / Non_Pedestrians) shared with the demographic and brand-affinity
  tables. `dim_Visitation` is shared across Footfall and Brand_Affinity.
- Composition charts pin the opposite modality to "All", so the modality slicers
  are wired (via *Edit interactions*) to drive only the brand-affinity chart, not
  the composition visuals.

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