"""Causality and reproducibility checks for saved factor research."""
import sys
import unittest
import json
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT

class FactorStudyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs=pd.read_csv(ROOT/'factor_observations.csv',parse_dates=['signal_date','filed','effective','entry_date'])
        cls.pred=pd.read_csv(ROOT/'factor_oos_observations.csv',parse_dates=['signal_date','train_last_exit','exit_date'])
        cls.prices,_,_=bt.load_chart('NVDA')

    def test_filing_and_growth_information_was_available(self):
        obs=self.obs.dropna(subset=['filed','effective'])
        self.assertTrue((obs.filed<obs.effective).all())
        self.assertTrue((obs.effective<=obs.signal_date).all())
        valid=obs.dropna(subset=['peg','PE','eps_growth'])
        self.assertTrue((valid.eps_growth>0).all())
        np.testing.assert_allclose(valid.peg,valid.PE/(100*valid.eps_growth),rtol=1e-10)

    def test_future_filing_revisions_do_not_change_earlier_snapshots(self):
        _,splits,_=bt.load_chart('NVDA')
        original=bt.pit_fundamentals('NVDA',splits)
        source=json.loads((ROOT/'raw'/'NVDA_facts.json').read_text(encoding='utf8'))
        for tag in ('NetIncomeLoss','WeightedAverageNumberOfDilutedSharesOutstanding'):
            for records in source['facts']['us-gaap'][tag]['units'].values():
                for entry in records:
                    if entry.get('filed','') >= '2024-01-01': entry['val']*=17
        with patch.object(Path,'read_text',return_value=json.dumps(source)):
            modified=bt.pit_fundamentals('NVDA',splits)
        a=original[original.effective<'2024-01-01'].reset_index(drop=True)
        b=modified[modified.effective<'2024-01-01'].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)

    def test_forward_returns_use_later_opens_and_end_before_cutoff(self):
        for horizon in (1,3,6,12):
            col=f'exit_{horizon}m'; ret=f'return_{horizon}m'
            rows=self.obs.dropna(subset=[col,ret]).copy()
            rows[col]=pd.to_datetime(rows[col])
            self.assertTrue((rows.entry_date>rows.signal_date).all())
            self.assertTrue((rows[col]>rows.entry_date).all())
            self.assertTrue((rows[col]<=pd.Timestamp('2026-11-06')).all())
            start=self.prices.loc[rows.entry_date,'adjopen'].to_numpy()
            finish=self.prices.loc[rows[col],'adjopen'].to_numpy()
            np.testing.assert_allclose(rows[ret].to_numpy(),finish/start-1,rtol=1e-10,atol=1e-12)

    def test_training_ends_before_year_and_labels_have_matured(self):
        cutoff=pd.to_datetime(self.pred.year.astype(str)+'-01-01')
        self.assertTrue((self.pred.train_last_exit<cutoff).all())
        self.assertTrue((cutoff<=self.pred.signal_date).all())
        self.assertTrue((self.pred.exit_date>self.pred.signal_date).all())
        self.assertTrue((self.pred.train_n>=36).all())

    def test_walkforward_uses_selected_rule_only_in_its_year(self):
        targets=pd.read_csv(ROOT/'factor_open_targets.csv',parse_dates=['date']).set_index('date')
        selections=pd.read_csv(ROOT/'walkforward_selections.csv')
        for item in selections.itertuples():
            annual=targets[targets.index.year==item.year]
            column='walkforward' if item.mode=='expanding' else 'walkforward_5y'
            self.assertTrue((annual[column]==annual[item.chosen]).all())

    def test_baselines_match_original_research(self):
        a=pd.read_csv(ROOT/'factor_strategy_metrics.csv')
        b=pd.read_csv(ROOT/'metrics.csv')
        for name in ('buy_hold','trend'):
            for period in ('full','1y','3y','5y'):
                left=a[(a.strategy==name)&(a.period==period)].iloc[0]
                right=b[(b.strategy==name)&(b.period==period)].iloc[0]
                for key in ('CAGR','max_drawdown','stock_orders_per_year'):
                    self.assertAlmostEqual(left[key],right[key],places=9)

if __name__=='__main__': unittest.main()
