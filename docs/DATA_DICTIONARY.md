# Data dictionary

Output schemas of the cleaned Parquet tables, the rules for selecting rows, and
the quirks worth knowing before writing a query, a DAX measure or a pandas
transformation.

Everything below describes the **processed** layer under `data/processed/`, which
is what Power BI reads. The raw Locomizer CSVs are not documented here — the
pipelines are the contract.

## Contents

1. [Star schema](#star-schema)
2. [Keys: CODE vs SITE_ID](#keys-code-vs-site_id)
3. [Choosing the right rows](#choosing-the-right-rows)
4. [Footfall](#footfall)
5. [Demographics — wide](#demographics--wide)
6. [Demographics — age-long](#demographics--age-long)
7. [Brand Affinity](#brand-affinity)
8. [Master site list](#master-site-list)
9. [Known data quirks](#known-data-quirks)
10. [Query recipes](#query-recipes)

---

## Star schema

```
                     Master site list (dimension)
                       SITE_ID — canonical key
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   Footfall               Demographics          Brand Affinity
   grain: SITE_ID ×       grain: SITE_ID ×      grain: SITE_ID ×
   DATE × HOUR ×          YEAR_MONTH ×          YEAR_MONTH × HOUR ×
   MOVEMENT ×             HOUR × MOVEMENT       MOVEMENT × VISITATION
   VISITATION                                   × CATEGORY
```

Footfall is **daily**; Demographics and Brand Affinity are **monthly**. There is
no day-level join between them — derive `YEAR_MONTH` from Footfall's `DATE` when
you need to combine the three.

All three tables export `CODE` and `SITE_ID` as **string** so the join-key dtype
matches, and normalise modality values to **Title Case** so a single slicer drives
all three.

| Table | Path under `data/processed/` | Columns |
|---|---|---|
| Footfall | `footfall/` | 22 |
| Demographics (wide) | `demographics/clean/` | 104 |
| Demographics (age-long) | `demographics/age_long/` | 10 |
| Brand Affinity | `brand_affinity/` | 13 |
| Master site list | `sites/master_sites_unified.csv` | 35 |

---

## Keys: CODE vs SITE_ID

Two identifier columns exist on every fact table, and they are not
interchangeable.

| Column | What it is | Use it for |
|---|---|---|
| `CODE` | the screen ID **exactly as Locomizer delivered it** — 5 digits, string | audit and traceability back to the source file |
| `SITE_ID` | the **canonical** screen ID after crosswalk resolution | every join, every relationship, every grouping |

Micromedia is migrating screen codes from a legacy MM ID scheme to a new one, and
Locomizer's monthly exports arrive under either scheme depending on when the
export was cut. `scripts/site_id_crosswalk.py` maps both schemes onto one
`SITE_ID`, so a screen keeps a stable identity across months.

**Join on `SITE_ID`.** Joining on `CODE` silently loses whichever scheme a given
file used. Codes with no match in the master list are left unmapped
(`SITE_ID = CODE`) and reported as orphans in the run log — check that log before
concluding a screen has no audience.

---

## Choosing the right rows

This is the section that prevents wrong numbers. Locomizer ships pre-aggregated
totals **alongside** their own segment breakdowns, and the segments overlap: one
panellist can be counted as both a pedestrian and a resident in the same hour, and
again in each hour they linger. **Summing rows is almost always wrong.**

Measured on the March 2025 export (243 screens, 320,286 rows):

| What you might do | What happens |
|---|---|
| `SUM` the whole Footfall table | Total Population inflated **8.08×** |
| Sum `HOUR` 0–23 for a daily total | Inflated **1.46×** |
| Sum movement segments | Exceeds the true total in **37.7%** of cells |
| Sum visitation segments | Exceeds the true total in **15.8%** of cells |

The pipelines therefore **delete nothing** and add a flag column instead.
Selecting the right rows is the analyst's job, at query time, every time.

### Footfall — flag is `IS_GRAND_TOTAL`

| Need | Filter |
|---|---|
| Daily / monthly audience (deduplicated) | `IS_GRAND_TOTAL = 1 AND HOUR = 25` |
| Hourly curve — "busiest times" | `IS_GRAND_TOTAL = 1 AND HOUR < 25` |
| Movement mix (pedestrians vs car…) | `IS_GRAND_TOTAL = 0 AND VISITATION_MODALITY = 'All'` |
| Visitation mix (residents vs transient…) | `IS_GRAND_TOTAL = 0 AND MOVEMENT_MODALITY = 'All'` |

`HOUR = 25` is Locomizer's all-day sentinel and the **only** deduplicated daily
count available. Never include it in an hourly chart; never omit it from a daily
KPI.

Segment **percentages** are reliable. Segment **absolute volumes** overcount by
40–50%. Always render segment breakdowns as share-of-total.

### Demographics — no flag, but pick one modality

Each `MOVEMENT_MODALITY` row is an independent profile that sums to 100%. Never
aggregate across `All`, `Pedestrians` and `Non_Pedestrians` — choose one. `HOUR`
is 0–23 with no sentinel.

### Brand Affinity — flag is `IS_DEFAULT`

`IS_DEFAULT = 1` marks the `All` + `All` rows. A chart that forgets it mixes 3–6
segment rows per screen/hour/category and lands **5–48 index points** off.

Only six modality combinations exist: `MOVEMENT = All` pairs with any visitation
type; `Pedestrians` and `Non_Pedestrians` pair only with `VISITATION = All`.

Unlike Footfall, the `All` + `All` row is **kept and used** here — the affinity
index is a normalised characteristic of the audience, not a sum of parts.

---

## Footfall

`process_footfall.py` v3.6.1 → `data/processed/footfall/<name>.parquet`
Grain: `SITE_ID` × `DATE` × `HOUR` × `MOVEMENT_MODALITY` × `VISITATION_MODALITY`.
No rows removed.

| Column | Type | Notes |
|---|---|---|
| `CODE` | str | as delivered by Locomizer |
| `SITE_ID` | str | canonical join key |
| `DATE` | date | built from DAY + MONTH + YEAR, which are then dropped |
| `HOUR` | int8 | 0–23, or **25 = all-day sentinel** |
| `RADIUS` | int16 | viewshed radius in metres (canonical radius per screen) |
| `MOVEMENT_MODALITY` | category | All / Pedestrians / Cyclists / Car_City / Car_Highway |
| `VISITATION_MODALITY` | category | All / Residents / Workers / Transient |
| `IS_GRAND_TOTAL` | int8 | 1 where both modalities are `All` |
| `NUMBER_OF_USERS` | int32 | raw panellists detected |
| `NUMBER_OF_SIGNALS` | int32 | raw device signals |
| `DWELL_TIME` | float32 | fraction of the interval, 0–1 |
| `REACH` | float32 | % of the national panel at this location |
| `EXTRAPOLATED_NUMBER_OF_USERS` | float32 | **PaS** — mobile-carrying population |
| `EXTRAPOLATED_NUMBER_OF_SIGNALS` | float32 | |
| `EXTRAPOLATED_USERS_2` | float32 | **Total Population** |
| `EXTRAPOLATED_SIGNALS_2` | float32 | |
| `NUMBER_OF_EYE_CONTACTS` | int32 | raw |
| `NUMBER_OF_EYE_CONTACTS_WEIGHTED` | int32 | |
| `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS` | float32 | **OTS** |
| `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED` | float32 | |
| `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED_2` | float32 | |
| `SOURCE_FILE` | str | audit trail |

Dropped on purpose: `DISPLAY NAME`, `LATITUDE`, `LONGITUDE` — the master site list
owns them. Do not reintroduce them from the Locomizer export.

### The three headline KPIs

All three are pre-computed by Locomizer and share one filter
(`IS_GRAND_TOTAL = 1 AND HOUR = 25`). **Never recompute them from
`NUMBER_OF_USERS`.**

| KPI | Column | Meaning |
|---|---|---|
| Total Population | `EXTRAPOLATED_USERS_2` | whole population passing |
| PaS (Passage) | `EXTRAPOLATED_NUMBER_OF_USERS` | mobile-carrying population |
| OTS (Opportunity to See) | `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS` | moving toward the screen, inside its azimuth cone |

Quote **OTS** for impressions claims — it is the only metric that accounts for
which way the screen faces. Eye contacts depend on the `azimuth` recorded in the
master list, so an OTS figure is only as good as that azimuth record.

### Why `HOUR = 25` and `(All, All)` are kept

Pipeline versions ≤ 2.x deleted `(All, All)` believing it equalled the segment
sum; ≤ 3.0 deleted `HOUR = 25` believing hours 0–23 could be summed. Both were
measured wrong against the full March 2025 export. The reproducible SQL audit
lives in `docs/footfall_methodology/`.

---

## Demographics — wide

`process_demographics.py` v1.8.0 →
`data/processed/demographics/clean/<name>_clean.parquet`
Grain: `SITE_ID` × `YEAR_MONTH` × `HOUR` × `MOVEMENT_MODALITY`.

| Column | Type | Notes |
|---|---|---|
| `CODE` | str | extracted from the first 5 chars of `DISPLAY NAME` |
| `SITE_ID` | str | canonical join key |
| `YEAR_MONTH` | str | "YYYY-MM" |
| `HOUR` | int8 | 0–23, no sentinel |
| `RADIUS` | int16 | |
| `MOVEMENT_MODALITY` | category | All / Pedestrians / Non_Pedestrians |
| `T1_1AGE{band}{M\|F}_REACH` | float32 | % of audience, 0–100 |
| `T9_2_P*_REACH` | float32 | social grade, % |
| `T13_*`, `T14_*` | float32 | occupation / industry segments, % |
| `SOURCE_FILE` | str | |

Note the asymmetry: Demographics needs `CODE` **extracted** from `DISPLAY NAME`,
while Footfall and Brand Affinity ship a clean `CODE` column.

### Age columns

Pattern `T1_1AGE{band}{gender}_REACH`, gender `M` or `F`. Bands: individual years
0–19, then 5-year bands 20–24 … 80–84, then `GE_85`.

**All 37 total columns were dropped** as verified-exact duplicates:
`T1_1AGETM_REACH`, `T1_1AGETF_REACH`, every `T1_1AGE{band}T_REACH`, and
`T1_1AGETT_REACH` (always 100.0). Recreate any total as `M + F` in a measure — do
not expect the column to exist.

### Social grade codes

| Code | Meaning | | Code | Meaning |
|---|---|---|---|---|
| PA | Employers and managers | | PE | Manual skilled |
| PB | Higher professional | | PF | Semi-skilled |
| PC | Lower professional | | PG | Unskilled |
| PD | Non-manual | | PH | Own account workers |

---

## Demographics — age-long

Same script → `data/processed/demographics/age_long/<name>_age_long.parquet`

| Column | Type | Notes |
|---|---|---|
| `CODE` | str | |
| `SITE_ID` | str | canonical join key |
| `YEAR_MONTH` | str | "YYYY-MM" |
| `HOUR` | int8 | 0–23 |
| `RADIUS` | int16 | |
| `MOVEMENT_MODALITY` | category | All / Pedestrians / Non_Pedestrians |
| `AGE_BRACKET` | ordered category | see below |
| `GENDER` | category | M / F |
| `REACH_PCT` | float32 | % of audience |
| `SOURCE_FILE` | str | |

`AGE_BRACKET` is an **ordered** categorical, so Power BI and pandas sort the axis
without a helper column:

`Under 18` → `18-24` → `25-34` → `35-44` → `45-54` → `55-64` → `65+`

Under-18s are grouped because minors are not addressable OOH targets; `65+` folds
five sparse bands together; `18-24` is assembled from individual years 18 and 19
plus the 20–24 band.

If Locomizer ships an age column whose prefix is not in `AGE_BRACKET_MAP`, the
script raises `ValueError` rather than silently dropping that audience. Adding the
prefix to the map is the only fix needed.

Use this table for any age chart. Use the wide table only when you need
single-year granularity, social grade, or occupation / industry segments.

---

## Brand Affinity

`process_brand_affinity.py` v1.5.0 →
`data/processed/brand_affinity/<name>_clean.parquet`
Grain: `SITE_ID` × `YEAR_MONTH` × `HOUR` × `MOVEMENT` × `VISITATION` × `CATEGORY`.

| Column | Type | Notes |
|---|---|---|
| `CODE` | str | |
| `SITE_ID` | str | canonical join key |
| `YEAR_MONTH` | str | "YYYY-MM" |
| `HOUR` | int8 | 0–23 — **converted** from `TIME_INTERVAL` 1–24 |
| `RADIUS` | int16 | |
| `MOVEMENT_MODALITY` | category | All / Pedestrians / Non_Pedestrians |
| `VISITATION_MODALITY` | category | All / Residents / Workers / Transient |
| `IS_DEFAULT` | int8 | 1 where both modalities are `All` |
| `BRAND_AFFINITY_CATEGORY_NAME` | category | 11 POI categories |
| `BRAND_AFFINITY_INDEX` | float32 | **primary metric**, national average = 100 |
| `BRAND_AFFINITY_DWELL_TIME` | float32 | dwell time of the target audience, % |
| `PROPORTION_OF_TARGET_USERS` | float32 | % of audience with positive affinity |
| `SOURCE_FILE` | str | |

Dropped: `DISPLAY NAME`; `TIME_INTERVAL_DESCRIPTION` (1-to-1 with `HOUR`, so
rebuild the label from `HOUR` if a visual needs it);
`BRAND_AFFINITY_PROFILING_TIME_INTERVAL` (constant `08_22`, the window Locomizer
uses to learn affinity profiles); `DAY_START` / `DAY_END` (always the first and
last day of the month).

Read the category values from the data rather than hardcoding a list.

### Reading the index

- `> 100` — the audience over-indexes for this category. Above ~150 is a strong
  targeting story for a client.
- `< 100` — under-indexes.
- Values above 200, occasionally above 16,000, are **genuine hotspots, not
  errors**. Never winsorise or cap during preprocessing — cap in the visual layer
  only, and say so in the caption.

Compare indices **within** a category across screens, or rank categories **within**
one screen. An average of indices across unrelated categories has no meaning.

---

## Master site list

`data/processed/sites/master_sites_unified.csv` — 35 columns, built by
`build_master_sites.py`. Single source of truth for screen metadata.

| Column | Use |
|---|---|
| `MM ID` / `NEW MM ID` | legacy and new screen identity, resolved into `SITE_ID` |
| `Display Name` | human-readable screen name |
| `Network` | URBAN / CAMPUS / LIFESTYLE / LARGE FORMAT |
| `City`, `Address`, `County`, `Postcode` | location |
| `Latitude`, `Longitude` | maps and heatmaps |
| `asset.setting` | indoor / street.facing / outdoor |
| `azimuth` | screen facing, degrees — drives the eye-contact cone |
| `viewing.radius` | canonical radius used by the Footfall pipeline |

The folder also holds the crosswalk and audit files. The Power BI `Master_Sites`
query filters explicitly to `master_sites_unified.csv`, because reading the whole
folder would try to parse those other files as the 35-column master and corrupt
the dimension.

---

## Known data quirks

**Zero-data rows.** Locomizer emits placeholder rows where the panel was too small
to compute a reliable score. Demographics drops rows whose reach values are all
~0; Brand Affinity drops rows where index, dwell time and proportion are all zero
(33.2% of the Feb 2025 export, 36.9% of Mar 2025 — verified to flip to zero
together).

**Screens that disappear.** A fully-zeroed screen vanishes from the cleaned table
for that period. Observed: 50254 and 50255 in Feb 2025; 50022, 50254, 50255 in Mar
2025. If a client's screen is missing from a report, read the pipeline log before
assuming a bug — and tell the client the panel was too small, rather than
reporting zero audience.

**Segment overlap.** A panellist can be classified into more than one modality
within the same hour, which is why segment sums exceed the total. This is a
property of the panel methodology, not a data error.

**Two catchment radii.** From May 2026 Locomizer began shipping two radii per
screen. Footfall keeps each screen's canonical radius from the master list (the
radii differ ~4.3× because absolute counts grow with catchment size); Demographics
and Brand Affinity collapse the duplicate, which is lossless there because the
normalised values are byte-identical. See `docs/radius_canonicalisation.md`.

**Modality casing.** Footfall and Demographics arrive UPPERCASE from Locomizer;
Brand Affinity arrives Title Case. All pipelines normalise to Title Case. Expect
the inconsistency only when reading a raw CSV directly.

---

## Query recipes

Post-campaign totals for a screen selection and date range:

```python
ff = pd.read_parquet("data/processed/footfall/")
sel = ff[
    (ff.IS_GRAND_TOTAL == 1)
    & (ff.HOUR == 25)
    & (ff.SITE_ID.isin(site_ids))
    & (ff.DATE.between(start, end))
]
kpis = {
    "total_population": sel.EXTRAPOLATED_USERS_2.sum(),
    "pas":              sel.EXTRAPOLATED_NUMBER_OF_USERS.sum(),
    "ots":              sel.EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS.sum(),
}
```

Summing across screens and dates is correct here — deduplication is *within* a
screen-day, not across them.

Busiest hours:

```python
hourly = ff[(ff.IS_GRAND_TOTAL == 1) & (ff.HOUR < 25) & ff.SITE_ID.isin(site_ids)]
curve = hourly.groupby("HOUR")["EXTRAPOLATED_NUMBER_OF_USERS"].sum()
```

Visitation mix, as shares only:

```python
seg = ff[
    (ff.IS_GRAND_TOTAL == 0)
    & (ff.MOVEMENT_MODALITY == "All")
    & (ff.HOUR == 25)
    & ff.SITE_ID.isin(site_ids)
]
mix = seg.groupby("VISITATION_MODALITY", observed=True)["EXTRAPOLATED_USERS_2"].sum()
mix = (mix / mix.sum() * 100).round(1)
```

Top affinity categories for one screen:

```python
ba = pd.read_parquet("data/processed/brand_affinity/")
top = (
    ba[(ba.IS_DEFAULT == 1) & (ba.SITE_ID == site_id) & (ba.YEAR_MONTH == period)]
      .groupby("BRAND_AFFINITY_CATEGORY_NAME", observed=True)["BRAND_AFFINITY_INDEX"]
      .mean()
      .sort_values(ascending=False)
)
```

Averaging over hours within one category is fine — the index is a rate, not a
count.

Age profile for a campaign, weighted by screen size:

```python
age = pd.read_parquet("data/processed/demographics/age_long/")
age = age[(age.MOVEMENT_MODALITY == "All") & age.SITE_ID.isin(site_ids)]

weights = (
    ff[(ff.IS_GRAND_TOTAL == 1) & (ff.HOUR == 25) & ff.SITE_ID.isin(site_ids)]
      .groupby("SITE_ID")["EXTRAPOLATED_USERS_2"].sum()
)
age["W"] = age.SITE_ID.map(weights)
profile = (
    age.assign(WP=age.REACH_PCT * age.W)
       .groupby(["AGE_BRACKET", "GENDER"], observed=True)
       .apply(lambda g: g.WP.sum() / g.W.sum())
)
```

A plain `mean()` of `REACH_PCT` would give a 200-passer-by campus screen the same
weight as a city-centre screen with 40,000.

---

## When something is ambiguous

These numbers end up in client proposals, so a confident wrong number is worse
than a flagged uncertainty. If a screen is missing for a period, if codes do not
reconcile, or if a filter combination is not covered above, say so explicitly in
the output rather than picking the interpretation that looks tidiest.
