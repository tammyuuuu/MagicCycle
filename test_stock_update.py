import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import stock_monitor


class StockUpdateTests(unittest.TestCase):
    def test_intraday_bar_is_removed_from_all_arrays_without_mutation(self):
        data = {'chart': {'result': [{'meta': {'symbol': 'NVDA'},
            'timestamp': [1794578400, 1794837600],
            'indicators': {'quote': [{'close': [10, 11], 'volume': [100, 120]}],
                           'adjclose': [{'adjclose': [9, 10]}]}}]}}
        result = stock_monitor.completed_chart(data, 'NVDA', dt.date(2026, 11, 13))['chart']['result'][0]
        self.assertEqual(len(result['timestamp']), 1)
        self.assertEqual(result['indicators']['quote'][0]['close'], [10])
        self.assertEqual(result['indicators']['quote'][0]['volume'], [100])
        self.assertEqual(result['indicators']['adjclose'][0]['adjclose'], [9])
        self.assertEqual(len(data['chart']['result'][0]['timestamp']), 2)

    def test_rejects_misaligned_chart_before_cache_write(self):
        data = {'chart': {'result': [{'meta': {'symbol': 'NVDA'}, 'timestamp': [1794578400],
                'indicators': {'quote': [{'close': []}]}}]}}
        with self.assertRaises(ValueError):
            stock_monitor.completed_chart(data, 'NVDA', dt.date(2026, 11, 13))

    def test_failed_sources_preserve_cache_and_report_each_stock(self):
        with tempfile.TemporaryDirectory(dir='.') as directory:
            root = Path(directory)
            old = b'previous valid data'
            (root / 'NVDA.json').write_bytes(old)
            with patch.object(stock_monitor, 'ROOT', root), \
                 patch.object(stock_monitor.requests, 'get', side_effect=requests.ConnectionError('offline')), \
                 patch.object(stock_monitor.time, 'sleep'), \
                 patch('msft_monitor.expected_date', return_value=dt.date(2026, 11, 12)):
                stock_monitor.refresh()
            self.assertEqual((root / 'NVDA.json').read_bytes(), old)
            self.assertEqual(set(stock_monitor.UPDATE_ERRORS), set(stock_monitor.INFO))
            self.assertIn('offline', stock_monitor.UPDATE_ERRORS['NVDA'])


if __name__ == '__main__':
    unittest.main()
