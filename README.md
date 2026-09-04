# Micromedia OOH Audience Analytics Dashboard

Interactive Power BI dashboard for analysing audience data across Micromedia
Ireland's digital Out-of-Home (OOH) billboard network. A Python pipeline cleans
the monthly Locomizer exports; Power BI consumes the processed files for pre- and
post-campaign reporting.

Every output answers three questions: **WHO** is the audience, **WHERE** are they,
and **WHEN** can they be reached — turning monthly raw data dumps into sales-ready
audience proposals and post-campaign proof, without manual spreadsheet work.

### The hard part

The Locomizer data is **pre-aggregated and ships overlapping segment rows** — the
same person can be counted as both a pedestrian and a resident in the same hour,
and again for every hour they linger. Summing rows naively therefore **inflates
the audience by 40–800%**. The pipeline is built around **empirically validated
deduplication rules** and ships data-quality guardrails, so the numbers that reach
a client proposal are the correct ones. See **Data-quality engineering** below.

## Data

Provided monthly by Locomizer as CSV exports:

- **Footfall** — audience volume and movement profile per screen
- **Demographics** — age, gender, social grade, occupation and industry
  distribution per screen
- **Brand Affinity** — affinity index for brand / POI categories per screen

Screens are joined to the **Master Site List** on `CODE` (Custom ID), the shared
key across all three datasets. Raw data files are not version-controlled (client
confidential).

## Data-quality engineering

Locomizer ships pre-aggregated totals *alongside* their own overlapping segment
breakdowns, so summing rows is almost always wrong. Two problems, both found by
**measuring the real data** rather than assuming, and fixed with validation:

**1. Segment / hour overcounting.**
A naive `SUM` over the footfall table inflates Total Population **8.08×** — measured
on the full March 2025 export (243 screens, 320,286 rows): movement-segment sums
exceed the true total in **37.7%** of cells, and summing hours 0–23 inflates the
daily total **1.46×** (someone who stays three hours is counted three times). The
pipeline keeps every row and adds a **flag column** instead of deleting anything;
every measure then selects the deduplicated grain
(`IS_GRAND_TOTAL = 1 AND HOUR = 25`). Segment views are always shown as
share-of-total, never summed back to a headline number.

**2. Catchment-radius duplication.**
From May 2026 Locomizer began shipping **two catchment radii** (50 m and 183 m) per
screen, duplicating each row and threatening to double the audience. Measured
across the real exports, the behaviour was **not uniform**: the duplication is
persistent from May onward in **Footfall**, but a one-off (May only) in
**Demographics** and **Brand Affinity**; and the two radii are **byte-identical**
in the normalised datasets (percentages / index — max abs diff = 0 over 410k keys)
while they differ **~4.3×** in Footfall (absolute counts grow with catchment size).
Each pipeline therefore handles it the way its data demands — Footfall keeps each
screen's **canonical radius** from the master site list; Demographics and Brand
Affinity **collapse the identical duplicate** (lossless, no master needed). The
step is trigger-gated, so single-radius months pass through untouched. Full
write-up in [`docs/radius_canonicalisation.md`](docs/radius_canonicalisation.md).

Every pipeline change is versioned with a changelog entry in the script that
states what changed **and the empirical evidence for it** — no behaviour in these
scripts was assumed.

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
├── docs/                          ← Methodology notes & reviews
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

## Tech stack

Python (pandas, pyarrow) · Parquet · Power BI (PBIP, DAX, Power Query) · git.

## Versioning

Versioned with git. The `.pbip` format stores the report and semantic model as
text, so model and visual changes are reviewable in diffs. Raw data under
`data/raw/` is git-ignored (client confidential). Pipeline scripts carry an
in-file changelog; cross-cutting data decisions are written up under `docs/`.
