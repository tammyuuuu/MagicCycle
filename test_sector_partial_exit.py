import unittest
import numpy as np
import pandas as pd
from industry_strategy import trend_positions
from research_sector_trend import backtest
from research_sector_partial_exit import exit_targets, backtest_partial


class PartialExitTests(unittest.TestCase):
    def flat(self,n):
        return pd.DataFrame({'open':1.,'close':1.,'high':1.01,'low':.99},index=pd.bdate_range('2025-01-01',periods=n))

    def test_two_step_targets_and_recovery(self):
        close=pd.Series([100.,102.,100.,99.,101.])
        self.assertEqual(exit_targets(close,window=2).tolist(),[0.,1.,.5,0.,1.])
        self.assertEqual(exit_targets(close,window=2,confirmation=3).tolist(),[0.,1.,.5,.5,1.])

    def test_no_future_prices_are_used(self):
        close=pd.Series(np.r_[np.linspace(100,120,35),np.linspace(110,140,35)])
        original=exit_targets(close)
        close.iloc[50:]=1
        changed=exit_targets(close)
        pd.testing.assert_series_equal(original.iloc[:50],changed.iloc[:50])

    def test_next_day_trim_and_exit_with_minimum_fees(self):
        data=self.flat(4);target=pd.Series([1.,.5,0.,0.],index=data.index)
        stats,curve,trades=backtest_partial(data,target,1,4,initial_cash=1000,slippage=0)
        self.assertEqual([t['action'] for t in trades],['买入','减仓','退出'])
        self.assertEqual([t['quantity'] for t in trades],[900,400,500])
        self.assertEqual([t['date'] for t in trades],[str(d.date()) for d in data.index[1:]])
        self.assertEqual(stats['return_pct'],-1.5)
        self.assertEqual(stats['fees_yuan'],15.)
        self.assertEqual(stats['closed_round_trips'],1)
        self.assertEqual(stats['losing_round_trips'],1)
        self.assertEqual(curve.cash.iloc[-1],985.)

    def test_half_stage_does_not_rebalance_daily_and_recovery_costs_money(self):
        data=self.flat(7);data.loc[data.index[3],'open']=1.2
        target=pd.Series([1.,.5,.5,1.,1.,0.,0.],index=data.index)
        stats,curve,trades=backtest_partial(data,target,1,7,initial_cash=1000,slippage=0)
        self.assertEqual([t['action'] for t in trades],['买入','减仓','恢复买入','退出'])
        self.assertNotIn(str(data.index[3].date()),[t['date'] for t in trades])
        self.assertEqual(curve.quantity.iloc[1],curve.quantity.iloc[2])
        self.assertEqual(stats['fees_yuan'],20.)
        self.assertEqual(stats['return_pct'],-2.)
        self.assertEqual(stats['restoration_orders'],1)

    def test_cash_does_not_enter_a_delayed_exit_stage(self):
        data=self.flat(4)
        targets=pd.Series([1.,1.,0.,0.],index=data.index)
        stats,_,trades=backtest_partial(data,targets,1,4,entry_allowed=pd.Series(False,index=data.index))
        self.assertEqual(trades,[])
        self.assertEqual(stats['return_pct'],0)
        targets.iloc[:2]=.5
        self.assertEqual(backtest_partial(data,targets,1,4)[2],[])

    def test_single_lot_cannot_be_cut_in_half(self):
        data=self.flat(4);target=pd.Series([1.,.5,0.,0.],index=data.index)
        stats,curve,trades=backtest_partial(data,target,1,4,initial_cash=110,slippage=0)
        self.assertEqual([t['quantity'] for t in trades],[100,100])
        self.assertEqual(stats['partial_orders'],0)
        self.assertEqual(stats['partial_too_small'],1)
        self.assertEqual(curve.quantity.iloc[1],100)
        self.assertEqual(curve.quantity.iloc[-1],0)

    def test_one_price_limit_down_blocks_partial_sell(self):
        data=self.flat(4);data.loc[data.index[2],['open','close','high','low']]=.9
        target=pd.Series([1.,.5,0.,0.],index=data.index)
        stats,curve,trades=backtest_partial(data,target,1,4,initial_cash=1000,slippage=0,limit_pct=.1)
        self.assertEqual(stats['partial_orders'],0)
        self.assertEqual(curve.quantity.iloc[1],900)
        self.assertEqual(trades[-1]['quantity'],900)
        self.assertEqual(trades[-1]['date'],str(data.index[3].date()))

    def test_binary_engine_matches_original(self):
        rng=np.random.default_rng(123)
        close=100*np.exp(np.cumsum(rng.normal(0,.02,240)))
        data=pd.DataFrame({'close':close,'open':np.r_[100,close[:-1]],'high':close*1.03,'low':close*.97},
                          index=pd.bdate_range('2025-01-01',periods=len(close)))
        signal=trend_positions(data.close)
        for cash,minimum in [(100000,5),(1000,5),(1000,0)]:
            old,curve,_=backtest(data,signal,120,len(data),initial_cash=cash,minimum_fee=minimum,limit_pct=.1)
            new,new_curve,_=backtest_partial(data,signal.astype(float),120,len(data),initial_cash=cash,
                                            minimum_fee=minimum,entry_allowed=signal,limit_pct=.1)
            for k,v in old.items():self.assertEqual(new[k],v)
            pd.testing.assert_series_equal(curve.equity,new_curve.equity)


if __name__=='__main__':unittest.main()
