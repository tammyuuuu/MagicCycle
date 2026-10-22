"""研究引擎验证：信号无未来数据、次日执行及现金机会成本。"""
import unittest

import numpy as np
import pandas as pd

from research_sector_trend import backtest
from research_us_etf_extended import exposure_backtest, entry_backtest, monthly_state


def prices(values):
    index = pd.bdate_range('2020-01-01', periods=len(values))
    return pd.DataFrame({key: values for key in ('open', 'close', 'high', 'low')}, index=index)


class USResearchTests(unittest.TestCase):
    def test_binary_engine_matches_existing_reference(self):
        data = prices(100 + np.sin(np.arange(100) / 10) * 5)
        signal = pd.Series([True] * 20 + [False] * 20 + [True] * 60, index=data.index)
        expected, _, _ = backtest(data, signal, 1, len(data), limit_pct=.10)
        actual, _, _ = exposure_backtest(data, signal.astype(float), 1, len(data))
        self.assertEqual(actual['return_pct'], expected['return_pct'])
        self.assertEqual(actual['max_drawdown_pct'], expected['max_drawdown_pct'])
        self.assertEqual(actual['trades'], expected['trades'])

    def test_monthly_signals_do_not_change_with_future_prices(self):
        close = prices(np.linspace(100, 150, 600)).close
        for cutoff in (250, 300, 450):
            prefix = close.iloc[:cutoff]
            for kwargs in ({}, {'band': .02}, {'confirmations': 2}, {'months': 12}):
                expected = monthly_state(prefix, **kwargs)
                actual = monthly_state(close, **kwargs).iloc[:cutoff]
                pd.testing.assert_series_equal(actual, expected)

    def test_partial_target_can_enter_from_cash_and_only_trades_on_change(self):
        data = prices(np.full(20, 100.))
        target = pd.Series(.5, index=data.index)
        result, curve, trades = exposure_backtest(data, target, 1, len(data))
        self.assertEqual(len(trades), 1)
        self.assertGreater(curve.exposure.iloc[0], .4)
        self.assertLess(curve.exposure.iloc[0], .5)
        self.assertEqual(result['trades'], 1)

    def test_entry_uses_previous_day_and_waiting_keeps_cash(self):
        data = prices(np.linspace(100, 150, 100))
        signal = pd.Series(False, index=data.index)
        result = entry_backtest(data, signal, 1, len(data))
        self.assertEqual(result['return_pct'], 0)
        self.assertTrue(result['never_entered'])
        signal.iloc[4] = True
        result = entry_backtest(data, signal, 1, len(data))
        self.assertEqual(result['wait_days'], (data.index[5] - data.index[1]).days)
        self.assertEqual(result['trades'], 1)

    def test_deadline_and_equal_total_capital_installments(self):
        data = prices(np.full(100, 100.))
        signal = pd.Series(False, index=data.index)
        result = entry_backtest(data, signal, 1, len(data), deadline=63)
        self.assertEqual(result['wait_days'], (data.index[64] - data.index[1]).days)
        result = entry_backtest(data, signal, 1, len(data), installments=True)
        self.assertEqual(result['trades'], 3)
        self.assertLess(result['return_pct'], 0)
        self.assertGreater(result['return_pct'], -1)


if __name__ == '__main__':
    unittest.main()
