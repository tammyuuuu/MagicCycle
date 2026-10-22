import unittest
import numpy as np
import pandas as pd
from research_sector_add import add_signals, simulate
from research_sector_partial_exit import backtest_partial
from industry_strategy import trend_positions, partial_exit_targets
from test_asset_strategies import frame


class SectorAddTests(unittest.TestCase):
    def test_signal_rebounds_once_per_near_episode(self):
        close=pd.Series(np.r_[np.linspace(80,100,40),97.,97.5,98.,98.5])
        signals=add_signals(close)
        self.assertTrue(signals.iloc[-3])
        self.assertFalse(signals.iloc[-2])
        self.assertFalse(signals.iloc[-1])

    def test_future_values_do_not_change_signal(self):
        close=pd.Series(np.r_[np.linspace(80,100,40),97.,97.5,98.,98.5])
        original=add_signals(close)
        changed=close.copy();changed.iloc[-2:]=1.
        pd.testing.assert_series_equal(original.iloc[:-2],add_signals(changed).iloc[:-2])

    def test_orders_next_day_and_capital_conserved(self):
        data=frame(np.r_[np.linspace(80,100,40),97.,97.5,98.,98.5])
        data['open']=data.close;data['high']=data.close*1.01;data['low']=data.close*.99
        _,curve,trades=simulate(data,30,len(data),initial_cash=100000)
        adds=[t for t in trades if t['action']=='加仓']
        self.assertEqual(len(adds),1)
        self.assertEqual(adds[0]['date'],str(data.index[-2].date()))
        cash=100000.;qty=0
        for t in trades:
            self.assertEqual(t['quantity']%100,0)
            if t['action'] in ('买入','加仓','恢复买入'):
                qty+=t['quantity'];cash-=t['quantity']*t['price']+t['fee']
            else:
                qty-=t['quantity'];cash+=t['quantity']*t['price']-t['fee']
        self.assertGreaterEqual(curve.cash.min(),0)
        self.assertAlmostEqual(cash+qty*data.close.iloc[-1],curve.equity.iloc[-1])

    def test_full_budget_baseline_matches_existing_engine(self):
        data=frame(np.r_[np.linspace(80,110,40),90.,89.,115.,116.,80.,79.])
        data['open']=data.close;data['high']=data.close*1.01;data['low']=data.close*.99
        result,curve,_=simulate(data,25,len(data),base=1,enable_add=False)
        reference,other,_=backtest_partial(data,partial_exit_targets(data.close),25,len(data),entry_allowed=trend_positions(data.close),limit_pct=.20)
        for key in ('return_pct','max_drawdown_pct','trades'):self.assertEqual(result[key],reference[key])
        pd.testing.assert_series_equal(curve.equity,other.equity)


if __name__=='__main__':unittest.main()
