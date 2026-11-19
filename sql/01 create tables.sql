-- =====================================================================
-- Banque Horizon - Gold : création des tables (Warehouse wh_horizon)
-- MODE D'EMPLOI : nouvelle requête SQL, colle TOUT le fichier,
-- ne sélectionne rien, clique sur Exécuter.
-- Prérequis : les schémas gold et etl existent déjà.
-- Si une table existe déjà (essai précédent), supprime-la d'abord dans
-- l'explorateur : elle est vide, il n'y a rien à perdre.
-- Aucune contrainte ici : un Warehouse Fabric n'accepte pas PRIMARY KEY
-- dans CREATE TABLE (voir 03_add_primary_keys.sql, facultatif).
-- =====================================================================

CREATE TABLE gold.dim_date (
    date_key        int          NOT NULL,
    full_date       date         NOT NULL,
    year_num        smallint     NOT NULL,
    quarter_num     smallint     NOT NULL,
    month_num       smallint     NOT NULL,
    month_name      varchar(12)  NOT NULL,
    day_num         smallint     NOT NULL,
    iso_day_of_week smallint     NOT NULL,
    day_name        varchar(10)  NOT NULL,
    is_weekend      bit          NOT NULL
);

CREATE TABLE gold.dim_desk (
    desk_key     int          NOT NULL,
    desk_name    varchar(30)  NOT NULL,
    asset_class  varchar(30)  NULL,
    loaded_at    datetime2(6) NOT NULL
);

CREATE TABLE gold.dim_instrument (
    instrument_key  int           NOT NULL,
    instrument_id   varchar(20)   NOT NULL,
    instrument_name varchar(200)  NULL,
    isin            varchar(20)   NULL,
    desk            varchar(30)   NULL,
    asset_class     varchar(30)   NULL,
    currency        varchar(3)    NULL,
    ref_price       decimal(18,2) NULL,
    loaded_at       datetime2(6)  NOT NULL
);

CREATE TABLE gold.dim_client (
    client_key           int          NOT NULL,
    client_id            varchar(20)  NOT NULL,
    client_name          varchar(200) NULL,
    country              varchar(10)  NULL,
    segment              varchar(50)  NULL,
    risk_rating          smallint     NULL,
    created_at           date         NULL,
    duplicate_group_size int          NULL,
    valid_from           date         NOT NULL,
    valid_to             date         NOT NULL,
    is_current           bit          NOT NULL,
    loaded_at            datetime2(6) NOT NULL
);

CREATE TABLE gold.fact_transactions (
    transaction_id  varchar(30)   NOT NULL,
    date_key        int           NOT NULL,
    client_key      int           NOT NULL,
    instrument_key  int           NOT NULL,
    desk_key        int           NOT NULL,
    trade_timestamp datetime2(6)  NULL,
    side            varchar(4)    NOT NULL,
    quantity        int           NOT NULL,
    price           decimal(18,4) NOT NULL,
    notional        decimal(18,2) NULL,
    currency        varchar(3)    NULL,
    status          varchar(20)   NULL,
    file_date       date          NOT NULL,
    silver_batch_id varchar(40)   NULL,
    loaded_at       datetime2(6)  NOT NULL
);

CREATE TABLE etl.load_log (
    run_date       date         NOT NULL,
    step_name      varchar(100) NOT NULL,
    rows_expected  int          NULL,
    rows_loaded    int          NULL,
    status         varchar(30)  NOT NULL,
    message        varchar(500) NULL,
    logged_at      datetime2(6) NOT NULL
);