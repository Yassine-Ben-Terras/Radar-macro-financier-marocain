# Partie 4 — Assistant documentaire et SQL

## Livré

Un assistant local déterministe : recherche lexicale de passages PDF avec citations et réponses chiffrées via cinq intentions SQL autorisées. Il fonctionne sans clé API, sans LLM et sans service cloud. Ce socle n'est pas encore un agent RAG génératif ni un système Text-to-SQL libre. Le statut `retrieved` désigne des résultats de recherche, pas une réponse factuelle synthétisée.

Deux documents originaux BAM ont été téléchargés : rapport annuel 2024 (358 pages) et statistiques monétaires de septembre 2024 (9 pages). Extraction pypdf, découpage de 180 mots avec recouvrement de 30 mots, sans traverser les frontières de pages. Index SQLite FTS5, classement BM25.

| Corpus | Pages indexées | Pages à vérifier |
|---|---:|---:|
| Rapport annuel 2024 | 336 | 22 |
| Statistiques monétaires septembre 2024 | 7 | 2 |
| Total | 343 | 24 |

1 008 passages indexés et 29 151 observations structurées disponibles. Le contrôle de pages repose sur un minimum de 60 mots extractibles : une couverture courte, une page vide ou une image est exclue, mais cela ne prouve pas que toute page exclue requiert un OCR. Inversement, le seuil ne garantit pas la qualité des tableaux ou l'ordre de lecture. Les tableaux PDF ne servent jamais de source au calcul SQL.

## Démarrage

```powershell
python -m pip install -r requirements-assistant.txt
# Facultatif si les deux PDF sont déjà téléchargés :
./scripts/download-pdfs.ps1
python -m radar.assistant --build
python -m radar.assistant --interactive
```

Le téléchargeur conserve les versions par SHA-256 dans `data/documents/archive/` et place la version courante à la racine de `data/documents/`. Il n'est jamais lancé automatiquement par une question. Les fichiers téléchargés initialement ont été récupérés directement depuis les URL officielles ; le téléchargeur réutilisable a fait l'objet d'une vérification de syntaxe PowerShell, sans nouvel essai réseau.

Le constructeur vérifie la signature PDF et reconstruit l'index dans un fichier temporaire, puis le remplace après succès. Un échec laisse l'index précédent intact. La date de modification locale du PDF est enregistrée comme indice de collecte, jamais comme date de publication.

Exemples pris en charge :

```powershell
python -m radar.assistant --question "Quel est le crédit bancaire total en août 2026 ?"
python -m radar.assistant --question "Quelle est la variation annuelle du crédit bancaire en août 2026 ?"
python -m radar.assistant --question "Quelle est la part du secteur privé dans le crédit bancaire en août 2026 ?"
python -m radar.assistant --question "Quel est l'IPC national en 2025 ?"
python -m radar.assistant --question "Quelle est la variation annuelle de l'IPC national en 2025 ?"
python -m radar.assistant --question "Recherche documentaire : politique monétaire"
```

Les formulations restent strictes, à l'exception des accents, de la casse et de la ponctuation finale. Une question hors modèle reçoit une abstention ; aucun routage silencieux vers une autre métrique. Une question documentaire doit utiliser le préfixe explicite. La recherche exige tous les mots utiles retenus ; ce choix peut manquer des synonymes ou paraphrases. Il ne faut pas interpréter une absence de résultat comme une absence d'information dans le document.

## Traçabilité et limites

Réponse SQL : période, unité, valeur, requête paramétrée, paramètres, empreinte source, feuille et cellule. Le calcul de part cite le numérateur et le dénominateur. Un résultat nul n'est pas transformé en zéro. La base est ouverte avec `mode=ro` et `query_only=ON` ; aucun SQL fourni par l'utilisateur n'est exécuté. Les requêtes sont bornées en lignes et en étapes de VM SQLite. Ce mécanisme ne remplace pas les permissions Unity Catalog lors du déploiement.

Résultat documentaire : titre, numéro physique de page PDF, étiquette de page fournie par le PDF, URL avec `#page=`, empreinte du fichier, identifiant du passage et extrait court. Le numéro PDF et le numéro imprimé peuvent différer. Exemple vérifié visuellement : page PDF 42 du rapport annuel, étiquette imprimée 22. L'extrait renvoie bien à l'encadré de politique monétaire affiché sur cette page. Une page du bulletin monétaire a également été rendue et inspectée ; ses tableaux ne sont pas structurés automatiquement.

BM25 est un score de classement lexical, pas une probabilité de vérité ou un score de confiance. Des mots présents dans une page ne suffisent pas à prouver qu'elle répond exactement à la question. La réponse indique donc « passages retrouvés » et invite à lire le contexte. Aucun texte du corpus n'est exécuté comme une instruction. Les chiffres d'années différentes entre PDF et tables restent séparés.

Les droits de redistribution des PDF BAM ne sont pas établis : l'accès public ne leur attribue pas automatiquement la licence ODbL des séries structurées. PDF, index, passages et exports restent locaux et ignorés par Git ; ne pas les publier tels quels avec le code sans vérifier les conditions applicables.

## Évaluation et démonstration

```powershell
python -m unittest discover -s tests -v
python -m radar.evaluate_assistant
```

27 tests passent sur l'ensemble du projet. Les dix tests ajoutés portent notamment sur le routage, le découpage, la lecture seule, les requêtes invalides, les périodes absentes, le calcul d'une part et la correspondance des citations avec les passages stockés.

Le jeu `config/assistant-evaluation.json` contient 11 scénarios fonctionnels ; 11 passent. Il inclut quatre questions chiffrées, une recherche documentaire connue et six cas d'abstention. Le cas documentaire a été fixé après inspection du corpus : ce n'est pas un benchmark indépendant de pertinence. Ne pas annoncer « 100 % de précision » ni une qualité générale du RAG à partir de ce jeu.

Sorties :

- `outputs/partie-4/demonstration.md` : questions, résultats et liens de provenance.
- `outputs/partie-4/evaluation.json` : résultats détaillés des scénarios.
- `data/assistant.quality.json` : statut de chaque page et empreinte de l'entrée Gold.
- `data/assistant.sqlite` : index de recherche et copie locale des observations.

## Databricks

Le notebook `notebooks/04_assistant.py` a réussi sur Azure le 3 novembre 2026 : run `<run-id>`, tâche `<task-run-id>`. Il lit les vues Gold ADLS, collecte 5 787 observations nationales, construit SQLite sur le disque temporaire du driver et archive 1 008 passages dans `radar_adls.radar_bronze.document_chunks`, physiquement dans le conteneur ADLS `lakehouse`. L'index de recherche courant ne mélange pas les anciennes versions conservées dans Delta. Deux PDF, 343 pages indexées, 24 pages courtes ou sans texte à examiner, onze contrôles fonctionnels réussis. Démarrage 186 s ; exécution 230 s. Preuve : `docs/assistant-validation-2026-11-03.json`.

La configuration `infra/assistant-adls-run.json` installe pypdf 6.10.0 dans l'environnement serverless 4 et utilise `catalog=radar_adls`. Aucun endpoint ni job permanent. Le coût facturé reste à vérifier. L'index fermé, la démonstration, la qualité des pages et l'évaluation sont conservés dans le volume ADLS `radar_adls.radar_gold.artifacts`, sous `assistant/e292fc863ae840e4afa2efbd9086a34c`.

La copie téléchargée sous `outputs/partie-4-azure/artifacts` permet de démontrer l'index produit par Databricks sans relancer Spark :

```powershell
python -m radar.assistant --index outputs/partie-4-azure/artifacts/assistant.sqlite --interactive
```

Le fichier SQLite doit être ouvert depuis une copie locale ; il ne doit jamais être utilisé directement comme base active sur le volume partagé.

## Suite nécessaire avant de parler de projet Azure complet

1. Les notebooks 02, 03 et 04 ont réussi sur Azure/ADLS. Vérifier les coûts facturés et l'idempotence lors d'une relance cloud avant de clôturer ces critères.
2. Évaluer la récupération documentaire sur des questions et pages annotées indépendamment ; mesurer rappel et pertinence avant d'ajouter un générateur.
3. Si le budget le permet, ajouter un LLM à la demande pour une synthèse fondée exclusivement sur les passages, avec citations contrôlées, abstention et mesure du coût par requête. Une couche de génération reste nécessaire pour un RAG génératif complet.
4. Ajouter l'OCR seulement aux pages qui en ont réellement besoin, puis vérifier les extractions. La CNSS et les données par branche restent des chantiers de sources distincts.

Argumentaire d'entretien : « J'ai d'abord établi des réponses traçables et un jeu de contrôle sans coût récurrent. Les données tabulaires sont interrogées par des modèles SQL bornés ; les PDF fournissent des preuves documentaires avec numéros de page. Je distingue explicitement cette première version d'un agent génératif, dont je dois encore mesurer la pertinence et le coût. »
