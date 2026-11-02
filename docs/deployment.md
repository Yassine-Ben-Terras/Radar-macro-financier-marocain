# Déployer le portfolio sur Azure

## Préparer la configuration

Prérequis : Python 3.12, PowerShell, Azure CLI, Databricks CLI, connexion Entra ID, abonnement et région compatibles avec les ressources demandées. Vérifier les droits de création de ressources, d'attribution RBAC et de gestion Unity Catalog. Un groupe de ressources et l'enregistrement des fournisseurs sont nécessaires avant les déploiements groupés.

Copier `config/deployment.example.json` vers `config/deployment.local.json`. Remplir l'abonnement, le groupe, le workspace, son URL, le compte de stockage et l'Access Connector. Ce fichier ne contient pas de secret mais reste hors Git. Les scripts ne changent pas l'offre ni la limite de dépenses de l'abonnement.

Les scripts transmettent aux templates ARM le nom du workspace, le nom du stockage et le nom de l'Access Connector depuis la configuration locale. La région par défaut est France Central. L'URL du workspace doit être reportée depuis le déploiement ; les scripts de convenance supposent une configuration locale complète. Pour un premier provisionnement sans URL connue, utiliser directement les templates ARM puis compléter la configuration avant les scripts de connexion.

## Ordre des opérations

1. Authentifier Azure CLI avec `az login` et vérifier l'abonnement cible.
2. Examiner les templates ARM et valider avec `scripts/provision-azure.ps1 -Action Validate` et `scripts/provision-adls.ps1 -Action Validate`.
3. Examiner `-Action WhatIf`, puis utiliser `-Action Deploy` seulement pour les ressources souhaitées. Ces étapes sont payantes selon l'offre et l'utilisation.
4. Exécuter `scripts/connect-adls.ps1`. Le script génère les requêtes locales de credential et d'external locations depuis la configuration ; il vérifie l'identité et les emplacements existants.
5. Acquérir les sources localement : `python -m radar.pipeline --fetch` puis `scripts/download-pdfs.ps1`.
6. Exécuter `scripts/import-workspace.ps1` puis `scripts/upload-adls-sources.ps1`. L'import inclut `deployment.local.json` dans le workspace pour que les notebooks vérifient la destination ADLS. Les fichiers source sont vérifiés par SHA-256 après transfert.
7. Soumettre l'ingestion avec `scripts/run-ingestion.ps1 -RunToken <jeton-unique>`. Conserver le jeton et le run ID pour les reprises réseau. Le script cible `infra/ingestion-adls-run.json`.
8. Vérifier SUCCESS, les rejets et les emplacements avant de soumettre l'analyse et l'assistant à partir de leurs configurations `infra/*-adls-run.json`.

Les scripts d'import n'écrasent pas silencieusement un workspace existant. Une nouvelle version des fichiers doit faire l'objet d'un import contrôlé ; cette livraison prépare le dépôt local, elle ne redéploie pas Azure.

## Nouveau clone et historique

Le catalogue et les chemins logiques restent `radar_adls` et `/Shared/radar-macro`. Le contrôleur utilise les configurations de runs existantes. Adapter l'ensemble si ces noms changent.

`config/refresh-baseline.json` est une référence historique utilisée par les tests. Elle n'est pas appliquée automatiquement à un nouvel environnement. Seul `config/refresh-baseline.local.json`, s'il existe, initialise un état déjà traité. Ne le créer qu'après avoir vérifié que son contenu correspond réellement au workspace cible. Conserver `data/refresh/state.json` après chaque traitement.

## Coûts et limites

Les runs sont ponctuels et bornés, sans horaire récurrent. Aucune mesure de coût facturé n'est encore validée. La cible historique de 35 USD plus 15 USD de réserve ne constitue pas un plafond technique. L'accès ADLS est public et authentifié, LRS n'offre pas de protection contre une panne de région et le contrôleur local n'est pas un service hautement disponible.
