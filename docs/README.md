# Documentation

## Parcours conseillé

1. [Architecture](architecture.md) : stockage, traitement et gouvernance.
2. [Déploiement](deployment.md) : prérequis Azure et commandes dans l'ordre.
3. [Ingestion](partie-2.md), [analyse](partie-3.md) et [assistant](partie-4.md) : fonctionnement et limites.
4. [Idempotence](idempotence.md) et [actualisation](actualisation-incrementale.md) : exploitation et reprise.
5. [Présentation orale](presentation-5-minutes.md) : scénario de démonstration.
6. [Publication GitHub](github.md) : premier commit et premier push.

## Preuves de validation

Les preuves ci-dessous décrivent les exécutions de novembre 2026. Les adresses du workspace, de l'abonnement et du stockage sont anonymisées dans les copies publiques ; les originaux restent hors Git. Elles ne prouvent pas qu'un nouveau déploiement fonctionne.

- [Stockage et ingestion](adls-validation-2026-11-03.json)
- [Idempotence](idempotence-validation-2026-11-03.json)
- [Analyse et MLflow](analytics-validation-2026-11-03.json)
- [Assistant documentaire](assistant-validation-2026-11-03.json)
- [Contrôleur d'actualisation](refresh-validation-2026-11-04.json)

`private/` conserve les journaux de mise en service et les preuves originales. Ce répertoire est ignoré par Git et n'appartient pas à la documentation publique.
