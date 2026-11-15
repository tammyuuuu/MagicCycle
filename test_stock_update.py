import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import stock_monitor


class StockUpdateTests(unittest.TestCase):
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
