import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import app
import strategies
import gold_strategy
from research_gold_heat import heat_targets
from test_asset_strategies import frame
from asset_states import display_status, render_guide

ITEM={'code':'518850','name':'华夏黄金ETF','asset_type':'macro_asset','subtype':'gold'}


class GoldStrategyTests(unittest.TestCase):
    def test_reduce_once_then_restore(self):
        values=[100.]*130+[130.]
        reduced=strategies.analyze_asset(frame(values),ITEM)
        self.assertEqual(reduced['status'],'reduce')
        self.assertEqual(reduced['details']['heat_phase'],True)
        self.assertEqual(len(reduced['decision_basis']),2)
        later=strategies.analyze_asset(frame(values+[131.]),ITEM)
        self.assertEqual(later['status'],'watch')
        for n in range(1,81):
            r=strategies.analyze_asset(frame(values+[131.]*n),ITEM)
            if r['details']['fresh_add']:
                self.assertEqual(r['status'],'add')
                self.assertIn('买回',r['reason'])
                held=strategies.analyze_asset(frame(values+[131.]*n),ITEM,{'holding':True,'current_return':-50})
                self.assertEqual(held['decision_basis'],r['decision_basis'])
                self.assertEqual(display_status(held),'buy')
                self.assertNotIn('target_exposure',r['details'])
                self.assertEqual(strategies.analyze_asset(frame(values+[131.]*(n+1)),ITEM)['status'],'watch')
                break
        else:self.fail('未冷却加仓')

    def test_holding_and_profit_do_not_change_conditions(self):
        for values in ([100.]*130+[130.],[100.]*130+[90.]):
            base=strategies.analyze_asset(frame(values),ITEM)
            for h in ({'holding':True,'current_return':-80},{'holding':True,'current_return':80}):
                held=strategies.analyze_asset(frame(values),ITEM,h)
                self.assertEqual(held['status'],base['status'])
                self.assertEqual(held['decision_basis'],base['decision_basis'])
                self.assertEqual(display_status(held),display_status(base))

    def test_warmup_and_initial_buy(self):
        self.assertEqual(strategies.analyze_asset(frame([100.]*119),ITEM)['status'],'watch')
        self.assertEqual(strategies.analyze_asset(frame([100.]*120),ITEM)['status'],'buy')
        self.assertEqual(strategies.analyze_asset(frame([100.]*121),ITEM)['status'],'watch')

    def test_live_and_research_all_stages_match(self):
        values=np.r_[np.full(130,100.),130.,131.,np.full(90,131.),100.,160.]
        data=frame(values)
        expected=heat_targets(data.close,use_trend=False,exit_on_weak=False)
        pd.testing.assert_series_equal(gold_strategy.stages(data.close).target,expected)
        for end in range(120,len(data)+1):
            result=gold_strategy.analyze_latest(data.iloc[:end])
            self.assertEqual(result['heat_phase'],expected.iloc[end-1]==.5)

    def test_unrounded_threshold(self):
        data=frame([100.]*130+[130.])
        boundary=gold_strategy.stages(data.close).deviation.iloc[-1]
        self.assertEqual(gold_strategy.analyze_latest(data,{'heat_threshold':boundary-1e-10})['status'],'reduce')
        self.assertEqual(gold_strategy.analyze_latest(data,{'heat_threshold':boundary+1e-10})['status'],'watch')

    def test_gold_two_node_rail_and_waiting(self):
        from bs4 import BeautifulSoup
        from asset_states import render_rail
        for values,expected in [([100.]*130,'buy'),([100.]*130+[130.],'reduce'),([100.]*130+[130.,131.],'reduce')]:
            summary=strategies.analyze_asset(frame(values),ITEM)
            soup=BeautifulSoup(render_rail(summary),'html.parser')
            self.assertEqual(len(soup.select('.state-step')),2)
            self.assertEqual(display_status(summary),expected)
            self.assertIn('买入／持有',soup.get_text())
            self.assertNotIn('预算',soup.get_text())
            if len(values)==132:self.assertIn('等待冷却，暂不买回',soup.get_text())

    def test_api_consistency(self):
        with patch.dict(app._DATA,{'518850':frame([100.]*130+[130.])}),app.app.test_client() as client:
            alerts=client.post('/api/alerts',json={'etf':'518850'}).json[0]['summary']
            decision=client.post('/api/decide',json={'etf':'518850','holding':True,'current_return':-80}).json
            self.assertEqual(decision['summary']['status'],'reduce')
            self.assertEqual(alerts['decision_basis'],decision['summary']['decision_basis'])
            self.assertEqual(decision['decision']['action'],'reduce')

    def test_guide_only_current_conditions(self):
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(render_guide(),'html.parser')
        heading=next(h for h in soup.find_all('h3') if h.get_text()=='黄金 ETF')
        text=heading.find_next('table').get_text()
        self.assertIn('15%',text)
        self.assertIn('5%',text)
        self.assertNotIn('RSI',text)
        self.assertNotIn('盈利',text)
        self.assertIn('买回',text)
        self.assertNotIn('预算',text)


if __name__=='__main__':unittest.main()
