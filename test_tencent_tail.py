import unittest
from datetime import date
from unittest.mock import Mock, patch
import data_fetcher as d


class TencentTailTests(unittest.TestCase):
    def test_fills_only_missing_final_session_using_same_adjustment(self):
        older = Mock()
        older.json.return_value = {'data': {'sh588000': {'qfqday': [['2026-11-13', '1.4', '1.354', '1.419', '1.343', '100']]}}}
        latest = Mock()
        latest.json.return_value = {'data': {'sh588000': {'qfqday': [['2026-11-16', '1.329', '1.282', '1.34', '1.27', '200']]}}}
        with patch.object(d, '_expected_latest_trade_date', return_value=date(2026, 11, 16)), \
             patch.object(d.requests, 'get', side_effect=[older, latest]) as get:
            result = d._fetch_tencent('588000', '20261104', '20261116')
        self.assertEqual(str(result.index[-1].date()), '2026-11-16')
        self.assertEqual(result.iloc[-1]['close'], 1.282)
        self.assertIn('sh588000,day,2026-11-16,2026-11-16,640,qfq', get.call_args[0][0])

    def test_does_not_skip_missing_intermediate_sessions(self):
        response = Mock()
        response.json.return_value = {'data': {'sh588000': {'qfqday': [['2026-11-12', '1.4', '1.354', '1.419', '1.343', '100']]}}}
        with patch.object(d, '_expected_latest_trade_date', return_value=date(2026, 11, 16)), \
             patch.object(d.requests, 'get', return_value=response) as get:
            result = d._fetch_tencent('588000', '20261104', '20261116')
        self.assertEqual(get.call_count, 1)
        self.assertEqual(str(result.index[-1].date()), '2026-11-12')


if __name__ == '__main__':
    unittest.main()
