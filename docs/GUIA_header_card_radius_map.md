# Guide — Header card (exact dates), replicate across 5 tabs, and radius bubbles

Aesthetic changes to the Micromedia OOH dashboard. Agreed scope:

1. `Header Title` card shows the **exact start/end dates** (day-level) of the selected period.
2. Card + "Who you'll reach" text box replicated across the **5 client tabs**: Home, Overview, Demographics, Site Map, Audience Segments.
3. Site Map bubbles sized by each site's **real viewshed radius in metres**.

> Delivery: step-by-step for you to apply in Power BI Desktop. No report files were changed by me. Git versioning in the final section.

---

## Diagnosis (current state)

- The **`Header Title`** measure already exists in `_Measures` and already renders `"246 sites · Mar 2026 – May 2026"`, but at **month** granularity (derived from `Footfall[YEAR_MONTH]`).
- The Site Map map is an **Azure Maps** visual (`azureMap`). **Size** bucket = `Total Population (Hourly)`, with `bubbleRadius = min = max = 6` → bubbles are currently **fixed size**.
- `Footfall[RADIUS]` = viewshed radius in metres. Verified in the data: **constant per site** (0 sites with more than one radius in the file), range **50–183 m**.
- Card height: original `32` → changed to `33` (looks good — keep it).

---

## 1. Header card with exact start/end dates

Replace the expression of the **`Header Title`** measure (keeps the site count; swaps month period for day-level).

```dax
Header Title =
VAR NSites   = DISTINCTCOUNT ( Master_Sites[MM ID] )
VAR MinDate  = CALCULATE ( MIN ( Footfall[DATE] ), Footfall[HasValidSite] = TRUE () )
VAR MaxDate  = CALCULATE ( MAX ( Footfall[DATE] ), Footfall[HasValidSite] = TRUE () )
VAR NoData   = ISBLANK ( MinDate )
VAR Period =
    SWITCH (
        TRUE (),
        NoData,                          "No period",
        MinDate = MaxDate,               FORMAT ( MinDate, "D MMM YYYY" ),
        YEAR ( MinDate ) = YEAR ( MaxDate ),
            FORMAT ( MinDate, "D MMM" ) & " – " & FORMAT ( MaxDate, "D MMM YYYY" ),
        FORMAT ( MinDate, "D MMM YYYY" ) & " – " & FORMAT ( MaxDate, "D MMM YYYY" )
    )
VAR SitesTxt = FORMAT ( NSites, "0" ) & " " & IF ( NSites = 1, "site", "sites" )
RETURN
    SitesTxt & " · " & Period
```

Result: `246 sites · 1 Mar – 31 May 2026` (same year abbreviates the first year; different years spell out both). It respects the date-range slicer — `MIN`/`MAX` of `Footfall[DATE]` reflect the exact first and last day with data in the selection.

**Steps in Power BI Desktop:**

1. **Data** pane → `_Measures` table → `Header Title` measure.
2. Paste the expression above into the formula bar → Enter.
3. Site Map: check the card. Move the date slicer to confirm start/end follow the selection.

Notes:
- `NSites` kept as in the original (`DISTINCTCOUNT(Master_Sites[MM ID])`), preserving the count you already see. To make the count react to screen/period filters, switch to `DISTINCTCOUNT(Footfall[CODE])`.
- Date format in UK/IE style (`D MMM YYYY`), consistent with the Irish market.

---

## 2. Replicate card + text box across the 5 client tabs

The card uses the `Header Title` measure (page-independent) and the text box is static text — both can be copied with no reconfiguration. On paste, each card recalculates against its own page filters.

**Steps:**

1. On the **Site Map** tab, click the `Header Title` card; hold **Ctrl** and also click the "Who you'll reach" text box (selects both).
2. **Ctrl + C**.
3. Go to **Home** → **Ctrl + V**. They paste at the **same position** (x/y) as the source — keeps alignment across tabs.
4. Repeat **Ctrl + V** on **Overview**, **Demographics**, **Audience Segments**.
5. If a target tab already has an old card/text box in that spot, delete the old one so they don't overlap.

Tips:
- To avoid misalignment, **don't drag** after pasting; if you need to adjust, use **Format → General → Properties → Position** and replicate the same X/Y on every tab.
- Card height is now `33` — apply the same value on all tabs for consistency.
- The text box reads "Who you'll reach" on every tab. For a different title per tab, edit the text after pasting (double-click the text box).
- For full consistency, group both (right-click → **Group**) before copying and treat them as one block.

---

## 3. Site Map bubbles with real radius in metres

**Azure Maps limitation.** Microsoft docs confirm the Azure Maps *bubble layer* draws circles with a **fixed pixel radius**; it can scale size proportionally to a value, but it **does not draw a geographic circle of X metres** that grows/shrinks with zoom.

**Icon Map Pro is not free.** The visual has a free *Developer License* to build in Power BI Desktop, but production use (publishing to clients) is **paid per usage** — so it doesn't fit a free requirement. Note the original free **Icon Map** draws data-bound circles too, but sized proportionally in **pixels** (min/max), not literal metres — same concept as Option A below.

Free options compared:

| Option | Real metres? | Data-bound (reacts to slicers)? | New visual / licence? |
|---|---|---|---|
| A. Size existing Azure Maps bubble by `[Site Radius (m)]` | No — proportional pixels | Yes | None |
| B. Azure Maps GeoJSON **reference layer** | **Yes** | No — static | None (built-in) |
| C. **Deneb** custom visual (Vega-Lite) | **Yes** | Yes | Free visual + a Vega spec |

> Key point: a site's viewshed radius is a **fixed physical property** — it does not change with date/demographic filters. So the "static" limitation of Option B mostly matters only for the *screen* filter (other sites' circles stay visible when you filter to a campaign's screens).

**Recommendation:** if a static coverage overlay is acceptable → **Option B** (free, native, true metres). If it must react to slicers → **Option C (Deneb)**.

First, create the radius measure in `_Measures` (used by A and C; B reads radius from the data):

```dax
Site Radius (m) =
CALCULATE (
    MAX ( Footfall[RADIUS] ),
    Footfall[IS_GRAND_TOTAL] = 1,
    Footfall[HOUR] = 25,
    Footfall[HasValidSite] = TRUE ()
)
```

### Option A — proportional bubbles on the existing Azure Maps (no new visual)

Keeps everything as-is; bubbles scale by radius but in pixels, not metres.

1. On the Azure Maps visual, set the **Size** bucket = `[Site Radius (m)]`.
2. **Format → Bubbles**: set **Min radius** (e.g. 4) and **Max radius** (e.g. 20) so bubbles scale across the 50–183 m range. Turn **Range scaling** on.

### Option B — GeoJSON reference layer — CHOSEN

Keeps the Azure Maps visual (street tiles + zoom). One **circular polygon per site** (real radius in metres), loaded as a **Reference Layer**. Draws true geographic circles that scale with zoom. Static (shows every site in the file, ignores slicers) — acceptable because the viewshed radius is a fixed physical property.

**The file is already generated: `docs/site_radius_circles.geojson`** — 222 circles, on the `_loco` coordinates the map already uses.

Radius source: **`viewing.radius_loco`** from the master site list (confirmed by Rafael as authoritative). 222 circles — 137 at 50 m, 85 at 183 m. (There is a second source, `Footfall[RADIUS]`, that disagrees on ~61 sites; not used.)

**Revert from Option C (Deneb):** on the Site Map, select the Deneb visual → Delete. The `Site Radius (m)` measure isn't needed by Option B (the GeoJSON is pre-computed) — keep it or delete it, your call.

**Load the reference layer:**
1. Select the Azure Maps visual → **Format** pane → **Reference layer** → **Type: File upload** → **Browse** → pick `docs/site_radius_circles.geojson`.
2. **Reference layer → Polygons**: set Fill colour `#29B6E8`, Fill transparency ~65%, Border colour `#003D52`, Border width 1. (Or leave blank to use the `color` property baked into the file.)
3. Keep the existing bubble layer for the clickable points; the circles sit under them as the coverage overlay.

Script used to generate the file (reproducible; from the project folder):

```python
import pandas as pd, math, json

s = pd.read_csv("data/processed/sites/master_sites_unified.csv")
s["CODE"] = s["MM ID"].astype(str).str.extract(r"(\d{5})")[0]
s = s.dropna(subset=["Latitude_loco","Longitude_loco","viewing.radius_loco"]).copy()

def circle(lat, lon, r_m, n=64):
    out=[]
    for i in range(n+1):
        a=2*math.pi*i/n
        dlat=(r_m/111320.0)*math.cos(a)
        dlon=(r_m/(111320.0*math.cos(math.radians(lat))))*math.sin(a)
        out.append([round(lon+dlon,6), round(lat+dlat,6)])
    return out

feats=[]
for _,r in s.iterrows():
    rad=float(r["viewing.radius_loco"])
    feats.append({
        "type":"Feature",
        "properties":{"MM ID": r["CODE"], "radius_m": int(rad), "radius_source":"viewing.radius_loco", "color":"#29B6E8"},
        "geometry":{"type":"Polygon","coordinates":[circle(float(r["Latitude_loco"]), float(r["Longitude_loco"]), rad)]}
    })

json.dump({"type":"FeatureCollection","features":feats}, open("docs/site_radius_circles.geojson","w"))
print(len(feats), "circles generated")
```

> Uses the `_loco` coordinates so circles line up with the map's bubble layer, and `viewing.radius_loco` for the radius.

### Option C — Deneb (free custom visual, true metres, data-bound) — NOT USED (kept for reference)

For true metric circles that **also react to the slicers**, use **Deneb** (free on AppSource). It renders a Vega-Lite spec bound to the Power BI data; each circle's pixel radius is computed from metres at its latitude.

**Two caveats (set expectations):**
- Deneb has **no street/tile base map** and no slippy pan/zoom by default. The spec adds a faint graticule for context, but you lose the street map the Azure Maps visual shows. If street context is essential, prefer Option B.
- Framing is **fixed** (centred on Dublin below). Sites in other cities fall outside until you adjust `center`/`scale`.

**Setup:**
1. **Insert → More visuals → Get more visuals** → search **"Deneb"** → **Add** (free).
2. Fields (Values): `Master_Sites[MM ID]`, `Master_Sites[Longitude_loco]`, `Master_Sites[Latitude_loco]`, `[Site Radius (m)]`.
3. Open Deneb → **Edit** → language **Vega-Lite** → paste the spec below → **Apply**.

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "description": "Micromedia — site viewshed radius (true metres)",
  "width": "container",
  "height": "container",
  "background": "transparent",
  "projection": { "type": "mercator", "center": [-6.2603, 53.3498], "scale": 228000 },
  "layer": [
    {
      "data": { "graticule": { "stepMinor": [0.05, 0.05] } },
      "mark": { "type": "geoshape", "stroke": "#E3E9EC", "strokeWidth": 0.4, "fill": null }
    },
    {
      "data": { "name": "dataset" },
      "transform": [
        { "filter": "isValid(datum['Latitude_loco']) && isValid(datum['Longitude_loco'])" },
        { "calculate": "datum['Site Radius (m)'] * (2*PI*228000) / (cos(datum['Latitude_loco']*PI/180) * 40075016.686)", "as": "rpx" },
        { "calculate": "PI * datum.rpx * datum.rpx", "as": "sizePx2" }
      ],
      "mark": { "type": "circle", "fill": "#29B6E8", "fillOpacity": 0.35, "stroke": "#003D52", "strokeWidth": 1 },
      "encoding": {
        "longitude": { "field": "Longitude_loco", "type": "quantitative" },
        "latitude": { "field": "Latitude_loco", "type": "quantitative" },
        "size": { "field": "sizePx2", "type": "quantitative", "scale": null, "legend": null },
        "tooltip": [
          { "field": "MM ID", "type": "nominal", "title": "Site" },
          { "field": "Site Radius (m)", "type": "quantitative", "title": "Radius (m)" }
        ]
      }
    },
    {
      "data": { "name": "dataset" },
      "transform": [ { "filter": "isValid(datum['Latitude_loco']) && isValid(datum['Longitude_loco'])" } ],
      "mark": { "type": "circle", "size": 8, "fill": "#003D52" },
      "encoding": {
        "longitude": { "field": "Longitude_loco", "type": "quantitative" },
        "latitude": { "field": "Latitude_loco", "type": "quantitative" }
      }
    }
  ]
}
```

**How it works / tuning:**
- Metres→pixels lives in the two `calculate` steps: `rpx` = pixel radius, `sizePx2` = area (the `circle` mark uses area in px²). At `scale = 228000`, a 50 m radius ≈ 3 px, 183 m ≈ 11 px.
- **To zoom**, change `scale` in `projection` **and** the `228000` inside the first `calculate` — both must match or circles lose metric proportion.
- **For another city**, change `center` (`[lon, lat]`).
- Circles are semi-transparent, so overlapping coverage renders darker. Reacts to the Gender/Age/date slicers automatically.
- Optional: a real street base map is possible in Deneb via raster tile marks, but it's substantially more complex and external tiles may be blocked in the Power BI service — Option B is simpler if street tiles are required.

---

## 4. Versioning (git)

Same repo convention (conventional commits + `dashboard-vX.Y.Z` tag; latest = `dashboard-v2.7.0`).

```bash
# 1. close the .pbip in Power BI Desktop only when committing
git checkout -b feat/header-card-radius-map

# 2. make the edits in Power BI Desktop and save (this updates the PBIP files)

# 3. one commit per change
git add MM_Dashbard__Final.SemanticModel/definition/tables/_Measures.tmdl
git commit -m "feat(card): Header Title shows exact dates (MIN/MAX Footfall[DATE])"

git add MM_Dashbard__Final.Report/definition/pages
git commit -m "feat(layout): replicate header card + text box across 5 client tabs"

# radius map (Option B reference layer, or Option C Deneb):
git add MM_Dashbard__Final.SemanticModel/definition/tables/_Measures.tmdl \
        MM_Dashbard__Final.Report/definition/pages docs/site_radius_circles.geojson
git commit -m "feat(map): show site viewshed radius in metres + Site Radius measure"

# 4. change record + tag
git add docs/
git commit -m "docs: change record for header card + radius map (dashboard-v2.8.0)"
git tag dashboard-v2.8.0
```

Suggested version: **`dashboard-v2.8.0`** (feature). Record a `docs/PR_header_card_radius_map.md` following the pattern of the existing change records.

---

## Validation checklist

- [ ] Card shows `246 sites · 1 Mar – 31 May 2026`; updates when you move the date slicer.
- [ ] Card + text box appear on all 5 tabs, aligned (same X/Y, height `33`).
- [ ] Each card recalculates with its own tab's filters.
- [ ] Map: bubbles vary in size by radius (50 m smaller, 183 m larger).
- [ ] No orphan CODEs (`scripts/check_join_keys.py`).
