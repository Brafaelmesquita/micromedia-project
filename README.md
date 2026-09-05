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

Screens are joined to the **Master Site List** on `SITE_ID`, the canonical key
resolved from the raw `CODE` (see *Canonical screen identity* below). Raw and
processed data files are **not version-controlled** (client confidential) — the
repository ships the code that produces them, not the data itself.

Full output schemas, column meanings and query recipes live in
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).

## Data-quality engineering

Locomizer ships pre-aggregated totals *alongside* their own overlapping segment
breakdowns, so summing rows is almost always wrong. Three problems, all found by
**measuring the real data** rather than assuming, and each fixed with validation:

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

**3. Canonical screen identity.**
Micromedia is migrating screen codes from a legacy MM ID scheme to a new one, and
Locomizer delivers monthly exports under **either** scheme depending on when the
export was cut. Joining on the raw `CODE` therefore silently dropped whichever
scheme a given file happened to use. A crosswalk (`scripts/site_id_crosswalk.py`,
built by `build_master_sites.py`) maps every `CODE` — old or new — onto a single
canonical **`SITE_ID`**, which is what the Power BI relationships join on. The raw
`CODE` is preserved as delivered, and codes absent from the master list are left
unmapped and **logged as orphans** rather than dropped silently.

Every pipeline change is versioned with a changelog entry in the script that
states what changed **and the empirical evidence for it** — no behaviour in these
scripts was assumed.

## Project structure

```
micromedia-project/
├── data/
│   ├── raw/                          ← Original Locomizer CSVs (not versioned)
│   └── processed/                    ← Cleaned Parquet for Power BI (not versioned)
│       ├── footfall/
│       ├── demographics/clean/       ← wide table (single-year age, social grade)
│       ├── demographics/age_long/    ← tidy age × gender table for charting
│       ├── brand_affinity/
│       └── sites/                    ← master_sites_unified.csv + crosswalk
├── scripts/
│   ├── rename_raw_chrono.py          ← Canonical raw filenames
│   ├── build_master_sites.py         ← Master screen list + SITE_ID crosswalk
│   ├── site_id_crosswalk.py          ← Canonical key resolution (v1.0.0)
│   ├── process_footfall.py           ← Clean footfall            (v3.6.1)
│   ├── process_demographics.py       ← Clean demographics        (v1.8.0)
│   └── process_brand_affinity.py     ← Clean brand affinity      (v1.5.0)
├── pbix/
│   └── Micromedia_OOH_Dashboard.pbip ← Power BI project (report + semantic model)
├── docs/
│   ├── DATA_DICTIONARY.md            ← Output schemas & query recipes
│   ├── radius_canonicalisation.md    ← Radius duplication write-up
│   └── footfall_methodology/         ← Reproducible SQL audit of the sum rules
├── .gitattributes
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
python scripts/rename_raw_chrono.py       # Canonical raw filenames
python scripts/build_master_sites.py      # Master screen list + SITE_ID crosswalk
python scripts/process_footfall.py        # Clean footfall
python scripts/process_demographics.py    # Clean demographics (wide + age-long)
python scripts/process_brand_affinity.py  # Clean brand affinity
```

Order matters: `rename_raw_chrono.py` normalises the incoming filenames, and
`build_master_sites.py` produces the crosswalk the other three use to resolve
`SITE_ID`.

Drop the new monthly CSVs into `data/raw/<dataset>/` and re-run — cleaned outputs
land in `data/processed/`. No code changes are needed to add a new month. Input
filenames must contain `footfall`, `demograph` or `brandaffinity`.

Each script logs any column Locomizer adds that it does not expect, so schema
drift surfaces in the run log instead of silently reaching the dashboard.

## Power BI dashboard

The `.pbip` lives under `pbix/` (text-based, so the report and semantic model diff
cleanly in git).

### Pointing it at your data

The semantic model reads its Parquet through a single Power Query parameter,
**`DataFolder`**, so the project is not tied to one machine. After cloning:

1. Open `pbix/Micromedia_OOH_Dashboard.pbip` in Power BI Desktop.
2. **Transform data → Manage parameters → `DataFolder`**.
3. Set it to your clone's `data/processed` folder, then **Refresh**.

All five sources (`footfall`, `demographics\clean`, `demographics\age_long`,
`brand_affinity`, `sites`) derive their path from that one parameter.

### Pages

Client-facing:

- **Home** — navigation and a reading guide for the metrics.
- **Site Map** — screens plotted on Ireland, sized/coloured by audience volume.
- **Overview** — headline KPIs and the audience trend over the selected dates.
- **Demographics** — age profile (M/F) and gender split.
- **Audience Profile** — social grade, occupation and industry, plus visitation
  mix (residents / workers / transient) and movement mix (how they travel).
- **Affinity Explorer** — brand-affinity index by POI category, baseline 100.
- **Category Ranking** — categories ranked for the selected screens.
- **Site Profile Card** — single-screen summary for a sales conversation.

All filterable by screen, network, city, date range and time of day. The same
semantic model serves both output modes: a **pre-campaign proposal** (estimated
audience for a proposed screen/date selection) and a **post-campaign report**
(the delivered screens and campaign dates, with actual impressions).

Internal QA — not client-facing:

- **QA — Daily vs Hourly Validation** — checks Locomizer's all-day totals against
  the hourly sums.
- **QA — Inflation Stability Trend** — tracks the Hourly ÷ Daily ratio over time,
  so a change in Locomizer's methodology shows up as a break in the line.
- **QA — Exposure & Screen Validation** — screen coverage and orphan-code checks.
- **QA — Site Comparison Table** — screen-level figures for spot-checking.

### Reading the numbers

Always report from the **Daily** figure (`IS_GRAND_TOTAL = 1 AND HOUR = 25`, the
deduplicated all-day total). Hourly is for the busiest-times curve and for
validation. Inflation = Hourly ÷ Daily behaves predictably by metric (≈1.0 for
signals, ≈1.5 for unique-person counts, ≈0.7–0.9 for reach/eye-contact metrics).

The three headline KPIs are pre-computed by Locomizer and must never be
recalculated from `NUMBER_OF_USERS`:

| KPI | Column | Meaning |
|---|---|---|
| Total Population | `EXTRAPOLATED_USERS_2` | whole population passing |
| PaS (Passage) | `EXTRAPOLATED_NUMBER_OF_USERS` | mobile-carrying population |
| OTS (Opportunity to See) | `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS` | moving toward the screen, inside its azimuth cone |

OTS is the metric to quote for impressions, because it is the only one that
accounts for which way the screen faces.

Demographic composition is **audience-weighted by footfall**, so a multi-screen
profile reflects where the audience actually is rather than a simple per-screen
average — otherwise a quiet campus screen would carry the same weight as a
city-centre one.

## Semantic model notes

- Profile visuals are driven by long-format demographic tables:
  `Demographics_AgeLong` (age × gender, from the Python pipeline) and
  `Demographics_ClassLong` (social grade / occupation / industry, unpivoted in
  Power Query with a `BREAKDOWN` / `SEGMENT` structure).
- Monthly demographic tables join the date `Calendar` on a `YEAR_MONTH` text key
  (`YYYY-MM`); the relationship is many-to-many, single-direction. Footfall is
  daily, the other two monthly — there is no day-level join.
- Movement is modelled in two tiers: a fine-grained `dim_Movement` for the
  footfall travel chart, and a coarse `dim_Movement_Group`
  (Pedestrians / Non_Pedestrians) shared with the demographic and brand-affinity
  tables. `dim_Visitation` is shared across Footfall and Brand_Affinity.
- Composition charts pin the opposite modality to "All", so the modality slicers
  are wired (via *Edit interactions*) to drive only the brand-affinity chart, not
  the composition visuals.
- The `Master_Sites` query filters the source folder to `master_sites_unified.csv`
  explicitly, so the other files that live alongside it cannot leak into the
  dimension table.

## Monthly refresh & publish

Data is delivered monthly, so refresh is manual:

1. Drop the new CSVs in `data/raw/` and run the pipeline (above).
2. Open the `.pbip` in Power BI Desktop → **Refresh** → **Publish** (overwrite).
3. The published **app** (Power BI Service, *MicroMedia-Audience* workspace)
   reflects the new data.

The dashboard is distributed to the company through a Power BI **app** — share the
app link, not the `.pbix`/`.pbip`.

## Tech stack

Python (pandas, pyarrow) · Parquet · Power BI (PBIP, DAX, Power Query / M) · git.

## Versioning

Versioned with git. The `.pbip` format stores the report and semantic model as
text, so model and visual changes are reviewable in diffs; `.gitattributes` pins
line endings per file type so Power BI's rewrites do not produce phantom diffs.
Data under `data/raw/` and `data/processed/` is git-ignored (client confidential).
Pipeline scripts carry an in-file changelog; cross-cutting data decisions are
written up under `docs/`.
