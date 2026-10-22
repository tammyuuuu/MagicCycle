from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'research_xingxun_v2'),str(R/'research_xingxun_v1')]
from engine_v2 import run_portfolio_v2
from otc_engine import FundFee
from run_v23 import month_ret,run
from run_v21 import training_episode_allowed,horizon_end
from entry_engine import OnceEntry,run_episode
class CausalTests(unittest.TestCase):
 def setUp(self):
  self.d=pd.bdate_range('2026-01-01',periods=100);self.p={'A':np.ones(100),'B':np.ones(100)}
  tiers=[{'condition':'小于7天','original_pct':1.5},{'condition':'大于等于7天','original_pct':0}]
  self.f={c:FundFee(c,[],tiers) for c in self.p}
 def engine(self,**kw):
  opts=dict(prices=self.p,dates=self.d,cash_ret=np.zeros(100),weights={'A':1},capital=2000,fees=self.f,start=0,end=99)
  opts.update(kw);return run_portfolio_v2(**opts)
 def test_future_perturbation_preserves_historical_signals_and_trades(self):
  def rule(h,dates):return {'A':1} if h['A'][-1]>=h['B'][-1] else {'B':1}
  r=self.engine(weight_rule=rule);changed={k:v.copy() for k,v in self.p.items()};changed['B'][50:]=5
  q=self.engine(prices=changed,weight_rule=rule)
  for key in ['signals','trades']:
   self.assertEqual([x for x in r[key] if x.get('date')<self.d[50]],[x for x in q[key] if x.get('date')<self.d[50]])
 def test_rule_receives_only_known_slice(self):
  def rule(h,dates):
   self.assertEqual(len(h['A']),len(dates));return {'A':1}
  r=self.engine(weight_rule=rule)
  for t in r['trades']:self.assertLess(t['known_through'],t['decision_date']);self.assertLess(t['decision_date'],t['date'])
 def test_opening_has_no_preinvestment_interest(self):
  r=self.engine(cash_ret=np.full(100,.01),weights={});self.assertEqual(r['equity'][0],2000)
 def test_no_confirmation_no_sell(self):
  r=self.engine(weights=lambda i:{'A':1} if i<3 else {'B':1},confirm_days=60)
  self.assertFalse(any(t['side']=='sell' and t['date']<self.d[63] for t in r['trades']))
 def test_unknown_nav_day_defers_execution(self):
  mask={c:np.ones(100,dtype=bool) for c in self.p};mask['A'][3:8]=False
  r=self.engine(tradable=mask);self.assertEqual(r['trades'][0]['date'],self.d[8])
 def test_settlement_cash_conservation_and_short_fee(self):
  r=self.engine(weights=lambda i:{'A':1} if i<3 else {'B':1},settle={'A':10,'B':2},confirm_days=1)
  s=next(t for t in r['trades'] if t['side']=='sell');b=next(t for t in r['trades'] if t['code']=='B')
  self.assertGreaterEqual(b['date'],s['settlement_date']);self.assertTrue(np.all(r['cash']>=0))
  np.testing.assert_allclose(r['equity'],r['cash']+r['held']+r['receivable'])
 def test_fifo_hold_days_start_at_confirmation(self):
  self.d=pd.bdate_range('2026-01-26',periods=100)
  r=self.engine(weights=lambda i:{'A':1} if i<3 else {'B':1},confirm_days=1)
  s=next(t for t in r['trades'] if t['side']=='sell');self.assertLess(s['hold_days'],7);self.assertGreater(s['fee'],29)
 def test_blocked_code_never_buys(self):self.assertEqual(len(self.engine(blocked_codes=['A'])['trades']),0)
 def test_invalid_inputs_fail(self):
  for weights in [{'A':-1},{'A':float('nan')},{'A':2},{'Z':1}]:
   with self.assertRaises(ValueError):self.engine(weights=weights)
  p={**self.p,'A':self.p['A'].copy()};p['A'][40]=np.nan
  with self.assertRaises(ValueError):self.engine(prices=p)
 def test_once_entry_and_direct_hold_share_execution_engine(self):
  a=self.engine(once=True)
  b=run_episode(self.p,self.d,np.zeros(100),{'A':1},self.f,2000,0,99,OnceEntry({'A':1},2000,0))
  np.testing.assert_allclose(a['equity'],b['equity'])
 def test_training_episode_cannot_cross_cutoff(self):
  dates=pd.bdate_range('2020-07-01','2026-01-01');end=horizon_end(dates,0,3)
  self.assertFalse(training_episode_allowed(dates,0,end));self.assertTrue(training_episode_allowed(dates,0,100))
 def test_unrelated_missing_asset_does_not_truncate(self):
  dates=pd.bdate_range('2020-01-01','2026-10-21');p=pd.DataFrame({'A':np.linspace(1,2,len(dates)),'000198':np.linspace(1,1.1,len(dates)),'dead':1.},index=dates);p.loc['2025-01-01':,'dead']=np.nan
  m,_=run(p,month_ret(p),lambda h,dt:{'A':1},'2021-11-01','2026-10-21');self.assertEqual(m['months'],59);self.assertEqual(m['last_return'],'2026-09-30')
 def test_monthly_rule_cannot_see_current_month(self):
  dates=pd.bdate_range('2020-01-01','2026-10-21');p=pd.DataFrame({'A':np.linspace(1,2,len(dates)),'000198':np.linspace(1,1.1,len(dates))},index=dates)
  def rule(h,dt):self.assertLess(h.index[-1],dt.to_period('M').start_time);return {'A':1}
  run(p,month_ret(p),rule,'2021-11-01','2026-10-21')
 def test_missing_required_month_fails(self):
  dates=pd.bdate_range('2020-01-01','2026-10-21');p=pd.DataFrame({'A':1.,'000198':1.},index=dates);p.loc['2024-01-01':'2024-02-29','A']=np.nan
  with self.assertRaises(ValueError):run(p,month_ret(p),lambda h,dt:{'A':1},'2021-11-01','2026-10-21')
 def test_legacy_dca_uses_prior_signal_and_next_close(self):
  sys.path.insert(0,str(R))
  import dca
  from unittest.mock import patch
  idx=pd.bdate_range('2026-01-05',periods=3)
  frame=pd.DataFrame({'close':[1.,2.,2.],'hist_high':[2.,2.,2.],'max_gain':[1.,1.,1.],'pct':[10.,90.,90.],'vol':[.01,.01,.01]},index=idx)
  with patch.object(dca,'_precompute',return_value=frame):
   res=dca.run_dca(frame,params={'initial_cash':2000,'fee_rate':0,'min_fee':0},sell_rules=[{'id':'pause','conds':['D'],'action':'pause','enabled':True}])
  buys=[e for e in res.events if e['kind']=='buy']
  self.assertEqual(buys[0]['date'],idx[1]);self.assertEqual(res.df['shares'].iloc[0],0)
if __name__=='__main__':unittest.main(verbosity=2)
