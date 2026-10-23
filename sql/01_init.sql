-- Exécuter dans un catalogue Unity Catalog EXISTANT choisi dans l'interface.
-- Vérifier current_catalog() avant de continuer. Ne pas utiliser hive_metastore.
SELECT current_catalog();

CREATE SCHEMA IF NOT EXISTS radar_bronze COMMENT 'Sources et audit ingestion';
CREATE SCHEMA IF NOT EXISTS radar_silver COMMENT 'Observations normalisees et rejets';
CREATE SCHEMA IF NOT EXISTS radar_gold COMMENT 'Indicateurs explicables';
CREATE VOLUME IF NOT EXISTS radar_bronze.raw_files
COMMENT 'Fichiers sources conserves avec leur empreinte et provenance';

-- Les tables à schéma explicite sont créées par notebooks/02_lakehouse.py.
-- La table observations_v2 distingue catégorie de consommation et secteur
-- institutionnel, et conserve la géographie. Aucune table existante n'est supprimée.
