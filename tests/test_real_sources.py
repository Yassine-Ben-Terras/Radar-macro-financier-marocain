"""Integration checks against locally downloaded public data; skipped before --fetch."""
import json
from collections import defaultdict
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'data/prepared/indicators.jsonl'


@unittest.skipUnless(PATH.exists(), 'Run python -m radar.pipeline --fetch first')
class RealSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [json.loads(line) for line in PATH.read_text(encoding='utf-8').splitlines()]

    def test_bam_top_level_balance(self):
        periods = defaultdict(dict)
        for row in self.rows:
            if row['source_id'] == 'bam_credit':
                periods[row['period_start']][row['category_label']] = row['value']
        self.assertTrue(periods)
        for period, values in periods.items():
            with self.subTest(period=period):
                # Source rounding tolerance: 0.01 MDH = 10,000 MAD.
                self.assertAlmostEqual(values['Crédit bancaire'], values['Secteur public hors AC'] +
                    values['Secteur privé'] + values['Autres sociétés financières'], delta=0.01)

    def test_hcp_inspected_source_cell(self):
        row, = [r for r in self.rows if r['source_id'] == 'hcp_ipc'
                and r['geography'] == 'National' and r['category_code'] == 'GR'
                and r['period_start'] == '2025-01-01']
        self.assertEqual(row['cell'], 'C3')
        self.assertEqual(row['value'], 119.6)
        self.assertAlmostEqual(row['yoy_pct'], (119.6 / 118.7 - 1) * 100)

    def test_unique_observations_and_traceability(self):
        self.assertEqual(len(self.rows), len({r['observation_key'] for r in self.rows}))
        for row in self.rows:
            self.assertEqual(len(row['file_sha256']), 64)
            self.assertTrue(row['source_url'].startswith('https://data.gov.ma/'))
            self.assertTrue(row['sheet'] and row['cell'])
            self.assertIsNone(row['published_at'])
