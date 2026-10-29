import json
import unittest
from unittest.mock import patch
from datetime import date
import pandas as pd
import numpy as np
from research_bond_entry import ROOT, OUT, NAV, features, study
from bond_monitor import render_bond_monitor


class BondEntryTests(unittest.TestCase):
    def test_data_status_does_not_change_strategy(self):
        stale = render_bond_monitor(today=date(2030, 1, 1))
        self.assertIn('数据待更新', stale)
        with patch('bond_monitor.json.loads', return_value={}):
            missing = render_bond_monitor()
        for card in (stale, missing):
            self.assertEqual(card.count('class="state-step'), 1)
            self.assertIn('买入／持有', card)
            self.assertNotIn('买入环境', card)

    @classmethod
    def setUpClass(cls):
        cls.nav = pd.read_csv(NAV, parse_dates=['date']).set_index('date')
        raw = pd.DataFrame(json.loads((OUT/'treasury_history.json').read_text(encoding='utf8')))
        cls.rates = raw.rename(columns={'SOLAR_DATE':'date','EMM00166466':'y10'})[['date','y10']]
        cls.rates.date = pd.to_datetime(cls.rates.date)
        cls.rates = cls.rates.dropna().drop_duplicates('date').set_index('date')

    def test_future_changes_do_not_change_past_features(self):
        cutoff = pd.Timestamp('2020-06-30')
        a = features(self.nav, self.rates)
        nav, rates = self.nav.copy(), self.rates.copy()
        nav.loc[nav.index > cutoff, 'nav'] *= 2
        rates.loc[rates.index > cutoff, 'y10'] += 5
        b = features(nav, rates)
        pd.testing.assert_frame_equal(a.loc[:cutoff], b.loc[:cutoff])

    def test_missing_rates_never_generate_environment(self):
        a = features(self.nav, self.rates.iloc[:20])
        self.assertTrue((a.environment == '数据不足').all())

    def test_execution_and_maturity(self):
        a = features(self.nav, self.rates)
        s = study(a)
        self.assertTrue((pd.to_datetime(s.entry) > pd.to_datetime(s.decision)).all())
        self.assertTrue((pd.to_datetime(s.end) <= self.nav.index[-1]).all())
        self.assertTrue((s.mdd_pct <= 0).all())
        self.assertTrue((a.dropna(subset=['rate_date']).rate_date < a.dropna(subset=['rate_date']).index).all())
        good = s[s.environment == '较好']
        np.testing.assert_allclose(good.wait_excess_pct, 0, atol=1e-10)

    def test_dividend_reconstruction_matches_existing_total_return(self):
        a = features(self.nav, self.rates)
        np.testing.assert_allclose(a.wealth, self.nav.tr, atol=2e-5)

    def test_card_and_formal_export(self):
        card = render_bond_monitor()
        page = (ROOT/'docs/index.html').read_text(encoding='utf8')
        self.assertNotIn('综合判断：数据不足', card)
        self.assertNotIn('买入环境偏差', card)
        self.assertIn('买入／持有', card)
        self.assertEqual(card.count('class="state-step'), 1)
        self.assertIn('class="current-reason"', card)
        self.assertIn('<summary>查看判断依据</summary>', card)
        self.assertIn('长期持有是当前主要策略', card)
        self.assertIn(card, page)
        self.assertIn('today-category-bond', page)


if __name__ == '__main__':
    unittest.main()
