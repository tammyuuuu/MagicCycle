import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import strategies
from broad_individual_strategy import individual_frame
from broad_signal_rules import valuation_positions
from research_broad_individual import candidate_rules, secondary_sector_rules
from research_broad_valuation import load
from valuation_data import attach_valuation


class IndividualStrategyTests(unittest.TestCase):
    def test_csi500_entry_ceiling_and_persistent_permission(self):
        from broad_signal_rules import low_value_or_trend
        index=pd.bdate_range('2020-01-01',periods=8)
        close=pd.Series([100.,100.,100.,110.,120.,130.,90.,80.],index=index)
        pct=pd.Series([60.,60.,60.,60.,59.,65.,30.,29.],index=index)
        permission=low_value_or_trend(close,pct,3,ceiling=60)
        self.assertEqual(permission.iloc[3],0.) # 等于60%不允许趋势入场
        self.assertEqual(permission.iloc[4],1.)
        self.assertEqual(permission.iloc[5],1.) # 入场后升到60%以上不单独卖出
        self.assertEqual(permission.iloc[6],0.)
        self.assertEqual(permission.iloc[7],1.) # 低估仍可直接进入
        prices,history,_=load('510500','000905')
        s=strategies.analyze_asset(prices,self.item('510500',history))
        self.assertEqual(s['details']['strategy_version'],'csi500_value_trend_v2')
        self.assertEqual(s['details']['parameters']['trend_entry_ceiling'],60)

    def test_csi300_confirmation_and_permission_persistence(self):
        index=pd.bdate_range('2020-01-01',periods=100)
        close=pd.Series([100.]*80+[90.]*5+[110.]*5+[80.]*10,index=index)
        pct=pd.Series(20.,index=index)
        pct.iloc[90:]=50.
        position=valuation_positions(pct,close,confirm_exit=True,entry_ma=60,exit_ma=80)
        self.assertEqual(position.iloc[84],0.)
        self.assertEqual(position.iloc[85],1.)
        self.assertEqual(position.iloc[95],1.) # 离开低估、跌回线下不独自触发退出
        pct.iloc[96:]=95.
        exited=valuation_positions(pct,close,confirm_exit=True,entry_ma=60,exit_ma=80)
        self.assertEqual(exited.iloc[96],0.)

    def item(self, code, history):
        return {**next(i for i in config.TARGET_ETFS if i['code']==code),
                'valuation_history':history.assign(date=history.date.dt.strftime('%Y-%m-%d')).to_dict('records')}

    def test_live_frames_equal_researched_candidates(self):
        for code,index,key in [('510300','000300','pe5_confirmed_exit'),('510500','000905','low_value_or_trend120'),('588000','000688','ma20')]:
            prices, history, _ = load(code,index)
            item = self.item(code,history)
            rules,_ = candidate_rules(prices,history,code)
            if code=='510300':
                from broad_signal_rules import signal_frame
                rules[key]=valuation_positions(signal_frame(prices,history,5).percentile,prices.close,
                                                confirm_exit=True,entry_ma=60,exit_ma=80)
            if code=='588000':
                from research_star50_search import confirmed_ma
                rules[key]=confirmed_ma(prices.close,16,buffer=.02)
            if code=='510500':
                from broad_signal_rules import low_value_or_trend,signal_frame
                rules[key]=low_value_or_trend(prices.close,signal_frame(prices,history,5).percentile,120,ceiling=60)
            actual=individual_frame(prices,history,item['broad_strategy'])
            pd.testing.assert_series_equal(actual.position,rules[key],check_names=False)
            for n in (int(len(prices)*.6),len(prices)):
                past=prices.iloc[:n]
                summary=strategies.analyze_asset(past,item)
                row=actual.iloc[n-1]
                if row.ready and row.position:
                    self.assertEqual(summary['status'],'buy')
                self.assertEqual(summary['details']['strategy_version'],'csi300_value_confirm_v2' if code=='510300' else 'csi500_value_trend_v2' if code=='510500' else 'star50_buffer_v2')
                self.assertEqual(summary['details']['enabled_decisions'],['buy','watch','exit'])

    def test_holding_and_old_overrides_do_not_change_new_decisions(self):
        prices,history,_=load('510300','000300');item=self.item('510300',history)
        empty=strategies.analyze_asset(prices,item)
        held=strategies.analyze_asset(prices,item,holding={'holding':True,'avg_cost':.1,'return_rate':900,'position_ratio':1},
                                     overrides={'drawdown_medium':0,'drawdown_large':0,'p_low':99,'valuation_exit_percentile':0})
        for key in ('status','reason','decision_basis'):
            self.assertEqual(empty[key],held[key])

    def test_year_options_replay_history_and_no_future(self):
        prices,history,_=load('510300','000300');item=self.item('510300',history)
        past=prices.loc[:'2020-06-30']
        summary=strategies.analyze_asset(past,item)
        earlier=history[history.date<=past.index[-1]]
        other=strategies.analyze_asset(past,self.item('510300',earlier))
        self.assertEqual(summary['details']['strategy_options'],other['details']['strategy_options'])
        for years in (3,5,10):
            option=summary['details']['strategy_options'][str(years)]
            row=individual_frame(past,earlier,item['broad_strategy'],years).iloc[-1]
            self.assertEqual(option['valuation_percentile'],float(row.percentile))
            self.assertLess(option['valuation']['date'],summary['date'])

    def test_no_valuation_calls_for_kechuang_and_bad_data_observe(self):
        prices,history,_=load('588000','000688');item=self.item('588000',history)
        with patch('valuation_data.get_valuation',side_effect=AssertionError('不应取得PE')):
            attached=attach_valuation(item,prices.index[-1].date().isoformat())
        self.assertEqual(attached,item)
        short=strategies.analyze_asset(prices.head(3),item)
        self.assertEqual(short['status'],'watch')
        self.assertTrue(short['details']['insufficient_history'])
        self.assertEqual(strategies.analyze_asset(prices,{**item,'valuation_history':[]})['status'],strategies.analyze_asset(prices,item)['status'])
        prices.attrs['stale_note']='更新失败'
        self.assertEqual(strategies.analyze_asset(prices,item)['status'],'watch')

    def test_estimation_missing_does_not_fallback_to_old_strategy(self):
        prices,history,_=load('510500','000905');item=self.item('510500',history)
        s=strategies.analyze_asset(prices,{**item,'valuation_history':[]})
        self.assertEqual(s['status'],'watch')
        self.assertTrue(s['details']['insufficient_history'])
        self.assertIsNone(s['details']['legacy'])

    def test_api_and_guides_use_individual_strategy(self):
        import app
        from asset_states import render_guide,render_rail,STATE_CATALOG
        from bs4 import BeautifulSoup
        code='510300';prices,history,_=load(code,'000300');item=self.item(code,history)
        with app.app.test_client() as client,patch.object(app,'_load_data',return_value=(prices,item)),patch.object(app,'_get_df',return_value=prices),patch('valuation_data.attach_valuation',side_effect=lambda item,date:item):
            response=client.post('/api/decide',json={'etf':code,'holding':True})
            self.assertEqual(response.status_code,200)
            payload=response.get_json()
            self.assertEqual(payload['decision']['action'],payload['summary']['status'])
            self.assertIsNone(payload['rep'])
            self.assertEqual(client.post('/api/backtest',json={'etf':code}).status_code,400)
            alerts=client.post('/api/alerts',json={'etf':code}).get_json()
            self.assertTrue(any(a.get('summary',{}).get('details',{}).get('strategy_version')=='csi300_value_confirm_v2' for a in alerts))
        s=strategies.analyze_asset(prices,item)
        rail=render_rail(s)
        self.assertIn('60日均价',rail)
        self.assertIn('80日均价',rail)
        self.assertNotIn('回撤中等',rail)
        soup=BeautifulSoup(render_guide(),'html.parser')
        self.assertEqual(len(soup.select('#guide-category-0 table')),3)
        self.assertEqual(len(STATE_CATALOG['trend20']),5)


if __name__=='__main__':unittest.main()
