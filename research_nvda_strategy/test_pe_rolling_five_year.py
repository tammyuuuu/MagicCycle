"""Validate aligned five-year summary and recent comparison windows."""
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT

class RollingFiveYearTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=pd.read_csv(ROOT/'pe_rolling_5y_summary.csv')
        cls.paired=pd.read_csv(ROOT/'pe_rolling_5y_paired.csv')
        cls.recent=pd.read_csv(ROOT/'pe_recent_aligned.csv')
        cls.stock,_,_=bt.load_chart('NVDA');cls.cash,_,_=bt.load_chart('BIL')
        idx=cls.stock.index.intersection(cls.cash.index)
        cls.stock,cls.cash=cls.stock.loc[idx],cls.cash.loc[idx]

    def test_all_windows_share_start_end_and_full_five_year_horizon(self):
        self.assertEqual(len(self.paired),107*6)
        for (start,end),group in self.paired.groupby(['start','end']):
            self.assertEqual(set(group.threshold),{0,30,40,50,60,70})
            a=pd.Timestamp(start);z=pd.Timestamp(end)
            self.assertGreaterEqual(z,a+pd.DateOffset(years=5)-pd.Timedelta(days=7))
            self.assertLess(z,a+pd.DateOffset(years=5))
            self.assertLessEqual(z,pd.Timestamp('2026-11-06'))

    def test_summary_recomputed_and_no_entry_counted(self):
        for s in self.summary.itertuples():
            group=self.paired[self.paired.threshold==s.threshold]
            self.assertEqual(s.n,len(group))
            self.assertEqual(s.entered,int(group.bought.sum()))
            self.assertEqual(s.not_entered,int((~group.bought).sum()))
            self.assertEqual(s.total_stock_entries,int(group.stock_orders.sum()))
            self.assertEqual(s.win,int((group.delta_cagr>1e-10).sum()))
            self.assertEqual(s.loss,int((group.delta_cagr< -1e-10).sum()))
            self.assertEqual(s.tie,s.n-s.win-s.loss)
            self.assertAlmostEqual(s.mean_cagr,group.CAGR.mean(),places=10)
            self.assertAlmostEqual(s.median_drawdown,group.max_drawdown.median(),places=10)
            self.assertAlmostEqual(s.mean_wait_sessions,group.wait_sessions.mean(),places=9)

    def test_unbought_account_is_bil_for_complete_window(self):
        rows=self.paired[(self.paired.threshold>0)&(~self.paired.bought)]
        self.assertGreater(len(rows),0)
        row=rows.iloc[0]
        target=pd.Series(False,index=self.cash.index)
        result,_,_=bt.simulate(self.stock,self.cash,target,row['start'],row['end'],ticker='NVDA')
        self.assertEqual(row.stock_orders,0)
        self.assertAlmostEqual(result['CAGR'],row.CAGR,places=10)
        self.assertAlmostEqual(result['max_drawdown'],row.max_drawdown,places=10)

    def test_recent_periods_are_paired_at_correct_horizons(self):
        endpoint=pd.Timestamp('2026-11-06')
        for years in (1,3,5):
            group=self.recent[self.recent.period==f'{years}y']
            self.assertEqual(len(group),6)
            self.assertEqual(group.start.nunique(),1)
            self.assertEqual(group.end.nunique(),1)
            expected=endpoint-pd.DateOffset(years=years)
            self.assertGreaterEqual(pd.Timestamp(group.start.iloc[0]),expected)
            self.assertEqual(pd.Timestamp(group.end.iloc[0]),endpoint)

if __name__=='__main__':unittest.main()
