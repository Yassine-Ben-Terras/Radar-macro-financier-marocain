# Partie 2 — Ingestion et Lakehouse

## Livré et exécuté

Deux fichiers réels téléchargés le 2 novembre 2026, archivés avec SHA-256, URL, date de collecte UTC et copie du catalogue CKAN. La source originale reste inchangée. Les métadonnées du portail déclarent la licence ODbL pour les deux jeux.

| Source | Mesure | Fréquence | Couverture chargée | Observations |
|---|---|---|---|---:|
| HCP | IPC, base 2017 = 100, par ville et catégorie | Annuelle | 2017–2025 | 24 696 |
| BAM | Encours du crédit par secteur institutionnel, millions MAD | Mensuelle | Décembre 2001–août 2026 | 4 455 |

Le nom historique du jeu BAM mentionne septembre 2023, mais la ressource sélectionnée couvre août 2026. La sélection utilise un identifiant de ressource explicite et les périodes sont lues dans le fichier, pas déduites du titre du catalogue.

Les catégories de consommation HCP ne sont pas des secteurs économiques. Les secteurs institutionnels BAM ne sont pas des branches d'activité. Aucun rapprochement sectoriel arbitraire n'est effectué ; les données actuelles forment un socle macroéconomique. CNSS et les données par branche restent à intégrer après vérification.

## Exécution locale

Python 3.10+ et openpyxl 3.1.5 sont requis. Le Python embarqué de Codex a servi aux vérifications sur cette machine ; le projet reste indépendant de ce chemin.

```powershell
python -m pip install -r requirements.txt
python -m radar.pipeline --fetch
python -m radar.pipeline
python -m unittest discover -s tests -v
```

`--fetch` consulte seulement les deux ressources configurées dans `config/ingestion.json`. Sans cet argument, aucun accès réseau n'est réalisé. Pour un nouveau format source, l'analyse échoue explicitement au lieu de deviner le schéma.

Sorties locales (ignorées par Git) :

- `data/bronze/<source>/<sha256>/` : Excel original, catalogue, manifeste.
- `data/radar.sqlite` : contrôle local de l'idempotence avec clés uniques, transactions et historique des versions.
- `data/prepared/*.jsonl` : exports reproductibles Bronze, Silver, rejets et indicateurs.
- `data/quality_report.json` : effectifs et couverture.

SQLite sert uniquement à la validation locale. Les tables Azure sont bien des tables Delta, créées par le notebook. Les PDF restent hors de ce lot et seront traités dans la partie documentaire.

## Exécution Databricks préparée, non encore vérifiée

1. Terminer les prérequis Azure de la partie 1 : coût et workspace serverless.
2. Importer le projet dans un dossier workspace/Git folder. Ajouter `openpyxl==3.1.5` à l'environnement serverless.
3. Choisir un catalogue Unity Catalog existant et exécuter `sql/01_init.sql`.
4. Copier les archives dans le volume, après authentification CLI sur le bon workspace :

```powershell
databricks fs cp ./data/bronze dbfs:/Volumes/<catalog>/radar_bronze/raw_files/bronze --recursive
```

5. Ouvrir `notebooks/02_lakehouse.py`, renseigner `catalog` et `repo_root` (chemin `/Workspace/...` du projet), lancer manuellement une fois.
6. Le notebook vérifie les empreintes, normalise les fichiers originaux avec le même module Python, puis effectue des MERGE à insertion seule dans Bronze/Silver. Les schémas sont explicites, y compris pour les rejets vides.
7. Relancer et vérifier les mêmes effectifs, puis contrôler le coût. Aucun job planifié ni warehouse permanent n'est nécessaire.

Ne lancer qu'un chargement à la fois. Les MERGE de tables distinctes ne constituent pas une transaction multi-table : une interruption peut nécessiter une relance idempotente avant consultation de Gold. L'exécution Spark/Delta et l'éligibilité serverless n'ont pas été testées dans cette session.

## Règles de qualité et de version

La clé métier contient source, indicateur, fréquence, période, géographie, catégorie, nomenclature et unité. La clé de version ajoute empreinte du fichier et version de transformation. Chaque observation conserve feuille et cellule. Les valeurs manquantes, non numériques, infinies, négatives ou à dimensions absentes sont mises en quarantaine. Toutes les occurrences d'une clé métier dupliquée sont rejetées.

Les dates BAM contiennent des jours variables ; la période mensuelle est normalisée au premier jour, et la date brute reste dans `source_period`. On ne prétend pas que ces jours représentent une date de publication. Les dates de publication inconnues restent nulles.

Gold retient la dernière archive collectée par source et la version active du parseur. Les données anciennes restent consultables en Silver. Une observation supprimée ou invalide dans la nouvelle archive ne doit pas réapparaître depuis une archive plus ancienne.

La variation annuelle compare exactement le même mois de l'année précédente pour BAM, et l'année précédente pour HCP. Période absente ou dénominateur nul : résultat null. Pas d'interpolation, pas de somme d'indices, pas de somme des parents et sous-catégories. Les vues courantes ne constituent pas un jeu de backtest historique sans fuite d'information : les dates de publication ne sont pas disponibles.

## Vérifications réalisées

- 29 151 cellules candidates et observations ; zéro rejet réel dans les fichiers sélectionnés.
- Deux exécutions locales : effectifs identiques et empreinte identique de l'export des observations.
- Tests des nombres français, valeurs manquantes/non finies, doublons, géographies, clés stables, périodes manquantes, division par zéro et révisions.
- Rapprochement des trois grands secteurs BAM avec le crédit total sur 297 périodes : écart maximal 0,007 MDH, sous la tolérance de contrôle de 0,01 MDH.
- Contrôle d'une cellule HCP et de sa variation annuelle contre les valeurs originales.
- Compilation Python réussie ; aucune exécution Azure réalisée.

## Attribution et réutilisation

Sources : HCP, « Indice des prix à la consommation (Base 100 2017) », et Bank Al-Maghrib, « Ventilation du crédit bancaire par secteur institutionnel », via data.gov.ma. Transformations : passage au format long, normalisation des périodes, contrôle qualité et variations annuelles. Données originales et dérivées non publiées dans le dépôt par défaut. Conserver l'attribution et respecter les obligations ODbL lors d'une redistribution ; la licence du code doit être choisie séparément.

- HCP : https://data.gov.ma/data/dataset/data_i3981
- BAM : https://data.gov.ma/data/dataset/ventilation-du-credit-bancaire-par-secteur-institutionnel-dec-2001-a-sept-2023
- Licence indiquée : https://opendatacommons.org/licenses/odbl/1-0/
- MERGE Delta : https://learn.microsoft.com/en-us/azure/databricks/delta/merge
- Copie vers volumes : https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/fs-commands
