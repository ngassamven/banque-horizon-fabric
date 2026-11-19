-- =====================================================================
-- Banque Horizon - Gold : chargement complet d'un jour, EN UNE FOIS
-- MODE D'EMPLOI : nouvelle requête SQL, colle TOUT le fichier, ne
-- sélectionne rien, clique sur Exécuter. Après exécution, le message doit
-- commencer par « Début de l'exécution en ligne 1 » : sinon, une partie du
-- script (dont les DECLARE du début) n'a pas été exécutée. Pour un autre jour, change
-- uniquement la date de la première ligne et relance : le chargement
-- est rejouable, relancer le même jour ne crée pas de doublon.
-- Données lues dans le Lakehouse par lh_horizon.dbo.<table>. Si ton
-- Lakehouse a un autre nom, remplace "lh_horizon" partout (Ctrl+H).
-- =====================================================================

DECLARE @run_date   date        = '2026-01-05';      -- <== SEUL PARAMETRE A CHANGER
DECLARE @date_start date        = '2026-01-01';      -- période de la dimension date
DECLARE @date_end   date        = '2026-12-31';
DECLARE @day_txt    varchar(10) = CAST(@run_date AS varchar(10));
DECLARE @today      date        = CAST(GETDATE() AS date);
DECLARE @expected   int;
DECLARE @loaded     int;

-- ---------- 1. dim_date : ajoute les jours manquants ----------
WITH d AS (
    SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS v(n)
),
nums AS (
    SELECT a.n + 10 * b.n + 100 * c.n + 1000 * e.n AS n
    FROM d AS a CROSS JOIN d AS b CROSS JOIN d AS c CROSS JOIN d AS e
),
days AS (
    SELECT DATEADD(day, n, @date_start) AS full_date
    FROM nums
    WHERE DATEADD(day, n, @date_start) <= @date_end
),
calc AS (
    SELECT full_date,
           ((DATEDIFF(day, CAST('2024-01-01' AS date), full_date) % 7) + 7) % 7 + 1 AS iso_dow
    FROM days
)
INSERT INTO gold.dim_date
    (date_key, full_date, year_num, quarter_num, month_num, month_name,
     day_num, iso_day_of_week, day_name, is_weekend)
SELECT
    YEAR(full_date) * 10000 + MONTH(full_date) * 100 + DAY(full_date),
    full_date,
    YEAR(full_date),
    DATEPART(quarter, full_date),
    MONTH(full_date),
    CASE MONTH(full_date)
        WHEN 1 THEN 'janvier'  WHEN 2 THEN 'février'   WHEN 3 THEN 'mars'
        WHEN 4 THEN 'avril'    WHEN 5 THEN 'mai'       WHEN 6 THEN 'juin'
        WHEN 7 THEN 'juillet'  WHEN 8 THEN 'août'      WHEN 9 THEN 'septembre'
        WHEN 10 THEN 'octobre' WHEN 11 THEN 'novembre' ELSE 'décembre' END,
    DAY(full_date),
    iso_dow,
    CASE iso_dow
        WHEN 1 THEN 'lundi' WHEN 2 THEN 'mardi' WHEN 3 THEN 'mercredi'
        WHEN 4 THEN 'jeudi' WHEN 5 THEN 'vendredi' WHEN 6 THEN 'samedi' ELSE 'dimanche' END,
    CASE WHEN iso_dow >= 6 THEN 1 ELSE 0 END
FROM calc AS c
WHERE NOT EXISTS (SELECT 1 FROM gold.dim_date AS x WHERE x.full_date = c.full_date);

-- ---------- 2. dim_desk : ajoute les desks manquants ----------
INSERT INTO gold.dim_desk (desk_key, desk_name, asset_class, loaded_at)
SELECT
    (SELECT ISNULL(MAX(desk_key), 0) FROM gold.dim_desk) + ROW_NUMBER() OVER (ORDER BY s.desk),
    s.desk,
    s.asset_class,
    GETDATE()
FROM (SELECT DISTINCT desk, asset_class
      FROM lh_horizon.dbo.silver_instruments
      WHERE desk IS NOT NULL) AS s
WHERE NOT EXISTS (SELECT 1 FROM gold.dim_desk AS d WHERE d.desk_name = s.desk);

-- ---------- 3. dim_instrument (type 1) : met à jour puis ajoute ----------
UPDATE t
SET t.instrument_name = s.instrument_name,
    t.isin            = s.isin,
    t.desk            = s.desk,
    t.asset_class     = s.asset_class,
    t.currency        = s.currency,
    t.ref_price       = s.ref_price,
    t.loaded_at       = GETDATE()
FROM gold.dim_instrument AS t
INNER JOIN lh_horizon.dbo.silver_instruments AS s
    ON s.instrument_id = t.instrument_id;

INSERT INTO gold.dim_instrument
    (instrument_key, instrument_id, instrument_name, isin, desk, asset_class, currency, ref_price, loaded_at)
SELECT
    (SELECT ISNULL(MAX(instrument_key), 0) FROM gold.dim_instrument) + ROW_NUMBER() OVER (ORDER BY s.instrument_id),
    s.instrument_id, s.instrument_name, s.isin, s.desk, s.asset_class, s.currency, s.ref_price, GETDATE()
FROM lh_horizon.dbo.silver_instruments AS s
WHERE NOT EXISTS (SELECT 1 FROM gold.dim_instrument AS t WHERE t.instrument_id = s.instrument_id);

-- ---------- 4. dim_client (type 2) ----------
-- 4a. fermer la version courante des clients dont un attribut suivi a changé
UPDATE t
SET t.valid_to   = @today,
    t.is_current = 0
FROM gold.dim_client AS t
INNER JOIN lh_horizon.dbo.silver_clients AS s
    ON s.client_id = t.client_id
WHERE t.is_current = 1
  AND (   ISNULL(t.client_name, '') <> ISNULL(s.client_name, '')
       OR ISNULL(t.country, '')     <> ISNULL(s.country, '')
       OR ISNULL(t.segment, '')     <> ISNULL(s.segment, '')
       OR ISNULL(t.risk_rating, -1) <> ISNULL(s.risk_rating, -1));

-- 4b. insérer les nouveaux clients et les nouvelles versions
INSERT INTO gold.dim_client
    (client_key, client_id, client_name, country, segment, risk_rating,
     created_at, duplicate_group_size, valid_from, valid_to, is_current, loaded_at)
SELECT
    (SELECT ISNULL(MAX(client_key), 0) FROM gold.dim_client) + ROW_NUMBER() OVER (ORDER BY s.client_id),
    s.client_id, s.client_name, s.country, s.segment, s.risk_rating,
    s.created_at, s.duplicate_group_size,
    CASE WHEN EXISTS (SELECT 1 FROM gold.dim_client AS x WHERE x.client_id = s.client_id)
         THEN @today ELSE CAST('1900-01-01' AS date) END,
    CAST('9999-12-31' AS date),
    1,
    GETDATE()
FROM lh_horizon.dbo.silver_clients AS s
WHERE NOT EXISTS (SELECT 1 FROM gold.dim_client AS c
                  WHERE c.client_id = s.client_id AND c.is_current = 1);

-- ---------- 5. faits du jour : suppression puis réinsertion (rejouable) ----------
DELETE FROM gold.fact_transactions WHERE file_date = @run_date;

INSERT INTO gold.fact_transactions
    (transaction_id, date_key, client_key, instrument_key, desk_key, trade_timestamp,
     side, quantity, price, notional, currency, status, file_date, silver_batch_id, loaded_at)
SELECT
    s.transaction_id, dt.date_key, c.client_key, i.instrument_key, d.desk_key,
    s.trade_timestamp, s.side, s.quantity, s.price, s.notional, s.currency, s.status,
    @run_date, s.[_silver_batch_id], GETDATE()
FROM lh_horizon.dbo.silver_transactions AS s
INNER JOIN gold.dim_client AS c
    ON  c.client_id = s.client_id
    AND s.trade_date >= c.valid_from
    AND s.trade_date <  c.valid_to
INNER JOIN gold.dim_instrument AS i ON i.instrument_id = s.instrument_id
INNER JOIN gold.dim_desk       AS d ON d.desk_name     = s.desk
INNER JOIN gold.dim_date       AS dt ON dt.full_date   = s.trade_date
WHERE s.[_file_date] = @day_txt;

-- ---------- 6. rapprochement avec Silver ----------
SELECT @expected = COUNT(*)
FROM lh_horizon.dbo.silver_transactions
WHERE [_file_date] = @day_txt;

SELECT @loaded = COUNT(*)
FROM gold.fact_transactions
WHERE file_date = @run_date;

-- Si les chiffres ne correspondent pas, on annule les faits du jour.
-- (Pas de IF ni de transaction : une seule instruction, conditionnée par les variables.)
DELETE FROM gold.fact_transactions
WHERE file_date = @run_date
  AND @loaded <> @expected;

INSERT INTO etl.load_log (run_date, step_name, rows_expected, rows_loaded, status, message, logged_at)
VALUES (
    @run_date,
    'load_gold',
    @expected,
    CASE WHEN @loaded <> @expected THEN 0 ELSE @loaded END,
    CASE WHEN @expected = 0 OR @loaded <> @expected THEN 'FAILED' ELSE 'SUCCESS' END,
    CASE WHEN @expected = 0 THEN 'Aucune ligne Silver pour ce jour : lancer Silver d abord'
         WHEN @loaded <> @expected THEN 'Rapprochement KO : une ligne Silver ne trouve pas sa dimension. Faits annules.'
         ELSE NULL END,
    GETDATE()
);

-- ---------- Résultat : lis la colonne status ----------
SELECT TOP 1 run_date, status, rows_expected, rows_loaded, message
FROM etl.load_log
ORDER BY logged_at DESC;
