# Professional review — Site Map & Site Profile Card

**Version:** v1
**Date:** 28 Jul 2026
**Author:** Data / OOH analysis
**Scope:** *Site Map* tab ("Who you'll reach") + *Site Profile Card*.
**References:** `micromedia-ooh` skill, `references/visual_identity.md`, `references/report_templates.md`, data in `data/processed/`.

> Goal: a data-professional + OOH-planning lens. What's missing, what's wrong, and what **not** to repeat from what already exists in the Home / Overview / Demographics / Audience Segments tabs.

---

## 0. Executive summary

Two views with distinct purposes and one shared problem: **neither one states a metric or a period on the visual itself, and the card's headline number is wrong by ~4 orders of magnitude.**

- **Site Map** works as a *network-coverage* view (WHERE), but today it delivers a map with no legend, a "Top Screens" list **with no metric**, and a **dead** hour grid (WHEN not encoded).
- **Site Profile Card** is the dashboard's **only screen-level view** — that's where its value is and where it is most incomplete. Today it shows three things (a number, an age donut, a gender bar) and none of them puts *that* screen in context.

Top priority: fix the **"3bn"** headline (item 1). It's the kind of error that, in a pre-campaign, destroys credibility in front of the client.

---

## 1. 🔴 CRITICAL — the "Total Footfall 3bn" headline is wrong

**What shows:** card with "33 RPM Record Store" selected → **Total Footfall 3bn**.

**Check against the data** (screen 33 RPM = `CODE 50426`, Urban, **Cork** — Mar 2026, correct rule `IS_GRAND_TOTAL = 1 AND HOUR = 25`):

| Metric | Correct value (Mar 2026) |
|---|---|
| Total Population (`EXTRAPOLATED_USERS_2`) | **≈ 481,638** |
| PaS (`EXTRAPOLATED_NUMBER_OF_USERS`) | ≈ 214,061 |
| **OTS / impressions** (`EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS`) | ≈ 84,217 |

In other words: the real one-month value for this screen is in the **hundreds of thousands**, not billions. **"3bn" is ~4 orders of magnitude too high** — and it does not match any plausible sum for *that* screen (even naively summing all 4,628 rows of the screen in the month gives 3.9M; summing the 17 months gives ~0.1bn). The only place "billions" appears is in the **whole-network total** (≈1.85bn over the entire period, correct; ≈15.7bn if summed wrong).

**Likely diagnosis (two overlapping bugs):**
1. **The screen slicer is not wired to the KPI** — the card shows a network-level number, not the selected screen's. Classic symptom of a missing *Edit interactions* / relationship.
2. **The measure sums rows instead of filtering** `IS_GRAND_TOTAL = 1 AND HOUR = 25` — exactly the 8× overcount the skill warns about.

**Action:** wire the slicer to the KPI and rewrite the measure over the dedup grain. Then validate: 33 RPM / Mar 2026 should give **~482k** (Total Population) and **~84k** (OTS). And label the metric explicitly — "Total Footfall" is ambiguous; for a client, impressions = **OTS**.

---

## 2. *Site Map* tab — findings

### 2.1 "Top Screens" is a list with no metric
Today it's just `CODE – Display Name`, with no value and no visible sort order. "Top" by what? A planner can't read the list. **Add the ranking metric** (OTS or Total Population) next to each screen, **sorted desc**, with a cyan data bar. Including City + Network helps read the mix. It's the same content as item 4 (table) of the post-campaign template — reuse it.

### 2.2 The hour grid (00:00–23:00) is dead
It's 24 grey boxes with no data. Communicates nothing. Two better outcomes:
- **A functional hour slicer** — with an active/selected state (cyan) that **filters the map and Top Screens**; or
- **Encode intensity** — shade each hour by `MM_CYAN_SCALE` (the skill already defines the hour-bar intensity), turning it into an actual "when you can reach them".
Rule reminder: for the hourly view use `IS_GRAND_TOTAL = 1 AND HOUR < 25` and **never** include `HOUR = 25`.

### 2.3 The map has no legend or OOH semantics
- **No size/colour legend for the bubble.** What does the radius mean? (should be ∝ `EXTRAPOLATED_USERS_2`, colour by the cyan scale — skill). Without a legend, the map is decorative.
- **No differentiation by Network** (Urban / Campus / Lifestyle / Large Format). A planner wants to see the network mix in space. The skill itself flags that the network badge colours are missing — resolve by deriving them from the cyan ramp and document it.
- **Tooltip** should carry: name, city, network, monthly footfall (not confirmed today).
- **Only shows Dublin.** There are 249 sites, but the network has Cork, Limerick, Sligo, Galway (33 RPM itself is Cork). Either the map doesn't auto-fit nationally, or the selection is biased to Dublin. It needs a **national view + drill by city**.
- **Catchment unused:** `docs/site_radius_circles.geojson` exists (per-site radius circles) and is **not on the map**. Catchment/isochrone is gold in OOH ("who lives/works within X of the screen") and a real differentiator versus the other tabs.

### 2.4 Filters
Only Gender and Age at the top. For a network view, these are missing: **Network, City, Date range and Time of day** (the README promises all of them). And the side card does not visually reflect the active filters (the skill asks for the active filter as a cyan pill).

---

## 3. *Site Profile Card* — what's missing

This is the most important point of your question. The card is the **only single-screen view** — it's a screen's "fact sheet". It's where a media buyer decides on *that* point. Precisely for that reason it **should not replicate** the age donut from the network tabs; its value is **physical context + comparison to the network + timing + brand fit**. Today almost all of those blocks are missing:

1. **Physical screen sheet (absent).** Display Name, CODE, Address, City, **Network**, `asset.setting` (indoor / street.facing / outdoor), **azimuth / direction the screen faces**, lat/long and a mini-map (or photo). Without this it's impossible to assess a single point. It all already exists in the master site list.
2. **The 3 header KPIs** (the skill requires): **Total Population, PaS, OTS** — not a single ambiguous "footfall". OTS is the impressions metric because it accounts for the azimuth.
3. **Busiest hours FOR THAT screen** (hourly curve) — the "WHEN" at the screen level. Different from the network aggregate.
4. **Hour × day-of-week heatmap** for the screen (the skill already specifies the visual) — shows the best play window.
5. **Brand affinity top categories for the screen (absent and essential).** It's the "why this screen serves brand X". Horizontal index bars, reference line at 100, top 8. Without it, the card doesn't sell.
6. **Visitation mix (residents / workers / transient)** for the screen — decisive (does a record store draw transient vs local?). Always as **% of total**, never an absolute sum (40–50% overcount).
7. **Time trend** for the screen — is it growing or falling month over month?
8. **Benchmark vs the network.** "9.8% for 18–24" says nothing on its own. The card should show the **screen's index vs the network median** ("over-indexes 18–24 by +X%"). This is the real analytical differentiator versus the Demographics tab — and the network average must be **weighted by `EXTRAPOLATED_USERS_2`**, never a plain mean (skill).
9. **Panel-sufficiency flag.** If the screen's panel is small in the period, say so explicitly — "reporting zero on an active screen is worse than reporting a gap" (skill).

---

## 4. Visual-identity compliance (`visual_identity.md`)

- 🔴 **Rainbow age donut.** Uses ~7 distinct colours (blue, navy, orange, purple, magenta, violet, yellow). Directly violates the rule: *"cyan is the only accent; never introduce red, green, yellow or purple; at most three colours; prefer a monochrome cyan ramp."* Age should be **cyan bars** (the spec says bars for age, donut for gender — here it's **inverted**), or, if a donut, a cyan ramp.
- 🔴 **Coral out of place.** The orange/coral (`#E05A3A`) is reserved for **under-index and warnings**. It's being used on an age slice and on the gender bar (female). Gender should be a donut: male `#29B6E8`, female `#0A7FA8`.
- **KPI:** "3bn" should be cyan on a black card, with a 10px uppercase label — and above all **with the metric and period named**.
- **Mandatory caption absent:** every visual must state metric + period. Neither the card nor the map does.

---

## 5. What **not** to repeat (anti-redundancy)

- **Network age/gender** already live in Overview / Demographics. On the card, it only makes sense **at the screen level and with a benchmark vs the network** — otherwise it's just a smaller, worse donut than the Demographics tab.
- **Social grade / occupation / industry** are already in Demographics; don't recreate them on the card — at most a summary with an index.
- **The aggregate hourly curve** for the network probably already exists; on the Site Map/card it should be **per screen / per selection**, not the aggregate.
- Before summing anything in these visuals, apply the grain rule (`IS_GRAND_TOTAL`, `HOUR = 25`) — it applies to the card KPI and to the Top Screens ranking.

---

## 6. Suggested prioritisation

**P1 — fixes a factual error (do now)**
1. The "3bn" bug: wire the slicer to the KPI + rewrite the measure at the dedup grain; validate 33 RPM = ~482k / OTS ~84k.
2. Name the metric + period on the card and map (caption).
3. Top Screens: add a metric + sort order.

**P2 — completes the value of the views**
4. Site Profile Card: physical screen sheet + 3 KPIs (Total Pop / PaS / OTS).
5. Card: brand affinity + visitation mix for the screen.
6. Card: benchmark vs the network median (weighted).
7. Map: legend, network mix, standard tooltip, national view.
8. Hour grid: turn it into a functional slicer **or** an intensity heatmap.

**P3 — differentiators / polish**
9. Catchment circles (`site_radius_circles.geojson`) on the map.
10. Visual compliance: age donut → cyan bars; remove coral outside warnings; gender → cyan donut.
11. Per-screen trend + insufficient-panel flag.
12. "Screen one-pager" export (card → PDF tied to `report_templates.md`).

---

## 7. Versioning

This document is **v1**. Future revisions: increment (`_v2`, `_v3`) and keep the history. I recommend committing it to the project git for traceability (suggested message: `docs: review v1 Site Map + Site Profile Card`).

*Audience data provided by Locomizer. Processed and presented by Micromedia.*
**Micromedia — Look to the Light**
