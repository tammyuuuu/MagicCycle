import unittest
import numpy as np
import pandas as pd
from research_csi500_search import guarded_value, all_candidates, make_groups
from research_csi300_search import batch_execute, summarize
from research_broad_valuation import load
from research_broad_individual import execute


class Csi500SearchTests(unittest.TestCase):
    def test_batch_reference_on_csi500(self):
        p,h,_=load('510500','000905')
        target=(p.close>p.close.rolling(120).mean()).astype(float)
        spans=[(1000,1400),(1300,1900)]
        for monthly in (False,True):
            values=batch_execute(p,target,spans,monthly)
            for j,(s,e) in enumerate(spans):
                stats,_,_=execute(p,target,s,e,monthly=1000. if monthly else None)
                self.assertAlmostEqual(values['profit'][j],stats['profit_on_contributions_pct'],places=2)
                self.assertAlmostEqual(values['dd'][j],stats['max_drawdown_pct'],places=2)

    def test_guard_low_value_does_not_override_exit(self):
        index=pd.bdate_range('2020-01-01',periods=20)
        close=pd.Series([100.]*5+[110.]*5+[80.]*10,index=index)
        pct=pd.Series(20.,index=index)
        target=guarded_value(close,pct,entry_ma=3,exit_ma=3)
        self.assertEqual(target.iloc[5],1.)
        self.assertEqual(target.iloc[10],0.)
        self.assertEqual(target.iloc[-1],0.)

    def test_candidate_prefix_and_no_future_pe(self):
        p,h,_=load('510500','000905')
        full=all_candidates(p,h)
        cut=1700
        prefix=all_candidates(p.iloc[:cut],h[h.date<=p.index[cut-1]])
        for key in full:
            pd.testing.assert_series_equal(full[key].iloc[:cut],prefix[key])

    def test_empty_training_is_not_success(self):
        v={'profit':np.array([0.]),'dd':np.array([0.])}
        s=summarize(v,v,np.array([False]))
        self.assertEqual(s['n'],0)
        self.assertIsNone(s['joint_win_pct'])


if __name__=='__main__':unittest.main()
