import copy
import unittest

from radar.pipeline import gold_current, normalize, numeric


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(source_id='test', source_url='https://example.test', file_sha256='abc',
                             retrieved_at='2026-11-02T00:00:00+00:00', published_at=None)
        self.dim = dict(indicator_id='cpi', frequency='annual', period_start='2024-01-01',
                        source_period='2024', geography='National', category_code='GR',
                        category_label='General', classification='IPC', unit='index')

    def test_french_number_and_zero(self):
        self.assertEqual(numeric('1\u202f234,50'), 1234.5)
        self.assertEqual(numeric(0), 0)

    def test_invalid_values_are_not_zero(self):
        for raw in (None, '', 'ND', 'text', float('nan'), float('inf'), -1, True):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                numeric(raw)

    def test_invalid_row_is_quarantined_with_cell(self):
        bronze, good, rejected = normalize(self.manifest, [('Data', 'C3', 'ND', self.dim)])
        self.assertEqual(len(bronze), 1)
        self.assertEqual(good, [])
        self.assertEqual(rejected[0]['reason'], 'missing_value')
        self.assertEqual(rejected[0]['cell'], 'C3')

    def test_duplicate_keys_reject_both_not_first_wins(self):
        _, good, rejected = normalize(self.manifest, [('Data', 'C3', 100, self.dim),
                                                    ('Data', 'C4', 101, self.dim)])
        self.assertEqual(good, [])
        self.assertEqual(len(rejected), 2)
        self.assertEqual(len({r['reject_id'] for r in rejected}), 2)

    def test_geographies_remain_distinct(self):
        _, good, rejected = normalize(self.manifest, [('Data', 'C3', 100, self.dim),
            ('Data', 'C4', 101, self.dim | {'geography': 'Rabat'})])
        self.assertEqual(len(good), 2)
        self.assertFalse(rejected)

    def test_repeat_has_stable_keys(self):
        cells = [('Data', 'C3', 100, self.dim)]
        self.assertEqual(normalize(self.manifest, cells), normalize(self.manifest, cells))

    def test_yoy_requires_exact_previous_year(self):
        _, rows, _ = normalize(self.manifest, [
            ('Data', 'C3', 100, self.dim),
            ('Data', 'D3', 110, self.dim | {'period_start': '2025-01-01'}),
            ('Data', 'E3', 130, self.dim | {'period_start': '2027-01-01'})])
        result = {r['period_start']: r for r in gold_current(rows)}
        self.assertAlmostEqual(result['2025-01-01']['yoy_pct'], 10)
        self.assertIsNone(result['2027-01-01']['yoy_pct'])

    def test_zero_denominator_and_revision(self):
        _, rows, _ = normalize(self.manifest, [('Data', 'C3', 0, self.dim),
            ('Data', 'D3', 110, self.dim | {'period_start': '2025-01-01'})])
        self.assertTrue(all(r['yoy_pct'] is None for r in gold_current(rows)))
        revised = copy.deepcopy(rows[1])
        revised.update(value=115, retrieved_at='2026-11-03T00:00:00+00:00', file_sha256='def')
        result = gold_current(rows + [revised])
        self.assertEqual(len(result), 2)
        self.assertEqual(next(r for r in result if r['period_start']=='2025-01-01')['value'], 115)


if __name__ == '__main__':
    unittest.main()
