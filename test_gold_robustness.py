import unittest
import numpy as np
import pandas as pd
from test_asset_strategies import frame
from research_gold_robustness import signal,execute,events


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.data=frame(np.r_[np.full(130,100.),130.,np.full(100,131.),180.,np.full(100,181.)])

    def test_causality(self):
        c=self.data.close
        for variant in ['cool5','no_rebuy','wait20']:
            a=signal(c.iloc[:220],10,variant)
            b=signal(c,10,variant).iloc[:220]
            pd.testing.assert_series_equal(a,b)

    def test_no_rebuy_only_after_actual_entry(self):
        _,curve,trades=execute(self.data,132,10,'no_rebuy')
        self.assertEqual(curve.iloc[0].quantity,0)
        self.assertEqual(trades[0]['action'],'买入')
        self.assertEqual(sum(t['action']=='减仓' for t in trades),1)
        self.assertFalse(any(t['action']=='恢复买入' for t in trades))

    def test_cooling_and_event_accounting(self):
        stats,curve,trades=execute(self.data,120,10,'cool5')
        e=events(self.data,trades,{})
        self.assertTrue(e[0]['closed'])
        t=next(t for t in trades if t['action']=='减仓')
        r=next(t for t in trades if t['action']=='恢复买入')
        expected=t['quantity']*(t['price']-r['price'])-t['fee']-max(5,t['quantity']*r['price']*.0001)
        self.assertAlmostEqual(e[0]['lot_timing_gain_yuan'],expected)
        for v in trades:
            self.assertLess(v['signal_date'],v['date'])
        # 最后60日内成交的未来60日列须为空，不能跨窗口读取。
        for v in trades:
            i=self.data.index.get_loc(pd.Timestamp(v['date']))
            if i+60>=len(self.data):self.assertIsNone(v['forward_60d_price_return_pct'])

    def test_wait20_restores_without_cooling(self):
        s=signal(self.data.close,10,'wait20')
        self.assertEqual(s.iloc[130],.5)
        self.assertEqual(s.iloc[149],.5)
        self.assertEqual(s.iloc[150],1.)


if __name__=='__main__':unittest.main()
