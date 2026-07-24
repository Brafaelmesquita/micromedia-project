# feat(report): exact-date header card across client tabs + site radius reference layer

**Tag:** `dashboard-v2.8.0` · **Layer:** report + semantic model (no pipeline change) · **Numbers:** unchanged (layout/visual only)

## Summary

Three client-facing aesthetic changes to the dashboard:

1. The blue header card (`Header Title`) now shows the **exact start and end dates** of the selected period instead of a month range.
2. The header card and the "Who you'll reach" text box are **replicated across the 5 client tabs** (Home, Overview, Demographics, Site Map, Audience Segments) for a consistent header.
3. The Site Map now shows each screen's **viewshed radius as a true metric circle** (real metres, scales with zoom) via a GeoJSON reference layer on the existing Azure Maps visual.

No data or KPI numbers change.

## 1. Header card — exact dates

`Header Title` measure rewritten to derive the period from `Footfall[DATE]` (daily grain) instead of `Footfall[YEAR_MONTH]` (monthly):

- `MinDate`/`MaxDate` = `CALCULATE ( MIN|MAX ( Footfall[DATE] ), Footfall[HasValidSite] = TRUE () )`, so the label tracks the exact first/last day with data in the current selection and respects the date-range slicer.
- Output e.g. `246 sites · 1 Mar – 31 May 2026` (same-year abbreviates the first year; cross-year spells out both).
- Site count logic unchanged (`DISTINCTCOUNT ( Master_Sites[MM ID] )`).
- Card height adjusted `32 → 33` for text fit.

## 2. Header replicated across client tabs

The `Header Title` card (measure-bound, page-independent) and the static "Who you'll reach" text box were copied to Home, Overview, Demographics, Site Map and Audience Segments at matching X/Y. Each card recalculates against its own page filters. Old duplicates on the affected tabs were removed and re-created (new visual IDs).

## 3. Site Map — viewshed radius circles

Real metric circles were needed ("circle sized by each site's radius in metres"). The Azure Maps bubble layer only draws **fixed-pixel** radii, so a **GeoJSON reference layer** was used instead — it renders true geographic polygons that scale with zoom.

- Generator: `scripts`-style one-off in `docs/` produces `docs/site_radius_circles.geojson` — one 64-vertex circular polygon per site.
- Coordinates: `Latitude_loco` / `Longitude_loco` (same as the map's bubble layer, so circles align).
- Radius source: **`viewing.radius_loco`** from the master site list (confirmed authoritative). 222 circles — 137 at 50 m, 85 at 183 m. A second source, `Footfall[RADIUS]`, disagrees on ~61 sites and was not used.
- Loaded via Azure Maps → Reference layer → File upload; the file is embedded under `StaticResources/RegisteredResources/`.
- The bubble layer is kept on top for clickable points; circles sit underneath as the coverage overlay.

### Alternatives evaluated

- **Icon Map Pro** — supports metric circles, but production use is paid (free developer licence only). Rejected.
- **Deneb (Vega-Lite)** — free, data-bound, true metres, but no street base map / slippy zoom by default. Spec kept in the guide for reference; not shipped.
- A new **`Site Radius (m)`** measure (`MAX ( Footfall[RADIUS] )`, grand-total/HOUR 25) was added during exploration and left in the model; the final reference-layer approach does not use it.

## Scope / impact

- **Changed (semantic model):** `_Measures.tmdl` (`Header Title` rewrite, new `Site Radius (m)`).
- **Changed (report):** 5 client pages under `definition/pages/**` (card + text box, Site Map reference layer), `report.json`, `pages.json`, `StaticResources/RegisteredResources/site_radius_circles*.geojson`.
- **New (docs):** `docs/GUIA_header_card_radius_map.md`, `docs/site_radius_circles.geojson`, this record.
- **Unchanged:** all pipelines, processed data, KPI numbers, QA pages.

## Notes for committing

- The working tree also shows large **EOL/whitespace-only churn** across many untouched files (README, scripts, QA pages, most tmdl tables) — Power BI / editor re-save. Commit this stage with **scoped `git add`** of the paths above only; do **not** `git add -A`. A `.gitattributes` to pin LF for `*.tmdl`/`*.json`/`*.pbir` would stop the recurring churn (separate cleanup).
