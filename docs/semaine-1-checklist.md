# Semaine 1 – Checklist

## Jour 1 : cadrage
- [ ] Relire et adapter le cahier des charges (auteur, date, périmètre)
- [ ] Créer le dépôt GitHub `banque-horizon-fabric` (public)
- [ ] Pousser la structure et le README

## Jour 2 : architecture
- [ ] Relire le schéma et le rendre cohérent avec ton choix final
- [ ] Compléter les décisions d'architecture (au moins une alternative par décision)
- [ ] Définir les conventions de nommage (ex. `bronze_transactions`, `silver_transactions`)

## Jour 3 : environnement
- [ ] Vérifier l'accès à Fabric (essai ou capacité) et les fonctions disponibles (Git, deployment pipelines)
- [ ] Créer les workspaces `horizon-dev`, `horizon-recette`, `horizon-prod`
- [ ] Créer un Lakehouse et un Warehouse dans Dev
- [ ] Mettre la capacité en pause quand tu ne travailles pas

## Jour 4 : données
- [ ] Installer Python et les dépendances du générateur
- [ ] Générer 5 jours de données : `python generate_transactions.py --start 2026-01-05 --days 5`
- [ ] Ouvrir un fichier : repérer les anomalies à la main
- [ ] Compter les anomalies attendues dans `_controle/issues_*.json`

## Jour 5 : bilan et contenu
- [ ] Mettre à jour le README (avancement)
- [ ] Préparer un schéma propre de l'architecture (capture ou Canva)
- [ ] Rédiger le numéro de newsletter : « Comment cadrer un projet Fabric avant d'écrire une ligne de code »
