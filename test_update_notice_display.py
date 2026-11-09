import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

import asset_states
import bond_monitor
import msft_monitor

class UpdateNoticeDisplayTest(unittest.TestCase):
    def test_etf_display_suppresses_update_message_without_changing_status(self):
        summary={'asset_type':'sector_etf','status':'watch','action':'观察',
                 'reason':'行情更新受限，待数据更新后再判断。',
                 'details':{'data_warning':'更新失败'},
                 'decision_basis':[('行情前提','更新受限，先观察'),('PE分位','数据不足或过旧'),('价格','100')]}
        rail=asset_states.render_rail(summary);basis=asset_states.render_basis(summary)
        self.assertIn('当前建议：观察',rail)
        self.assertIn('暂时观察',rail)
        self.assertNotIn('更新受限',rail+basis)
        self.assertNotIn('过旧',basis)
        self.assertIn('PE分位',basis)
        self.assertIn('暂无',basis)
        self.assertEqual(summary['details']['data_warning'],'更新失败')

    def test_bond_missing_values_remain_explicit_without_update_message(self):
        with patch.object(bond_monitor,'ROOT',Path('nonexistent_bond_fixture')):
            card=bond_monitor.render_bond_monitor()
        self.assertIn('数据日 —',card)
        self.assertNotIn('未更新',card)
        self.assertNotIn('待更新',card)
        self.assertEqual(card.count('class="state-step'),1)

    def test_stale_msft_never_promotes_pending_buy(self):
        snapshot=msft_monitor.read_snapshot().copy()
        snapshot.update(last_signal='买入',last_signal_date='2026-11-06',pending=True,
            last_trade={'signal_date':'2026-11-06','action':'买入','planned_date':'2026-11-09'})
        when=dt.datetime(2026,11,9,14,tzinfo=dt.timezone.utc)
        card=msft_monitor.render(snapshot,error='offline',now=when)
        self.assertIn('当前建议：持有/观察',card)
        self.assertNotIn('未更新',card)
        self.assertNotIn('等待数据更新',card)
        self.assertNotIn('待下个交易日开盘模拟执行',card)

if __name__=='__main__':unittest.main()
