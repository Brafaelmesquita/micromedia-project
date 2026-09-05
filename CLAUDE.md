# CLAUDE.md

Working notes for anyone — human or AI — making changes in this repository.
Read this before touching the pipelines, the semantic model, or the data.

## What this is

A monthly data pipeline plus a Power BI project that turn Locomizer's audience
exports into pre- and post-campaign reports for Micromedia's DOOH screen network
in Ireland. Every output answers three questions: **WHO** is the audience,
**WHERE** are they, **WHEN** can they be reached.

The repository is the single source of truth: the Python scripts write to
`data/processed/`, and Power BI reads the same folders. There is no second data
location to keep in sync.

## Non-negotiables

**Never commit data.** `data/raw/` and `data/processed/` are git-ignored and must
stay that way. The repository is public. Never commit Locomizer rows, audience
figures or screen coordinates, and do not paste real audience numbers into
anything public.

**Never sum rows blindly.** Locomizer ships pre-aggregated totals alongside
overlapping segment breakdowns — the same panellist can be a pedestrian *and* a
resident in the same hour, and is counted again for every hour they linger. A
naive `SUM` over Footfall inflates Total Population **8.08×**. Use the flag
columns:

- Footfall daily KPI → `IS_GRAND_TOTAL = 1 AND HOUR = 25`
- Footfall hourly curve → `IS_GRAND_TOTAL = 1 AND HOUR < 25`
- Brand Affinity → `IS_DEFAULT = 1`
- Demographics → pick one `MOVEMENT_MODALITY`; never aggregate across them

Segment percentages are reliable; segment absolute volumes are not. Render
breakdowns as share-of-total.

**Join on `SITE_ID`, never `CODE`.** `CODE` is the ID as Locomizer delivered it
and arrives under two different schemes depending on the export; `SITE_ID` is the
canonical ID resolved by the crosswalk. Joining on `CODE` silently drops rows.

**Never create a subfolder inside a processed data folder.** Power BI's
`Folder.Files` reads recursively, so a folder of older copies silently doubles
the audience.

Full detail — schemas, column meanings, quirks, query recipes — is in
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md). Read it before writing any
query, DAX measure or pandas transformation.

## Pipeline

Run order matters; the first two are prerequisites:

```bash
python scripts/rename_raw_chrono.py      # canonical raw filenames
python scripts/build_master_sites.py     # master list + SITE_ID crosswalk
python scripts/process_footfall.py       # v3.6.1
python scripts/process_demographics.py   # v1.8.0 -> clean/ and age_long/
python scripts/process_brand_affinity.py # v1.5.0
```

Drop new monthly CSVs into `data/raw/<dataset>/` and re-run — no code edits.
Filenames must contain `footfall`, `demograph` or `brandaffinity`.

**Always read the run log.** Each script reports columns Locomizer added that it
did not expect, files truncated at Excel's row limit, and codes that could not be
matched to the master (orphans). A silent dashboard bug usually announced itself
in that log first.

## Power BI

The project is `pbix/Micromedia_OOH_Dashboard.pbip` (PBIP text format, so the
report and semantic model diff cleanly).

Every source resolves its path from one Power Query parameter, **`DataFolder`**,
pointing at `data/processed`. To run on another machine, change that parameter
and nothing else: *Transform data → Manage parameters*.

The `Master_Sites` query filters its folder explicitly to
`master_sites_unified.csv`. Do not remove that filter — the folder holds other
files, and parsing them as the 35-column master corrupts the dimension that the
whole model joins on.

Renaming the PBIP means renaming three things together (`.pbip`, `.Report/`,
`.SemanticModel/`) **and** the two internal path references, or the project will
not open.

## Conventions

- **Language:** English, Irish/UK spelling — *visualisation*, *normalised*,
  *colour*.
- **Commits:** conventional commits. Explain *why*, with the evidence, not just
  what changed.
- **Changing a pipeline:** bump `__version__` and add a changelog entry in the
  module docstring stating what changed **and the empirical evidence for it**.
  Every existing behaviour in these scripts was measured, not assumed — match
  that bar.
- **Never winsorise or cap** affinity indices in preprocessing. Values above 200
  are real signal; cap in the visual only, and say so in the caption.
- **Averaging percentages across screens:** weight by that screen's
  `EXTRAPOLATED_USERS_2`, never a plain mean — otherwise a quiet campus screen
  counts as much as a city-centre one.
- **Line endings** are pinned in `.gitattributes` (CRLF under `pbix/`, LF
  elsewhere) because Power BI rewrites its files on every open. Do not remove it.

## When something is ambiguous

These numbers reach client proposals, so a confident wrong number is worse than a
flagged uncertainty. If a screen is missing for a period, if IDs do not
reconcile, or if a filter combination is not covered here, say so explicitly
rather than picking the interpretation that looks tidiest.
