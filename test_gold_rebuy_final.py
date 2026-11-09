import unittest
import numpy as np
import pandas as pd
from test_asset_strategies import frame
from research_gold_rebuy_final import indicators,run,cycle_attribution,VARIANTS
from gold_strategy import stages
from research_sector_partial_exit import backtest_partial


class RebuyTests(unittest.TestCase):
    def data(self):
        return frame(np.r_[np.full(130,5.),6.5,np.full(50,6.5),np.linspace(6.5,5.5,40),np.linspace(5.5,7.,80),np.full(150,7.)])

    def test_fixed_wait_and_never_repeat(self):
        d=self.data();f=indicators(d)
        for name,n in [('wait10',10),('wait20',20),('wait60',60)]:
            _,t,_=run(d,f,120,len(d),name)
            s=next(x for x in t if x['action']=='减仓');b=next(x for x in t if x['action']=='买回')
            self.assertEqual(d.index.get_loc(pd.Timestamp(b['date']))-d.index.get_loc(pd.Timestamp(s['date'])),n)
        _,t,_=run(d,f,120,len(d),'never')
        self.assertEqual([x['action'] for x in t],['首次建仓','减仓'])

    def test_trend_needs_actual_weakness(self):
        d=self.data();f=indicators(d);_,t,_=run(d,f,120,len(d),'trend20')
        s=next(x for x in t if x['action']=='减仓');b=next(x for x in t if x['action']=='买回')
        si=d.index.get_loc(pd.Timestamp(s['date']));bi=d.index.get_loc(pd.Timestamp(b['date']))
        self.assertTrue((d.close.iloc[si:bi]<=f.ma20.iloc[si:bi]).any())
        self.assertGreater(d.close.iloc[bi-1],f.ma20.iloc[bi-1])

    def test_cool5_matches_old_engine_on_common_nonhot_start(self):
        d=self.data();f=indicators(d)
        c,t,_=run(d,f,120,len(d),'cool5')
        _,old,ot=backtest_partial(d,stages(d.close).target,120,len(d),initial_cash=100000.,limit_pct=.10)
        np.testing.assert_allclose(c.equity,old.equity)
        self.assertEqual([x['date'] for x in t],[x['date'] for x in ot])

    def test_initial_listing_day_no_future_and_ledger(self):
        d=self.data();f=indicators(d)
        c,t,_=run(d,f,0,len(d),'wait20')
        self.assertEqual(t[0]['signal_date'],'');self.assertIsNone(t[0]['return20_pct'])
        cash=100000.;qty=0
        for date,row in c.iterrows():
            for v in t:
                if v['date']!=str(date.date()):continue
                sign=-1 if v['action']=='减仓' else 1
                cash-=sign*v['quantity']*v['price']+v['fee'];qty+=sign*v['quantity']
            self.assertAlmostEqual(cash,row.cash);self.assertEqual(qty,row.quantity)
            self.assertAlmostEqual(row.equity,cash+qty*d.loc[date,'close'])
        short=d.iloc[:220];a=run(short,indicators(short),0,220,'wait20')[0]
        pd.testing.assert_frame_equal(a,c.iloc[:220])

    def test_attribution_replay_and_unclosed(self):
        d=self.data();f=indicators(d);c,t,_=run(d,f,120,len(d),'never')
        a,cf=cycle_attribution(d,f,120,len(d),'never',c,t,d.index[120],d.index[-1]+pd.Timedelta(days=1))
        self.assertFalse(a[0]['closed']);self.assertEqual(a[0]['buyback_and_followup_return_contribution_pp'],0.)
        skip=next(v for k,v in cf.items() if k.endswith('skip_sale'))
        hold=run(d,f,120,len(d),'hold')[0]
        pd.testing.assert_frame_equal(skip,hold)

    def test_common_event_has_same_reduction_for_all_mechanisms(self):
        d=self.data();f=indicators(d);signal=f.index[f.pulse][0];start=d.index.get_loc(signal)
        sales=[]
        for name in VARIANTS[1:]:
            _,t,_=run(d,f,start,len(d),name,allowed_sales={str(signal.date())})
            s=[x for x in t if x['action']=='减仓']
            self.assertEqual(len(s),1)
            sales.append((s[0]['date'],s[0]['quantity'],s[0]['price']))
        self.assertTrue(all(x==sales[0] for x in sales))

    def test_ablation_does_not_rewrite_past(self):
        d=self.data();f=indicators(d);c,t,_=run(d,f,120,len(d),'wait20')
        sale=next(x for x in t if x['action']=='减仓');i=d.index.get_loc(pd.Timestamp(sale['date']))
        cf=run(d,f,120,len(d),'wait20',skip_sales={sale['event']})[0]
        pd.testing.assert_frame_equal(c.iloc[:i-120],cf.iloc[:i-120])


if __name__=='__main__':unittest.main()
