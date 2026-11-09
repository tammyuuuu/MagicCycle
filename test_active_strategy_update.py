import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from broad_signal_rules import confirmed_value_trend
from broad_individual_strategy import individual_frame
from csi500_pe_pb_strategy import STRATEGY_VERSION as CSI500_VERSION
from strategy_presentation import presentation,render

ROOT=Path(__file__).resolve().parent
class ActiveStrategyUpdateTests(unittest.TestCase):
 def test_low_price_waits_but_existing_low_valuation_holding_survives_weakness(self):
  idx=pd.bdate_range('2020-01-01',periods=12)
  c=pd.Series([100,100,100,90,110,90,80,100,90,130,120,80],index=idx,dtype=float)
  pct=pd.Series([20,20,20,20,20,20,29,30,60,59,65,30],index=idx,dtype=float)
  result=confirmed_value_trend(c,pct,window=3)
  self.assertEqual(result.tolist(),[0,0,0,0,1,1,1,1,0,1,1,0])

 def test_production_matches_frozen_research_and_no_future_pe(self):
  p=pd.read_csv(ROOT/'data_cache/etf_510500_tencent.csv',index_col='date',parse_dates=True)
  h=pd.read_csv(ROOT/'data_cache/valuation_000905_SH.csv',parse_dates=['date'])
  frozen=pd.read_csv(ROOT/'research_csi500_entry_timing/entry_targets.csv',index_col=0,parse_dates=True)
  f=individual_frame(p,h,'value_trend_confirm120',5)
  np.testing.assert_array_equal(f.position.loc[frozen.index],frozen.confirm120)
  cut=2100;short=individual_frame(p.iloc[:cut],h[h.date<=p.index[cut-1]],'value_trend_confirm120',5)
  np.testing.assert_array_equal(short.position,f.position.iloc[:cut])

 def test_entry_ceiling_is_strict_and_high_valuation_does_not_sell_alone(self):
  idx=pd.bdate_range('2020-01-01',periods=7)
  c=pd.Series([100.,100.,100.,110.,120.,130.,80.],index=idx)
  pct=pd.Series([60.,60.,60.,60.,59.,90.,30.],index=idx)
  self.assertEqual(confirmed_value_trend(c,pct,window=3).tolist(),[0,0,0,0,1,1,0])

 def test_metrics_are_bound_to_asset_version_and_preference(self):
  s=dict(symbol='510500',details={'strategy_version':CSI500_VERSION})
  five=presentation(s,5);self.assertAlmostEqual(five['backtest']['annual_pct'],12.209329,places=4)
  self.assertAlmostEqual(five['backtest']['max_drawdown_pct'],56.094470,places=4)
  self.assertEqual(presentation(s,3)['backtest'],five['backtest'])
  old=presentation(dict(symbol='510500',details={'strategy_version':'csi500_value_trend_v2'}))
  self.assertIsNone(old['backtest'])
  from bs4 import BeautifulSoup
  html=BeautifulSoup(render(five),'html.parser')
  self.assertIn('12.21%',html.get_text());self.assertIn('56.09%',html.get_text())
  self.assertEqual(len(html.select('.strategy-stats > div')),2)
  self.assertFalse(html.select('.strategy-method, .strategy-note'))

 def test_all_valuation_metrics_recomputed_from_accounts_in_percent_points(self):
  registry=json.loads((ROOT/'results/active_strategy_backtests/summary.json').read_text(encoding='utf8'))['assets']
  for code in ['510300','510500']:
   for year in ([3,5,10] if code=='510300' else [5]):
    bt=registry[code]['backtests'][str(year)]
    curve=pd.read_csv(ROOT/f'results/active_strategy_backtests/{code}_{year}_daily.csv',index_col=0,parse_dates=True)
    values=np.r_[100000.,curve.equity.to_numpy()]
    annual=((values[-1]/values[0])**(365.25/(curve.index[-1]-curve.index[0]).days)-1)*100
    drawdown=(1-np.min(values/np.maximum.accumulate(values)))*100
    self.assertAlmostEqual(bt['annual_pct'],annual)
    self.assertAlmostEqual(bt['max_drawdown_pct'],drawdown)
    self.assertEqual(bt['start'],str(curve.index[0].date()))
    self.assertEqual(bt['end'],str(curve.index[-1].date()))
    info=presentation(dict(symbol=code,details={'strategy_version':registry[code]['version']}),year)
    self.assertIn(f'{year}年估值参考' if code=='510300' else 'PE/PB固定5年',info['title'])
    self.assertIn(f'{annual:.2f}%',render(info))
    self.assertIn(f'{drawdown:.2f}%',render(info))

 def test_each_active_asset_has_its_own_backtest(self):
  import config,strategies
  registry=json.loads((ROOT/'results/active_strategy_backtests/summary.json').read_text(encoding='utf8'))['assets']
  for item in config.TARGET_ETFS:
   code=item['code'];p=pd.read_csv(ROOT/f'data_cache/etf_{code}_tencent.csv',index_col='date',parse_dates=True)
   target=dict(item)
   if code in ['510300','510500']:
    h=pd.read_csv(ROOT/f'data_cache/valuation_{"000300" if code=="510300" else "000905"}_SH.csv')
    target['valuation_history']=h.to_dict('records')
   s=strategies.analyze_asset(p,target);info=s['details']['strategy_presentation']
   self.assertEqual(info['version'],registry[code]['version']);self.assertIsNotNone(info['backtest'])
   self.assertIn(info['backtest']['end'],render(info))

 def test_custom_parameters_cannot_borrow_default_performance(self):
  custom=dict(symbol='518850',details={'strategy_version':'gold_heat_actions_v2','parameters':{'heat_threshold':.2}})
  self.assertIsNone(presentation(custom)['backtest'])

 def test_api_csi500_uses_confirmed_strategy(self):
  import app,config
  from unittest.mock import patch
  p=pd.read_csv(ROOT/'data_cache/etf_510500_tencent.csv',index_col='date',parse_dates=True)
  h=pd.read_csv(ROOT/'data_cache/valuation_000905_SH.csv')
  item={**next(x for x in config.TARGET_ETFS if x['code']=='510500'),'valuation_history':h.to_dict('records')}
  with app.app.test_client() as client,patch.object(app,'_load_data',return_value=(p,item)),patch('valuation_data.attach_valuation',side_effect=lambda x,date:x):
   result=client.post('/api/decide',json={'etf':'510500','holding':True,'current_return':-80}).get_json()
   self.assertEqual(result['summary']['details']['strategy_version'],CSI500_VERSION)
   self.assertEqual(result['decision']['action'],result['summary']['status'])
   self.assertEqual(result['summary']['details']['parameters']['entry_percentile'],60)
   self.assertEqual(result['summary']['details']['parameters']['pb_entry_percentile'],10)

if __name__=='__main__':unittest.main()
