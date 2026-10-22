import unittest

import numpy as np
import pandas as pd

from research_broad_individual import candidate_rules, choose_training, dominates, execute, secondary_sector_rules
from research_broad_valuation import load, simulate, signal_frame
from research_sector_trend import backtest


class IndividualResearchTests(unittest.TestCase):
    def test_binary_engine_matches_existing_reference(self):
        prices, history, _ = load('588000', '000688')
        target = (prices.close > prices.close.rolling(20).mean()).astype(float)
        current, _, trades = execute(prices, target, 250)
        reference = backtest(prices, target.eq(1), 250, len(prices), limit_pct=.20)[0]
        for key in ('return_pct', 'max_drawdown_pct', 'trades'):
            self.assertEqual(current[key], reference[key])
        self.assertTrue(all(t['signal_date'] < t['date'] for t in trades))

    def test_hold_and_monthly_match_original_funding_engine(self):
        prices, history, _ = load('510300', '000300')
        frame = signal_frame(prices, history)
        target = pd.Series(1., index=prices.index)
        for monthly in (None, 1000.):
            stats, curve, trades = execute(prices, target, 250, monthly=monthly)
            funding = 'fixed' if monthly is None else 'monthly'
            old, previous, _ = simulate(prices, frame, 250, mode='hold', funding=funding)
            self.assertEqual(stats['return_pct'], old['nav_return_pct'])
            self.assertEqual(stats['max_drawdown_pct'], old['max_drawdown_pct'])
            np.testing.assert_allclose(curve.equity, previous.equity)

    def test_all_rules_use_only_available_history(self):
        for code, index in [('510300','000300'),('588000','000688')]:
            prices, history, _ = load(code, index)
            end = int(len(prices)*.8)
            past = prices.iloc[:end]
            earlier_history = history[history.date <= past.index[-1]]
            full, _ = candidate_rules(prices, history, code)
            earlier, _ = candidate_rules(past, earlier_history, code)
            for key in full:
                pd.testing.assert_series_equal(full[key].loc[past.index], earlier[key])
        prices, history, _ = load('510500', '000905')
        past = prices.iloc[:2000]
        full, _ = secondary_sector_rules(prices, history)
        earlier, _ = secondary_sector_rules(past, history[history.date<=past.index[-1]])
        for key in full:
            pd.testing.assert_series_equal(full[key].loc[past.index], earlier[key])

    def test_selection_and_strict_two_objectives(self):
        baseline = {'return_pct': 10., 'max_drawdown_pct': -20.}
        self.assertFalse(dominates({'return_pct':10.,'max_drawdown_pct':-10.},baseline))
        self.assertFalse(dominates({'return_pct':20.,'max_drawdown_pct':-20.},baseline))
        self.assertIsNone(choose_training({'bad':{'return_pct':5.,'max_drawdown_pct':-10.,'calmar':1.}},baseline))
        training = {'a':{'return_pct':12.,'max_drawdown_pct':-10.,'calmar':1.2},
                    'b':{'return_pct':15.,'max_drawdown_pct':-15.,'calmar':1.}}
        self.assertEqual(choose_training(training,baseline),'a')

    def test_no_signal_holds_cash_and_deposits_preserve_nav(self):
        prices, _, _ = load('510300','000300')
        target = pd.Series(0.,index=prices.index)
        stats, curve, trades = execute(prices,target,250,end=400,monthly=1000)
        self.assertEqual(stats['return_pct'],0)
        self.assertEqual(stats['max_drawdown_pct'],0)
        self.assertEqual(trades,[])
        self.assertGreater(stats['principal_yuan'],1000)
        self.assertTrue((curve.nav==1).all())

    def test_invalid_targets_and_lot_sizes(self):
        prices, _, _ = load('510300','000300')
        with self.assertRaises(ValueError):
            execute(prices,pd.Series(.5,index=prices.index),250)
        stats, curve, trades = execute(prices,pd.Series(1.,index=prices.index),250,initial=1000)
        self.assertTrue((curve.cash>=0).all())
        self.assertTrue((curve.quantity%100==0).all())
        self.assertTrue(all(t['fee']>=5 for t in trades))


if __name__ == '__main__':
    unittest.main()
