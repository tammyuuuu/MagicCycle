from pathlib import Path
import sys,subprocess,json,hashlib,unittest
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
commands=[['node','--test','test_portfolio_ledger.js','test_journal_integration.js'],[sys.executable,'-B','-m','unittest','test_research_causality','-v'],['node','test_monthly_budget.js'],['node','test_strategy_preferences.js'],[sys.executable,'-B','research_xingxun_v1/test_capital_pool.py'],[sys.executable,'-B','research_xingxun_v1/test_capital_pool_acceptance.py']]
failed=[]
for n,cmd in enumerate(commands):
 p=subprocess.run(cmd,cwd=R,capture_output=True,text=True,encoding='utf8',errors='replace')
 (O/f'validation_{n}.log').write_text(p.stdout+p.stderr,encoding='utf8');print(n,p.returncode,' '.join(cmd))
 if p.returncode:failed.append(cmd)
p=subprocess.run([sys.executable,'-B','-m','unittest','test_parity_capital_pool','-v'],cwd=R/'research_xingxun_v1',capture_output=True,text=True,encoding='utf8',errors='replace')
(O/'validation_parity.log').write_text(p.stdout+p.stderr,encoding='utf8');print('parity',p.returncode)
if p.returncode:failed.append('parity')
sys.path.insert(0,str(R));import test_asset_strategies
orig=Path.write_text
def write(self,*args,**kwargs):
 if self.as_posix()=='results/test_export.html':return orig(O/'site_preview.html',*args,**kwargs)
 return orig(self,*args,**kwargs)
Path.write_text=write
with (O/'validation_site.log').open('w',encoding='utf8') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_asset_strategies))
print('site',result.testsRun,'passed',result.wasSuccessful())
if not result.wasSuccessful():failed.append('site')
print('FAILED',failed);sys.exit(bool(failed))
