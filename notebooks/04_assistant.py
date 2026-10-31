# Databricks notebook source
# MAGIC %md
# MAGIC # Assistant local au driver : documents et SQL encadré
# MAGIC Installer pypdf==6.10.0 dans l'environnement. Copier les deux PDF dans
# MAGIC /Volumes/<catalog>/radar_bronze/raw_files/documents/.
# MAGIC Aucun LLM ni service vectoriel. Les questions sont traitées par le driver du job.

# COMMAND ----------
from pathlib import Path
import json
import re
import sys
import tempfile
import shutil
import uuid
from contextlib import closing

dbutils.widgets.text('catalog','')
dbutils.widgets.text('repo_root','')
dbutils.widgets.text('question','Recherche documentaire : politique monétaire')
catalog=dbutils.widgets.get('catalog')
repo=Path(dbutils.widgets.get('repo_root'))
if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',catalog) or catalog=='hive_metastore':
    raise ValueError('Catalogue Unity Catalog requis')
if not (repo/'radar/assistant.py').is_file():
    raise ValueError('repo_root invalide')
sys.path.insert(0,str(repo))
from radar.settings import deployment
expected_storage = deployment()["storage_account"]
from radar.assistant import build_index, ask, connect_readonly
from radar.evaluate_assistant import evaluate

# COMMAND ----------
# Snapshot national borné ; SQLite est placé sur disque temporaire du driver,
# jamais directement dans un volume partagé.
work=Path(tempfile.mkdtemp(prefix='radar-assistant-'))
rows=spark.sql(f"SELECT * FROM `{catalog}`.radar_gold.indicators WHERE geography='National'").limit(10001).collect()
if len(rows)>10000:
    raise ValueError('Plus de 10 000 observations : revoir le dimensionnement')
gold=work/'gold.jsonl'
with gold.open('w',encoding='utf-8') as out:
    for row in rows:
        out.write(json.dumps(row.asDict(),default=str,ensure_ascii=False)+'\n')
index=work/'assistant.sqlite'
quality=build_index(Path(f'/Volumes/{catalog}/radar_bronze/raw_files/documents'),gold,index,repo/'config/sources.json')
print({k:v for k,v in quality.items() if k!='page_quality'})

# COMMAND ----------
# Archivage Delta des passages extraits pour gouvernance et audit.
with closing(connect_readonly(index)) as conn:
    chunk_rows=[tuple(row) for row in conn.execute('''SELECT c.chunk_id,c.doc_id,c.pdf_page,
      c.printed_page,c.word_start,c.text,d.source_url,d.file_sha256 FROM chunks c
      JOIN documents d ON d.doc_id=c.doc_id''')]
frame=spark.createDataFrame(chunk_rows,'chunk_id string, doc_id string, pdf_page int, printed_page string, word_start int, text string, source_url string, file_sha256 string')
frame.createOrReplaceTempView('incoming_document_chunks')
table=f'`{catalog}`.radar_bronze.document_chunks'
spark.sql(f'CREATE TABLE IF NOT EXISTS {table} USING DELTA AS SELECT * FROM incoming_document_chunks WHERE 1=0')
spark.sql(f'MERGE INTO {table} t USING incoming_document_chunks s ON t.chunk_id=s.chunk_id WHEN NOT MATCHED THEN INSERT *')

# COMMAND ----------
# Recherche sur le snapshot courant. Les passages archivés d'anciennes versions
# dans Delta ne sont pas mélangés à l'index courant.
answer = ask(index,dbutils.widgets.get('question'))
print(json.dumps(answer,ensure_ascii=False,indent=2))
evaluation_dir = work/'evaluation'
evaluation = evaluate(index, repo/'config/assistant-evaluation.json', evaluation_dir)
spark.sql(f'CREATE VOLUME IF NOT EXISTS `{catalog}`.radar_gold.artifacts')
artifact_dir = Path(f'/Volumes/{catalog}/radar_gold/artifacts/assistant/{uuid.uuid4().hex}')
artifact_dir.mkdir(parents=True)
for artifact in evaluation_dir.iterdir():
    shutil.copyfile(artifact, artifact_dir/artifact.name)
# Closed immutable snapshot; never open SQLite in place on shared storage.
shutil.copyfile(index, artifact_dir/'assistant.sqlite')
(artifact_dir/'quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
(artifact_dir/'answer.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding='utf-8')
location = spark.sql(f'DESCRIBE DETAIL {table}').select('location').first()['location']
if catalog == 'radar_adls' and not location.startswith(f'abfss://lakehouse@{expected_storage}.dfs.core.windows.net/'):
    raise ValueError('Passages PDF hors du compte ADLS attendu')
dbutils.notebook.exit(json.dumps({
    'artifact_uri': 'dbfs:' + str(artifact_dir),
    'quality': {k:v for k,v in quality.items() if k!='page_quality'},
    'evaluation_passed': evaluation['passed'], 'evaluation_total': evaluation['total'],
    'document_table_location': location, 'response': answer
},ensure_ascii=False))
