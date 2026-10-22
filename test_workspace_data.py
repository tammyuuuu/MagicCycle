import unittest,json,hashlib
from pathlib import Path
import pandas as pd
import correlation_data
R=Path(__file__).resolve().parent
class WorkspaceDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  m=json.loads((R/'workspace_data/manifest.json').read_text(encoding='utf8'));cls.data=json.loads((R/'workspace_data'/m['current']).read_text(encoding='utf8'))
 def test_metrics_come_from_reaccepted_versioned_results(self):
  df=pd.read_csv(R/'correctness_20261022/results/summary.csv')
  for s in self.data['research']['strategies']:
   df=pd.read_csv(R/s['source']/'summary.csv')
   self.assertEqual(s['status'],'research_conditional')
   for r in s['runs']:
    raw=df[(df.scheme==s['id'])&(df.segment==r['segment'])&(df['mode']==r['mode'])].iloc[0]
    self.assertAlmostEqual(r['cagr'],raw.cagr);self.assertAlmostEqual(r['mdd'],raw.mdd)
    self.assertEqual(r['first'],r['curve'][0][0]);self.assertEqual(r['last'],r['curve'][-1][0]);self.assertAlmostEqual(r['curve'][0][1],1)
 def test_l34_matches_l12_intervals_and_preserves_old_runs(self):
  old=json.loads((R/'workspace_data/daily_causal_v3_20261022_bd1f797ee2.json').read_text(encoding='utf8'))
  current={s['id']:s for s in self.data['research']['strategies']}
  for prior in old['research']['strategies']:
   for run in prior['runs']:
    now=next(r for r in current[prior['id']]['runs'] if r['segment']==run['segment'] and r['mode']==run['mode'])
    for key,value in run.items():self.assertEqual(value,now[key])
   self.assertEqual(prior['weights'],current[prior['id']]['weights'])
  for name,code in [('L3','001214'),('L4','160706')]:
   strategy=current[name]
   self.assertTrue(strategy['lab_only'])
   self.assertEqual(set(strategy['weights']),{'000015','008701',code})
   for run,baseline in zip(strategy['runs'],current['L2']['runs']):
    for key in ['segment','mode','first','last','days']:self.assertEqual(run[key],baseline[key])
    years=(pd.Timestamp(run['last'])-pd.Timestamp(run['first'])).days/365.25
    self.assertAlmostEqual(run['cagr'],(run['final']/2000)**(1/years)-1)
    self.assertAlmostEqual(run['mdd'],min(p[2] for p in run['curve']),places=7)
 def test_scenarios_and_weights(self):
  for s in self.data['research']['strategies']:
   self.assertAlmostEqual(sum(s['weights'].values()),1)
   self.assertEqual(any(c in s['weights'] for c in ['161130','050025']),s['scenario']=='nasdaq_available')
 def test_nav_source_hashes_and_no_account_data(self):
  for f in self.data['funds'].values():self.assertEqual(f['sha256'],hashlib.sha256((R/f['source']).read_bytes()).hexdigest())
  self.assertNotIn('profile',self.data);self.assertNotIn('journal',self.data)
 def test_old_journal_and_guide_are_not_mounted(self):
  source=(R/'templates/_invest_tools.html').read_text(encoding='utf8');self.assertNotIn('diaryForm',source);self.assertIn('invest-review',source);self.assertIn('invest-lab',source)
  script=correlation_data.investment_script();self.assertNotIn('window.InvestmentLogic=',script);self.assertIn('window.WORKSPACE_DATA=',script)
if __name__=='__main__':unittest.main(verbosity=2)
