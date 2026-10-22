import unittest
import numpy as np
import pandas as pd
from research_monthly_execution import order, simulate
from us_guidance import guidance_frame

class MonthlyExecutionTests(unittest.TestCase):
    def data(self):
        dates=pd.bdate_range('2024-01-02','2024-04-30')
        return pd.DataFrame({k:np.ones(len(dates)) for k in ['open','high','low','close']},index=dates)
    def test_lots_and_commission(self):
        self.assertEqual(order(500,2.399),(200,5.))
        self.assertEqual(order(250,2.74),(0,0.))
    def test_repeated_signal_and_no_rollover(self):
        d=self.data();a=pd.Series('buy',index=d.index)
        m,c,t=simulate(d,a,1,slippage=0.)
        self.assertEqual(m['principal_yuan'],4000.)
        self.assertEqual(len(t),4)
        self.assertTrue(all(x['quantity']==400 for x in t))
        self.assertEqual(m['ending_yuan'],3980.)
        self.assertTrue((c.month_spent<=500).all())
    def test_add_fills_only_current_month(self):
        d=self.data();a=pd.Series('buy',index=d.index);a.iloc[5]='add';a.iloc[6]='add'
        m,c,t=simulate(d,a,1,slippage=0.)
        january=[x for x in t if x['date'].startswith('2024-01')]
        self.assertEqual(len(january),2)
        self.assertEqual(sum(x['quantity'] for x in january),900)
        self.assertTrue((c.month_spent+c.month_fees<=1000).all())
    def test_sell_does_not_refill_month(self):
        d=self.data();a=pd.Series('buy',index=d.index);a.iloc[5]='exit'
        m,c,t=simulate(d,a,1,slippage=0.)
        january=[x for x in t if x['date'].startswith('2024-01')]
        self.assertEqual([x['quantity'] for x in january],[400,-400])
    def test_prior_close_and_lookahead(self):
        d=self.data();a=pd.Series('watch',index=d.index);a.iloc[8]='buy'
        _,_,t=simulate(d,a,1,slippage=0.)
        self.assertEqual(t[0]['date'],str(d.index[9].date()))
        a.iloc[20:]='add'
        short=simulate(d,a,1,20,slippage=0.)[1]
        long=simulate(d,a,1,slippage=0.)[1].iloc[:19]
        pd.testing.assert_frame_equal(short,long)
    def test_guidance_truncation(self):
        dates=pd.bdate_range('2019-01-01','2024-01-01')
        close=pd.Series(np.linspace(1.,3.,len(dates)),index=dates)
        full=guidance_frame(close)
        cut=guidance_frame(close.iloc[:1000])
        pd.testing.assert_series_equal(full.status.iloc[:1000],cut.status)
    def test_cash_only_and_deposit_neutral_nav(self):
        d=self.data();a=pd.Series('watch',index=d.index)
        m,c,t=simulate(d,a,1)
        self.assertEqual(m['max_drawdown_pct'],0.)
        self.assertEqual(m['profit_yuan'],0.)
        self.assertEqual(m['cash_only_months'],4)
        self.assertTrue((c.nav==1.).all())

if __name__=='__main__':unittest.main()
