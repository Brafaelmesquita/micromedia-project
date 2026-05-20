/* ============================================================================
   CENARIO 1 — HOUR=25 vs sum of HOUR 0..23
   ============================================================================
   Pra mostrar
   -------
   Locomizer's Footfall table stores hourly granular rows (HOUR 0..23) AND an
   all-day aggregate row (HOUR=25). The HOUR=25 row is NOT just the arithmetic
   sum of the 24 hourly rows — it is the all-day DEDUPLICATED unique-user count
   that Locomizer pre-computes for us. Summing the 24 hourly rows counts the
   same person multiple times (once per hour they were detected in the radius).

   This script proves it by picking one screen, one day, and showing both numbers
   side by side.

   EXAMPLE CELL
   ------------
   Screen CODE=50003 (Coppers), DAY=3, MOVEMENT='ALL', VISITATION='ALL'.

   EXPECTED OUTPUT (from raw Mar 2025 data)
   ----------------------------------------
   sum_of_hours_0_23 = 6,042   (people-hours, NOT people)
   hour_25_row       = 2,789   (unique people for the day)
   inflation_factor  = ~2.17x

   INTERPRETATION
   --------------
   The average person who passed by the screen on day 3 was detected in
   ~2.17 different hourly slots — i.e. they hung around for ~2 hours.
   Summing across HOUR therefore inflates the audience by ~117%.

   THE RULE
   --------
   For day-level or month-level reporting, ALWAYS use HOUR = 25.
   For hour-of-day reporting (e.g. "audience between 07:00-09:00"), use
   HOUR IN (7,8,9) — but the number is NOT unique users, it is exposures
   in that window (and must be labelled as such in the dashboard).
   ============================================================================ */

-- breakdown for screen 50003 on day 3 of March 2025
WITH per_hour AS (
    SELECT
        HOUR,
        NUMBER_OF_USERS,
        EXTRAPOLATED_NUMBER_OF_USERS,           -- PaS 
        EXTRAPOLATED_USERS_2,                   -- Total Population 
        EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS     -- OTS
    FROM footfall_raw
    WHERE CODE = '50003'
      AND DAY = 3
      AND MONTH = 3
      AND YEAR = 2025
      AND MOVEMENT_MODALITY = 'ALL'
      AND VISITATION_MODALITY = 'ALL'
)
SELECT
    -- Per-hour breakdown (24 rows expected for HOUR 0..23 + 1 row for HOUR=25)
    HOUR,
    NUMBER_OF_USERS,
    ROUND(EXTRAPOLATED_USERS_2, 0) AS total_population_est
FROM per_hour
ORDER BY HOUR;

SELECT
    'sum_of_hours_0_23' AS calculation_method,
    SUM(EXTRAPOLATED_USERS_2) AS total_population_value
FROM footfall_raw
WHERE CODE = '50003'
  AND DAY = 3 AND MONTH = 3 AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR BETWEEN 0 AND 23     -- ← the WRONG approach

UNION ALL

SELECT
    'hour_25_dedup_row' AS calculation_method,
    EXTRAPOLATED_USERS_2 AS total_population_value
FROM footfall_raw
WHERE CODE = '50003'
  AND DAY = 3 AND MONTH = 3 AND YEAR = 2025
  AND MOVEMENT_MODALITY = 'ALL'
  AND VISITATION_MODALITY = 'ALL'
  AND HOUR = 25;                -- ← the CORRECT approach for day-level totals
