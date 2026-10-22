import unittest
import numpy as np
import pandas as pd
from research_csi300_search import batch_execute, summarize, candidates
from research_broad_individual import execute
from research_broad_valuation import load


class SearchTests(unittest.TestCase):
    def test_batch_matches_reference_with_different_end_dates(self):
        p,_,_=load('510300','000300')
        target=(p.close>p.close.rolling(60).mean()).astype(float)
        spans=[(1000,1250),(1100,1800),(1700,2000)]
        for monthly in (False,True):
            batch=batch_execute(p,target,spans,monthly)
            for j,(s,e) in enumerate(spans):
                stats,_,_=execute(p,target,s,e,monthly=1000. if monthly else None)
                self.assertAlmostEqual(batch['profit'][j],stats['profit_on_contributions_pct'],places=2)
                self.assertAlmostEqual(batch['dd'][j],stats['max_drawdown_pct'],places=2)

    def test_strict_joint_score(self):
        value={'profit':np.array([10.,11.,11.]),'dd':np.array([-10.,-20.,-10.])}
        base={'profit':np.array([10.,10.,10.]),'dd':np.array([-20.,-20.,-20.])}
        self.assertEqual(summarize(value,base,np.ones(3,dtype=bool))['joint_win_pct'],33.3)

    def test_candidates_do_not_use_future_prices_or_pe(self):
        p,h,_=load('510300','000300')
        full=candidates(p,h)
        cut=1800
        prefix=candidates(p.iloc[:cut],h[h.date<=p.index[cut-1]])
        for key in full:
            pd.testing.assert_series_equal(full[key].iloc[:cut],prefix[key])


if __name__=='__main__': unittest.main()
