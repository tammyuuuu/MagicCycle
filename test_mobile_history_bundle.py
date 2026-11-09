import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class MobileHistoryTests(unittest.TestCase):
 def test_current_mobile_bundle_keeps_identical_continuous_accounts_only(self):
  manifest=json.loads((ROOT/'workspace_data/manifest.json').read_text(encoding='utf8'))
  payload=json.loads((ROOT/'workspace_data'/manifest['current']).read_text(encoding='utf8'))
  urls=json.loads((ROOT/'docs/bundle-assets.json').read_text(encoding='utf8'))
  path=ROOT/'docs'/next(u.removeprefix('./') for u in urls if '/research.' in u)
  self.assertLess(path.stat().st_size,1024*1024)
  data,_=json.JSONDecoder().raw_decode(path.read_text(encoding='utf8').split('const runs=',1)[1])
  self.assertEqual(set(data),{s['id'] for s in payload['research']['strategies']})
  for strategy in payload['research']['strategies']:
   source=strategy.get('continuous_run') or next(r for r in strategy['runs'] if r['segment']=='real_2020' and r['mode']=='rebalance')
   self.assertEqual(data[strategy['id']]['continuous_run'],source)
   self.assertEqual(data[strategy['id']]['runs'],[])

if __name__=='__main__':unittest.main()
