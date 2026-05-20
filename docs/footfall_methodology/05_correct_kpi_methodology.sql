/* ============================================================================
   SCENARIO 5 — Correct methodology for Total Population, PaS and OTS
   ============================================================================
   PURPOSE
   -------
   This is the OFFICIAL query the dashboard should use. Run this and the three
   numbers it returns are what we publish to the client.

   THE THREE KPIs AND THE COLUMNS THAT REPRESENT THEM
   --------------------------------------------------
   1) Total Population  →  EXTRAPOLATED_USERS_2
        Locomizer formula:  NUMBER_OF_USERS × (Total Country Population / Panel size)
        Includes children, the elderly, and people without a mobile phone.

   2) PaS (People at Screen)  →  EXTRAPOLATED_NUMBER_OF_USERS
        Locomizer formula:  NUMBER_OF_USERS × (Mobile Device Holding Population / Panel size)
        Includes only people represented by the mobile panel.
        Excludes very young children, part of the elderly, anyone without a smartphone.

   3) OTS (Opportunity to See)  →  EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS
        Locomizer formula:  Signals from mobile-holding users who are moving TOWARDS
                            the screen, within the viewability cone defined by the
                            screen's azimuth and viewing angle.
        Subset of PaS: only people who are actually looking at the screen.

   THE FILTER (same for all three KPIs)
   ------------------------------------
       MOVEMENT_MODALITY = 'ALL'      -- avoid summing overlapping movement segments
       AND VISITATION_MODALITY = 'ALL' -- avoid summing overlapping visitation segments
       AND HOUR = 25                  -- use the daily deduplicated row

   EXPECTED OUTPUT (Mar 2025, all 243 screens)
   -------------------------------------------
   total_population = 149,821,318
   pas              =  66,587,252   (44.4% of Total Population)
   ots              =  28,102,238   (42.2% of PaS, 18.8% of Total Population)
   ============================================================================ */

-- The headline query: returns one row with the three official KPIs for Mar 2025.
SELECT
    SUM(EXTRAPOLATED_USERS_2)                  AS total_population,
    SUM(EXTRAPOLATED_NUMBER_OF_USERS)          AS pas,
    SUM(EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS)   AS ots
FROM footfall_raw
WHERE MONTH = 3
  AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR = 25;


-- ----------------------------------------------------------------------------
-- Same query, broken down by screen (for a per-screen post-campaign report).
-- Top 10 screens by OTS for the campaign month.
-- ----------------------------------------------------------------------------
SELECT
    CODE,
    SUM(EXTRAPOLATED_USERS_2)                AS total_population,
    SUM(EXTRAPOLATED_NUMBER_OF_USERS)        AS pas,
    SUM(EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS) AS ots,
    ROUND(
        100.0 * SUM(EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS)
              / NULLIF(SUM(EXTRAPOLATED_NUMBER_OF_USERS), 0),
        1
    ) AS ots_pct_of_pas
FROM footfall_raw
WHERE MONTH = 3
  AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR = 25
GROUP BY CODE
ORDER BY ots DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Daily trend (for the "audience over time" chart in the dashboard).
-- One row per day with the three KPIs.
-- ----------------------------------------------------------------------------
SELECT
    YEAR, MONTH, DAY,
    SUM(EXTRAPOLATED_USERS_2)                AS total_population,
    SUM(EXTRAPOLATED_NUMBER_OF_USERS)        AS pas,
    SUM(EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS) AS ots
FROM footfall_raw
WHERE MONTH = 3 AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR = 25
GROUP BY YEAR, MONTH, DAY
ORDER BY YEAR, MONTH, DAY;


-- ----------------------------------------------------------------------------
-- IMPORTANT CAVEAT — hour-of-day reporting
-- ----------------------------------------------------------------------------
-- The filter above (HOUR=25) only works for DAY-level or MONTH-level reporting.
-- If the dashboard needs to filter by a specific HOUR window (e.g. a campaign
-- that only ran 07:00-09:00), use this filter INSTEAD:
--
--     MOVEMENT_MODALITY = 'ALL'
--     AND VISITATION_MODALITY = 'ALL'
--     AND HOUR IN (7, 8, 9)
--
-- BUT note: the resulting number is NOT "unique audience for the day", it is
-- "exposures in the time window" — which carries the dwell-time overcounting
-- effect from scenario 01 (people who stay multiple hours are counted multiple
-- times). The dashboard UI must label this metric as "Exposures" or
-- "Impressions", NOT "Unique Audience".

-- Example — exposures during 07:00-09:00 window across March 2025:
SELECT
    SUM(EXTRAPOLATED_USERS_2)                AS exposures_total_pop,
    SUM(EXTRAPOLATED_NUMBER_OF_USERS)        AS exposures_pas,
    SUM(EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS) AS exposures_ots
FROM footfall_raw
WHERE MONTH = 3 AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR IN (7, 8, 9);
