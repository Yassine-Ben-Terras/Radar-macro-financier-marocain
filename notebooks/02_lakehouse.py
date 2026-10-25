# Databricks notebook source
# MAGIC %md
# MAGIC # Ingestion BAM / HCP vers Delta
# MAGIC Importer le dépôt comme Git folder. Installer openpyxl==3.1.5 dans l'environnement serverless.
# MAGIC Exécuter 01_init.sql dans le catalogue choisi, puis copier data/bronze dans le volume raw_files/bronze.
# MAGIC Aucun téléchargement ni endpoint externe n'est lancé par ce notebook.

# COMMAND ----------
import hashlib
import json
from pathlib import Path
import re
import sys

dbutils.widgets.text('catalog', '')
dbutils.widgets.text('repo_root', '')
dbutils.widgets.text('verify_idempotence', 'false')
verify_idempotence = dbutils.widgets.get('verify_idempotence').lower() == 'true'
catalog = dbutils.widgets.get('catalog')
repo_root = Path(dbutils.widgets.get('repo_root'))
if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', catalog) or catalog == 'hive_metastore':
    raise ValueError('Fournir un catalogue Unity Catalog existant, identifiant simple')
if not (repo_root / 'radar/pipeline.py').is_file():
    raise ValueError('repo_root doit pointer vers le dossier du dépôt importé')
sys.path.insert(0, str(repo_root))
from radar.settings import deployment
expected_storage = deployment()["storage_account"]
from radar.pipeline import VERSION, candidates, normalize
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

volume = Path(f'/Volumes/{catalog}/radar_bronze/raw_files')
config = json.loads((repo_root / 'config/ingestion.json').read_text())
spark.sql(f'USE CATALOG `{catalog}`')

# COMMAND ----------
# Schémas explicites : valeurs nulles et lots vides supportés.
base = 'source_id source_url file_sha256 retrieved_at published_at sheet cell cell_id transformation_version'
fields = {
    'manifests': 'manifest_id source_id source_url dataset_url license file_sha256 retrieved_at published_at resource_name relative_path',
    'raw_cells': base + ' raw_value dimensions_json',
    'observations': base + ' indicator_id frequency period_start source_period geography category_code category_label classification unit observation_key record_id value',
    'rejects': base + ' reject_id reason raw_payload',
}
targets = {'manifests': 'radar_bronze.manifests', 'raw_cells': 'radar_bronze.raw_cells',
           'observations': 'radar_silver.observations_v2', 'rejects': 'radar_silver.rejects'}
keys = {'manifests': 'manifest_id', 'raw_cells': 'cell_id',
        'observations': 'record_id', 'rejects': 'reject_id'}
batches = {name: [] for name in fields}

def table_fingerprint(table, key):
    source = spark.table(table)
    records = source.select(F.col(key).alias('key'),
        F.sha2(F.to_json(F.struct(*[F.col(c) for c in sorted(source.columns)])), 256).alias('row_hash')
    ).orderBy('key', 'row_hash').limit(100001).collect()
    if len(records) > 100000:
        raise ValueError('Verification limitee a 100 000 lignes par objet')
    digest = hashlib.sha256()
    for record in records:
        digest.update((record['row_hash'] + '\n').encode())
    return {'rows': len(records), 'distinct_keys': len({r['key'] for r in records}),
            'null_keys': sum(r['key'] is None for r in records), 'sha256': digest.hexdigest()}

verification_targets = {targets[name]: keys[name] for name in targets}
verification_targets['radar_gold.indicators'] = 'observation_key'
before = {table: table_fingerprint(table, key) for table, key in verification_targets.items()} if verify_idempotence else None
if verify_idempotence:
    assert before['radar_silver.observations_v2']['rows'] == 29151, 'Etat initial inattendu'
    assert before['radar_gold.indicators']['rows'] == 29151, 'Gold initial inattendu'

# Valider tous les fichiers avant de modifier Delta. Les archives brutes restent dans le volume.
for source in config['sources']:
    manifests = sorted((volume / 'bronze' / source['id']).glob('*/manifest.json'))
    if not manifests:
        raise ValueError(f"Archive absente : {source['id']}")
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        raw = (volume / manifest['relative_path']).resolve()
        if not raw.is_relative_to(volume.resolve()):
            raise ValueError('Chemin source hors volume')
        if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest['file_sha256']:
            raise ValueError('Empreinte source invalide')
        bronze, observations, rejects = normalize(manifest, candidates(raw, source['parser']))
        batches['manifests'].append(manifest)
        batches['raw_cells'].extend(bronze)
        batches['observations'].extend(observations)
        batches['rejects'].extend(rejects)

for name, rows in batches.items():
    schema = StructType([StructField(field, DoubleType() if field == 'value' else StringType(), True)
                         for field in fields[name].split()])
    frame = spark.createDataFrame(rows, schema)
    for field in ('period_start', 'published_at'):
        if field in frame.columns:
            frame = frame.withColumn(field, F.to_date(field))
    if 'retrieved_at' in frame.columns:
        frame = frame.withColumn('retrieved_at', F.to_timestamp('retrieved_at'))
    key = keys[name]
    if frame.filter(F.col(key).isNull()).limit(1).count():
        raise ValueError(f'Clé nulle : {name}')
    if frame.groupBy(key).count().filter('count > 1').limit(1).count():
        raise ValueError(f'Clés dupliquées : {name}')
    frame.createOrReplaceTempView(f'incoming_{name}')
    table = targets[name]
    spark.sql(f'CREATE TABLE IF NOT EXISTS {table} USING DELTA AS SELECT * FROM incoming_{name} WHERE 1=0')
    spark.sql(f'''MERGE INTO {table} t USING incoming_{name} s
                  ON t.{key} = s.{key} WHEN NOT MATCHED THEN INSERT *''')

# COMMAND ----------
# Gold : dernière archive collectée par source, sans réintroduire les cellules
# supprimées ou rejetées dans une nouvelle version du fichier.
spark.sql(f'''
CREATE OR REPLACE VIEW radar_gold.current_observations AS
WITH latest AS (
  SELECT *, row_number() OVER (
    PARTITION BY source_id ORDER BY retrieved_at DESC, file_sha256 DESC
  ) AS rn FROM radar_bronze.manifests
)
SELECT o.* FROM radar_silver.observations_v2 o
JOIN latest m ON o.source_id=m.source_id AND o.file_sha256=m.file_sha256 AND m.rn=1
WHERE o.transformation_version='{VERSION}'
''')
spark.sql('''
CREATE OR REPLACE VIEW radar_gold.indicators AS
SELECT c.*, p.record_id AS previous_record_id,
       CASE WHEN p.value IS NOT NULL AND p.value <> 0
            THEN 100 * (c.value / p.value - 1) END AS yoy_pct
FROM radar_gold.current_observations c
LEFT JOIN radar_gold.current_observations p
ON c.source_id=p.source_id AND c.indicator_id=p.indicator_id
AND c.frequency=p.frequency AND c.geography=p.geography
AND c.category_code=p.category_code AND c.classification=p.classification AND c.unit=p.unit
AND p.period_start=add_months(c.period_start, -12)
''')

# COMMAND ----------
# Vérifications après chargement. Relancer et comparer les effectifs pour l'idempotence.
display(spark.sql('''SELECT source_id, count(*) AS observations,
                    min(period_start) AS first_period, max(period_start) AS last_period
                    FROM radar_gold.indicators GROUP BY source_id'''))
display(spark.sql('SELECT source_id, reason, count(*) AS rejected FROM radar_silver.rejects GROUP BY source_id, reason'))
assert not spark.sql('''SELECT observation_key FROM radar_gold.current_observations
                       GROUP BY observation_key HAVING count(*) > 1''').take(1)

summary = [r.asDict() for r in spark.sql('''
    SELECT source_id, count(*) AS observations,
           min(period_start) AS first_period, max(period_start) AS last_period
    FROM radar_gold.indicators GROUP BY source_id
''').collect()]
locations = {}
for table in targets.values():
    location = spark.sql(f'DESCRIBE DETAIL {table}').select('location').first()['location']
    locations[table] = location
    if catalog == 'radar_adls' and not location.startswith(
        f'abfss://lakehouse@{expected_storage}.dfs.core.windows.net/'):
        raise ValueError(f'Table hors du compte ADLS attendu : {table}')
result = {'sources': summary, 'table_locations': locations,
          'rejected': spark.table('radar_silver.rejects').count()}
if verify_idempotence:
    import uuid
    from datetime import datetime, timezone
    after = {table: table_fingerprint(table, key) for table, key in verification_targets.items()}
    checks = {table: before[table] == after[table] and after[table]['null_keys'] == 0
              and after[table]['rows'] == after[table]['distinct_keys'] for table in verification_targets}
    checks['expected_sources'] = {r['source_id']: r['observations'] for r in summary} == {'bam_credit':4455, 'hcp_ipc':24696}
    proof = {'checked_at': datetime.now(timezone.utc).isoformat(), 'before': before,
             'after': after, 'checks': checks, 'passed': all(checks.values()),
             'scope': 'Same two source archives, one real ingestion rerun; logical content excludes Delta transaction metadata'}
    destination = Path(f'/Volumes/{catalog}/radar_gold/artifacts/idempotence/{uuid.uuid4().hex}.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(proof, indent=2), encoding='utf-8')
    result['idempotence'] = proof
    result['proof_uri'] = 'dbfs:' + str(destination)
    assert proof['passed'], 'Idempotence non confirmee : consulter la preuve avant/apres'
dbutils.notebook.exit(json.dumps(result, default=str))
