import unittest
import numpy as np
import pandas as pd
from test_asset_strategies import frame
from research_gold_entry_value import fixed_weight,match_exposure,state_features,select_analogues,event_path


class EntryValueTests(unittest.TestCase):
    def test_fixed_weight_and_match(self):
        d=frame(np.linspace(4.,6.,600))
        c,t=fixed_weight(d,260,600,.5)
        cash=100000.;qty=0
        for date,row in c.iterrows():
            for v in t:
                if v['date']!=str(date.date()):continue
                sign=1 if v['action'].startswith('买入') else -1
                cash-=sign*v['quantity']*v['price']+v['fee'];qty+=sign*v['quantity']
            self.assertAlmostEqual(cash,row.cash);self.assertEqual(qty,row.quantity)
            self.assertAlmostEqual(row.equity,cash+qty*d.loc[date,'close'])
        w,a,_=match_exposure(d,260,600,.43)
        self.assertLess(abs(a.exposure.mean()-.43),.006)
        short=d.iloc[:420];p,_=fixed_weight(short,260,420,w)
        full,_=fixed_weight(d,260,600,w)
        pd.testing.assert_frame_equal(p,full.iloc[:160])

    def test_analogue_features_have_no_future_dependency(self):
        d=frame(np.r_[np.full(260,10.),np.linspace(10.,6.,120),np.full(100,6.),np.linspace(6.,9.,100),np.linspace(9.,6.,100)])
        target=state_features(d).iloc[-1]
        a=select_analogues(d,'primary',target_state=target)
        mutated=d.copy();mutated.loc[mutated.index[470:],'close']*=1.6
        b=select_analogues(mutated,'primary',target_state=target)
        self.assertEqual(list(a[1].index[a[1].index<d.index[470]]),list(b[1].index[b[1].index<d.index[470]]))
        for dates in (a[2],b[2]):
            for x,y in zip(dates,dates[1:]):self.assertGreaterEqual(y,x+pd.DateOffset(months=12))

    def test_missing_forward_and_waiting_cash_not_deleted(self):
        d=frame(np.linspace(10.,4.,900));f=state_features(d);event=d.index[500]
        a=event_path(d,f,event,3,'immediate')
        b=event_path(d,f,event,3,'wait_ma120')
        self.assertFalse(b[0]['entered']);self.assertEqual(b[0]['return_pct'],0.)
        self.assertLess(a[0]['return_pct'],0.)
        self.assertIsNone(event_path(d,f,d.index[-10],12,'immediate'))
        self.assertEqual(a[2][0]['date'],str(d.index[501].date()))

    def test_fixed_wait_and_costs(self):
        d=frame(np.full(900,5.));f=state_features(d);event=d.index[500]
        r,c,t=event_path(d,f,event,3,'wait20')
        self.assertEqual(r['entry_date'],str(d.index[521].date()))
        self.assertLess(r['return_pct'],0.)
        self.assertEqual(len(t),2)
        self.assertAlmostEqual(r['fees'],sum(x['fee'] for x in t))


if __name__=='__main__':unittest.main()
