"""Checks for fresh-account PE entry, cash decomposition and rolling cutoffs."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT

class PEEntryGridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics=pd.read_csv(ROOT/'pe_entry_grid_metrics.csv')
        cls.cohorts=pd.read_csv(ROOT/'pe_entry_grid_cohorts.csv')
        cls.selections=pd.read_csv(ROOT/'pe_entry_grid_selections.csv')
        cls.oos=pd.read_csv(ROOT/'pe_entry_grid_oos.csv')
        cls.stock,splits,_=bt.load_chart('NVDA');cls.cash,_,_=bt.load_chart('BIL')
        idx=cls.stock.index.intersection(cls.cash.index);idx=idx[idx<=pd.Timestamp('2026-11-06')]
        cls.stock,cls.cash=cls.stock.loc[idx],cls.cash.loc[idx]
        x,_=bt.signals(cls.stock,bt.pit_fundamentals('NVDA',splits))
        cls.rank=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)

    def test_existing_entry_results_unchanged(self):
        old=pd.read_csv(ROOT/'entry_wait_metrics.csv')
        for threshold,name in [(0,'immediate'),(30,'pe_30'),(50,'pe_50'),(70,'pe_70')]:
            for period in ('full','1y','3y','5y'):
                a=self.metrics[(self.metrics.threshold==threshold)&(self.metrics.period==period)].iloc[0]
                b=old[(old.strategy==name)&(old.period==period)].iloc[0]
                for key in ('CAGR','max_drawdown','stock_orders','wait_sessions'):
                    self.assertAlmostEqual(a[key],b[key],places=9)

    def test_every_buy_uses_eligible_prior_month_end(self):
        rows=self.cohorts[(self.cohorts.threshold>0)&(self.cohorts.bought)]
        for row in rows.itertuples():
            signal=pd.Timestamp(row.signal_date);buy=pd.Timestamp(row.buy_date)
            self.assertLess(signal,buy)
            self.assertEqual(self.stock.index[self.stock.index.get_loc(signal)+1],buy)
            self.assertNotEqual(signal.month,buy.month)
            self.assertLessEqual(self.rank.loc[signal],row.threshold/100+1e-12)
            self.assertEqual(row.stock_orders,1)
        self.assertTrue((self.cohorts[~self.cohorts.bought].stock_orders==0).all())

    def test_cash_decomposition_against_bil_and_nav(self):
        for row in self.metrics.itertuples():
            start=pd.Timestamp(row.start);end=pd.Timestamp(row.end)
            if not row.bought:
                factor=self.cash.loc[end,'adjclose']/self.cash.loc[start,'adjopen']
            elif row.wait_sessions:
                factor=self.cash.loc[pd.Timestamp(row.buy_date),'adjopen']/self.cash.loc[start,'adjopen']
            else:factor=1.
            self.assertAlmostEqual(row.bil_multiplier,factor,places=10)
            zero=(row.ending_NAV/factor)**(1/row.years)-1
            self.assertAlmostEqual(row.cash_effect_cagr,row.CAGR-zero,places=10)

    def test_training_cutoff_and_winner(self):
        for item in self.selections.itertuples():
            start=pd.Timestamp(item.start)
            self.assertLess(pd.Timestamp(item.train_last_end),start)
            dates=pd.to_datetime(self.cohorts.start)
            training=self.cohorts[(self.cohorts.horizon==item.horizon)&
                (dates>=start-pd.DateOffset(years=10))&(pd.to_datetime(self.cohorts.end)<start)]
            scores=[]
            for threshold in (30,40,50,60,70):
                group=training[training.threshold==threshold]
                self.assertGreaterEqual(len(group),12)
                scores.append((group.CAGR.mean(),-group.stock_orders_per_year.mean(),-threshold,len(group)))
            self.assertEqual(-max(scores)[2],item.chosen_threshold)
            picked=self.oos[(self.oos.horizon==item.horizon)&(self.oos.start==item.start)&(self.oos.selected)]
            self.assertEqual(len(picked),1)
            self.assertEqual(picked.iloc[0].threshold,item.chosen_threshold)

if __name__=='__main__':unittest.main()
