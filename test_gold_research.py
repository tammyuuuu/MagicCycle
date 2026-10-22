import unittest
import numpy as np
import pandas as pd
from research_gold_strategy import gold_targets
from research_sector_trend import backtest
from test_asset_strategies import frame


class GoldResearchTests(unittest.TestCase):
    def test_future_changes_do_not_change_prior_rules(self):
        close=pd.Series(np.r_[np.linspace(80,110,260),np.linspace(110,90,40)])
        changed=close.copy();changed.iloc[280:]=200.
        original=gold_targets(close);future=gold_targets(changed)
        for name in original:
            pd.testing.assert_series_equal(original[name].iloc[:280],future[name].iloc[:280])

    def test_pullback_requires_trend_and_holds_until_break(self):
        close=pd.Series([100.]*250+[120.,113.,115.,80.])
        signal=gold_targets(close)['回撤5%买入、跌破120日线退出']
        self.assertFalse(signal.iloc[250])
        self.assertTrue(signal.iloc[251])
        self.assertTrue(signal.iloc[252])
        self.assertFalse(signal.iloc[253])

    def test_equality_to_average_exits(self):
        close=pd.Series([100.]*251)
        for name,signal in gold_targets(close).items():
            if name!='长期持有':self.assertFalse(signal.iloc[-1])

    def test_next_day_execution(self):
        data=frame([100.]*25+[105.,106.,80.,79.])
        data['open']=data.close;data['high']=data.close*1.01;data['low']=data.close*.99
        _,_,trades=backtest(data,gold_targets(data.close)['20日均线'],25,len(data),limit_pct=.10)
        self.assertEqual(trades[0]['date'],str(data.index[26].date()))
        self.assertEqual(trades[1]['date'],str(data.index[28].date()))


if __name__=='__main__':unittest.main()
