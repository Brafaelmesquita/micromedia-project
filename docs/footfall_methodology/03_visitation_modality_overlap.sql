/* ============================================================================
   SCENARIO 3 — VISITATION_MODALITY overlap (Residents + Workers + Transient)
   ============================================================================
   PURPOSE
   -------
   The Footfall table classifies each panellist into a visitation type:

       VISITATION_MODALITY ∈ { ALL, RESIDENTS, WORKERS, TRANSIENT }

   Definitions from the Locomizer schema:
     - RESIDENTS = panellist with highest dwell-time during 00:00-06:00 of the month
     - WORKERS   = panellist with highest dwell-time during 09:00-17:00 on workdays
     - TRANSIENT = panellist who is neither resident nor worker for this area
     - ALL       = the deduplicated union of all panellists, regardless of type

   These categories ARE NOT mutually exclusive. A person who lives near a
   screen AND works near it will be tagged as BOTH Resident AND Worker.
   Adding Residents + Workers + Transient therefore overcounts the audience.

   EXAMPLE CELL
   ------------
   Screen CODE=50247, DAY=9, HOUR=17, MOVEMENT_MODALITY='ALL'.

   EXPECTED OUTPUT
   ---------------
   VISITATION_MODALITY    NUMBER_OF_USERS    EXTRAPOLATED_USERS_2
   ALL                    8                  3,819     ← unique users
   RESIDENTS              1                    477
   TRANSIENT              8                  3,819
   WORKERS                1                    477
   --------------------------------------------------
   SUM of segments       10 (NOT 8)         4,773 (NOT 3,819)

   Inflation: +25% on raw panel users, +25% on extrapolated users.
   ============================================================================ */

-- Show the raw breakdown for the example cell.
SELECT
    VISITATION_MODALITY,
    NUMBER_OF_USERS,
    ROUND(EXTRAPOLATED_NUMBER_OF_USERS, 0) AS pas_est,
    ROUND(EXTRAPOLATED_USERS_2, 0)         AS total_pop_est
FROM footfall_raw
WHERE CODE = '50247'
  AND DAY = 9 AND MONTH = 3 AND YEAR = 2025
  AND HOUR = 17
  AND MOVEMENT_MODALITY = 'ALL'    -- isolate the visitation dimension
ORDER BY VISITATION_MODALITY;


-- ----------------------------------------------------------------------------
-- ALL row vs sum of segments — side by side.
-- ----------------------------------------------------------------------------
WITH cell AS (
    SELECT VISITATION_MODALITY, NUMBER_OF_USERS, EXTRAPOLATED_USERS_2
    FROM footfall_raw
    WHERE CODE = '50247'
      AND DAY = 9 AND MONTH = 3 AND YEAR = 2025
      AND HOUR = 17
      AND MOVEMENT_MODALITY = 'ALL'
)
SELECT
    'ALL row (correct unique users)' AS calculation_method,
    NUMBER_OF_USERS                   AS raw_users,
    ROUND(EXTRAPOLATED_USERS_2, 0)    AS extrap_users_2
FROM cell
WHERE VISITATION_MODALITY = 'ALL'

UNION ALL

SELECT
    'Sum of Res+Work+Trans (wrong, overcounts)' AS calculation_method,
    SUM(NUMBER_OF_USERS)                          AS raw_users,
    ROUND(SUM(EXTRAPOLATED_USERS_2), 0)           AS extrap_users_2
FROM cell
WHERE VISITATION_MODALITY <> 'ALL';


-- ----------------------------------------------------------------------------
-- same check across the whole month — what share of
-- (CODE, DAY, HOUR) cells exhibit visitation overlap?
-- ----------------------------------------------------------------------------
WITH per_cell AS (
    SELECT
        CODE, DAY, HOUR,
        MAX(CASE WHEN VISITATION_MODALITY = 'ALL'  THEN NUMBER_OF_USERS END) AS all_row,
        SUM(CASE WHEN VISITATION_MODALITY <> 'ALL' THEN NUMBER_OF_USERS END) AS sum_segments
    FROM footfall_raw
    WHERE MOVEMENT_MODALITY = 'ALL'
      AND HOUR <> 25
      AND MONTH = 3 AND YEAR = 2025
    GROUP BY CODE, DAY, HOUR
)
SELECT
    COUNT(*)                                            AS total_cells,
    SUM(CASE WHEN sum_segments > all_row THEN 1 END)    AS cells_with_overlap,
    ROUND(100.0 * SUM(CASE WHEN sum_segments > all_row THEN 1 END) / COUNT(*), 1)
                                                        AS pct_cells_with_overlap
FROM per_cell
WHERE all_row IS NOT NULL AND sum_segments IS NOT NULL;
-- Expected output for Mar 2025: total_cells=66,703, cells_with_overlap=10,507,
-- pct_cells_with_overlap=15.8%. Visitation overlap is less common than movement
-- overlap (37.7%) — most people in a given hour fit cleanly into a single
-- visitation type. But for those ~16% of cells where it does happen, summing
-- Residents+Workers+Transient inflates the audience.
