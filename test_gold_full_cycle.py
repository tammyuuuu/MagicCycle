import unittest
import numpy as np
import pandas as pd
from test_asset_strategies import frame
from research_gold_full_cycle import Rule,candidates,features,simulate,statistics,rank_training


class FullCycleTests(unittest.TestCase):
    def test_grid_and_equivalent_hold(self):
        rules=candidates();self.assertEqual(len(rules),65)
        self.assertEqual(len({r.key for r in rules}),len(rules))
        d=frame(np.linspace(100,140,400));f=features(d)
        a=simulate(d,f,Rule('buy_hold'),260,400)
        b=simulate(d,f,Rule('immediate_full_none_trend'),260,400)
        pd.testing.assert_frame_equal(a[0],b[0])

    def test_ledger_and_causality(self):
        d=frame(np.r_[np.linspace(100,110,260),np.linspace(110,160,25),np.linspace(160,90,80),np.linspace(90,180,120),np.full(150,180.)])
        r=Rule('test','trend','half','heat10trend','trend20')
        curve,trades,orders=simulate(d,features(d),r,260,len(d))
        cash=100000.;qty=0
        for day,row in curve.iterrows():
            for t in trades:
                if t['date']!=str(day.date()):continue
                sign=-1 if t['action'] in ('减仓','清仓') else 1
                qty+=sign*t['quantity'];cash-=sign*t['quantity']*t['price']+t['fee']
                self.assertLess(t['signal_date'],t['date']);self.assertEqual(t['quantity']%100,0)
            self.assertAlmostEqual(row.cash,cash);self.assertEqual(row.quantity,qty)
            self.assertAlmostEqual(row.equity,cash+qty*d.loc[day,'close'])
            self.assertGreaterEqual(cash,-1e-8);self.assertGreaterEqual(qty,0)
        short=d.iloc[:350];a=simulate(short,features(short),r,260,350)
        pd.testing.assert_frame_equal(a[0],curve.iloc[:90])
        self.assertTrue(any(t['action']=='减仓' for t in trades))
        self.assertTrue(any(t['action']=='清仓' for t in trades))
        self.assertTrue(any(t['action']=='重新入场' for t in trades))

    def test_dca_no_external_cash(self):
        d=frame(np.full(1700,100.));r=Rule('monthly60',entry='monthly')
        curve,trades,_=simulate(d,features(d),r,260,len(d))
        self.assertLessEqual(len(trades),60)
        self.assertTrue(all(t['quantity']*t['price']+t['fee']<=100000/60+1e-7 for t in trades))
        self.assertGreaterEqual(curve.cash.min(),0)

    def test_fresh_window_and_training_only(self):
        d=frame(np.linspace(200,50,400));r=Rule('trend','trend','quarter','trend')
        curve,trades,_=simulate(d,features(d),r,260,400)
        self.assertEqual(len(trades),0);self.assertTrue((curve.equity==100000).all())
        stats=statistics(curve,curve.index[0],curve.index[-1],trades)
        self.assertTrue(np.isnan(stats['calmar']));self.assertTrue(np.isnan(stats['sharpe']))
        t=pd.DataFrame([dict(rule='buy_hold',calmar=.5,sharpe=.6,trades=1),dict(rule='x',calmar=.4,sharpe=.5,trades=2),dict(rule='cash',calmar=np.nan,sharpe=np.nan,trades=0)])
        self.assertEqual(rank_training(t).iloc[0].rule,'buy_hold')


if __name__=='__main__':unittest.main()
