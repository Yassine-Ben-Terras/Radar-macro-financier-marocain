"""Run: python -m radar.pipeline --fetch (or omit --fetch to reuse snapshots)."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen

import openpyxl
from openpyxl.utils import get_column_letter

VERSION = '2.0.0'
ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(dumps(value), encoding='utf-8')
    tmp.replace(path)


def download(url):
    if not url.startswith('https://data.gov.ma/'):
        raise ValueError('Only the configured official portal is allowed')
    with urlopen(Request(url, headers={'User-Agent': 'RadarMacroPortfolio/0.1'}), timeout=60) as response:
        payload = response.read(20_000_001)
    if len(payload) > 20_000_000:
        raise ValueError('Source exceeds 20 MB MVP limit')
    return payload


def fetch(source, data_dir):
    package = json.loads(download(source['catalog_api']))['result']
    resource = next(r for r in package['resources'] if r['id'] == source['resource_id'])
    if package['license_id'] != 'odc-odbl':
        raise ValueError('Source licence changed; review before ingestion')
    payload = download(resource['url'])
    if not payload.startswith(b'PK'):
        raise ValueError('Expected XLSX ZIP signature, not an HTML response')
    sha = hashlib.sha256(payload).hexdigest()
    folder = data_dir / 'bronze' / source['id'] / sha
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / 'source.xlsx'
    if not raw.exists():
        raw.write_bytes(payload)
    manifest_path = folder / 'manifest.json'
    if not manifest_path.exists():
        write_json(folder / 'catalog.json', package)
        write_json(manifest_path, {
            'manifest_id': digest(source['id'] + sha),
            'source_id': source['id'], 'source_url': resource['url'],
            'dataset_url': source['dataset_url'], 'license': package['license_id'],
            'file_sha256': sha, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'published_at': None, 'resource_name': resource['name'],
            'relative_path': str(raw.relative_to(data_dir)).replace('\\', '/'),
        })
    return manifest_path


def numeric(raw):
    if raw is None or (isinstance(raw, str) and raw.strip() in ('', '-', '..', '...', 'ND', 'N.D.')):
        raise ValueError('missing_value')
    if isinstance(raw, bool):
        raise ValueError('invalid_number')
    try:
        value = float(str(raw).replace('\u00a0', '').replace('\u202f', '').replace(' ', '').replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError('invalid_number') from None
    if not math.isfinite(value):
        raise ValueError('non_finite_value')
    if value < 0:
        raise ValueError('negative_index_or_credit')
    return value


def candidates(path, parser):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book.active
        rows = list(sheet.values)
        if parser == 'hcp_ipc':
            if rows[1][:2] != ('Villes', 'Divisions et groupes de produits'):
                raise ValueError('HCP header changed')
            years = [int(y) for y in rows[1][2:]]
            if len(years) != len(set(years)) or any(y < 2017 or y > 2100 for y in years):
                raise ValueError('Invalid HCP periods')
            for row_num, row in enumerate(rows[2:], 3):
                if not any(v is not None for v in row):
                    continue
                label = str(row[1] or '').strip()
                match = re.match(r'^\(([^)]+)\)', label)
                for col, year in enumerate(years, 3):
                    yield sheet.title, f'{get_column_letter(col)}{row_num}', row[col-1], {
                        'indicator_id': 'cpi', 'frequency': 'annual',
                        'period_start': f'{year}-01-01', 'source_period': str(year),
                        'geography': str(row[0] or '').strip(),
                        'category_code': match.group(1) if match else '',
                        'category_label': label, 'classification': 'HCP_IPC_2017',
                        'unit': 'index_2017_100',
                    }
        elif parser == 'bam_credit':
            if rows[1][0] != 'Encours en MDH':
                raise ValueError('BAM unit/header changed')
            periods = rows[2][1:]
            if not periods or any(not isinstance(p, datetime) for p in periods):
                raise ValueError('BAM periods must be Excel dates')
            normalized = [p.strftime('%Y-%m-01') for p in periods]
            if len(normalized) != len(set(normalized)):
                raise ValueError('Duplicate BAM month')
            for row_num, row in enumerate(rows[3:], 4):
                # Blank lines and textual footnotes are preserved in the raw workbook.
                if not any(v is not None for v in row[1:]):
                    continue
                label = str(row[0] or '').strip()
                for col, period in enumerate(periods, 2):
                    yield sheet.title, f'{get_column_letter(col)}{row_num}', row[col-1], {
                        'indicator_id': 'bank_credit_outstanding', 'frequency': 'monthly',
                        'period_start': period.strftime('%Y-%m-01'),
                        'source_period': period.date().isoformat(),
                        'geography': 'National', 'category_code': label,
                        'category_label': label, 'classification': 'BAM_institutional_sector',
                        'unit': 'million_MAD',
                    }
        else:
            raise ValueError(f'Unknown parser: {parser}')
    finally:
        book.close()


KEY_FIELDS = ('source_id', 'indicator_id', 'frequency', 'period_start', 'geography',
              'category_code', 'classification', 'unit')


def normalize(manifest, cells):
    bronze, observations, rejects = [], [], []
    staged = []
    for sheet, cell, raw, dimensions in cells:
        cell_id = digest('|'.join([manifest['source_id'], manifest['file_sha256'], sheet, cell]))
        base = {k: manifest[k] for k in ('source_id', 'source_url', 'file_sha256', 'retrieved_at', 'published_at')}
        base.update(sheet=sheet, cell=cell, cell_id=cell_id, transformation_version=VERSION)
        bronze.append({**base, 'raw_value': str(raw) if raw is not None else None,
                       'dimensions_json': dumps(dimensions)})
        observation = {**base, **dimensions}
        observation['observation_key'] = digest(dumps({k: observation[k] for k in KEY_FIELDS}))
        observation['record_id'] = digest(observation['observation_key'] + manifest['file_sha256'] + VERSION)
        try:
            if not dimensions['geography'] or not dimensions['category_code']:
                raise ValueError('missing_dimension')
            date.fromisoformat(dimensions['period_start'])
            observation['value'] = numeric(raw)
            staged.append(observation)
        except ValueError as error:
            rejects.append({**base, 'reject_id': digest(cell_id + VERSION),
                            'reason': str(error), 'raw_payload': dumps(dimensions | {'value': raw})})
    counts = Counter(r['observation_key'] for r in staged)
    for row in staged:
        if counts[row['observation_key']] > 1:
            rejects.append({**{k: row[k] for k in base}, 'reject_id': digest(row['cell_id'] + VERSION),
                            'reason': 'duplicate_business_key', 'raw_payload': dumps(row)})
        else:
            observations.append(row)
    return bronze, observations, rejects


def gold_current(rows):
    current = {}
    for row in rows:
        key = row['observation_key']
        # Latest collected snapshot, NOT a point-in-time/publication-date backtest.
        order = (row['retrieved_at'], row['file_sha256'])
        if key not in current or order > (current[key]['retrieved_at'], current[key]['file_sha256']):
            current[key] = row
    lookup = {tuple(r[k] for k in KEY_FIELDS): r for r in current.values()}
    result = []
    for row in current.values():
        previous_period = f"{int(row['period_start'][:4])-1}{row['period_start'][4:]}"
        previous_key = tuple(previous_period if k == 'period_start' else row[k] for k in KEY_FIELDS)
        previous = lookup.get(previous_key)
        yoy = (100 * (row['value'] / previous['value'] - 1)
               if previous and previous['value'] != 0 else None)
        result.append({**row, 'yoy_pct': yoy,
                       'previous_record_id': previous['record_id'] if previous else None})
    return sorted(result, key=lambda r: r['observation_key'])


def run(data_dir, do_fetch=False):
    config = json.loads((ROOT / 'config/ingestion.json').read_text(encoding='utf-8'))
    data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(data_dir / 'radar.sqlite')
    tables = ('manifests', 'raw_cells', 'observations', 'rejects')
    for table in tables:
        connection.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    stats = {}
    try:
        with connection:
            for source in config['sources']:
                if do_fetch:
                    fetch(source, data_dir)
                paths = sorted((data_dir / 'bronze' / source['id']).glob('*/manifest.json'))
                if not paths:
                    raise FileNotFoundError(f"No snapshot for {source['id']}; run --fetch")
                for manifest_path in paths:
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                    path = data_dir / manifest['relative_path']
                    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['file_sha256']:
                        raise ValueError('Raw file hash mismatch')
                    bronze, observations, rejects = normalize(manifest, candidates(path, source['parser']))
                    for table, rows, key in (
                        ('manifests', [manifest], 'manifest_id'), ('raw_cells', bronze, 'cell_id'),
                        ('observations', observations, 'record_id'), ('rejects', rejects, 'reject_id')):
                        connection.executemany(f'INSERT OR IGNORE INTO {table} VALUES (?, ?)',
                                               [(r[key], dumps(r)) for r in rows])
        export = data_dir / 'prepared'
        export.mkdir(exist_ok=True)
        for table in tables:
            rows = [json.loads(r[0]) for r in connection.execute(f'SELECT payload FROM {table} ORDER BY id')]
            with (export / f'{table}.jsonl').open('w', encoding='utf-8', newline='\n') as out:
                out.writelines(dumps(r) + '\n' for r in rows)
            stats[table] = len(rows)
        observations = [json.loads(r[0]) for r in connection.execute('SELECT payload FROM observations')]
        latest = {}
        for payload, in connection.execute('SELECT payload FROM manifests'):
            manifest = json.loads(payload)
            source = manifest['source_id']
            if source not in latest or (manifest['retrieved_at'], manifest['file_sha256']) > (latest[source]['retrieved_at'], latest[source]['file_sha256']):
                latest[source] = manifest
        active = [r for r in observations if r['transformation_version'] == VERSION
                  and r['file_sha256'] == latest[r['source_id']]['file_sha256']]
        gold = gold_current(active)
        with (export / 'indicators.jsonl').open('w', encoding='utf-8', newline='\n') as out:
            out.writelines(dumps(r) + '\n' for r in gold)
        stats['gold_indicators'] = len(gold)
        stats['by_source'] = dict(Counter(r['source_id'] for r in gold))
        stats['coverage'] = {s: {'first': min(r['period_start'] for r in gold if r['source_id'] == s),
                                 'last': max(r['period_start'] for r in gold if r['source_id'] == s)}
                             for s in stats['by_source']}
        stats['rejection_reasons'] = dict(Counter(json.loads(r[0])['reason'] for r in connection.execute('SELECT payload FROM rejects')))
        write_json(data_dir / 'quality_report.json', stats)
        return stats
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    print(dumps(run(args.data_dir, args.fetch)))
