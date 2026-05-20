/* ============================================================================
   CENARIO 2 — MOVEMENT_MODALITY overlap (Pedestrians + Car_city + ...)
   ============================================================================
   Ideia
   -------

       MOVEMENT_MODALITY ∈ { ALL, PEDESTRIANS, CYCLISTS, CAR_CITY, CAR_HIGHWAY }

   Intuition would say:
       ALL = PEDESTRIANS + CYCLISTS + CAR_CITY + CAR_HIGHWAY

   But this is FALSE. The categories overlap because the same panellist can be
   classified into more than one movement mode during the same hour. Example:
   a person who drives to a parking spot and then walks past the screen will
   be tagged as BOTH Car_city AND Pedestrians for that hour.

   So summing the segment rows DOUBLE-COUNTS people. We should use the ALL row.

   EXAMPLE CELL
   ------------
   Screen CODE=50247, DAY=9, HOUR=17, VISITATION_MODALITY='ALL'.
   We pick this cell because it has all 5 modality rows populated, making
   the overlap visible.   

   Inflation: +50% on both the raw panel count and the extrapolated number.
   ============================================================================ */

-- Step 1: breakdown for the example cell.
SELECT
    MOVEMENT_MODALITY,
    NUMBER_OF_USERS,
    ROUND(EXTRAPOLATED_NUMBER_OF_USERS, 0) AS pas_est,
    ROUND(EXTRAPOLATED_USERS_2, 0)         AS total_pop_est
FROM footfall_raw
WHERE CODE = '50247'
  AND DAY = 9 AND MONTH = 3 AND YEAR = 2025
  AND HOUR = 17
  AND VISITATION_MODALITY = 'ALL'   -- isolate the movement dimension
ORDER BY MOVEMENT_MODALITY;


-- ----------------------------------------------------------------------------
-- Step 2: ALL-row vs sum-of-segments — side by side.
-- ----------------------------------------------------------------------------
WITH cell AS (
    SELECT MOVEMENT_MODALITY, NUMBER_OF_USERS, EXTRAPOLATED_USERS_2
    FROM footfall_raw
    WHERE CODE = '50247'
      AND DAY = 9 AND MONTH = 3 AND YEAR = 2025
      AND HOUR = 17
      AND VISITATION_MODALITY = 'ALL'
)
SELECT
    'ALL row (correct unique users)' AS calculation_method,
    NUMBER_OF_USERS                   AS raw_users,
    ROUND(EXTRAPOLATED_USERS_2, 0)    AS extrap_users_2
FROM cell
WHERE MOVEMENT_MODALITY = 'ALL'

UNION ALL

SELECT
    'Sum of segments (wrong, overcounts)' AS calculation_method,
    SUM(NUMBER_OF_USERS)                   AS raw_users,
    ROUND(SUM(EXTRAPOLATED_USERS_2), 0)    AS extrap_users_2
FROM cell
WHERE MOVEMENT_MODALITY <> 'ALL';


-- ----------------------------------------------------------------------------
-- Step 3: how widespread is this overlap across the whole month?
-- For every (CODE, DAY, HOUR) cell with VIS='ALL', compare the ALL row to the
-- sum of its movement segments. The output shows the % of cells where the
-- segments sum to MORE than the ALL row (i.e. where overlap is happening).
-- ----------------------------------------------------------------------------
WITH per_cell AS (
    SELECT
        CODE, DAY, HOUR,
        MAX(CASE WHEN MOVEMENT_MODALITY = 'ALL'  THEN NUMBER_OF_USERS END) AS all_row,
        SUM(CASE WHEN MOVEMENT_MODALITY <> 'ALL' THEN NUMBER_OF_USERS END) AS sum_segments
    FROM footfall_raw
    WHERE VISITATION_MODALITY = 'ALL'
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
-- Expected output for Mar 2025: total_cells=66,703, cells_with_overlap=25,126,
-- pct_cells_with_overlap=37.7%. So in roughly 4 out of every 10 (CODE,DAY,HOUR)
-- cells the segments overlap. The remaining ~62% are cells where only one
-- movement type was detected — there is no overlap simply because there is
-- only one segment row to begin with (still, the ALL row remains the right
-- one to read, just by accident the sum matches it).
