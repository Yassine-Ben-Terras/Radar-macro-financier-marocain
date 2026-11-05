# Présentation et démonstration — cinq minutes

## Préparation avant l'entretien

Ouvrir le PowerPoint `outputs/presentation/Radar-macro-financier.pptx` et le rapport `outputs/partie-3-azure/artifacts/radar.html`. Garder `outputs/partie-4-azure/artifacts/demonstration.md` ouvert comme secours. Ces fichiers proviennent des traitements Azure ; la démonstration locale ne nécessite aucune nouvelle exécution cloud.

Dans PowerShell, depuis `<dossier-du-projet>`, lancer l'assistant avec l'index téléchargé d'ADLS :

```powershell
python -m radar.assistant --index outputs/partie-4-azure/artifacts/assistant.sqlite --interactive
```

Préparer les trois questions à copier, une à la fois :

1. `Quel est le crédit bancaire total en août 2026 ?`
2. `Recherche documentaire : politique monétaire`
3. `Quel est le crédit bancaire total en août 2099 ?`

## Déroulé chronométré et texte oral

### 0:00–0:25 — Objectif (diapositive 1)

« Ce portfolio est un radar macro-financier marocain. Il rassemble des séries de Bank Al-Maghrib et du HCP ainsi que deux rapports PDF. Mon objectif est de construire une chaîne traçable : conserver les sources, produire des données contrôlées, comparer des prévisions simples et répondre à des questions avec des preuves. »

### 0:25–1:20 — Architecture (diapositive 2)

« Les données métier sont stockées dans ADLS Gen2, dans mon abonnement Azure. Le conteneur raw conserve les fichiers sources et leurs manifestes. Le conteneur lakehouse contient les tables Delta et les artefacts de restitution. Bronze conserve la provenance ; Silver normalise les observations et isole les rejets ; Gold expose les vues analytiques.

Databricks exécute les notebooks à la demande. Unity Catalog gère les métadonnées et les permissions. Une identité managée, portée par un Access Connector, accède aux conteneurs sans clé de stockage. Le stockage des données du catalogue est dans ADLS ; cela ne signifie pas que la base interne des métadonnées Unity Catalog est une table que j'administre dans ce conteneur. »

### 1:20–2:00 — Choix et budget (diapositive 3)

« À cette échelle, Spark n'est pas indispensable : les vingt-neuf mille observations pourraient être traitées localement. Databricks est un choix de portfolio pour démontrer Delta, la gouvernance et MLflow. Les exécutions sont manuelles, en mode serverless Standard, avec une durée limitée. ADLS utilise LRS et le niveau Hot en France Central. LRS ne protège pas contre la perte d'une région. Mon enveloppe est de cinquante dollars, avec une cible de trente-cinq et quinze de réserve. Le coût réellement facturé reste à vérifier. »

### 2:00–2:40 — Idempotence (diapositive 4)

« J'ai relancé l'ingestion sur Azure avec les mêmes archives sources : vingt-neuf mille cent cinquante et une observations avant et après, sans doublons. Il compare avant et après les effectifs, l'unicité des clés et l'empreinte SHA-256 du contenu de quatre tables et d'une vue Gold. Les cinq empreintes sont identiques et aucune clé n'est nulle. Le mécanisme MERGE utilise des identifiants stables pour éviter les nouvelles insertions des mêmes lignes. Ce test porte sur cette relance et ce jeu de données ; il ne couvre pas encore les exécutions concurrentes ou tous les scénarios de révision. »

### 2:40–3:20 — Résultats analytiques (diapositive 5)

« Je compare trois références simples sur vingt-quatre mois, de septembre 2024 à août 2026. Reprendre la dernière valeur donne l'erreur absolue moyenne la plus faible, environ dix-neuf milliards de dirhams. La dérive est légèrement meilleure en RMSE. Les métriques sont suivies dans MLflow. Il s'agit de séries révisées dont les dates historiques de publication ne sont pas connues : ce résultat ne démontre donc pas une performance de prévision en temps réel. »

### 3:20–4:20 — Démonstration (diapositive 6 puis écran)

**20 secondes :** montrer le rapport HTML et le crédit bancaire total d'août 2026 : environ **1 292,32 milliards de MAD**. Montrer rapidement la comparaison des méthodes.

**25 secondes :** poser les deux premières questions. Montrer la valeur issue de SQL, puis un extrait de politique monétaire avec sa référence documentaire et sa page. Le résultat de référence cite la page physique **42** du rapport annuel BAM (page imprimée 22). Lire la citation affichée, sans inventer une synthèse.

**15 secondes :** poser la question sur 2099. Montrer l'abstention faute de donnée. En cas de problème de terminal, utiliser les réponses déjà enregistrées dans `demonstration.md` en précisant qu'il s'agit d'une trace d'exécution.

### 4:20–5:00 — Limites et suite (diapositive 7)

« Les traitements d'ingestion, d'analyse et d'assistant ont réussi sur Azure. L'assistant exploite mille huit passages PDF et passe onze scénarios fonctionnels. Ce n'est pas une mesure indépendante de pertinence. Il utilise une recherche textuelle et des requêtes SQL autorisées, sans génération par LLM. CNSS et le risque par branche ne sont pas encore intégrés ; vingt-quatre pages PDF restent à examiner. Les prochaines priorités sont de vérifier les coûts facturés et d'évaluer la recherche sur de nouvelles questions. »

## Réponses courtes pour l'entretien

| Question | Réponse défendable |
|---|---|
| Pourquoi ADLS en plus de Databricks ? | Pour conserver sources, tables et artefacts dans un stockage Azure explicite, gouverné par identité managée et référencé dans Unity Catalog. |
| Où est le metastore ? | Unity Catalog gère le service de métadonnées. Le catalogue `radar_adls` a sa racine de stockage des données dans le conteneur lakehouse. Les vues Gold sont des définitions, pas une seconde copie des observations. |
| Pourquoi pas un cluster permanent ? | Les publications sont périodiques et les démonstrations ponctuelles. Les runs manuels évitent de maintenir du calcul pour attendre des données. |
| Le timeout garantit-il une facture inférieure à 50 $ ? | Non. Il borne une exécution, pas la dépense cumulée. Les coûts réels, le stockage et toutes les exécutions doivent être suivis. |
| Est-ce un agent RAG génératif ? | La version livrée combine recherche documentaire FTS5/BM25 et SQL encadré. Elle cite des extraits et s'abstient ; elle n'utilise pas encore de LLM. |
| Pourquoi comparer le contenu et pas seulement le nombre de lignes ? | Un effectif identique peut masquer des modifications. L'empreinte du contenu ordonné complète les contrôles de clés et de cardinalité. |
| Et les corrections de source ? | Le test courant rejoue les mêmes fichiers. Les nouvelles versions, corrections et exécutions concurrentes nécessitent des scénarios séparés. |
| Pourquoi ne pas annoncer un score de risque sectoriel ? | CNSS, les données de branches et les labels adaptés manquent encore. Les résultats actuels sont macroéconomiques. |

## Dossier de preuves

- Idempotence : `outputs/idempotence/run-output.json` et `docs/idempotence-validation-2026-11-03.json`.
- Stockage et ingestion : `docs/adls-validation-2026-11-03.json`.
- Analyse et MLflow : `docs/analytics-validation-2026-11-03.json`.
- Assistant : `docs/assistant-validation-2026-11-03.json`.
- Validation du PowerPoint : `outputs/presentation-build/validation.json`.

Répéter une fois avec chronomètre. À 3:20, passer à la démonstration même si un détail d'architecture reste à expliquer ; le réserver aux questions.
