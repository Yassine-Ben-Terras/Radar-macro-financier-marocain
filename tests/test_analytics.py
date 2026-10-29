import unittest
from radar.analytics import evaluate, forecast


def series(n=72):
    return [{'period_start':f'{2020+i//12}-{i%12+1:02d}-01','value':100.0+i} for i in range(n)]


class AnalyticsTests(unittest.TestCase):
    def test_known_linear_forecasts(self):
        history = [100.0+i for i in range(24)]
        self.assertEqual(forecast(history,'last_month'),123)
        self.assertEqual(forecast(history,'same_month_last_year'),112)
        self.assertEqual(forecast(history,'drift_12m'),124)

    def test_metrics_and_initial_scale(self):
        result = evaluate(series())
        metrics = {r['method']:r for r in result['metrics']}
        self.assertEqual(metrics['last_month']['mae_mdh'],1)
        self.assertEqual(metrics['last_month']['mase'],1)
        self.assertEqual(metrics['same_month_last_year']['mae_mdh'],12)
        self.assertEqual(metrics['drift_12m']['rmse_mdh'],0)
        self.assertEqual(len(result['predictions']),72)

    def test_future_perturbation_cannot_change_prior_predictions(self):
        original = series()
        changed = [dict(r) for r in original]
        changed[-1]['value'] = 99999
        a, b = evaluate(original), evaluate(changed)
        self.assertEqual(a['scale_mae_training_mdh'], b['scale_mae_training_mdh'])
        for x,y in zip(a['predictions'],b['predictions']):
            self.assertEqual(x['prediction_mdh'],y['prediction_mdh'])
            self.assertLess(x['training_end'],x['target_period'])

    def test_missing_month_fails(self):
        rows=series()
        del rows[40]
        with self.assertRaises(ValueError):
            evaluate(rows)

    def test_zero_scale_is_unavailable(self):
        rows=[r | {'value':10.0} for r in series()]
        for metric in evaluate(rows)['metrics']:
            self.assertIsNone(metric['mase'])
            self.assertEqual(metric['mae_mdh'],0)

    def test_short_history_fails(self):
        with self.assertRaises(ValueError):
            evaluate(series(30))
