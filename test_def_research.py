import unittest,json,ast
from pathlib import Path
import pandas as pd
import numpy as np
import correlation_data
R=Path(__file__).resolve().parent
class DefResearchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  manifest=json.loads((R/'workspace_data/manifest.json').read_text());cls.data=json.loads((R/'workspace_data'/manifest['current']).read_text(encoding='utf8'));cls.strategies={s['id']:s for s in cls.data['research']['strategies']};cls.df=pd.read_csv(R/'research_def_20261022/results/summary.csv')
 def test_pairs_only_replace_nasdaq_with_sp500(self):
  for a,b in [('A','D'),('B','E'),('C','F')]:
   expected={('050025' if c=='161130' else c):w for c,w in self.strategies[a]['weights'].items()}
   self.assertEqual(expected,self.strategies[b]['weights'])
   for ra,rb in zip(self.strategies[a]['runs'],self.strategies[b]['runs']):
    for key in ['first','last','segment','mode','data_type','days']:self.assertEqual(ra[key],rb[key])
 def test_all_original_seven_runs_retained(self):
  previous=json.loads((R/'workspace_data/daily_causal_v3_plan_20261022_f4c1dc95cc.json').read_text(encoding='utf8'))
  for s in previous['research']['strategies']:
   for old in s['runs']:
    new=next(r for r in self.strategies[s['id']]['runs'] if (r['segment'],r['mode'])==(old['segment'],old['mode']))
    for key in old:self.assertEqual(old[key],new[key])
 def test_actual_fund_history_is_not_silently_truncated(self):
  for s in self.strategies.values():
   for segment in ['real_2013','real_2017','real_2019']:
    self.assertFalse(any(r['segment']==segment for r in s['runs']))
    self.assertIn('008701',next(r['reason'] for r in s['unavailable'] if r['segment']==segment))
 def test_proxy_runs_expose_actual_codes_and_data_type(self):
  for s in self.strategies.values():
   for run in s['runs']:
    if run['segment'] in ['long_proxy','proxy_2013','proxy_2019']:
     self.assertEqual(run['data_type'],'index_proxy');self.assertEqual(run['substitutions']['008701'],'000216');self.assertIn('000216',run['actual_weights']);self.assertNotIn('008701',run['actual_weights'])
 def test_sp500_dividends_are_corrected_without_changing_original(self):
  old=pd.read_csv(R/'research_xingxun_v1/clean/050025.csv');new=pd.read_csv(R/'research_def_20261022/results/050025_corrected.csv')
  self.assertEqual(old['div'].sum(),0);self.assertAlmostEqual(new['div'].sum(),.059)
  np.testing.assert_allclose(new.acc_nav.sub(new.nav).diff().fillna(0),new['div'],atol=1e-6)
  events=new['div']>0
  np.testing.assert_allclose(new.loc[events,'ret'],new.loc[events,'src_return'],atol=6e-7)
 def test_sp500_has_qdii_confirmation_and_payout_delays(self):
  panel=pd.read_csv(R/'research_xingxun_v1/clean/tr_panel.csv',index_col=0,parse_dates=True);dates=panel['160706'].dropna().index
  for mode in ['rebalance','buy_hold']:
   trades=pd.read_csv(R/f'research_def_20261022/results/main_D_{mode}_trades.csv',dtype={'code':str})
   for t in trades[trades.code=='050025'].itertuples():
    if t.side=='buy':self.assertEqual(dates.get_loc(pd.Timestamp(t.confirmation_date))-dates.get_loc(pd.Timestamp(t.date)),2)
    if t.side=='sell':self.assertEqual(dates.get_loc(pd.Timestamp(t.settlement_date))-dates.get_loc(pd.Timestamp(t.date)),10)
 def test_no_strategy_has_implicit_simulation_approval(self):
  for s in self.strategies.values():self.assertEqual(s['simulation_validation'],'conditional')
 def test_monitor_data_is_embedded_safely_and_no_old_plan_mount(self):
  script=correlation_data.investment_script({'rows':[],'test':'</script>'});self.assertNotIn('</script>',script);self.assertIn('window.FUND_ACCESS_MONITOR=',script)
  self.assertNotIn("root=document.getElementById('invest-plan')",(R/'purchase_monitor.js').read_text(encoding='utf8'))
if __name__=='__main__':unittest.main(verbosity=2)
