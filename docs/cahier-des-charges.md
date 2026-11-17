# Cahier des charges – Plateforme de données Banque Horizon

**Version** : 0.1 | **Statut** : brouillon | **Auteur** : à compléter | **Date** : à compléter

## 1. Contexte
Banque Horizon (fictive) dispose de données réparties dans plusieurs systèmes (application de trading,
référentiels, fichiers Excel de la Finance, données de marché). Les équipes produisent leurs chiffres
chacune de leur côté, ce qui crée des écarts, des délais et un manque de traçabilité.

## 2. Objectifs
| # | Objectif | Indicateur de réussite |
|---|---|---|
| O1 | Centraliser les données dans une plateforme unique | Toutes les sources du périmètre chargées dans OneLake |
| O2 | Fiabiliser la donnée | Contrôles qualité automatiques, anomalies tracées dans une table de rejet |
| O3 | Garantir la traçabilité | Chaque ligne Gold remonte à son fichier source (lot, date de chargement) |
| O4 | Sécuriser l'accès | Chaque équipe ne voit que son périmètre (RLS) |
| O5 | Automatiser et superviser | Chargement quotidien sans intervention, alerte en cas d'échec |
| O6 | Maîtriser les coûts | Chargements incrémentaux, consommation suivie |

## 3. Périmètre
**Inclus** : transactions de trading, référentiels clients et instruments, taux de change,
fichiers Finance, modèle analytique, rapport Power BI, sécurité, supervision.
**Exclu** : temps réel intrabanque, machine learning, calcul réglementaire complet.

## 4. Utilisateurs et besoins
| Équipe | Besoin | Accès |
|---|---|---|
| Trading | Positions et transactions du jour | Son desk uniquement |
| Risques | Expositions par instrument et par client | Tous les desks |
| Conformité | Détection d'opérations atypiques, traçabilité | Lecture complète, avec audit |
| Finance | P&L et reporting mensuel | Données agrégées |

## 5. Sources de données
| Source | Format | Fréquence | Volume (estimé) | Risques connus |
|---|---|---|---|---|
| Transactions trading | CSV (extraction SQL) | Quotidienne | ~5 000 lignes/jour | Doublons, champs manquants, dates en formats mixtes |
| Référentiel instruments | CSV | Hebdomadaire | ~40 lignes | Instruments inconnus dans les transactions |
| Référentiel clients | CSV | Hebdomadaire | ~200 lignes | Doublons métier |
| Taux de change | API / fichier | Quotidienne | Faible | Arrivée tardive |
| Fichiers Finance | Excel | Mensuelle | Faible | Colonnes qui changent |

## 6. Exigences fonctionnelles
- EF1 : ingestion quotidienne automatisée de chaque source
- EF2 : conservation de la donnée brute sans modification (couche Bronze)
- EF3 : nettoyage, typage, dédoublonnage (couche Silver)
- EF4 : modèle en étoile : faits `Transactions`, dimensions `Client`, `Instrument`, `Date`, `Desk` (couche Gold)
- EF5 : historisation des clients (SCD type 2)
- EF6 : table de rejet avec motif pour chaque ligne écartée
- EF7 : rapport Power BI : volumes, notionnel, répartition par desk, qualité des données

## 7. Exigences non fonctionnelles
- **Sécurité** : RLS par desk, rôles par workspace, aucun secret en clair
- **Traçabilité** : colonnes techniques (lot, date de chargement, source), journal des exécutions
- **Fiabilité** : chargement idempotent (relancer ne crée pas de doublons), reprise sur erreur
- **Performance** : chargement quotidien terminé avant 7 h
- **Maintenabilité** : code versionné dans Git, trois environnements (Dev, Recette, Prod)
- **Coûts** : suivi de la consommation (Capacity Metrics), pause de la capacité hors usage

## 8. Contraintes et hypothèses
- Données exclusivement fictives ou publiques
- Capacité Fabric limitée (essai ou petite capacité) : à vérifier selon ta licence
- Projet réalisé seul, en environ 6 semaines

## 9. Risques
| Risque | Impact | Parade |
|---|---|---|
| Qualité des sources | Chiffres faux | Contrôles + table de rejet |
| Changement de schéma | Pipeline en échec | Gestion de l'évolution de schéma + alerte |
| Dépassement de capacité | Lenteurs, coûts | Suivi, incrémental, pause |
| Accès trop larges | Fuite de données | RLS, revue des droits |

## 10. Livrables
Dépôt Git, pipelines, notebooks, modèle Gold, rapport Power BI, documentation, fiches d'incident.

## 11. Planning
Voir le tableau d'avancement du [README](../README.md).
