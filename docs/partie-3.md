# Partie 3 — Analyse et restitution

## Résultat

Le rapport autonome `outputs/partie-3/radar.html` s'ouvre dans un navigateur sans serveur ni connexion internet pour ses graphiques. Plotly est embarqué dans le fichier. Les liens de sources nécessitent une connexion si on les ouvre. Les données proviennent exclusivement de la partie 2 ; aucun rafraîchissement n'est effectué pendant la génération.

Le rapport contient les séries de crédit et d'IPC, les parts des trois grands secteurs institutionnels, les douze divisions IPC nationales et une comparaison de trois prévisions de référence. Les graphiques permettent zoom, survol et sélection par légende. Les tableaux conservent les valeurs lisibles.

## Reproduction

```powershell
python -m pip install -r requirements-analytics.txt
python -m radar.analytics
python -m unittest discover -s tests -v
```

Sur cette machine, les bibliothèques de graphique ont été installées dans `.deps`, sans modifier le Python embarqué. Si cet environnement est réutilisé, ajouter `.deps` à `PYTHONPATH` avant l'exécution. Une installation Python normale utilise les commandes ci-dessus.

Sorties : `radar.html`, `analysis.json`, `macro_indicators.csv`, `baseline_predictions.csv`, `baseline_metrics.csv`. Les exports de données conservent leur attribution ODbL. Le JSON comprend les empreintes des sources et de l'entrée complète, les dates de collecte, les prédictions et les métriques. Les exports restent ignorés par Git.

## Lecture du dernier instantané

- BAM, août 2026 : encours total d'environ 1 292,3 milliards MAD ; variation sur douze mois de 11,31 %.
- HCP, année 2025 : IPC national de 119,6 (base 2017 = 100), soit une variation de 0,76 % par rapport à l'indice annuel 2024.
- Ces dates correspondent aux dernières périodes des fichiers chargés, pas à une garantie de fraîcheur des publications disponibles aujourd'hui.
- Les trois grands secteurs BAM sont mutuellement exclusifs au niveau retenu. Les sous-catégories ne sont pas ajoutées à leurs parents.
- L'IPC national publié est utilisé directement. Une moyenne simple des indices par ville ou division serait incorrecte sans pondérations.

## Évaluation temporelle

Série : crédit bancaire total, mensuel, décembre 2001 à août 2026. Les 24 dernières périodes, septembre 2024 à août 2026, sont évaluées successivement à horizon un mois. L'apprentissage initial s'arrête en août 2024, puis la fenêtre s'agrandit avec chaque observation passée.

Méthodes fixées avant comparaison :

1. Dernier mois : prévision de t égale à l'encours de t−1.
2. Même mois de l'année précédente : encours de t−12.
3. Dérive sur douze mois : encours de t−1 plus un douzième de son évolution depuis t−13.

| Méthode | MAE, millions MAD | RMSE, millions MAD | MASE |
|---|---:|---:|---:|
| Dernier mois | 19 194,45 | 25 275,29 | 2,517 |
| Même mois, année précédente | 72 890,14 | 78 117,24 | 9,560 |
| Dérive sur 12 mois | 19 803,46 | 24 375,52 | 2,597 |

MASE utilise une échelle fixe : erreur absolue moyenne de la méthode dernier mois sur l'apprentissage initial seulement. Une MASE supérieure à 1 compare donc le test à cette erreur historique, et non à la méthode dernier mois sur le test. Aucune optimisation des paramètres ni sélection de modèle de production n'est effectuée sur ces 24 observations.

Limite fondamentale : il s'agit des séries révisées actuellement collectées, sans dates historiques de publication. Le découpage empêche d'utiliser une période future dans le calcul, mais ne corrige pas le biais lié aux révisions ni les délais de publication. Ne pas qualifier cette évaluation de backtest en temps réel sans fuite d'information.

## Databricks et MLflow

`notebooks/03_analytics.py` lit les vues Gold de la partie 2, limite explicitement la collecte à 10 000 observations nationales, produit le même rapport et enregistre paramètres, métriques, empreinte d'entrée et fichiers dans une expérience MLflow. Renseigner `catalog`, `repo_root` et `experiment_path`, puis lancer manuellement après déploiement du workspace.

Le notebook utilise les API de suivi documentées par MLflow : https://mlflow.org/docs/latest/ml/tracking/tracking-api/

Statut au 3 novembre 2026 : exécution Databricks réussie, run `<run-id>`, sur `radar_adls`. 5 787 observations nationales collectées pour l'analyse. Expérience MLflow `<experiment-id>`, run `<mlflow-run-id>`. Artefacts dans `dbfs:/Volumes/radar_adls/radar_gold/artifacts/mlflow/<mlflow-run-id>/artifacts`, puis téléchargés sous `outputs/partie-3-azure/artifacts`. Démarrage 196 s, exécution 217 s. Les neuf métriques des trois méthodes correspondent aux résultats locaux. Aucun endpoint de modèle ni job périodique créé. Coût réel non encore vérifié.

## Argumentaire d'entretien

« J'ai commencé par des méthodes de référence explicables pour mesurer ce qu'un modèle plus complexe devrait améliorer. Les 297 points mensuels permettent une comparaison temporelle simple. Les neuf indices annuels HCP servent au contexte descriptif ; ils ne justifient pas un modèle complexe. Je distingue les classifications des sources et je conserve les limites des dates de publication. Le rapport autonome permet de démontrer le projet sans laisser de calcul cloud actif. »

Le titre du projet reste un objectif : ce lot apporte le radar macro-financier, pas encore une mesure de risque sectoriel par branche ni une probabilité de défaut. Ces objectifs nécessitent des données appropriées et, pour le défaut, des labels.

## Vérifications

17 tests réussis au total, dont six nouveaux tests analytiques : prévisions connues, métriques attendues, perturbation d'une valeur future sans effet sur les prévisions antérieures, mois manquant, dénominateur MASE nul et historique insuffisant. Compilation des modules et notebooks réussie.

Rapport ouvert dans Chrome headless : graphiques rendus, interaction de légende fonctionnelle, aucune erreur JavaScript, aucun débordement de page à 390 px. Capture desktop examinée visuellement. La vérification de navigateur est reproductible via `scripts/check-report.cjs` avec Playwright et Chrome disponibles.
