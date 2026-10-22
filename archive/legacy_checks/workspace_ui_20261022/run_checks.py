from pathlib import Path
import subprocess,sys,json,hashlib,unittest
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
commands=[['node','--test','test_portfolio_ledger.js','test_journal_integration.js','test_portfolio_valuation.js','test_investment_planner.js','test_purchase_monitor_policy.js'],[sys.executable,'-B','-m','unittest','test_research_causality','test_workspace_data','test_def_research','test_purchase_monitor','-v'],['node','test_monthly_budget.js'],['node','test_strategy_preferences.js'],[sys.executable,'-B','research_xingxun_v1/test_capital_pool.py'],[sys.executable,'-B','research_xingxun_v1/test_capital_pool_acceptance.py']]
failed=[]
for i,cmd in enumerate(commands):
 p=subprocess.run(cmd,cwd=R,capture_output=True,text=True,encoding='utf8',errors='replace');(O/f'tests_{i}.log').write_text(p.stdout+p.stderr,encoding='utf8');print(i,p.returncode)
 if p.returncode:failed.append(cmd)
p=subprocess.run([sys.executable,'-B','-m','unittest','test_parity_capital_pool','-v'],cwd=R/'research_xingxun_v1',capture_output=True,text=True,encoding='utf8',errors='replace');(O/'tests_parity.log').write_text(p.stdout+p.stderr,encoding='utf8');print('parity',p.returncode)
if p.returncode:failed.append('parity')
sys.path.insert(0,str(R));import test_asset_strategies
original=Path.write_text
def redirected(self,*args,**kwargs):
 if self.as_posix()=='results/test_export.html':return original(O/'regression_export.html',*args,**kwargs)
 return original(self,*args,**kwargs)
Path.write_text=redirected
with (O/'tests_site.log').open('w',encoding='utf8') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_asset_strategies))
print('site',result.testsRun,result.wasSuccessful())
if not result.wasSuccessful():failed.append('site')
protected=json.loads((R/'audit_codex_20261022/input_hashes.json').read_text(encoding='utf8'));protected={k.replace('\\','/'):v for k,v in protected.items()}
checks={k:hashlib.sha256((R/k).read_bytes()).hexdigest()==protected[k] for k in ['docs/portfolio_data.json','research_xingxun_v1/strategy_registry.json','research_xingxun_v2/clean_v2/panel_v2.csv']}
if not all(checks.values()):failed.append(checks)
(O/'protected_inputs.json').write_text(json.dumps(checks,indent=2),encoding='utf8');print('protected',checks);print('FAILED',failed);sys.exit(bool(failed))
