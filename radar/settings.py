"""Deployment parameters are local; no account credentials belong in Git."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def deployment():
    path = ROOT / 'config/deployment.local.json'
    if not path.exists():
        raise ValueError('Copy config/deployment.example.json to deployment.local.json and configure Azure first')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', config.get('subscription_id', '')):
        raise ValueError('Invalid subscription_id in deployment.local.json')
    if not re.fullmatch(r'https://adb-[0-9.]+\.azuredatabricks\.net', config.get('workspace_host', '')):
        raise ValueError('Invalid workspace_host in deployment.local.json')
    if not re.fullmatch(r'[a-z0-9]{3,24}', config.get('storage_account', '')):
        raise ValueError('Invalid storage_account in deployment.local.json')
    return config
