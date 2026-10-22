import unittest
import pandas as pd
from research_sector_trend import backtest, signals
from research_sector_confirmation import confirmed_signal


class SectorResearchTests(unittest.TestCase):
    def data(self, count=150):
        return pd.DataFrame({'open':[100.]*count,'close':[100.]*count},
                            index=pd.bdate_range('2025-01-01',periods=count))

    def test_next_day_execution_and_costs(self):
        data=self.data(5)
        signal=pd.Series([False,True,False,False,False],index=data.index)
        result,curve,trades=backtest(data,signal,1,5)
        self.assertEqual(trades[0]['date'],str(data.index[2].date()))
        self.assertEqual(trades[1]['date'],str(data.index[3].date()))
        self.assertLess(result['return_pct'],0)
        self.assertEqual(result['losing_round_trips'],1)
        self.assertTrue(all(trade['quantity']%100==0 for trade in trades))
        costly,_,_=backtest(data,signal,1,5,slippage=.002)
        self.assertLess(costly['return_pct'],result['return_pct'])

    def test_signal_does_not_read_future(self):
        data=self.data()
        original=signals(data)
        data.loc[data.index[140:],'close']=1000.
        changed=signals(data)
        for name in original:
            pd.testing.assert_series_equal(original[name].iloc[:140],changed[name].iloc[:140])

    def test_cash_only_stays_flat(self):
        data=self.data(5)
        result,curve,trades=backtest(data,pd.Series(False,index=data.index),1,5)
        self.assertEqual(result['return_pct'],0)
        self.assertEqual(result['max_drawdown_pct'],0)
        self.assertEqual(trades,[])

    def test_confirmation_and_original_rule_match(self):
        close=pd.Series([100.,102.,104.,106.,104.,102.])
        confirmed=confirmed_signal(close,2,2,2)
        self.assertEqual(confirmed.tolist(),[False,False,True,True,True,False])
        pd.testing.assert_series_equal(confirmed_signal(close,2),close>close.rolling(2).mean())
        flat=pd.Series([100.]*10)
        self.assertFalse(confirmed_signal(flat,2).any())

    def test_confirmation_has_no_lookahead(self):
        close=self.data().close.copy()
        original=confirmed_signal(close,20,2,2,.01)
        close.iloc[100:]=200.
        changed=confirmed_signal(close,20,2,2,.01)
        pd.testing.assert_series_equal(original.iloc[:100],changed.iloc[:100])


if __name__=='__main__':unittest.main()
