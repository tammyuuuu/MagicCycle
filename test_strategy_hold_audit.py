import unittest

import numpy as np
import pandas as pd

from gold_strategy import analyze_latest as analyze_gold
from industry_strategy import analyze_latest as analyze_sector
from research_strategy_hold_audit import gold_actions, sector_actions, monthly_budget, verdict, load
from research_broad_individual import execute


class HoldAuditTests(unittest.TestCase):
    def test_strict_joint_criterion(self):
        hold={'return_pct':10.,'max_drawdown_pct':-20.}
        self.assertFalse(verdict({'return_pct':10.,'max_drawdown_pct':-10.},hold)['both_better'])
        self.assertFalse(verdict({'return_pct':11.,'max_drawdown_pct':-20.},hold)['both_better'])
        self.assertTrue(verdict({'return_pct':11.,'max_drawdown_pct':-19.},hold)['both_better'])

    def test_actions_match_live_models(self):
        for code,model,function in [('518850',analyze_gold,gold_actions),('588170',analyze_sector,sector_actions)]:
            data,_=load(code)
            _,actions=function(data.close)
            # 检查全部动作的首个事件，以及较晚的观察日和样本末日。
            positions={len(data)-1,19,119}
            for status in ('buy','add','reduce','exit','watch'):
                matches=np.flatnonzero(actions.to_numpy()==status)
                if len(matches):positions.add(int(matches[0]));positions.add(int(matches[-1]))
            for i in positions:
                if i<len(data):
                    self.assertEqual(model(data.iloc[:i+1])['status'],actions.iloc[i])

    def test_prefix_invariance(self):
        for code,function in [('518850',gold_actions),('588170',sector_actions)]:
            data,_=load(code)
            n=int(len(data)*.7)
            full,actions=function(data.close)
            partial,earlier=function(data.close.iloc[:n])
            pd.testing.assert_series_equal(actions.iloc[:n],earlier)
            if isinstance(full,pd.DataFrame):pd.testing.assert_frame_equal(full.iloc[:n],partial)
            else:pd.testing.assert_series_equal(full.iloc[:n],partial)

    def test_full_budget_monthly_hold_equals_existing_engine(self):
        data,_=load('518850')
        actions=pd.Series('buy',index=data.index)
        result,curve,trades=monthly_budget(data,actions,120,buy_fraction=1.)
        reference,old,orders=execute(data,pd.Series(1.,index=data.index),120,monthly=1000)
        self.assertEqual(result['return_pct'],reference['return_pct'])
        self.assertEqual(result['max_drawdown_pct'],reference['max_drawdown_pct'])
        np.testing.assert_allclose(curve.equity,old.equity)
        self.assertEqual(len(trades),len(orders))

    def test_watch_contributions_do_not_create_returns(self):
        data,_=load('588170')
        result,curve,trades=monthly_budget(data,pd.Series('watch',index=data.index),20)
        self.assertEqual(result['return_pct'],0)
        self.assertEqual(result['max_drawdown_pct'],0)
        self.assertEqual(result['ending_yuan'],result['principal_yuan'])
        self.assertEqual(trades,[])

    def test_reduce_event_is_once_and_exit_sells_remaining(self):
        data,_=load('588170');data=data.iloc[:30].copy()
        data[['open','close','high','low']]=1.
        actions=pd.Series('watch',index=data.index)
        actions.iloc[19]='buy';actions.iloc[20]='reduce';actions.iloc[22]='exit'
        _,curve,trades=monthly_budget(data,actions,20,buy_fraction=1.,minimum_fee=0,slippage=0)
        self.assertEqual([t['action'] for t in trades],['buy','reduce','exit'])
        self.assertEqual(curve.quantity.iloc[-1],0)
        self.assertTrue((curve.cash>=0).all())


if __name__=='__main__':unittest.main()
