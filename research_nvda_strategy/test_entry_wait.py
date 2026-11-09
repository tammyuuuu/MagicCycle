"""Validate fresh-account one-entry comparisons and rolling cutoffs."""
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT

class EntryWaitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics=pd.read_csv(ROOT/'entry_wait_metrics.csv')
        cls.cohorts=pd.read_csv(ROOT/'entry_wait_cohorts.csv')
        cls.selections=pd.read_csv(ROOT/'entry_wait_oos_selections.csv')
        cls.stock,cls.splits,_=bt.load_chart('NVDA')
        cls.cash,_,_=bt.load_chart('BIL')
        idx=cls.stock.index.intersection(cls.cash.index)
        cls.stock,cls.cash=cls.stock.loc[idx],cls.cash.loc[idx]

    def test_immediate_matches_frozen_baseline(self):
        baseline=pd.read_csv(ROOT/'metrics.csv')
        for period in ('full','1y','3y','5y'):
            a=self.metrics[(self.metrics.strategy=='immediate')&(self.metrics.period==period)].iloc[0]
            b=baseline[(baseline.strategy=='buy_hold')&(baseline.period==period)].iloc[0]
            for key in ('CAGR','max_drawdown','stock_orders_per_year'):
                self.assertAlmostEqual(a[key],b[key],places=9)

    def test_wait_has_no_buy_before_start_and_valid_signal(self):
        rows=self.cohorts[self.cohorts.bought & (self.cohorts.strategy!='immediate')]
        self.assertTrue((pd.to_datetime(rows.buy_date)>=pd.to_datetime(rows.start)).all())
        self.assertTrue((pd.to_datetime(rows.signal_date)<pd.to_datetime(rows.buy_date)).all())
        self.assertTrue((pd.to_datetime(rows.buy_date)<=pd.to_datetime(rows.end)).all())
        self.assertTrue((rows.stock_orders==1).all())
        unbought=self.cohorts[~self.cohorts.bought]
        self.assertTrue((unbought.stock_orders==0).all())

    def test_training_outcomes_are_fully_mature_at_selection(self):
        self.assertTrue((pd.to_datetime(self.selections.train_last_end)<pd.to_datetime(self.selections.start)).all())
        self.assertTrue((self.selections.train_n>=12).all())
        for item in self.selections.itertuples():
            dates=pd.to_datetime(self.cohorts.start)
            eligible=self.cohorts[(self.cohorts.horizon==item.horizon)&
                (dates>=pd.Timestamp(item.start)-pd.DateOffset(years=10))&
                (pd.to_datetime(self.cohorts.end)<pd.Timestamp(item.start))]
            ranked=[]
            for name in ('immediate','pe_50','drawdown_20'):
                group=eligible[eligible.strategy==name]
                ranked.append((group.CAGR.mean(),-group.stock_orders_per_year.mean(),name,len(group)))
            self.assertEqual(max(ranked)[2],item.chosen)

    def test_opportunity_cost_matches_simulator(self):
        for row in self.metrics[self.metrics.strategy.isin(['pe_50','drawdown_20'])].itertuples():
            target=pd.Series(False,index=self.stock.index)
            if row.bought: target.loc[pd.Timestamp(row.buy_date):]=True
            m,_,_=bt.simulate(self.stock,self.cash,target,row.start,row.end,ticker='NVDA')
            self.assertAlmostEqual(m['CAGR'],row.CAGR,places=9)
            self.assertAlmostEqual(m['max_drawdown'],row.max_drawdown,places=9)

if __name__=='__main__':unittest.main()
