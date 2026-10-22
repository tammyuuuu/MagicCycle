import unittest
import pandas as pd
from research_gold_heat import heat_targets


class GoldHeatTests(unittest.TestCase):
    def test_heat_latches_until_cool_and_then_recovers(self):
        close=pd.Series([100.]*130+[130.,131.]+[131.]*80)
        targets=heat_targets(close,exit_on_weak=False,use_trend=False)
        self.assertEqual(targets.iloc[129],1.)
        self.assertEqual(targets.iloc[130],.5)
        self.assertTrue((targets.iloc[130:151]==.5).all())
        self.assertEqual(targets.iloc[-1],1.)
        self.assertEqual(((targets==.5)&(targets.shift(1)==1.)).sum(),1)

    def test_heat_exit_priority_before_cooling(self):
        close=pd.Series([100.]*130+[130.,131.,101.])
        targets=heat_targets(close,use_trend=False)
        self.assertEqual(targets.iloc[-2],.5)
        self.assertEqual(targets.iloc[-1],0.)

    def test_no_future_information(self):
        close=pd.Series([100.]*130+[130.,131.]+[131.]*80)
        changed=close.copy();changed.iloc[145:]=10.
        for trend in (True,False):
            pd.testing.assert_series_equal(heat_targets(close,use_trend=trend).iloc[:145],heat_targets(changed,use_trend=trend).iloc[:145])

    def test_no_trend_exit_in_long_holding_variant(self):
        close=pd.Series([100.]*130+[90.,89.])
        self.assertEqual(heat_targets(close).iloc[-1],0.)
        self.assertEqual(heat_targets(close,use_trend=False).iloc[-1],1.)


if __name__=='__main__':unittest.main()
