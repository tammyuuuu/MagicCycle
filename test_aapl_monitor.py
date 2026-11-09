import datetime as dt
import unittest
from unittest.mock import patch
import aapl_monitor as a

NOW=dt.datetime(2026,11,9,8,30,tzinfo=dt.timezone.utc)

class AppleMonitorTest(unittest.TestCase):
    def test_point_in_time_valuation_and_strategy(self):
        s=a.calculate(NOW)
        self.assertEqual(s['date'],'2026-11-06')
        self.assertAlmostEqual(s['close'],342.37,places=2)
        self.assertAlmostEqual(s['pe'],38.129684837,places=6)
        html=a.render(s,now=NOW)
        self.assertEqual(html.count('class="state-step'),2)
        self.assertIn('当前建议：持有/观察',html)
        self.assertIn('候选加仓策略',html)
        self.assertIn('总投资预算的10%',html)
        self.assertIn('已过执行日',html)
        self.assertEqual([x['planned_date'] for x in s['trade_history']],['2013-01-02','2016-01-04','2016-05-02','2018-12-03'])
        self.assertLess(s['reserve_value'],.25)

    def test_active_and_expired_signal(self):
        s=a.calculate(NOW)
        s['monthly']={'date':'2026-10-30','drawdown':.21,'action':'加仓'}
        s['last_trade']={'signal_date':'2026-10-30','planned_date':'2026-11-02','action':'加仓'}
        s['date']='2026-10-30'
        active=dt.datetime(2026,11,2,14,tzinfo=dt.timezone.utc)
        self.assertIn('当前建议：加仓',a.render(s,now=active))
        self.assertIn('已过执行日',a.render(s,now=NOW))
        self.assertNotIn('当前建议：加仓',a.render(s,now=NOW))

    def test_failed_refresh_retains_date_without_update_warning(self):
        before=a.SNAPSHOT.read_bytes()
        with patch.object(a.requests,'get',side_effect=OSError('offline')):
            snapshot,error=a.refresh()
        self.assertTrue(error)
        self.assertEqual(before,a.SNAPSHOT.read_bytes())
        html=a.render(snapshot,error=error,now=NOW)
        self.assertIn('数据日 2026-11-06',html)
        self.assertNotIn('未更新',html)

    def test_separate_cards_and_endpoint(self):
        from asset_states import render_today_categories
        html=render_today_categories()
        for symbol in ('MSFT','NVDA','AAPL'):
            self.assertIn(f'data-asset-symbol="{symbol}"',html)
        import app
        with patch.object(a,'refresh',return_value=(a.read_snapshot(),None)):
            response=app.app.test_client().get('/api/aapl-monitor')
        self.assertEqual(response.status_code,200)
        self.assertIn('Apple',response.get_json()['html'])

if __name__=='__main__':unittest.main()
