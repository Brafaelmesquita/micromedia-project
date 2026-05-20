USE micromedia;

LOAD DATA LOCAL INFILE 'C:/Users/brafa/Documents/data-analyst/MicroMedia/Locomizer_Folders/Footfall/03_Mar25_Micromedia_Footfall.csv'
INTO TABLE footfall_raw
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'  
IGNORE 1 ROWS;                -- header

-- print 320,286
SELECT COUNT(*) AS rows_loaded FROM footfall_raw;

-- confirm columns
SELECT CODE, `DISPLAY NAME`, HOUR, DAY, MONTH, YEAR,
       MOVEMENT_MODALITY, VISITATION_MODALITY,
       NUMBER_OF_USERS,
       ROUND(EXTRAPOLATED_USERS_2, 0) AS total_pop_est
FROM footfall_raw
LIMIT 15;