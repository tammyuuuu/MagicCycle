import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent

class ResearchValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=pd.read_csv(ROOT/'metrics.csv')
        cls.check=pd.read_csv(ROOT/'robustness_metrics.csv')

    def test_recomputed_rules_match_existing_research(self):
        for original,variant in [('trend','trend_200'),('momentum12','momentum_252')]:
            for period in ['full','1y','3y','5y']:
                a=self.original[(self.original.strategy==original)&(self.original.period==period)].iloc[0]
                b=self.check[(self.check.variant==variant)&(self.check.period==period)&(self.check.cost_per_leg==.001)].iloc[0]
                for field in ('CAGR','max_drawdown','stock_orders_per_year'):
                    self.assertAlmostEqual(a[field],b[field],places=10)

    def test_last_sale_counterfactual_preserves_prior_target(self):
        ledger=pd.read_csv(ROOT/'robustness_trades.csv')
        cols=['date','action','asset']
        a=ledger[(ledger.strategy=='momentum_252')&(ledger.date<'2026-11-02')][cols].reset_index(drop=True)
        b=ledger[(ledger.strategy=='momentum_252_without_last_sale')&(ledger.date<'2026-11-02')][cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)
        changed=ledger[(ledger.strategy=='momentum_252')&(ledger.date=='2026-11-02')]
        self.assertEqual(len(changed),2)
        self.assertTrue(ledger[(ledger.strategy=='momentum_252_without_last_sale')&(ledger.date>='2026-11-02')].empty)

if __name__=='__main__': unittest.main()
