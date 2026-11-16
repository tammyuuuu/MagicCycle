import datetime as dt
import unittest
from unittest.mock import patch

import update_watchdog as w


class WatchdogTests(unittest.TestCase):
    def fixture(self):
        rows = [{'symbol': '510500', 'date': '2026-11-16', 'status': 'watch', 'metrics': {'price': 10}}]
        page = ''.join(f'<div data-asset-symbol="{s}"><h2>{s}</h2><p>行情日 2026-11-13 · 收盘 $10.00（已核对最新收盘日）</p></div>' for s in ('NVDA', 'MSFT', 'GOOGL', 'BWXT'))
        return rows, page

    def assess(self, rows, page):
        return w.assess(rows, page, '2026-11-16', '2026-11-13', ['510500'])[0]

    def test_current_mixed_market_dates(self):
        self.assertTrue(self.assess(*self.fixture()))

    def test_stale_etf_and_unavailable_stock_need_retry(self):
        rows, page = self.fixture()
        rows[0]['date'] = '2026-11-13'
        self.assertFalse(self.assess(rows, page))
        rows, page = self.fixture()
        self.assertFalse(self.assess(rows, page.replace('行情日 2026-11-13', '行情数据不可用', 1)))
        self.assertFalse(self.assess(rows, page.replace('已核对最新收盘日', '更新异常，沿用上次有效收盘价', 1)))

    def test_missing_and_invalid_etf(self):
        rows, page = self.fixture()
        self.assertFalse(self.assess([], page))
        rows[0]['metrics']['price'] = float('nan')
        self.assertFalse(self.assess(rows, page))

    def test_active_run_no_duplicate(self):
        now = dt.datetime(2026, 11, 16, 10, tzinfo=dt.timezone.utc)
        for status in w.ACTIVE:
            self.assertIn('active', w.decision([{'status': status}], now))

    def test_daily_limit_uses_beijing_date(self):
        now = dt.datetime(2026, 11, 16, 10, tzinfo=dt.timezone.utc)
        run = {'status': 'completed', 'event': 'workflow_dispatch', 'created_at': '2026-11-15T17:00:00Z'}
        self.assertIsNone(w.decision([run], now))
        self.assertIn('limit', w.decision([run] * 3, now))
        run['created_at'] = '2026-11-15T15:59:00Z'
        self.assertIsNone(w.decision([run] * 3, now))

    def test_api_rejects_credential_to_unrelated_host(self):
        with self.assertRaises(ValueError):
            w.request('https://example.com/', token='test')

    def test_post_is_not_retried_after_ambiguous_timeout(self):
        with patch.object(w, 'urlopen', side_effect=TimeoutError), patch.object(w.time, 'sleep'):
            with self.assertRaises(TimeoutError):
                w.request('https://api.github.com/example', body={'ref': 'main'})
            self.assertEqual(w.urlopen.call_count, 1)


if __name__ == '__main__':
    unittest.main()
