create schema micromdeia;

SET GLOBAL local_infile = 1;

SELECT COUNT(*) AS rows_now FROM footfall_raw;


USE micromedia;

-- Limpa a tabela!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
TRUNCATE TABLE footfall_raw;

-- Xeroo
SELECT COUNT(*) AS rows_now FROM footfall_raw;

-- Recarrega
LOAD DATA LOCAL INFILE 'C:/Users/brafa/Documents/data-analyst/MicroMedia/Locomizer_Folders/Footfall/03_Mar25_Micromedia_Footfall.csv'
INTO TABLE footfall_raw
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

-- numero correto
SELECT COUNT(*) AS rows_now FROM footfall_raw;
-- tem que dar 320286