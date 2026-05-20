/* ============================================================================
   SCENARIO 4 — Month-wide comparison of filter scenarios (A / B / C / D)
   ============================================================================
   MySQL 8.0+ compatible.

   PURPOSE
   -------
   Bring all the errors from scripts 01-03 together. This shows, in a single
   query, what each WRONG combination of filters produces at the FULL MONTH
   level — and what the CORRECT filter produces.

   This is the chart the team needs to see to understand the magnitude of
   the difference. Once they see scenario (A) is 8x the correct number,
   the conversation about "which filter do we use?" ends.

   THE FOUR SCENARIOS
   ------------------
   (A) NO FILTER AT ALL — sums every row in the table.
       Mixes HOUR=25 with hourly rows + sums overlapping segments.

   (B) MOV=ALL AND VIS=ALL but KEEPS BOTH HOUR=25 and HOUR 0..23
       The (All,All) filter fixes segment overlap, but mixing HOUR=25 with
       hourly rows counts each day twice (once via the 24 hourly rows,
       once via the all-day sentinel).

   (C) MOV=ALL AND VIS=ALL AND HOUR BETWEEN 0 AND 23
       Fixes segment overlap, drops HOUR=25, but sums the hourly rows.
       Same person who passed by for 3 hours appears 3 times.

   (D) MOV=ALL AND VIS=ALL AND HOUR=25         <-- CORRECT
       Uses the all-day deduplicated row Locomizer pre-computes.

   EXPECTED OUTPUT (Mar 2025, all 243 screens)
   -------------------------------------------
   scenario | total_population_est | factor_vs_correct
   ---------+----------------------+------------------
   A        |   1,210,969,108      | 8.08x
   B        |     369,039,170      | 2.46x
   C        |     219,217,852      | 1.46x
   D        |     149,821,318      | 1.00x  (reference)
   ============================================================================ */

USE micromedia;

-- ----------------------------------------------------------------------------
-- THE HEADLINE COMPARISON — one row per scenario, easy to read.
-- ----------------------------------------------------------------------------
WITH
scenario_a AS (
    SELECT SUM(EXTRAPOLATED_USERS_2) AS total_population
    FROM footfall_raw
    WHERE MONTH = 3 AND YEAR = 2025
),
scenario_b AS (
    SELECT SUM(EXTRAPOLATED_USERS_2) AS total_population
    FROM footfall_raw
    WHERE MONTH = 3 AND YEAR = 2025
      AND MOVEMENT_MODALITY = 'ALL'
      AND VISITATION_MODALITY = 'ALL'
    -- NOTE: NO filter on HOUR — the bug. Mixes daily total with hourly rows.
),
scenario_c AS (
    SELECT SUM(EXTRAPOLATED_USERS_2) AS total_population
    FROM footfall_raw
    WHERE MONTH = 3 AND YEAR = 2025
      AND MOVEMENT_MODALITY = 'ALL'
      AND VISITATION_MODALITY = 'ALL'
      AND HOUR BETWEEN 0 AND 23
),
scenario_d AS (
    SELECT SUM(EXTRAPOLATED_USERS_2) AS total_population
    FROM footfall_raw
    WHERE MONTH = 3 AND YEAR = 2025
      AND MOVEMENT_MODALITY = 'ALL'
      AND VISITATION_MODALITY = 'ALL'
      AND HOUR = 25
)
SELECT 'A -- no filter at all (mixes everything)'                       AS scenario,
       total_population,
       'Triple counting: HOUR=25 + 0..23 + overlapping segments'        AS what_goes_wrong,
       'WRONG'                                                           AS verdict
FROM scenario_a
UNION ALL
SELECT 'B -- MOV=ALL + VIS=ALL but HOUR=25 mixed with 0..23',
       total_population,
       'Each day counted twice: via 24 hourly rows AND via HOUR=25',
       'WRONG'
FROM scenario_b
UNION ALL
SELECT 'C -- MOV=ALL + VIS=ALL + HOUR 0..23 (sum of hours)',
       total_population,
       'Each person counted once per hour of presence (~1.5x dwell)',
       'WRONG'
FROM scenario_c
UNION ALL
SELECT 'D -- MOV=ALL + VIS=ALL + HOUR=25',
       total_population,
       'Daily dedup row provided by Locomizer',
       'CORRECT'
FROM scenario_d;


-- ----------------------------------------------------------------------------
-- BONUS: same table but with the inflation factor expressed as a ratio.
-- Easy to drop into a slide.
-- MySQL: no need for any cast — division of DOUBLEs returns DOUBLE.
-- ----------------------------------------------------------------------------
WITH d AS (
    SELECT SUM(EXTRAPOLATED_USERS_2) AS total_pop
    FROM footfall_raw
    WHERE MONTH = 3 AND YEAR = 2025
      AND MOVEMENT_MODALITY = 'ALL'
      AND VISITATION_MODALITY = 'ALL'
      AND HOUR = 25
),
all_scenarios AS (
    SELECT 'A -- no filter' AS scenario,
           (SELECT SUM(EXTRAPOLATED_USERS_2) FROM footfall_raw
            WHERE MONTH = 3 AND YEAR = 2025) AS total_population
    UNION ALL
    SELECT 'B -- ALL/ALL, HOUR mixed',
           (SELECT SUM(EXTRAPOLATED_USERS_2) FROM footfall_raw
            WHERE MONTH = 3 AND YEAR = 2025
              AND MOVEMENT_MODALITY = 'ALL'
              AND VISITATION_MODALITY = 'ALL')
    UNION ALL
    SELECT 'C -- ALL/ALL + HOUR 0..23',
           (SELECT SUM(EXTRAPOLATED_USERS_2) FROM footfall_raw
            WHERE MONTH = 3 AND YEAR = 2025
              AND MOVEMENT_MODALITY = 'ALL'
              AND VISITATION_MODALITY = 'ALL'
              AND HOUR BETWEEN 0 AND 23)
    UNION ALL
    SELECT 'D -- ALL/ALL + HOUR=25 (CORRECT)',
           (SELECT SUM(EXTRAPOLATED_USERS_2) FROM footfall_raw
            WHERE MONTH = 3 AND YEAR = 2025
              AND MOVEMENT_MODALITY = 'ALL'
              AND VISITATION_MODALITY = 'ALL'
              AND HOUR = 25)
)
SELECT
    a.scenario,
    a.total_population,
    ROUND(a.total_population / d.total_pop, 2) AS factor_vs_correct
FROM all_scenarios a
CROSS JOIN d;
