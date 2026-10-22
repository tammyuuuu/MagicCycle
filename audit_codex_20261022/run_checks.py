from pathlib import Path
import sys,unittest,contextlib
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
import test_asset_strategies
# Existing test writes a rendered fixture; retain it in audit directory only.
original=Path.write_text
def redirected(self,*args,**kw):
 if self.as_posix()=='results/test_export.html':return original(O/'test_export.html',*args,**kw)
 return original(self,*args,**kw)
Path.write_text=redirected
with (O/'site_tests.log').open('w',encoding='utf8') as f:
 result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_asset_strategies))
print('site tests',result.testsRun,'failures',len(result.failures),'errors',len(result.errors))
sys.exit(not result.wasSuccessful())
