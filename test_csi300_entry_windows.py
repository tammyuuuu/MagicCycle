import unittest
import pandas as pd

from research_csi300_entry_windows import windows, aggregate
from broad_signal_rules import valuation_positions


class EntryWindowTests(unittest.TestCase):
    def test_complete_horizons_and_previous_signal(self):
        index = pd.bdate_range('2020-01-01', '2022-06-30')
        prices = pd.DataFrame(index=index)
        ready = pd.Series(True, index=index)
        ready.iloc[:30] = False
        result = windows(prices, ready, 1)
        self.assertTrue(result)
        self.assertEqual(result[0][0], 31)
        for start, end in result:
            anniversary = index[start] + pd.DateOffset(years=1)
            self.assertLessEqual(anniversary, index[-1])
            self.assertLessEqual(index[end-1], anniversary)
            if end < len(index):
                self.assertGreater(index[end], anniversary)

    def test_joint_improvement_excludes_ties(self):
        def stat(profit, dd):
            return {'profit_on_contributions_pct': profit, 'max_drawdown_pct': dd}
        rows = [{'models': {'a': stat(p,d), 'b': stat(10,-20)}}
                for p,d in [(10,-10),(11,-20),(11,-10),(9,-10)]]
        result = aggregate(rows, 'a', 'b')
        self.assertEqual(result['joint_win_pct'], 25.)
        self.assertEqual(result['return_win_pct'], 50.)

    def test_market_permission_has_no_future_input(self):
        index = pd.bdate_range('2020-01-01', periods=150)
        close = pd.Series(range(100,250), index=index, dtype=float)
        pct = pd.Series(20., index=index)
        pct.iloc[80:] = 95.
        full = valuation_positions(pct, close, confirm_exit=True)
        prefix = valuation_positions(pct.iloc[:100], close.iloc[:100], confirm_exit=True)
        pd.testing.assert_series_equal(full.iloc[:100], prefix)


if __name__ == '__main__':
    unittest.main()
