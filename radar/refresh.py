"""Detect source changes without compute; --apply uploads and submits a bounded DAG.

State is local and must be retained. One controller host only; no distributed lock.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

from radar.pipeline import ROOT, fetch, candidates, normalize, write_json

from radar.settings import deployment
REMOTE = 'dbfs:/Volumes/radar_adls/radar_bronze/raw_files'
TERMINAL = {'TERMINATED', 'SKIPPED', 'INTERNAL_ERROR'}


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink()


def initial_state():
    # Explicit baseline backed by the successful ingestion and idempotence proofs.
    path = ROOT / 'config/refresh-baseline.local.json'
    baseline = json.loads(path.read_text()) if path.exists() else {'processed': {}, 'run_id': None}
    return {'version': 1, 'processed': baseline['processed'], 'active': None,
            'history': [], 'baseline_run_id': baseline['run_id']}


def discover(sources, data_dir):
    snapshots = {}
    for source in sources:
        path = fetch(source, data_dir)
        manifest = json.loads(path.read_text(encoding='utf-8'))
        raw = data_dir / manifest['relative_path']
        if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest['file_sha256']:
            raise ValueError('Corrupt archived source: ' + source['id'])
        _, good, rejected = normalize(manifest, candidates(raw, source['parser']))
        if not good or rejected:
            raise ValueError(f"Quality gate failed for {source['id']}: {len(rejected)} rejects")
        snapshots[source['id']] = {'sha256': manifest['file_sha256'],
                                   'manifest': str(path.resolve()), 'observations': len(good)}
    return snapshots


def run_config():
    result = {'run_name': 'radar-incremental-refresh', 'timeout_seconds': 1800,
              'performance_target': 'STANDARD', 'tasks': [], 'environments': []}
    previous = None
    for name in ('ingestion', 'analytics', 'assistant'):
        config = json.loads((ROOT / f'infra/{name}-adls-run.json').read_text())
        task = config['tasks'][0]
        if previous:
            task['depends_on'] = [{'task_key': previous}]
        task['max_retries'] = 0
        result['tasks'].append(task)
        result['environments'].extend(config['environments'])
        previous = task['task_key']
    return result


class Azure:
    def __init__(self):
        settings = deployment()
        subscription = settings['subscription_id']
        self.env = dict(os.environ, DATABRICKS_HOST=settings['workspace_host'], DATABRICKS_AUTH_TYPE='azure-cli')
        self.env.pop('DATABRICKS_TOKEN', None)
        self.env.pop('DATABRICKS_CONFIG_PROFILE', None)
        self.env['DATABRICKS_AZURE_RESOURCE_ID'] = (
            f"/subscriptions/{subscription}/resourceGroups/{settings['resource_group']}"
            f"/providers/Microsoft.Databricks/workspaces/{settings['workspace_name']}")
        self.env['ARM_TENANT_ID'] = self.command(
            ['az', 'account', 'show', '--subscription', subscription, '--query', 'tenantId', '-o', 'tsv']).strip()

    def command(self, args):
        # No shell interpolation, credentials never printed.
        import shutil
        args = [shutil.which(args[0]) or args[0], *args[1:]]
        return subprocess.run(args, env=self.env, check=True, capture_output=True,
                              text=True, encoding='utf-8', timeout=180).stdout

    def upload(self, snapshots):
        with tempfile.TemporaryDirectory() as folder:
            for source_id, snapshot in snapshots.items():
                local = Path(snapshot['manifest']).parent
                dest = f"{REMOTE}/bronze/{source_id}/{snapshot['sha256']}"
                # Manifest published last; a partially uploaded archive is not discoverable.
                for name in ('source.xlsx', 'catalog.json', 'manifest.json'):
                    target = f'{dest}/{name}'
                    self.command(['databricks', 'fs', 'cp', str(local/name), target, '--overwrite'])
                    check = Path(folder)/name
                    self.command(['databricks', 'fs', 'cp', target, str(check), '--overwrite'])
                    if hashlib.sha256(check.read_bytes()).digest() != hashlib.sha256((local/name).read_bytes()).digest():
                        raise ValueError('Upload verification failed: ' + target)

    def submit(self, token, config):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'run.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            return json.loads(self.command(['databricks', 'jobs', 'submit', '--json', '@'+str(path),
                '--idempotency-token', token, '--no-wait', '-o', 'json']))['run_id']

    def status(self, run_id):
        return json.loads(self.command(['databricks', 'jobs', 'get-run', str(run_id), '-o', 'json']))

    def output(self, run_id):
        response = json.loads(self.command(['databricks', 'jobs', 'get-run-output', str(run_id), '-o', 'json']))
        return json.loads(response['notebook_output']['result'])


def advance(state, save, cloud, retry=False):
    active = state['active']
    if active['status'] == 'failed':
        if not retry:
            return 'failed_requires_retry'
        state['history'].append(dict(active))
        active.update(status='detected', token=uuid.uuid4().hex, run_id=None)
        save()
    if active.get('run_id') is not None:
        run = cloud.status(active['run_id'])
        phase = run['state']['life_cycle_state']
        active['last_checked_at'] = now()
        if phase not in TERMINAL:
            save()
            return 'running'
        active['result'] = run['state'].get('result_state', phase)
        if active['result'] != 'SUCCESS':
            active['status'] = 'failed'
            save()
            return 'failed_requires_retry'
        active['outputs'] = {task['task_key']:cloud.output(task['run_id'])
                             for task in run.get('tasks', [])}
        state['processed'].update({k:v['sha256'] for k,v in active['snapshots'].items()})
        active.update(status='processed', completed_at=now())
        state['history'].append(dict(active))
        state['active'] = None
        save()
        return 'processed'
    if active['status'] == 'detected':
        cloud.upload(active['snapshots'])
        active['status'] = 'archived'
        save()
    # Persist token BEFORE submission: a lost HTTP response reuses the same token.
    active['status'] = 'submitting'
    save()
    active['run_id'] = cloud.submit(active['token'], active['config'])
    active['status'] = 'running'
    save()
    return 'submitted'


def tick(state, save, sources, data_dir, apply=False, retry=False, cloud_factory=Azure):
    if state['active']:
        return advance(state, save, cloud_factory(), retry) if apply else 'pending'
    snapshots = discover(sources, data_dir)
    state['last_checked_at'] = now()
    changes = {k:v for k,v in snapshots.items() if state['processed'].get(k) != v['sha256']}
    if not changes:
        save()
        return 'unchanged'
    # Reversion to an older archive needs explicit review: Gold orders collection dates.
    for key, value in changes.items():
        latest = max((json.loads(p.read_text()) for p in (data_dir/'bronze'/key).glob('*/manifest.json')),
                     key=lambda m:(m['retrieved_at'],m['file_sha256']))
        if latest['file_sha256'] != value['sha256']:
            raise ValueError('Source reverted to an older archive; manual review required: '+key)
    state['active'] = {'status':'detected', 'token':uuid.uuid4().hex, 'created_at':now(),
                       'snapshots':changes, 'config':run_config(), 'run_id':None}
    save()
    return advance(state, save, cloud_factory(), retry) if apply else 'detected'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Allow upload and paid cloud runs')
    parser.add_argument('--retry', action='store_true', help='Explicitly retry a failed cloud run')
    args = parser.parse_args()
    directory = ROOT/'data/refresh'
    path = directory/'state.json'
    with lock(directory/'controller.lock'):
        state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else initial_state()
        def save(): write_json(path, state)
        try:
            sources = json.loads((ROOT/'config/ingestion.json').read_text())['sources']
            result = tick(state, save, sources, ROOT/'data', args.apply, args.retry)
            state.pop('last_error', None)
            save()
            print(json.dumps({'status':result, 'active':state['active'], 'checked_at':state.get('last_checked_at')}, ensure_ascii=False))
            if result == 'failed_requires_retry':
                raise SystemExit(2)
        except Exception as error:
            state['last_error'] = {'at':now(), 'type':type(error).__name__, 'message':str(error)}
            save()
            raise


if __name__ == '__main__':
    main()
