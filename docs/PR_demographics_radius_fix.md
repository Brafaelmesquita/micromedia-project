# fix(demographics): collapse redundant catchment radius (May 2026 dual-radius export)

**Tag:** `dashboard-v2.7.0` · **Layer:** pipeline (`process_demographics.py` 1.6.0 → 1.7.0) · **Publish:** unblocked after Power BI refresh

## Summary

The "Who they are — hourly audience by age & gender" matrix reported audience at
**2.00× the true figure**: Male and Female each reproduced ~100% of Total
Population, so the age and gender columns summed to double the `Total Population`
column. Root cause was duplicate rows in the **May 2026** Demographics export,
not the DAX measure. Fixed at source in the pipeline; no model change required.

## Root cause

Locomizer measures each screen over one or more concentric **catchment radii**
(50 m and 183 m). For the May 2026 delivery only, Micromedia asked Locomizer to
additionally compute the 50 m radius for screens that normally run at 183 m,
purely to **compare the two rings**. This shipped as a second, duplicate set of
rows in the same CSV (raw rows ≈ 2× a normal month: 37,296 vs ~18,000).

- **Footfall:** the two radii are legitimately different, additive populations
  (screen 50033, hour 14: 33,380 at 50 m + 190,408 at 183 m = 223,789). Summing
  is correct; `Total Population (Hourly)` was never wrong.
- **Demographics:** reach values are *percentages of the screen's audience*, and
  Locomizer returned the **identical profile for both radii** (verified max abs
  difference = 0.0 across all 97 reach columns). The base measure
  `Age Audience (Hourly)` does `SUMX` over `MOVEMENT_MODALITY = "All"` without
  pinning `RADIUS`, so it summed both identical grids → 100% + 100% = 200%.

The 2× therefore appeared only on screens carrying both radii, which is why it
was inconsistent across the dashboard.

## Diagnostic evidence

Screen 50033, 2026-05, hour 14, `MOVEMENT_MODALITY = "All"`:

| RADIUS | GENDER | rows | Σ REACH_PCT |
|--------|--------|------|-------------|
| 50     | F      | 7    | 50.52 |
| 50     | M      | 7    | 49.48 |
| 183    | F      | 7    | 50.52 |
| 183    | M      | 7    | 49.48 |

Each radius alone is healthy (14 rows, M + F = 100). Two radii → 28 rows → 200.

Dataset-wide (18 months): only May 2026 carries two radii; 18,142 groups
affected, and every reach column is byte-for-byte identical across radii.

## Fix

`process_demographics.py` → new `collapse_redundant_radius()`, called after
`build_year_month_column()`. Keeps one row per
`(CODE, YEAR_MONTH, HOUR, MOVEMENT_MODALITY)`, retaining the **smallest available
radius** for determinism. Because it runs before export, **both** the wide
`_clean` and the `age_long` files are de-duplicated at source.

A naive `RADIUS = 50` filter in DAX was **rejected**: 262,712 groups carry only
one radius and it is not always 50, so a fixed pin would zero-out screens that
ship only the 183 m profile. `RADIUS` is kept in the schema (no measure
references it) — only the duplicate rows are removed. **No DAX change.**

## Validation (screen 50033, May 2026, after re-run)

| Hour  | Total Population | Male #          | Female #        | M + F   | Reconciles |
|-------|------------------|-----------------|-----------------|---------|------------|
| 14:00 | 223,789          | 110,735 (49.5%) | 113,054 (50.5%) | 223,789 | yes |
| 04:00 | 4,140            | 2,102 (50.8%)   | 2,038 (49.2%)   | 4,140   | yes |

Reproduced the DAX measure in pandas (`age_long` × `footfall`). Each cell now
has 14 rows summing to 100%; the age breakdown reconciles exactly to
`Total Population (Hourly)` at both hours. Totals match the live dashboard to
the unit. Re-ran all 18 months: only May 2026 changed (clean rows 36,284 →
18,142); the other 17 reprocessed with zero rows removed.

## Scope / impact

- **Changed:** `scripts/process_demographics.py` (v1.7.0), `docs/demographics_notes.md` (new).
- **Data:** `data/processed/demographics/**` regenerated (gitignored; requires
  a Power BI dataset refresh — done).
- **Unchanged:** Footfall pipeline, Brand Affinity pipeline, all DAX measures,
  Report and SemanticModel definitions.
- **Numbers change**, hence the tag bump; publish was blocked until this closed.

## Follow-ups (optional)

- Defensive DAX: average `Age Audience (Hourly)` across radii as a belt-and-
  suspenders guard if a dual-radius export ever recurs.
- Watch future exports for a repeat of the comparison request.
