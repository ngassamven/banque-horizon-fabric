# Banque Horizon – Plateforme de données sur Microsoft Fabric

> Projet personnel d'approfondissement. Banque, équipes, données et besoins sont **fictifs**.
> Aucune donnée, aucun schéma ni aucun code d'un employeur n'est utilisé.

## Contexte
Banque Horizon, banque d'investissement fictive, veut centraliser les données de trading,
de risque et de conformité dans une plateforme unique (Microsoft Fabric / OneLake).
Voir [le cahier des charges](docs/cahier-des-charges.md) et [l'architecture](docs/architecture.md).

## Stack
Microsoft Fabric (Lakehouse, Warehouse, Pipelines, Notebooks PySpark, Direct Lake, Activator),
ADLS Gen2, Delta Lake, Power BI, Git.

## Avancement
- [x] Semaine 1 : cadrage, architecture, générateur de données
- [ ] Semaine 2 : ingestion vers ADLS Gen2 et Bronze
- [ ] Semaine 3 : Silver (qualité, MERGE)
- [ ] Semaine 4 : Gold (modèle en étoile)
- [ ] Semaine 5 : sécurité (RLS), Power BI, alertes
- [ ] Semaine 6 : CI/CD, incidents simulés, documentation

## Démarrer
```bash
cd data-generator
pip install -r requirements.txt
python generate_transactions.py --start 2026-01-05 --days 5 --out ./output
```
Voir l'aide : `python generate_transactions.py --help`.

## Structure
```
docs/            cahier des charges, architecture, sécurité, incidents
data-generator/  génération des données fictives
notebooks/       Bronze, Silver, Gold, qualité (à venir)
pipelines/       orchestration (à venir)
sql/             T-SQL du Warehouse (à venir)
tests/           contrôles automatiques (à venir)
```
