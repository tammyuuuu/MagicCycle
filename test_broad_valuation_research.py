import unittest

import numpy as np
import pandas as pd

from research_broad_valuation import load, signal_frame, simulate, xirr
from valuation_data import summarize


class BroadResearchTests(unittest.TestCase):
    def synthetic(self, n=8):
        dates = pd.bdate_range('2024-01-02', periods=n)
        prices = pd.DataFrame({c: np.full(n, 10.) for c in ('open', 'close', 'high', 'low')}, index=dates)
        frame = pd.DataFrame({'percentile': 20., 'status': 'buy', 'ready': True}, index=dates)
        return prices, frame

    def test_next_open_and_one_reduction_per_high_episode(self):
        prices, frame = self.synthetic()
        frame['status'] = ['buy', 'add', 'reduce', 'reduce', 'reduce', 'exit', 'watch', 'watch']
        frame['percentile'] = [20, 20, 80, 80, 80, 95, 50, 50]
        result, curve, trades = simulate(prices, frame, 1, slippage=0, minimum_fee=0)
        self.assertEqual([t['action'] for t in trades], ['买入', '加仓', '减仓', '退出'])
        self.assertEqual(result['reductions'], 1)
        self.assertEqual(trades[0]['date'], str(prices.index[1].date()))
        self.assertEqual(trades[0]['signal_date'], str(prices.index[0].date()))
        self.assertEqual(curve.quantity.iloc[-1], 0)
        self.assertAlmostEqual(curve.equity.iloc[-1], 100000 - sum(t['fee'] for t in trades))

    def test_limit_retry_and_fees(self):
        prices, frame = self.synthetic()
        prices.loc[prices.index[1], ['open', 'close', 'high', 'low']] = 11.
        result, curve, trades = simulate(prices, frame, 1)
        self.assertEqual(curve.quantity.iloc[0], 0)
        self.assertEqual(trades[0]['date'], str(prices.index[2].date()))
        self.assertTrue(all(t['fee'] >= 5 for t in trades))
        self.assertTrue((curve.cash >= 0).all())

    def test_cash_only_monthly_has_no_artificial_return(self):
        prices, frame = self.synthetic(90)
        frame['status'] = 'watch'
        result, curve, trades = simulate(prices, frame, 1, funding='monthly')
        self.assertEqual(result['nav_return_pct'], 0)
        self.assertEqual(result['max_drawdown_pct'], 0)
        self.assertEqual(result['profit_yuan'], 0)
        self.assertGreater(result['principal_yuan'], 1000)
        self.assertEqual(trades, [])
        self.assertTrue((curve.nav == 1).all())

    def test_monthly_deposits_do_not_mask_drawdown(self):
        prices, frame = self.synthetic(90)
        prices.iloc[22:, prices.columns.get_indexer(['open','close','high','low'])] = 5.
        result, curve, trades = simulate(prices, frame, 1, funding='monthly', mode='hold',
                                         monthly=10000, slippage=0, minimum_fee=0)
        self.assertLess(result['max_drawdown_pct'], -45)
        self.assertEqual(result['principal_yuan'], 50000)
        self.assertEqual(len(trades), 5)

    def test_history_prefix_and_staleness(self):
        prices, history, _ = load('510300', '000300')
        full = signal_frame(prices, history)
        truncated = prices.loc[:'2018-12-28']
        past = signal_frame(truncated, history[history.date <= truncated.index[-1]])
        pd.testing.assert_frame_equal(full.loc[past.index], past)
        missing = history[(history.date < '2018-06-01') | (history.date > '2018-09-01')]
        gap = signal_frame(prices, missing, lag=0)
        self.assertFalse(gap.loc['2018-07-20', 'ready'])
        self.assertEqual(gap.loc['2018-07-20', 'status'], 'watch')

    def test_signal_matches_live_rules(self):
        from strategies import analyze_asset
        for code,index,name in [('510300','000300','沪深300'),('510500','000905','中证500'),('588000','000688','科创50')]:
            prices, history, _ = load(code, index)
            for years in (3, 5, 10):
                frame = signal_frame(prices, history, years, lag=0)
                for date in ['2015-06-30','2018-12-28','2021-03-31','2026-09-30']:
                    past = prices.loc[:date]
                    if len(past) < 250:
                        continue
                    actual = analyze_asset(past, {'code':code,'name':name,'asset_type':'broad_etf',
                                                  'valuation':summarize(history, past.index[-1], years)})
                    expected = frame.loc[past.index[-1], 'status']
                    self.assertEqual({'buy_more':'add'}.get(actual['status'], actual['status']), expected)

    def test_valuation_delay_and_short_history(self):
        prices, history, _ = load('588000', '000688')
        self.assertFalse(signal_frame(prices, history, 10).ready.any())
        earlier = signal_frame(prices, history, 5, lag=0)
        delayed = signal_frame(prices, history, 5, lag=1)
        pd.testing.assert_series_equal(earlier.percentile.shift(1), delayed.percentile)

    def test_xirr_known_cash_flow(self):
        self.assertEqual(xirr([('2023-01-01', -1000), ('2024-01-01', 1100)]), 10.01)


if __name__ == '__main__':
    unittest.main()
