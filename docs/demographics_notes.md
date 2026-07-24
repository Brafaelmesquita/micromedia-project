# Demographics — known data quirks

Non-obvious characteristics of the Locomizer Demographics feed that the
pipeline and dashboard must handle. These are **not code bugs** — they are
properties of the source data that will silently corrupt a report if ignored.

## RADIUS: additive in Footfall, redundant in Demographics

Locomizer measures each screen over one or more concentric **catchment radii**
(e.g. 50 m and 183 m). The two feeds treat radius very differently:

- **Footfall** — radius is **meaningful and additive**. Each ring holds a
  *different* absolute population. For screen 50033 in May 2026, hour 14, the
  monthly `EXTRAPOLATED_USERS_2` was 33,380 at 50 m and 190,408 at 183 m; the
  Total Population (223,789) is the **sum** of both rings. Summing radii here is
  correct, and `Total Population (Hourly)` relies on it.

- **Demographics** — radius is **redundant**. The reach values are
  *percentages of the screen's audience*, and Locomizer returns the **same
  percentage profile for every radius** (verified: max abs difference = 0.0
  across all 97 reach columns). Summing radii therefore double-counts: the
  age/gender matrix reports each gender at ~100% and the columns sum to 2×
  Total Population.

**Rule:** never sum Demographics rows across `RADIUS`. The pipeline collapses
them to one row per `(CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY)` — see below.

## May 2026 dual-radius export

For the **May 2026** delivery only, Micromedia asked Locomizer to additionally
compute the 50 m radius for screens that normally run at 183 m, purely to
**compare the two rings**. This shipped as a second, duplicate set of rows in
the same CSV (raw row count ≈ 2× a normal month: 37,296 vs ~18,000).

- In Footfall the extra rows are the (legitimate, different) 50 m populations.
- In Demographics the extra rows are **identical percentage profiles**, so they
  double every audience total built on the age/gender breakdown.

All other 17 months (2024-12 through 2026-04) ship a single radius — this was a
one-off comparison request, not a standing change. Watch for it recurring if a
similar comparison is requested again.

## Fix (pipeline layer, v1.7.0)

`process_demographics.py` → `collapse_redundant_radius()` keeps one row per
`(CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY)`, retaining the smallest available
radius. It runs after `YEAR_MONTH` is built, so both the wide `_clean` and the
`age_long` exports are de-duplicated at source. No DAX change was needed; the
`Age Audience (Hourly)` measure stays as-is.

**Validation (screen 50033, May 2026, after re-run):**

| Hour  | Total Population | Male # | Female # | M + F   | Reconciles |
|-------|------------------|--------|----------|---------|------------|
| 14:00 | 223,789          | 110,735 (49.5%) | 113,054 (50.5%) | 223,789 | yes |
| 04:00 | 4,140            | 2,102 (50.8%)   | 2,038 (49.2%)   | 4,140   | yes |

Each cell now has 14 rows (7 brackets × 2 genders) summing to 100%, and the age
breakdown reconciles exactly to `Total Population (Hourly)`.
