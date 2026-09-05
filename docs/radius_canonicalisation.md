# Catchment radius duplication — cross-dataset findings & handling

**Status:** implemented across all three pipelines (Sep 2026).
**Scripts:** `process_footfall.py` v3.6.1 · `process_demographics.py` v1.7.0 ·
`process_brand_affinity.py` v1.4.0.

## Summary

In **May 2026** Locomizer began shipping **two catchment radii** (50 m and
183 m) per screen instead of one. Left untreated, every screen appears twice,
which inflates any row-count-based aggregation. The correct handling is **not
the same across the three datasets**, because the scope and the nature of the
duplication differ. All findings below were **measured on the real exports**,
not assumed.

| | Footfall | Demographics | Brand Affinity |
|---|---|---|---|
| Months duplicated | May, Jun, Jul (**persistent, May onward**) | **May only** (reverted Jun/Jul) | **May only** (reverted Jun/Jul) |
| 50 m vs 183 m values | **Different** (absolute counts; 183 m ≈ 4.3× 50 m) | **Byte-identical** (normalised %) | **Byte-identical** (normalised index/%) |
| Correct fix | Keep master-canonical radius (mandatory) | Collapse duplicate (lossless) | Collapse duplicate (lossless) |
| Master consulted? | **Yes** (`viewing.radius`) | No | No |
| Orphan screens (not in master) | Dropped + flagged | Kept | Kept |

### Why the handling differs

Footfall carries **absolute audience counts**, which genuinely grow with
catchment size — a 183 m viewshed captures more people than a 50 m one
(measured on May 2026, All/All/HOUR=25: mean 50 m ≈ 5,004 vs 183 m ≈ 21,668,
ratio ≈ 4.3×, differing on 99.9% of keys). So footfall **must pick each
screen's canonical radius** from the master site list; keeping the wrong one
would ship wrong numbers.

Demographics and Brand Affinity carry **normalised** quantities — age/gender
reach **percentages** and the affinity **index** (base 100). These do not
change with catchment size, so the two radius rows are **byte-for-byte
identical**. The duplicate therefore carries no information; it only doubles
the row count. Collapsing to one row (keeping either radius) is **lossless**
and needs **no master file**.

## Evidence (real exports, 2026)

Radius distribution and duplication, by month (screens carrying **both** radii):

| Dataset | Mar | Apr | **May** | Jun | Jul |
|---|---|---|---|---|---|
| Footfall — dup screens | 0 | 0 | **257** | **256** | **255** |
| Demographics — dup screens | 0 | 0 | **259** | 0 | 0 |
| Brand Affinity — dup screens | 0 | 0 | **259** | 0 | 0 |

Radius values are identical across 50 m / 183 m for the normalised datasets
(May 2026):

- **Demographics:** 134 metric columns × 18,648 common (CODE, HOUR,
  MOVEMENT_MODALITY) keys → **max abs diff = 0**.
- **Brand Affinity:** 410,256 common (CODE, HOUR, MOVEMENT, VISITATION,
  CATEGORY) keys, on INDEX / DWELL_TIME / PROPORTION → **max abs diff = 0**.

Master concordance (single-radius months, both normalised datasets):

- **Apr 2026:** 246 / 246 screens match `viewing.radius`, 0 disagreements,
  5 orphans not in master.
- **Jun/Jul 2026:** 229 / 230 match, **1 disagreement (screen `50288`: file
  183 m, master 50 m)**, 28 orphans.

## Implementation per pipeline

**Footfall — `process_footfall.py` v3.6.0 / v3.6.1**
`load_radius_lookup()` builds `{CODE → viewing.radius}` from the master;
`remove_non_canonical_radius()` keeps only each screen's canonical-radius rows.
Trigger-gated (only files with >1 radius per screen are touched). Orphan CODEs
(absent from the master) are **dropped and flagged** per file and in the run
summary (14 such screens in May 2026). Runs **before** DATE/CASE/FLAG/SITE_ID
so every downstream count reflects the de-duplicated data.

**Demographics — `process_demographics.py` v1.7.0**
`collapse_redundant_radius()` keeps one row per
`(CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY)`, retaining the **smallest**
available radius (deterministic; values identical so lossless). No master
dependency; orphan screens are **kept**. Runs after `build_year_month_column`.

**Brand Affinity — `process_brand_affinity.py` v1.4.0** (this change)
`collapse_redundant_radius()` mirrors demographics, with the wider Brand
Affinity key:
`(CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY, VISITATION_MODALITY,
BRAND_AFFINITY_CATEGORY_NAME)`. Runs **after** the zero-row filter and before
IS_DEFAULT / the shape report / export, so every downstream count reflects the
de-duplicated data. Master **not** consulted; orphans **kept**.

### Why not master-canonical for Demographics / Brand Affinity

Because the two radii are identical, collapsing is already lossless. Switching
these two to footfall's master-canonical method would add a master-file
dependency **and** drop the 14 May orphan screens (`10065`, `10100`–`10105`,
`30067`, `30068`, `50888`, `60004`, `60010`, `70001`, `70002`) for **zero
numerical benefit**. So the two normalised datasets use `collapse`, and only
footfall — whose radii differ — uses the master.

## Production run — Brand Affinity v1.4.0

18 / 18 files OK. **May 2026: 820,512 raw → 745,642 after zero-filter →
372,821 clean** (collapse removed 372,821 identical duplicate rows). All 17
single-radius months were a **no-op** (`0 duplicate row(s) removed`), confirming
the trigger.

## Data-quality watch items

- **Screen `50288`** reports radius 183 m in Jun/Jul but the master says 50 m.
  This does **not** affect Demographics/Brand Affinity (they do not consult the
  master) nor footfall's duplicated months (it acts only on duplication), but
  the master entry is worth reconciling.
- **14 orphan CODEs** appear in May not present in the master
  (`10065`, `10100`–`10105`, `30067`, `30068`, `50888`, `60004`, `60010`,
  `70001`, `70002`). Collapse **keeps** them (Demo/BA); footfall **drops +
  flags** them. Add them to the master or confirm they are expected test IDs.
- If a **future month** duplicates radii again in Demographics/Brand Affinity,
  the collapse trigger handles it automatically — no code change needed.
