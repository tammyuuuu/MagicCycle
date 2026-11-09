"""Independent checks of daily signals, costs, cohorts and rolling cutoffs."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT

class DrawdownEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock,_,_=bt.load_chart('AAPL');cls.cash,_,_=bt.load_chart('BIL')
        idx=cls.stock.index.intersection(cls.cash.index);idx=idx[idx<=pd.Timestamp('2026-11-06')]
        cls.stock,cls.cash=cls.stock.loc[idx],cls.cash.loc[idx]
        cls.dd=1-cls.stock.close/cls.stock.close.rolling(252,min_periods=252).max()
        cls.recent=pd.read_csv(ROOT/'drawdown_entry_recent.csv')
        cls.paired=pd.read_csv(ROOT/'drawdown_entry_5y_cohorts.csv')
        cls.summary=pd.read_csv(ROOT/'drawdown_entry_5y_summary.csv')

    def test_daily_threshold_signals_and_next_open(self):
        rows=self.paired[(self.paired.threshold>0)&self.paired.bought]
        for row in rows.itertuples():
            signal=pd.Timestamp(row.signal_date);entry=pd.Timestamp(row.buy_date)
            self.assertEqual(self.stock.index[self.stock.index.get_loc(signal)+1],entry)
            self.assertGreaterEqual(self.dd.loc[signal]+1e-12,row.threshold/100)
            self.assertAlmostEqual(row.signal_drawdown,self.dd.loc[signal],places=10)
            self.assertGreaterEqual(entry,pd.Timestamp(row.start))
            self.assertLessEqual(entry,pd.Timestamp(row.end))
            start_pos=self.stock.index.get_loc(pd.Timestamp(row.start))
            signal_pos=self.stock.index.get_loc(signal)
            earlier=self.dd.iloc[max(0,start_pos-1):signal_pos]
            self.assertFalse((earlier>=row.threshold/100).any())
            self.assertEqual(row.stock_orders,1)
        self.assertTrue((self.paired[~self.paired.bought].stock_orders==0).all())

    def test_immediate_baseline_matches_prior_research(self):
        baseline=pd.read_csv(ROOT/'metrics.csv')
        for period in ('1y','3y','5y'):
            a=self.recent[(self.recent.period==period)&(self.recent.threshold==0)].iloc[0]
            b=baseline[(baseline.period==period)&(baseline.strategy=='buy_hold')].iloc[0]
            for key in ('CAGR','max_drawdown','stock_orders_per_year'):
                self.assertAlmostEqual(a[key],b[key],places=9)

    def test_five_year_windows_are_paired_and_complete(self):
        self.assertEqual(len(self.paired),107*6)
        for (a,z),group in self.paired.groupby(['start','end']):
            self.assertEqual(set(group.threshold),{0,10,15,20,25,30})
            start=pd.Timestamp(a);finish=pd.Timestamp(z)
            self.assertGreaterEqual(finish,start+pd.DateOffset(years=5)-pd.Timedelta(days=7))
            self.assertLess(finish,start+pd.DateOffset(years=5))

    def test_summary_wins_and_no_entry_accounting(self):
        for s in self.summary.itertuples():
            rows=self.paired[self.paired.threshold==s.threshold]
            self.assertEqual(s.n,len(rows))
            self.assertEqual(s.bought,int(rows.bought.sum()))
            self.assertEqual(s.not_bought,int((~rows.bought).sum()))
            self.assertEqual(s.win,int((rows.delta_cagr>1e-10).sum()))
            self.assertEqual(s.loss,int((rows.delta_cagr< -1e-10).sum()))
            self.assertEqual(s.tie,s.n-s.win-s.loss)
            self.assertAlmostEqual(s.median_cagr,rows.CAGR.median(),places=10)
            self.assertAlmostEqual(s.mean_wait_sessions,rows.wait_sessions.mean(),places=9)

    def test_bil_cash_multiplier_and_zero_return_attribution(self):
        for row in self.recent.itertuples():
            start=pd.Timestamp(row.start);finish=pd.Timestamp(row.end)
            if not row.bought:factor=self.cash.loc[finish,'adjclose']/self.cash.loc[start,'adjopen']
            elif row.wait_sessions:factor=self.cash.loc[pd.Timestamp(row.buy_date),'adjopen']/self.cash.loc[start,'adjopen']
            else:factor=1.
            self.assertAlmostEqual(row.bil_multiplier,factor,places=10)
            self.assertAlmostEqual(row.cash_effect_cagr,row.CAGR-(row.ending_NAV/factor)**(1/row.years)+1,places=10)
            if not row.bought:
                expected=.999*self.cash.loc[finish,'adjclose']/self.cash.loc[start,'adjopen']
                self.assertAlmostEqual(row.ending_NAV,expected,places=10)

    def test_rolling_training_only_matured_five_year_cohorts(self):
        selected=pd.read_csv(ROOT/'drawdown_entry_oos_selections.csv')
        for item in selected.itertuples():
            start=pd.Timestamp(item.start)
            self.assertLess(pd.Timestamp(item.train_last_end),start)
            train=self.paired[(pd.to_datetime(self.paired.start)>=start-pd.DateOffset(years=10))&
                              (pd.to_datetime(self.paired.end)<start)]
            scores=[]
            for t in (10,15,20,25,30):
                z=train[train.threshold==t];self.assertGreaterEqual(len(z),12)
                scores.append((z.CAGR.mean(),-z.stock_orders_per_year.mean(),-t,len(z)))
            self.assertEqual(-max(scores)[2],item.chosen_threshold)

if __name__=='__main__':unittest.main()
