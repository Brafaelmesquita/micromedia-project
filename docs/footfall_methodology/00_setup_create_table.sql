

USE micromedia;

DROP TABLE IF EXISTS footfall_raw;

CREATE TABLE footfall_raw (
    CODE                                              VARCHAR(10),
    `DISPLAY NAME`                                    VARCHAR(255),
    RADIUS                                            INT,
    LATITUDE                                          DOUBLE,
    LONGITUDE                                         DOUBLE,
    HOUR                                              INT,
    DAY                                               INT,
    MONTH                                             INT,
    YEAR                                              INT,
    MOVEMENT_MODALITY                                 VARCHAR(20),
    VISITATION_MODALITY                               VARCHAR(20),
    NUMBER_OF_USERS                                   INT,
    NUMBER_OF_SIGNALS                                 INT,
    DWELL_TIME                                        DOUBLE,
    REACH                                             DOUBLE,
    EXTRAPOLATED_NUMBER_OF_USERS                      DOUBLE,
    EXTRAPOLATED_NUMBER_OF_SIGNALS                    DOUBLE,
    EXTRAPOLATED_USERS_2                              DOUBLE,
    EXTRAPOLATED_SIGNALS_2                            DOUBLE,
    NUMBER_OF_EYE_CONTACTS                            INT,
    NUMBER_OF_EYE_CONTACTS_WEIGHTED                   INT,
    EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS               DOUBLE,
    EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED      DOUBLE,
    EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS_WEIGHTED_2    DOUBLE,
    -- Indexes that will be heavily used by the demo queries.
    -- Optional but make scripts 04 and 05 run in well under a second.
    INDEX idx_filter (MONTH, YEAR, MOVEMENT_MODALITY, VISITATION_MODALITY, HOUR),
    INDEX idx_code   (CODE)
);

-- Confirm the table is empty and ready to receive data:
SELECT COUNT(*) AS rows_loaded FROM footfall_raw;
-- Expected: 0
