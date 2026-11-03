# Relance d'ingestion vérifiée sur Azure

Le 3 novembre 2026, le run `<run-id>` s'est terminé avec **SUCCESS** sur le catalogue `radar_adls`. La même ingestion a réellement été rejouée sur les deux archives structurées déjà chargées.

| Objet | Lignes avant | Lignes après | Clés distinctes après | Empreinte du contenu |
|---|---:|---:|---:|---|
| Bronze manifests | 2 | 2 | 2 | Identique |
| Bronze raw_cells | 29 151 | 29 151 | 29 151 | Identique |
| Silver observations_v2 | 29 151 | 29 151 | 29 151 | Identique |
| Silver rejects | 0 | 0 | 0 | Identique |
| Gold indicators | 29 151 | 29 151 | 29 151 | Identique |

Toutes les clés contrôlées sont non nulles. La répartition finale est de **4 455 observations BAM** et **24 696 HCP**. Il n'y a aucun rejet.

## Mécanisme et portée

Le notebook vérifie les empreintes des fichiers archivés et utilise `MERGE ... WHEN NOT MATCHED THEN INSERT` avec les identifiants stables. En mode `verify_idempotence=true`, il capture avant et après les effectifs, les clés et un SHA-256 du contenu ordonné de chaque objet. Les assertions échouent si l'un de ces contrôles diverge.

La preuve porte sur le contenu logique de ces cinq objets pour **une relance avec les mêmes sources et transformations**. Les métadonnées de transaction Delta peuvent évoluer. Les révisions des sources, les écritures concurrentes et la reprise après panne demandent des tests distincts. Le calcul d'empreinte collecte au maximum 100 001 lignes par objet et refuse tout objet dépassant 100 000 lignes : cette vérification est adaptée au volume du portfolio, pas à une table de production massive.

## Preuves et reproduction

- Résumé lisible : `docs/idempotence-validation-2026-11-03.json`.
- Sortie Databricks originale : `outputs/idempotence/run-output.json`.
- Preuve archivée dans ADLS via Unity Catalog : `dbfs:/Volumes/radar_adls/radar_gold/artifacts/idempotence/<proof-id>.json`.
- Code : `notebooks/02_lakehouse.py` ; paramètres : `infra/idempotence-adls-run.json`.

Pour reproduire ultérieurement, importer le notebook actuel dans le workspace puis soumettre `infra/idempotence-adls-run.json` avec Azure CLI comme authentification Databricks. Cela déclenche une exécution payante : ne pas le faire pendant la démonstration orale. Le run utilise serverless Standard et un timeout de quinze minutes, démarrage compris. Le run vérifié a demandé 246 secondes de démarrage et 311 secondes d'exécution ; ces durées ne constituent pas une mesure de coût facturé.
