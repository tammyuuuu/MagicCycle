import datetime as dt
import json
import unittest
from unittest.mock import patch

import msft_monitor as m

NOW=dt.datetime(2026,11,9,0,tzinfo=dt.timezone.utc)

class MSFTMonitorTest(unittest.TestCase):
    def test_research_snapshot_and_backtest_state(self):
        s=m.calculate(NOW)
        self.assertEqual(s['date'],'2026-11-06')
        self.assertAlmostEqual(s['pe'],27.7003032365,places=5)
        self.assertAlmostEqual(s['percentile'],0.2404761905,places=6)
        self.assertEqual(s['position'],'持有')
        self.assertEqual(s['last_signal_date'],'2026-10-30')
        self.assertEqual(s['last_signal'],'持有/观察')
        self.assertEqual(s['monthly_position'],'持有')
        self.assertEqual(s['last_trade'],{'signal_date':'2026-01-30','action':'买入','planned_date':'2026-02-02'})
        self.assertEqual(len(s['trade_history']),5)
        self.assertEqual(s['transitions'],[
            {'date':'2019-03-01','action':'买入'}, {'date':'2023-12-01','action':'卖出'},
            {'date':'2025-02-03','action':'买入'}, {'date':'2025-07-01','action':'卖出'},
            {'date':'2026-02-02','action':'买入'}])

    def test_calendar_and_month_end(self):
        self.assertEqual(m.expected_date(NOW),dt.date(2026,11,6))
        self.assertTrue(m.month_end(dt.date(2026,10,30)))
        self.assertFalse(m.month_end(dt.date(2026,11,6)))
        self.assertFalse(m.session(dt.date(2026,11,26)))

    def test_signal_expires_after_us_execution_day(self):
        event={'signal_date':'2026-11-30','action':'买入','planned_date':'2026-12-01'}
        snapshot={'last_trade':event}
        before=dt.datetime(2026,12,1,1,tzinfo=dt.timezone.utc)
        day=dt.datetime(2026,12,2,4,59,tzinfo=dt.timezone.utc)
        after=dt.datetime(2026,12,2,5,tzinfo=dt.timezone.utc)
        self.assertEqual(m.signal_view(snapshot,before,True)[1:],('待计划日执行',True))
        self.assertEqual(m.signal_view(snapshot,day,True)[1:],('待计划日执行',True))
        self.assertEqual(m.signal_view(snapshot,after,True)[1:],('已过执行日',False))
        self.assertEqual(m.signal_view(snapshot,day,False)[1:],('数据未更新',False))

    def test_recent_historical_signal_is_not_current(self):
        snapshot=m.calculate(NOW)
        html=m.render(snapshot,now=NOW)
        self.assertIn('当前建议：持有/观察',html)
        self.assertIn('2026-01-30 · 买入 · 计划 2026-02-02',html)
        self.assertIn('已过执行日',html)
        self.assertIn('查看历史买卖信号',html)
        self.assertIn('历史回测中，延迟10个交易日内执行的全样本收益与最大回撤差异较小，仅供参考。',html)
        self.assertNotIn('未更新，暂停信号',html)
        self.assertIn('月末确认交易信号',html)

    def test_delay_baseline_matches_frozen_research(self):
        import pandas as pd
        results=pd.read_csv(m.ROOT.parent/'delay_metrics.csv')
        original=pd.read_csv(m.ROOT/'metrics.csv')
        for period, original_name in [('full','full'),('1y','trailing_1y'),('3y','trailing_3y'),('5y','trailing_5y')]:
            a=results[(results.extra_delay==0)&(results.period==period)].iloc[0]
            b=original[(original.ticker=='MSFT')&(original.strategy=='valuation')&(original.period==original_name)].iloc[0]
            for key in ('CAGR','max_drawdown','stock_orders_per_year'):
                self.assertAlmostEqual(a[key],b[key],places=9)

    def test_failure_retains_last_snapshot_and_no_signal(self):
        snapshot=m.read_snapshot()
        before=m.SNAPSHOT.read_bytes()
        with patch.object(m.requests,'get',side_effect=OSError('offline')):
            result,error=m.refresh()
        self.assertEqual(before,m.SNAPSHOT.read_bytes())
        self.assertEqual(result,snapshot)
        self.assertTrue(error)
        html=m.render(result,error,NOW)
        self.assertNotIn('未更新',html)
        self.assertIn('当前建议：持有/观察',html)
        self.assertIn('onclick="inspectAssetState(this)"',html)
        self.assertIn('class="strategy-summary"',html)
        self.assertIn('class="strategy-stats"',html)
        self.assertIn('class="strategy-basis"',html)
        self.assertNotIn('模拟仓位：',html)

    def test_page_and_flask_endpoint(self):
        import app
        snapshot=m.read_snapshot()
        with patch.object(m,'refresh',return_value=(snapshot,None)):
            response=app.app.test_client().get('/api/msft-monitor')
        self.assertEqual(response.status_code,200)
        self.assertIn('MSFT',response.get_json()['html'])
        from asset_states import render_today_categories
        self.assertIn('data-category="stock"',render_today_categories())

if __name__=='__main__': unittest.main()
