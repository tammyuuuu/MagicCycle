import json
from unittest import TestCase, main
from unittest.mock import patch
import numpy as np
import pandas as pd
import app
import strategies
import industry_strategy
from asset_states import display_status, render_guide
from test_asset_strategies import frame


ITEM={'code':'588170','name':'科创半导体ETF华夏','asset_type':'sector_etf'}


class SectorStrategyTests(TestCase):
    def test_partial_exit_and_recovery(self):
        values=[100.]*25+[105.,90.]
        reduced=industry_strategy.analyze_latest(frame(values))
        self.assertEqual(reduced['status'],'reduce')
        self.assertEqual(reduced['target_exposure'],.5)
        exited=industry_strategy.analyze_latest(frame(values+[89.]))
        self.assertEqual(exited['status'],'exit')
        self.assertEqual(exited['target_exposure'],0)
        recovered=industry_strategy.analyze_latest(frame(values+[110.]))
        self.assertEqual(recovered['status'],'buy')
        self.assertIn('买回减掉的部分',recovered['reason'])

    def test_new_entry_then_observe_without_repeated_buy(self):
        values=[100.]*25+[95.,105.]
        first=strategies.analyze_asset(frame(values),ITEM)
        self.assertEqual(first['status'],'buy')
        self.assertTrue(first['details']['fresh_entry'])
        later=strategies.analyze_asset(frame(values+[106.]),ITEM)
        self.assertEqual(later['status'],'watch')
        self.assertFalse(later['details']['fresh_entry'])
        self.assertEqual(later['details']['target_exposure'],1)
        self.assertLessEqual(len(later['decision_basis']),2)

    def test_exit_at_or_below_line_uses_unrounded_values(self):
        values=[100.]*25+[119.,101.]
        same=strategies.analyze_asset(frame(values),ITEM)
        self.assertEqual(same['metrics']['price'],same['metrics']['ma20'])
        self.assertEqual(same['status'],'reduce')
        for delta,expected in [(1e-8,'watch'),(-1e-8,'reduce')]:
            result=strategies.analyze_asset(frame(values[:-1]+[101.+delta]),ITEM)
            self.assertEqual(result['metrics']['price'],result['metrics']['ma20'])
            self.assertEqual(result['status'],expected)
        new=strategies.analyze_asset(frame([100.]*26+[100.+1e-8]),ITEM)
        self.assertEqual(new['status'],'buy')

    def test_no_holding_cost_or_valuation_changes_market_judgment(self):
        data=frame([100.]*25+[95.,105.])
        base=strategies.analyze_asset(data,ITEM)
        for holding in [{'holding':True,'current_return':50,'avg_cost':1,'position_ratio':1},
                        {'holding':True,'current_return':-80,'avg_cost':1000,'position_ratio':0}]:
            candidate=strategies.analyze_asset(data,{**ITEM,'valuation':{'percentile':99}},holding)
            self.assertEqual(candidate['status'],base['status'])
            self.assertEqual(candidate['reason'],base['reason'])
            self.assertEqual(candidate['decision_basis'],base['decision_basis'])
            self.assertEqual(display_status(candidate),'buy')

    def test_insufficient_history_and_first_complete_average(self):
        short=strategies.analyze_asset(frame(np.arange(1,20)),ITEM)
        self.assertEqual(short['status'],'watch')
        self.assertTrue(short['details']['insufficient_history'])
        complete=strategies.analyze_asset(frame(np.arange(1,21)),ITEM)
        self.assertEqual(complete['status'],'buy')
        self.assertFalse(complete['details']['insufficient_history'])
        json.dumps(complete,allow_nan=False)

    def test_live_target_and_backtest_share_all_history_signals(self):
        values=np.r_[np.full(25,100.),95.,105.,106.,90.,np.linspace(80,120,30)]
        data=frame(values)
        targets=industry_strategy.partial_exit_targets(data.close)
        signals=strategies.generate_signals(data,'sector_ma20')
        for end in range(20,len(data)+1):
            report=industry_strategy.analyze_latest(data.iloc[:end])
            self.assertEqual(report['target_exposure'],float(targets.iloc[end-1]))
            self.assertEqual(report['fresh_entry'],bool(signals.iloc[end-1]==1))
            self.assertEqual(report['crossed_down'],bool(signals.iloc[end-1]==-1))

    def test_future_prices_do_not_change_signals(self):
        data=frame(np.linspace(100,120,80))
        original=strategies.generate_signals(data,'sector_ma20')
        changed=data.copy();changed.loc[changed.index[50:],'close']=1
        future=strategies.generate_signals(changed,'sector_ma20')
        pd.testing.assert_series_equal(original.iloc[:50],future.iloc[:50])

    def test_alert_and_decide_endpoints_use_same_conditions(self):
        data=frame([100.]*25+[95.,105.])
        with patch.dict(app._DATA,{'588170':data}),app.app.test_client() as client:
            alert=client.post('/api/alerts',json={'etf':'588170'})
            self.assertEqual(alert.status_code,200)
            summary=alert.json[0]['summary']
            for held in (True,False):
                response=client.post('/api/decide',json={'etf':'588170','holding':held,'current_return':100})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json['summary']['status'],summary['status'])
                self.assertEqual(response.json['decision']['action'],summary['status'])
                self.assertEqual(response.json['summary']['decision_basis'],summary['decision_basis'])
                self.assertIsNone(response.json['decision']['buy_amount'])

    def test_guide_explains_active_and_inactive_decisions(self):
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(render_guide(),'html.parser')
        heading=next(h for h in soup.find_all('h3') if h.get_text()=='行业 ETF · 588170')
        table=heading.find_next('table').get_text()
        self.assertIn('20日均线',table)
        self.assertEqual(table.count('暂不单独触发'),1)
        self.assertNotIn('盈利',table)
        self.assertNotIn('RSI',table)
        self.assertNotIn('回撤至少',table)


if __name__=='__main__':main()
