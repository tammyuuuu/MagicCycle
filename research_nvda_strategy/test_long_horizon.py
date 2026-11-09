"""Check execution timing, training cutoffs and cohort measurement."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT

class LongHorizonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets=pd.read_csv(ROOT/'long_horizon_targets.csv',parse_dates=['date']).set_index('date')
        cls.decisions=pd.read_csv(ROOT/'long_horizon_decisions.csv',parse_dates=['signal_date','next_open'])
        cls.stock,_,_=bt.load_chart('NVDA');cls.cash,_,_=bt.load_chart('BIL')
        common=cls.stock.index.intersection(cls.cash.index)
        cls.stock,cls.cash=cls.stock.loc[common],cls.cash.loc[common]

    def test_trade_decisions_apply_next_open_only(self):
        events=self.decisions[self.decisions.action.isin(['买入','卖出'])].dropna(subset=['next_open'])
        for event in events.itertuples():
            self.assertGreater(event.next_open,event.signal_date)
            self.assertEqual(bool(self.targets.loc[event.next_open,event.strategy]),event.action=='买入')
            self.assertNotEqual(bool(self.targets.loc[event.signal_date,event.strategy]),event.action=='买入')

    def test_rolling_training_selection_uses_only_past(self):
        selections=pd.read_csv(ROOT/'long_horizon_selections.csv',parse_dates=['train_start','train_end'])
        names=['growth_trend','value_growth','pullback_growth','balanced']
        for item in selections.itertuples():
            self.assertLess(item.train_end,pd.Timestamp(item.year,1,1))
            rankings=[]
            for name in names:
                m,_,_=bt.simulate(self.stock,self.cash,self.targets[name],item.train_start,item.train_end,ticker='NVDA')
                rankings.append((m['CAGR'],-m['stock_orders_per_year'],name))
            self.assertEqual(item.chosen,max(rankings)[2])
            annual=self.targets[self.targets.index.year==item.year]
            self.assertTrue((annual.rolling_5y==annual[item.chosen]).all())

    def test_full_cohort_horizon_and_market_price_accounting(self):
        rows=pd.read_csv(ROOT/'long_horizon_cohorts.csv',parse_dates=['signal_date','start','end'])
        self.assertTrue((rows.start>rows.signal_date).all())
        self.assertTrue((rows.end<=pd.Timestamp('2026-11-06')).all())
        for row in rows.itertuples():
            self.assertEqual(row.end.to_period('M'),row.signal_date.to_period('M')+row.years*12)
        # Independent check of full-period NAV against adjusted prices + cost.
        for row in rows.iloc[::25].itertuples():
            years=((row.end-row.start).days+1)/365.25
            nav=.999*self.stock.loc[row.end,'adjclose']/self.stock.loc[row.start,'adjopen']
            self.assertAlmostEqual(row.CAGR,nav**(1/years)-1,places=9)

    def test_past_decision_inputs_are_as_of_signal(self):
        obs=pd.read_csv(ROOT/'factor_observations.csv',parse_dates=['signal_date','effective']).set_index('signal_date')
        self.assertTrue((obs.effective<=obs.index).all())
        for r in self.decisions.iloc[::30].itertuples():
            row=obs.loc[r.signal_date]
            for saved,raw in [(r.PE,row.PE),(r.PE_rank,row.pe_rank_3y),(r.eps_growth,row.eps_growth)]:
                if pd.isna(raw):self.assertTrue(pd.isna(saved))
                else:self.assertAlmostEqual(saved,raw,places=9)

    def test_original_and_counterfactual_only_differ_in_one_interval(self):
        targets=self.targets
        decision=self.decisions[(self.decisions.strategy=='value_growth')&(self.decisions.action=='卖出')].iloc[0]
        self.assertEqual(str(decision.next_open.date()),'2023-04-03')
        end=pd.Timestamp('2023-10-02')
        self.assertFalse(targets.loc['2023-04-03':'2023-09-29','value_growth'].any())
        self.assertTrue(targets.loc[end,'value_growth'])

if __name__=='__main__': unittest.main()
