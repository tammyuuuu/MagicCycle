import unittest
import pandas as pd
from valuation_data import normalize_history, summarize


class ValuationTests(unittest.TestCase):
    def history(self):
        return pd.DataFrame({'date': pd.date_range('2021-09-30', periods=61, freq='ME'),
                             'pe': list(range(10, 71))})

    def test_holiday_keeps_last_month_end(self):
        result = summarize(self.history(), '2026-10-03')
        self.assertEqual(result['date'], '2026-09-30')
        self.assertIsNotNone(result['percentile'])
        self.assertEqual(result['percentile'], summarize(self.history(), '2026-09-30')['percentile'])

    def test_future_data_excluded(self):
        history = self.history()
        before = summarize(history, '2026-09-30')
        history.loc[len(history)] = [pd.Timestamp('2026-10-31'), 1000]
        self.assertEqual(before, summarize(history, '2026-09-30'))

    def test_intramonth_updates_count_once_and_preserve_past(self):
        history = self.history()
        history.loc[len(history)] = [pd.Timestamp('2026-10-14'), 40]
        before = summarize(history, '2026-10-14')
        history.loc[len(history)] = [pd.Timestamp('2026-10-20'), 45]
        self.assertEqual(before, summarize(history, '2026-10-14'))
        latest = summarize(history, '2026-10-20')
        self.assertEqual(latest['samples'], before['samples'])
        self.assertEqual(latest['value'], 45)
        self.assertEqual(latest['date'], '2026-10-20')

    def test_signal_replays_intramonth_updates_without_future_data(self):
        from broad_signal_rules import signal_frame
        history = self.history()
        history.loc[len(history)] = [pd.Timestamp('2026-10-14'), 40]
        prices = pd.DataFrame({'close': 100.}, index=pd.bdate_range('2025-01-01', '2026-10-20'))
        before = signal_frame(prices, history)
        history.loc[len(history)] = [pd.Timestamp('2026-10-20'), 45]
        after = signal_frame(prices, history)
        pd.testing.assert_frame_equal(before, after)  # 当天更新仍延迟一个交易日

    def test_expired_and_short_history(self):
        self.assertIsNone(summarize(self.history(), '2026-11-10')['percentile'])
        self.assertIsNone(summarize(self.history().tail(12), '2026-09-30')['percentile'])

    def test_flat_valuations_are_neutral(self):
        history = self.history()
        history['pe'] = 20
        self.assertEqual(summarize(history, '2026-09-30')['percentile'], 50)

    def test_selected_window_needs_enough_history(self):
        self.assertIsNotNone(summarize(self.history(), '2026-09-30', 3)['percentile'])
        self.assertIsNone(summarize(self.history(), '2026-09-30', 10)['percentile'])
        with self.assertRaises(ValueError):
            summarize(self.history(), '2026-09-30', 7)

    def test_invalid_values_and_duplicate_dates(self):
        history = normalize_history([{'date':'2026-09-30','ttmPe':20},
                                     {'date':'2026-09-30','ttmPe':21},
                                     {'date':'bad','ttmPe':22},
                                     {'date':'2026-08-31','ttmPe':-1}])
        self.assertEqual(len(history), 1)
        self.assertEqual(history.iloc[0].pe, 21)


if __name__ == '__main__':
    unittest.main()
