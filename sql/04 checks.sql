-- =====================================================================
-- Contrôles et requêtes métier. Les contraintes étant NOT ENFORCED,
-- ces contrôles REMPLACENT la vérification d'unicité du moteur.
-- MODE D'EMPLOI : copie UNE requête (du SELECT jusqu'au point-virgule), colle-la dans
-- une nouvelle requête SQL et exécute-la. Ne sélectionne pas les lignes de commentaire.
-- =====================================================================

-- CONTROLE 1 : rapprochement Gold / Silver par jour (lignes ET montants)
SELECT g.file_date, g.nb_gold, s.nb_silver, g.sum_gold, s.sum_silver,
       CASE WHEN g.nb_gold = s.nb_silver AND g.sum_gold = s.sum_silver THEN 'OK' ELSE 'ECART' END AS verdict
FROM (SELECT file_date, COUNT(*) AS nb_gold, SUM(notional) AS sum_gold
      FROM gold.fact_transactions GROUP BY file_date) AS g
INNER JOIN (SELECT [_file_date] AS jour, COUNT(*) AS nb_silver, SUM(notional) AS sum_silver
            FROM lh_horizon.dbo.silver_transactions GROUP BY [_file_date]) AS s
    ON CAST(s.jour AS date) = g.file_date
ORDER BY g.file_date;

-- CONTROLE 2 : doublons de transaction_id dans les faits (attendu : aucune ligne)
SELECT transaction_id, COUNT(*) AS n
FROM gold.fact_transactions
GROUP BY transaction_id
HAVING COUNT(*) > 1;

-- CONTROLE 3 : plus d'une version courante pour un même client (attendu : aucune ligne)
SELECT client_id, COUNT(*) AS versions_courantes
FROM gold.dim_client
WHERE is_current = 1
GROUP BY client_id
HAVING COUNT(*) > 1;

-- CONTROLE 4 : clés en double dans les autres dimensions (attendu : aucune ligne)
SELECT 'dim_instrument' AS dimension, instrument_id AS cle, COUNT(*) AS n
FROM gold.dim_instrument GROUP BY instrument_id HAVING COUNT(*) > 1
UNION ALL
SELECT 'dim_desk', desk_name, COUNT(*) FROM gold.dim_desk GROUP BY desk_name HAVING COUNT(*) > 1;

-- CONTROLE 5 : versions client qui se chevauchent (attendu : aucune ligne)
SELECT a.client_id, a.client_key AS version_a, b.client_key AS version_b
FROM gold.dim_client AS a
INNER JOIN gold.dim_client AS b
    ON a.client_id = b.client_id AND a.client_key < b.client_key
   AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to;

-- CONTROLE 6 : journal des chargements Gold
SELECT * FROM etl.load_log ORDER BY logged_at DESC;

-- REQUETE METIER 1 : volume traité par desk
SELECT d.desk_name, COUNT(*) AS nb_transactions, SUM(f.notional) AS notionnel_total
FROM gold.fact_transactions AS f
INNER JOIN gold.dim_desk AS d ON d.desk_key = f.desk_key
GROUP BY d.desk_name
ORDER BY notionnel_total DESC;

-- REQUETE METIER 2 : 10 premiers clients par notionnel (avec la version valable au moment de la transaction)
SELECT TOP 10 c.client_id, c.client_name, c.country, SUM(f.notional) AS notionnel_total
FROM gold.fact_transactions AS f
INNER JOIN gold.dim_client AS c ON c.client_key = f.client_key
GROUP BY c.client_id, c.client_name, c.country
ORDER BY notionnel_total DESC;

-- REQUETE METIER 3 : historique des versions d'un client (test du type 2)
SELECT client_key, client_id, risk_rating, valid_from, valid_to, is_current
FROM gold.dim_client
WHERE client_id = 'CLI00001'
ORDER BY valid_from;