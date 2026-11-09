import unittest
import numpy as np
import pandas as pd
from research_gold_five_year import windows,metrics
from research_gold_extended import targets,run
from test_asset_strategies import frame


class FiveYearTests(unittest.TestCase):
    def test_calendar_boundaries_and_partial(self):
        idx=pd.bdate_range('2013-07-29','2026-09-30')
        w=list(windows(idx))
        fixed=[x for x in w if x[0]=='fixed']
        self.assertEqual([(x[1],x[4]) for x in fixed],[(2015,True),(2020,True),(2025,False)])
        rolling=[x for x in w if x[0]=='rolling' and x[4]]
        self.assertEqual([x[1] for x in rolling],list(range(2015,2022)))
        self.assertEqual(rolling[0][3],pd.Timestamp('2020-01-01'))

    def test_metrics_include_initial_capital(self):
        curve=pd.DataFrame({'equity':[90000.,110000.], 'drawdown_pct':[-10.,0.]})
        m=metrics(curve,pd.Timestamp('2020-01-01'),pd.Timestamp('2025-01-01'))
        expected=1.1**(365.2425/1827)-1
        self.assertAlmostEqual(m['annual_return_pct'],expected*100)
        self.assertAlmostEqual(m['calmar'],expected/.1)
        r=np.array([-.1,110000/90000-1])
        self.assertAlmostEqual(m['sharpe'],r.mean()/r.std(ddof=1)*np.sqrt(252))

    def test_reset_and_no_future(self):
        data=frame(np.r_[np.full(130,100.),130.,np.full(100,131.)])
        target=targets(data.close)[1]
        a=run(data.iloc[:180],targets(data.close.iloc[:180])[1],120,1,100000.)
        b=run(data,target,120,1,100000.)
        pd.testing.assert_frame_equal(a[1],b[1].iloc[:60])
        # 起点处已经过热，从全现金等冷却，不继承此前持仓。
        _,curve,trades=run(data,target,132,1,100000.)
        self.assertEqual(curve.iloc[0].cash,100000.)
        self.assertEqual(curve.iloc[0].quantity,0)
        self.assertTrue(all(t['date']>=str(data.index[132].date()) for t in trades))


if __name__=='__main__':unittest.main()
