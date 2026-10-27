# Databricks notebook source
# MAGIC %md
# MAGIC # Analyse et évaluation temporelle
# MAGIC Prérequis : notebook 02 terminé, environnement avec Plotly 6.3.0 et MLflow.
# MAGIC Exécution manuelle uniquement. Ne crée aucun endpoint de serving.

# COMMAND ----------
from pathlib import Path
import re
import sys
import tempfile
import json
import hashlib
import mlflow

dbutils.widgets.text('catalog','')
dbutils.widgets.text('repo_root','')
dbutils.widgets.text('experiment_path','')
catalog = dbutils.widgets.get('catalog')
repo_root = Path(dbutils.widgets.get('repo_root'))
experiment = dbutils.widgets.get('experiment_path')
if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',catalog) or catalog=='hive_metastore':
    raise ValueError('Catalogue Unity Catalog requis')
if not (repo_root/'radar/analytics.py').is_file() or not experiment.startswith('/'):
    raise ValueError('Fournir repo_root et un chemin absolu d’expérience MLflow')
sys.path.insert(0,str(repo_root))
from radar.analytics import summarize, report

# COMMAND ----------
# Petit volume de données nationales : collect explicite et borné, adapté à ce MVP.
frame=spark.sql(f"SELECT * FROM `{catalog}`.radar_gold.indicators WHERE geography='National'")
records=frame.limit(10001).collect()
if len(records)>10000:
    raise ValueError('Périmètre trop grand pour cette analyse locale au driver')
rows=[r.asDict() for r in records]
for row in rows:
    for key in ('period_start','retrieved_at','published_at'):
        if row[key] is not None:
            row[key]=row[key].isoformat()
summary=summarize(rows)
summary['input_sha256']=hashlib.sha256(json.dumps(sorted(rows,key=lambda r:r['observation_key']),sort_keys=True).encode()).hexdigest()
output=Path(tempfile.mkdtemp(prefix='radar-analysis-'))
report(summary,output)

# COMMAND ----------
spark.sql(f'CREATE VOLUME IF NOT EXISTS `{catalog}`.radar_gold.artifacts')
artifact_root = f'dbfs:/Volumes/{catalog}/radar_gold/artifacts/mlflow'
existing = mlflow.get_experiment_by_name(experiment)
if existing is None:
    mlflow.create_experiment(experiment, artifact_location=artifact_root)
elif existing.artifact_location.rstrip('/') != artifact_root:
    raise ValueError('L’experience existante utilise un autre stockage ; choisir un nouveau chemin')
mlflow.set_experiment(experiment)
with mlflow.start_run(run_name='radar-baselines-1-month') as tracked_run:
    mlflow.log_params({'evaluation_points':24,'forecast_horizon_months':1,
                      'initial_training_end':summary['evaluation']['training_end_initial'],
                      'test_start':summary['evaluation']['test_start'],
                      'test_end':summary['evaluation']['test_end'],
                      'input_sha256':summary['input_sha256']})
    mlflow.set_tags({'data_vintage':'latest_revised_snapshot','project':'radar-macro',
                     'publication_dates':'unknown','production_model_selected':'false'})
    for metric in summary['evaluation']['metrics']:
        for key in ('mae_mdh','rmse_mdh','mase'):
            if metric[key] is not None:
                mlflow.log_metric(f"{metric['method']}_{key}",metric[key])
    mlflow.log_artifacts(str(output))
displayHTML((output/'radar.html').read_text(encoding='utf-8'))
dbutils.notebook.exit(json.dumps({
    'mlflow_run_id': tracked_run.info.run_id,
    'experiment_id': tracked_run.info.experiment_id,
    'artifact_uri': tracked_run.info.artifact_uri,
    'national_rows': len(rows),
    'metrics': summary['evaluation']['metrics'],
    'test_start': summary['evaluation']['test_start'],
    'test_end': summary['evaluation']['test_end'],
    'credit_latest': summary['credit_latest'],
    'cpi_latest': summary['cpi_latest'],
    'input_sha256': summary['input_sha256']
}, default=str))
