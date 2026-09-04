# Professional review — Site Map & Site Profile Card

**Version:** v2
**Date:** 28 Jul 2026
**Author:** Data / OOH analysis
**Previous:** `site_map_profile_review_v1.md` (kept for history)

> v2 incorporates the decisions made with Rafael: it reclassifies the v1 findings in
> light of the views' real intent and details the aesthetic redesign of the Site Profile
> Card + its Power BI feasibility.

---

## 0. What changed from v1 to v2

- **"3bn" on the Site Profile Card — reclassified from 🔴 critical to "expected / aesthetic".** The card shows the total value **unfiltered** on purpose (it feeds the Site Map card, which works). It's not a bug. The number itself is not the focus of this view.
- **Site Map — intent confirmed:** show the **geographic distribution of the network**. The **Network, Site and Month** slicers (the same as Overview) filter the map. The map fit has already been implemented by Rafael.
- **Hour filter on the map:** decided **not** by default — an hour turns the distribution view into a daypart (a different question) and forces a grain change (`HOUR<25`, never sum). It stays as a separate mode, if ever needed.
- **Top Screens by gender/age — correct rule recorded** (section 2).
- **Current focus:** aesthetic redesign of the Site Profile Card (section 3).

---

## 1. Site Map — state and definitions

Purpose: geographic distribution of the network (WHERE). Bubble metric = monthly dedup total (`IS_GRAND_TOTAL=1 AND HOUR=25`). The Network / Site / Month slicers mirror Overview and filter the map. No hour filter by default.

---

## 2. Top Screens filtered by gender + age — calculation rule

Age and gender live in the **Demographics** table (not Footfall). Verified in the data: `REACH_PCT` is a composition that **closes to 100% per (screen, hour, modality)** and only exists **for hours 0–23 — there is no all-day row (HOUR=25)** in demographics.

Consequences for ranking screens by a segment:

1. **Don't rank by `%`.** A tiny screen can be 90% of a segment and have almost no audience. Rank by **absolute segment population = volume × %**.
2. **The % only exists per hour.** The correct monthly/all-day number weights each hour by that hour's footfall:
   `Pop_segment(screen) = Σ_hour [ Footfall(screen,hour) × %(screen,hour,segment) ]`
   (weight by the hour's `EXTRAPOLATED_USERS_2` — never a plain mean; fix `MOVEMENT_MODALITY='All'`).
   Equivalent alternative, if the model already stores the footfall-weighted monthly %:
   `Pop_segment ≈ TotalPop_dedup(HOUR=25) × weighted_monthly_%(segment)`.
3. **The per-hour population counter is the engine of the measure — but it does NOT require a visible hour slicer.** For the whole-month ranking, the user only picks gender+age; the hour stays internal to the measure.
4. **An hour slicer only becomes necessary** if the requirement is dayparting ("top screens for female 18-24 between 07:00–09:00"). Then the measure sums only the selected hours.

---

## 3. Site Profile Card — aesthetic redesign (brand identity)

Reference: `references/visual_identity.md`. Diagnosis of the current card: age donut in ~7 colours (rainbow) and gender bar in coral — both off-palette (cyan is the only accent; coral only for under-index/warning; max 3 colours).

Agreed decisions:

1. **Age donut → monochrome cyan ramp** (light→dark by age band). A natural encoding for age. Palette used in the mockup: Under 18 `#A8E4F5`, 18-24 `#7FD3EF`, 25-34 `#52C1E9`, 35-44 `#29B6E8`, 45-54 `#1D97C6`, 55-64 `#0A7FA8`, 65+ `#00566E`.
2. **Side legend with the value alongside** (e.g. "Under 18 · 21.5%") and **remove the leader lines** with % (clutter). One labelling system only.
   *More readable alternative:* 7 bands as **horizontal cyan bars** (the guide specifies age = bars) read better than 7 shades of the same blue; in that case the donut is left for gender only.
3. **Gender → more contrast within the brand.** Two near-identical cyans don't separate. Use the **two ends of the ramp**: male `#29B6E8` (cyan), female `#003D52` (navy). Coral stays forbidden here.
4. **KPI as a chip:** black background, 10px uppercase grey label (`#888888`), large value in cyan (`#29B6E8`). The guide's "cyan on black" pattern.
5. **Header with screen context:** `Custom ID` + `Display Name` + a **Network** badge (Urban/Campus/Lifestyle/Large Format) + city. Replaces the large dropdown box (lighter → **gains** space, doesn't lose it). Metadata comes from the master site list.
6. **Container:** white card, 0.5px `#DDDDDD` border, 12px corners, no shadow.

---

## 4. Power BI feasibility

Reproducible **~100% native, no custom visual**:

| Element | How | Fidelity |
|---|---|---|
| Cyan-ramp donut | Data colours per category (custom hex) | Exact |
| Black/cyan KPI chip | Card visual: black background, value colour, uppercase label | Exact |
| 100% gender bar | 100% stacked bar (1 category) + data labels + data colours | Exact |
| ID + Display Name header | Card / multi-row card | Exact |
| "URBAN" Network badge | Card with light-cyan background + rounded corners | ~90% (not a true pill) |
| White 12px container | Background + border + rounded corners | Exact |
| Legend with value alongside | Styled side matrix/table, or detail labels | Functional, not the native legend |
| Inter font | Select the font; install if missing (PBI default = Segoe) | Depends on the installed font |

Caveats: (a) the legend-with-value needs a side matrix or detail labels; (b) the pill badge is approximate; (c) fine control of leader lines is limited — resolve by turning labels off and using a side legend + tooltip; (d) Inter may fall back.

---

## 5. Versioning

v2 keeps v1 in history. Suggested commit: `docs(review): site map + profile card review v2 (card redesign + PBI feasibility)`.

*Audience data provided by Locomizer. Processed and presented by Micromedia.*
**Micromedia — Look to the Light**
