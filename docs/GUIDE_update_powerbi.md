# Guide — How to update the Power BI data

Dashboard: **MM_Dashbard__Final** · updated 26 Jul 2026

## How the dashboard reads its data (read this first)

Power BI does **not** read from the Git project folder (`micromedia-project`). Each table
points to its own folder under `MicroMedia_Dashboard\data\` and imports **every file** it
finds there (`Folder.Files`):

| Model table | Folder Power BI reads | Expected format |
|---|---|---|
| Footfall | `...\MicroMedia_Dashboard\data\footfall` | Parquet |
| Master_Sites | `...\MicroMedia_Dashboard\data\master_sites` | CSV, **35 columns** |
| Demographics | `...\MicroMedia_Dashboard\data\demographics` | Parquet |
| Brand_Affinity | `...\MicroMedia_Dashboard\data\brand_affinity` | Parquet |

Base path: `C:\Users\brafa\Documents\data-analyst\MicroMedia\MicroMedia_Dashboard\data\`

Because it imports the whole folder, you just **drop the new file into the folder** and
Refresh — no need to touch any query. If a file has more/fewer columns than expected, the
refresh fails (this is what causes the "1 of the loaded queries contained errors" message).

The tables join on **SITE_ID** (Footfall.SITE_ID → Master_Sites.SITE_ID). A site that sends
footfall but is missing from the master shows up in the counts **with no name** — that is the
case of the 6 orphans.

---

## A) Monthly update (a new Locomizer export arrived)

1. **Drop the 3 monthly CSVs** into the project input folders, keeping the structure:
   - `micromedia-project\data\raw\footfall\`
   - `micromedia-project\data\raw\demographics\`
   - `micromedia-project\data\raw\brand_affinity\`
   The filename must contain `footfall`, `demograph` or `brandaffinity`.

2. **Run the pipelines** (do not edit the code, just run):
   ```
   cd micromedia-project
   venv\Scripts\activate
   python scripts\rename_raw_chrono.py
   python scripts\process_footfall.py
   python scripts\process_demographics.py
   python scripts\process_brand_affinity.py
   ```
   Clean output lands in `data\processed\<dataset>\`. Check the run log: it warns if
   Locomizer added unexpected columns, or if a file was truncated at Excel's row limit.

3. **Copy the processed files into the folders Power BI reads:**
   - `data\processed\footfall\*.parquet` → `MicroMedia_Dashboard\data\footfall\`
   - `data\processed\demographics\...\*.parquet` → `MicroMedia_Dashboard\data\demographics\`
   - `data\processed\brand_affinity\*.parquet` → `MicroMedia_Dashboard\data\brand_affinity\`

4. **Open `MM_Dashbard__Final` in Power BI Desktop** and click **Home → Refresh**.
   Wait for all 4 tables to load.

5. **Check the cards:** the site total on Home should rise if new screens came in.
   If the refresh error appears, see section D.

> Never open a raw Locomizer CSV in Excel and save it — Excel caps files at 1,048,576 rows
> and silently truncates the rest. If you must inspect a CSV, use Notepad or Power Query.

---

## B) Fix the master (add orphans / resolve conflict)

Use **MicroMedia_Master_Site_List_Flagged.xlsx** as the task list — the coloured rows
(red = orphan, amber = conflict, grey = no data) are what needs adding/fixing.

1. Open the CSV that feeds the master:
   `MicroMedia_Dashboard\data\master_sites\` (the 35-column file).

2. **Orphans (red):** add one row per site — `SITE_ID` (new MM id), `Display Name`,
   `Address`, `County`, `Latitude_loco`, `Longitude_loco`, `azimuth_loco`, `Network`.
   They are: 10100, 10101, 10103, 30067, 50888 (Brown Thomas), 60004. Ask Locomizer for
   lat/long and azimuth.

3. **Conflict (amber):** site 10065 appears under two codes (legacy 50324 + new 10065).
   Confirm with Locomizer that they are the same screen and retire one code at source, so
   duplicated footfall stops arriving.

4. **Keep the 35 columns.** Do not add or remove columns from the CSV, or the refresh breaks.

5. Save the CSV, go back to Power BI and **Refresh**.

---

## C) Publish (if the dashboard is shared on the Power BI Service)

After the local refresh in Desktop: **Home → Publish** → choose the workspace. If a scheduled
refresh runs on the Service, it needs a Gateway pointing at the same folders.

---

## D) If the refresh errors ("1 of the loaded queries contained errors")

Most common causes, in order:
1. **Different columns** in a new file (Locomizer changed the layout) → check the pipeline log.
2. **Text where a number is expected** — e.g. azimuth arriving as `"N/A"` instead of blank.
3. File open/locked, or a parquet corrupted during the copy.

Open **Transform data (Power Query)** → the query with the error icon shows the failing step.

---

## Quick checklist

- [ ] Month's CSVs in the `raw\` folders
- [ ] `rename_raw_chrono.py` + 3 pipelines run with no errors in the log
- [ ] Parquets copied into the `MicroMedia_Dashboard\data\` folders
- [ ] Master CSV updated (orphans/conflicts), 35 columns kept
- [ ] Refresh in Power BI Desktop with no errors
- [ ] Site total on Home checks out
- [ ] (if applicable) Publish to the Service
