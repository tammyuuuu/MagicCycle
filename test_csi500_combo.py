"""Frozen v4 contract: boundaries, chronology, research replay and display."""
import unittest,json
from pathlib import Path
import numpy as np
import pandas as pd
from csi500_pe_pb_strategy import positions,frame,pb_frame,STRATEGY_VERSION
from valuation_data import load_pb_cache,normalize_pb_history
from research_broad_individual import execute

ROOT=Path(__file__).resolve().parent

class ComboTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=pd.read_csv(ROOT/'data_cache/etf_510500_tencent.csv',index_col='date',parse_dates=True)
  cls.pe=pd.read_csv(ROOT/'data_cache/valuation_000905_SH.csv',parse_dates=['date'])
  cls.pb=load_pb_cache();cls.f=frame(cls.p,cls.pe,cls.pb)

 def test_exit_priority_strict_thresholds_and_persistent_state(self):
  idx=pd.bdate_range('2020-01-01',periods=12)
  c=pd.Series([100,100,90,80,70,60,50,100,120,90,80,70],idx,dtype=float)
  pe=pd.Series([60,60,20,20,20,30,30,60,59,20,20,30],idx,dtype=float)
  pb=pd.Series([10,10,10,9,20,9,9,10,10,20,20,9],idx,dtype=float)
  self.assertEqual(positions(c,pe,pb,3).tolist(),[0,0,0,1,1,0,0,0,1,1,1,0])

 def test_full_curve_and_every_order_equal_frozen_research(self):
  start=np.flatnonzero(self.f.ready)[0]+1
  _,c,t=execute(self.p,self.f.position,start)
  r=pd.read_csv(ROOT/'research_csi500_pe_pb_combinations/accounts/P5_OR_in_A_out_daily.csv.gz',index_col='date',parse_dates=True)
  self.assertTrue(c.index.equals(r.index));np.testing.assert_allclose(c.equity,r.equity,rtol=0,atol=1e-8)
  expected=pd.read_csv(ROOT/'research_csi500_pe_pb_combinations/accounts/P5_OR_in_A_out_orders.csv')
  actual=pd.DataFrame(t)
  for col in expected.columns.intersection(actual.columns):
   if pd.api.types.is_numeric_dtype(expected[col]):np.testing.assert_allclose(actual[col],expected[col])
   else:self.assertEqual(actual[col].astype(str).tolist(),expected[col].astype(str).tolist(),col)
  self.assertEqual(len(t),60)

 def test_prefix_replay_future_data_cannot_change_past(self):
  for cut in [1400,2300]:
   short=frame(self.p.iloc[:cut],self.pe,self.pb)
   pd.testing.assert_frame_equal(short,self.f.iloc[:cut])
  mutated=self.pb.copy();date=self.p.index[2300];mutated.loc[mutated.date>date,'pb']=999
  future=frame(self.p,self.pe,mutated)
  pd.testing.assert_frame_equal(future.loc[:date],self.f.loc[:date])

 def test_missing_and_stale_pb_never_becomes_zero(self):
  missing=frame(self.p,self.pe,[])
  self.assertFalse(missing.ready.any());self.assertFalse(missing.position.any())
  stale=pb_frame(self.p,self.pb[self.pb.date<'2020-01-01'])
  self.assertTrue(stale.loc['2020-03-01':].percentile.isna().all())
  raw=normalize_pb_history([{'date':'2020-01-31','pb':2,'addPb':99}, {'date':'2020-02-28','pb':0}])
  self.assertEqual(raw.pb.tolist(),[2])

 def test_live_status_is_historical_state_and_fixed_window(self):
  import config,strategies
  item={**next(i for i in config.TARGET_ETFS if i['code']=='510500'),
        'valuation_history':self.pe.to_dict('records'),'pb_valuation_history':self.pb.to_dict('records')}
  s=strategies.analyze_asset(self.p,item)
  d=s['details'];self.assertEqual(d['strategy_version'],STRATEGY_VERSION)
  from asset_states import STATE_CATALOG
  self.assertEqual([x[0] for x in STATE_CATALOG[d['strategy_id']]],['add','buy','watch','reduce','exit'])
  self.assertEqual(d['strategy_options'],{});self.assertTrue(d['parameters']['fixed_valuation_years'])
  self.assertEqual(s['status']=='buy',bool(self.f.position.iloc[-1]))
  item['pb_valuation_history']=[]
  self.assertEqual(strategies.analyze_asset(self.p,item)['status'],'watch')

 def test_other_assets_metrics_unchanged(self):
  out=ROOT/'results/active_strategy_backtests'
  old=json.loads((out/'archive_csi500_v3/summary.json').read_text(encoding='utf8'))['assets']
  new=json.loads((out/'summary.json').read_text(encoding='utf8'))['assets']
  for code in old:
   if code=='510500':continue
   self.assertEqual(old[code]['version'],new[code]['version'])
   for key,b in old[code]['backtests'].items():
    for metric in ['start','end','annual_pct','max_drawdown_pct','total_pct','orders']:
     self.assertEqual(b[metric],new[code]['backtests'][key][metric],(code,key,metric))

if __name__=='__main__':unittest.main()
