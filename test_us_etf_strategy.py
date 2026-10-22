import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import app
import strategies
import valuation_data
from us_guidance import guidance_frame, VERSION
from us_etf_strategy import targets


def prices(values=None, end='2026-09-30'):
    if values is None:
        values = np.linspace(100., 180., 400)
    index = pd.bdate_range(end=end, periods=len(values))
    return pd.DataFrame({key: values for key in ('close', 'open', 'high', 'low')}, index=index)


def append(data, value):
    date = data.index[-1] + pd.offsets.BDay()
    result = data.copy()
    result.loc[date] = [value] * 4
    return result


class USTests(unittest.TestCase):
    item = {'code': '513500', 'name': '标普500', 'asset_type': 'broad_etf', 'strategy_mode': 'us_monthly_trend'}

    def analyze(self, data, holding=None, item=None):
        return strategies.analyze_asset(data, item or self.item, holding=holding)

    def test_regular_buy_is_new_money_permission_and_independent_of_holdings(self):
        data = prices()
        for holding in ({}, {'holding': True, 'current_return': -90}):
            result = self.analyze(data, holding)
            self.assertEqual(result['status'], 'buy')
            self.assertEqual(result['details']['strategy_version'], VERSION)
            self.assertEqual(result['details']['new_money_fraction'], .5)
            self.assertIn('已有持仓不必重复交易', result['reason'])
        data = prices(np.r_[np.linspace(100., 200., 300), np.linspace(100., 110., 100)])
        self.assertEqual(self.analyze(data)['status'], 'exit')

    def test_heat_reduction_once_and_recovery_requires_price_confirmation(self):
        data = prices(np.linspace(100., 120., 400), end='2026-08-31')
        data = append(data, 160.)
        self.assertEqual(self.analyze(data)['status'], 'reduce')
        data = append(data, 160.)
        self.assertEqual(self.analyze(data)['status'], 'watch')
        data = append(data, 122.)
        self.assertLess(guidance_frame(data.close).iloc[-1].deviation60, .05)
        self.assertEqual(self.analyze(data)['status'], 'watch')
        self.assertTrue(self.analyze(data)['details']['heat_active'])
        saw_add = False
        for i in range(25):
            data = append(data, 125. + i * .1)
            if self.analyze(data)['status'] == 'add':
                saw_add = True
                self.assertEqual(self.analyze(data, {'holding': False})['status'], 'add')
                self.assertEqual(self.analyze(data)['details']['new_money_fraction'], 1.)
                self.assertEqual(self.analyze(append(data, 128.))['status'], 'buy')
                break
        self.assertTrue(saw_add)

    def test_partial_month_does_not_change_long_term_direction(self):
        data = prices(end='2026-08-31')
        original = self.analyze(data)
        data = append(data, 50.)
        result = self.analyze(data)
        self.assertEqual(result['details']['signal_date'], '2026-08-31')
        self.assertEqual(result['metrics']['momentum12_pct'], original['metrics']['momentum12_pct'])
        self.assertEqual(result['status'], 'watch')

    def test_missing_month_short_history_and_nonpositive_direction(self):
        self.assertTrue(self.analyze(prices(np.linspace(100, 150, 200)))['details']['insufficient_history'])
        data = prices()
        data = data[data.index.to_period('M') != pd.Period('2026-04')]
        self.assertTrue(self.analyze(data)['details']['insufficient_history'])
        self.assertEqual(self.analyze(prices(np.full(400, 100.)))['status'], 'exit')

    def test_notice_is_dated_and_does_not_hide_sell_signal(self):
        item = {**self.item, 'premium_notice': {'date': '2026-09-30', 'source': 'test'}}
        self.assertEqual(self.analyze(prices(), item=item)['status'], 'watch')
        self.assertEqual(self.analyze(prices(end='2026-08-31'), item=item)['status'], 'buy')
        self.assertEqual(self.analyze(prices(np.full(400, 100.)), item=item)['status'], 'exit')
        data = prices(); data.attrs['stale_note'] = '更新失败'
        self.assertEqual(self.analyze(data)['status'], 'watch')

    def test_full_history_does_not_leak_into_past_signals(self):
        data = prices(np.linspace(100, 150, 700))
        full = guidance_frame(data.close)
        for n in (250, 400, 500, 620):
            expected = guidance_frame(data.close.iloc[:n])
            pd.testing.assert_frame_equal(full.iloc[:n], expected)

    def test_api_and_valuation_separation(self):
        data = prices(end='2026-08-31')
        with patch('app._get_df', return_value=data), patch('valuation_data.get_valuation', side_effect=AssertionError('不读取A股估值')):
            client = app.app.test_client()
            response = client.post('/api/alerts', json={'etf': '513500'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json[0]['summary']['status'], 'buy')
            decision = client.post('/api/decide', json={'etf': '513500'})
            self.assertEqual(decision.json['decision']['action'], 'buy')
            self.assertEqual(client.post('/api/backtest', json={'etf': '513500'}).status_code, 400)

    def test_research_target_matches_live_policy(self):
        from research_us_guidance import candidates
        data = prices(np.r_[np.linspace(100, 120, 400), np.linspace(160, 130, 30)])
        pd.testing.assert_series_equal(candidates(data.close)['12个月方向+15%过热+短期确认'], guidance_frame(data.close).target)


if __name__ == '__main__':
    unittest.main()
