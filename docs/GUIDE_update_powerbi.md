# Guide — How to update the Power BI data

Dashboard: **Micromedia_OOH_Dashboard** (`pbix/Micromedia_OOH_Dashboard.pbip`)

## How the dashboard reads its data (read this first)

Power BI reads the pipeline output **directly from this repository**. There is no
copy step and no second data folder to keep in sync — the scripts write, Power BI
reads, same place.

Every table resolves its path from a single Power Query parameter, **`DataFolder`**,
which points at `micromedia-project\data\processed`:

| Model table | Folder (relative to `DataFolder`) | Format |
|---|---|---|
| Footfall | `\footfall` | Parquet |
| Demographics | `\demographics\clean` | Parquet |
| Demographics_AgeLong | `\demographics\age_long` | Parquet |
| Brand_Affinity | `\brand_affinity` | Parquet |
| Master_Sites | `\sites` → `master_sites_unified.csv` | CSV, **35 columns** |

To point the project at a different machine or clone, change `DataFolder` only:
**Transform data → Manage parameters → `DataFolder`**.

Each table imports **every file** in its folder (`Folder.Files`), so adding a new
month means dropping a file in — no query edits. Two consequences worth knowing:

- **Do not create subfolders** inside those data folders. `Folder.Files` reads
  recursively, so a stray subfolder holding older copies would silently double the
  data.
- **Master_Sites is the exception.** Its folder holds several files, so the query
  filters explicitly to `master_sites_unified.csv`. Without that filter Power BI
  would try to parse the crosswalk and the audit spreadsheets as the 35-column
  master and corrupt the dimension.

The tables join on **SITE_ID** (`Footfall.SITE_ID` → `Master_Sites.SITE_ID`). A
site that sends footfall but is missing from the master shows up in the counts
**with no name** — those are the orphans, see section B.

---

## A) Monthly update (a new Locomizer export arrived)

1. **Drop the 3 monthly CSVs** into the raw folders, keeping the structure:
   - `data\raw\footfall\`
   - `data\raw\demographics\`
   - `data\raw\brand_affinity\`

   The filename must contain `footfall`, `demograph` or `brandaffinity`.

2. **Run the pipelines** in this order (do not edit the code, just run):

   ```
   cd micromedia-project
   venv\Scripts\activate
   python scripts\rename_raw_chrono.py      # canonical raw filenames
   python scripts\build_master_sites.py     # master list + SITE_ID crosswalk
   python scripts\process_footfall.py
   python scripts\process_demographics.py
   python scripts\process_brand_affinity.py
   ```

   The order matters: `rename_raw_chrono.py` standardises the incoming filenames,
   and `build_master_sites.py` produces the crosswalk that the three pipelines use
   to resolve `SITE_ID`.

   Clean output lands in `data\processed\<dataset>\`. **Read the run log** — it
   warns if Locomizer added unexpected columns, if a file was truncated at Excel's
   row limit, or if codes could not be matched to the master (orphans).

3. **Open `Micromedia_OOH_Dashboard.pbip`** in Power BI Desktop and click
   **Home → Refresh**. Wait for all tables to load.

4. **Check the cards:** the site total on Home should rise if new screens came in.
   If the refresh errors, see section D.

> Never open a raw Locomizer CSV in Excel and save it — Excel caps files at
> 1,048,576 rows and silently truncates the rest. If you must inspect a CSV, use
> Notepad or Power Query.

---

## B) Fix the master (add orphans / resolve conflicts)

Use **MicroMedia_Master_Site_List_Flagged.xlsx** as the task list — the coloured
rows (red = orphan, amber = conflict, grey = no data) are what needs attention.

The authoritative orphan list is the one printed by the **current** pipeline run,
not a list written down here; codes come and go as Locomizer changes its exports.
Read the log first.

1. Open the master source spreadsheet under `data\raw\sites\`, fix it there, and
   re-run `build_master_sites.py`. Do **not** hand-edit
   `data\processed\sites\master_sites_unified.csv` — it is generated output and
   the next run overwrites it.

2. **Orphans (red):** add one row per site — new MM ID, `Display Name`, `Address`,
   `County`, `Latitude`, `Longitude`, `azimuth`, `Network`. Ask Locomizer for
   lat/long and azimuth if they are missing.

3. **Conflicts (amber):** the same physical screen arriving under two codes (a
   legacy MM ID and a new one). The crosswalk resolves both to one `SITE_ID`, so
   the dashboard is correct either way — but confirm with Locomizer and retire one
   code at source, so duplicated footfall stops arriving.

4. **Keep the 35 columns.** Adding or removing a column breaks the refresh,
   because the Master_Sites query declares `Columns=35`.

5. Re-run `build_master_sites.py`, then **Refresh** in Power BI.

---

## C) Publish (Power BI Service)

After the local refresh in Desktop: **Home → Publish** → choose the workspace.
Distribute through the Power BI **app**, not the `.pbix`/`.pbip` file.

A scheduled refresh on the Service would need a Gateway pointing at this
repository's `data\processed` folder on a machine that stays on. Today the refresh
is manual and monthly, which matches the delivery cadence.

---

## D) If the refresh errors ("1 of the loaded queries contained errors")

Most common causes, in order:

1. **Different columns** in a new file (Locomizer changed the layout) → check the
   pipeline run log first; it flags unexpected columns before the dashboard sees
   them.
2. **`DataFolder` points somewhere wrong** — after moving or re-cloning the repo,
   update the parameter.
3. **A stray file or subfolder** in one of the data folders. A non-Parquet file in
   a Parquet folder produces *"Parquet magic bytes not found in footer"*; a
   subfolder of old copies silently doubles the rows.
4. **Text where a number is expected** — e.g. azimuth arriving as `"N/A"` instead
   of blank.
5. File open or locked in another program.

Open **Transform data (Power Query)** → the query with the error icon shows the
failing step.

---

## Quick checklist

- [ ] Month's CSVs in the `data\raw\` folders
- [ ] `rename_raw_chrono.py` → `build_master_sites.py` → 3 pipelines run clean
- [ ] Run log read: no unexpected columns, orphans reviewed
- [ ] Master fixed at source (`data\raw\sites\`) and rebuilt, 35 columns kept
- [ ] Refresh in Power BI Desktop with no errors
- [ ] Site total on Home checks out
- [ ] (if applicable) Publish to the Service
