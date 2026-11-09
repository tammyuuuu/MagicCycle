import datetime as dt
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import nvda_monitor as n

UTC=dt.timezone.utc
BEFORE=dt.datetime(2026,11,9,14,0,tzinfo=UTC)

class NvidiaMonitorTest(unittest.TestCase):
    def test_one_state_and_no_timing_signal(self):
        snapshot=n.read_snapshot()
        live=n.render(snapshot,now=BEFORE)
        self.assertIn('当前建议：买入／持有',live)
        self.assertIn('买点研究仅供参考',live)
        self.assertIn('PE 23.50',live)
        self.assertIn('不产生择时交易信号',live)
        self.assertEqual(live.count('class="state-step'),1)
        self.assertNotIn('模拟信号：',live)
        self.assertNotIn('计划执行',live)
        stale=n.render(snapshot,error='offline',now=BEFORE)
        self.assertNotIn('未更新',stale)
        self.assertIn('当前建议：买入／持有',stale)
        for label in ('近1年','近3年','近5年','107个窗口','65.81%','48.18%'): self.assertIn(label,live)

    def test_failure_does_not_create_or_modify_signal(self):
        before=n.SNAPSHOT.read_bytes();archive=n.LIVE/'activation.json';history=archive.read_bytes() if archive.exists() else None
        with patch.object(n.requests,'get',side_effect=OSError('offline')):
            result,error=n.refresh()
        self.assertTrue(error)
        self.assertEqual(before,n.SNAPSHOT.read_bytes())
        if history is not None:self.assertEqual(history,archive.read_bytes())
        self.assertEqual(result,n.read_snapshot())

    def test_successful_refresh_preserves_archived_signal_without_reissuing(self):
        archive=n.LIVE/'activation.json';history=archive.read_bytes() if archive.exists() else None
        payloads=[(n.RAW/'NVDA_chart.json').read_bytes(),(n.RAW/'NVDA_facts.json').read_bytes()]
        responses=[]
        for payload in payloads:
            response=MagicMock();response.content=payload;response.json.return_value={};responses.append(response)
        result_data={'date':'2026-11-06','version':n.VERSION}
        with patch.object(n,'SNAPSHOT') as destination, patch.object(n.requests,'get',side_effect=responses), patch.object(n,'calculate',return_value=result_data):
            result,error=n.refresh()
        self.assertIsNone(error)
        self.assertNotIn('activation',result)
        destination.with_suffix.return_value.replace.assert_called_once_with(destination)
        if history is not None:self.assertEqual(history,archive.read_bytes())

    def test_separate_cards_and_endpoint(self):
        from asset_states import render_today_categories
        html=render_today_categories()
        self.assertIn('data-asset-symbol="MSFT"',html)
        self.assertIn('data-asset-symbol="NVDA"',html)
        import app
        with patch.object(n,'refresh',return_value=(n.read_snapshot(),None)):
            response=app.app.test_client().get('/api/nvda-monitor')
        self.assertEqual(response.status_code,200)
        self.assertIn('NVDA',response.get_json()['html'])

    def test_baseline_metrics_match_selected_rule(self):
        d=pd.read_csv(n.ROOT/'pe_rolling_5y_summary.csv')
        full=d[d.threshold==0].iloc[0]
        self.assertEqual(full.n,107)
        self.assertAlmostEqual(full.mean_cagr,.6581495856833075,places=9)

if __name__=='__main__':unittest.main()
