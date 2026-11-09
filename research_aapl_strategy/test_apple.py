"""Timing, accounting and frozen data checks for the Apple study."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT

class AppleStudyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock,cls.splits,_=bt.load_chart('AAPL');cls.cash,_,_=bt.load_chart('BIL')
        idx=cls.stock.index.intersection(cls.cash.index);idx=idx[idx<=pd.Timestamp('2026-11-06')]
        cls.stock,cls.cash=cls.stock.loc[idx],cls.cash.loc[idx]
        cls.f=bt.pit_fundamentals('AAPL',cls.splits)
        cls.x,cls.states=bt.signals(cls.stock,cls.f)
        cls.metrics=pd.read_csv(ROOT/'metrics.csv')

    def test_frozen_hashes(self):
        meta=json.loads((ROOT/'sources.json').read_text(encoding='utf8'))
        for item in meta['files']:
            self.assertEqual(hashlib.sha256((ROOT/'raw'/item['file']).read_bytes()).hexdigest(),item['sha256'])

    def test_pit_and_split_adjustment(self):
        self.assertTrue((self.f.latest_source_filed<self.f.effective).all())
        self.assertIn(('2014-06-09',7),[(str(d.date()),v) for d,v in self.splits])
        self.assertIn(('2020-08-31',4),[(str(d.date()),v) for d,v in self.splits])
        for day in ('2014-06-09','2020-08-31'):
            i=self.x.index.get_loc(day)
            self.assertLess(abs(self.x.PE.iloc[i]/self.x.PE.iloc[i-1]-1),.15)

    def test_future_disclosures_do_not_rewrite_earlier_fundamentals(self):
        source=json.loads((ROOT/'raw'/'AAPL_facts.json').read_text(encoding='utf8'))
        for tag in ('NetIncomeLoss','WeightedAverageNumberOfDilutedSharesOutstanding'):
            for records in source['facts']['us-gaap'][tag]['units'].values():
                for row in records:
                    if row.get('filed','')>='2024-01-01':row['val']*=17
        with patch.object(Path,'read_text',return_value=json.dumps(source)):
            altered=bt.pit_fundamentals('AAPL',self.splits)
        pd.testing.assert_frame_equal(self.f[self.f.effective<'2024-01-01'].reset_index(drop=True),
                                      altered[altered.effective<'2024-01-01'].reset_index(drop=True))

    def test_buyhold_dividends_cost_and_no_buy_cash(self):
        full=self.metrics[(self.metrics.strategy=='buy_hold')&(self.metrics.period=='full')].iloc[0]
        d=self.stock.loc[full.start:full.end]
        self.assertAlmostEqual(full.ending_NAV,.999*d.adjclose.iloc[-1]/d.adjopen.iloc[0],places=9)
        waiting=self.metrics[(self.metrics.strategy=='drawdown_20')&(self.metrics.period=='1y')].iloc[0]
        c=self.cash.loc[waiting.start:waiting.end]
        self.assertEqual(waiting.stock_orders,0)
        self.assertAlmostEqual(waiting.ending_NAV,.999*c.adjclose.iloc[-1]/c.adjopen.iloc[0],places=9)

    def test_rolling_training_uses_matured_outcomes(self):
        d=pd.read_csv(ROOT/'rolling_oos_selection.csv',parse_dates=['start','train_last_end'])
        self.assertTrue((d.train_last_end<d.start).all())
        self.assertTrue((d.train_count>=12).all())

if __name__=='__main__':unittest.main()
