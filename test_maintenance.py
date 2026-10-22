import json, hashlib, unittest, zipfile, tempfile
from pathlib import Path
from unittest.mock import patch
import export_alerts, config
ROOT=Path(__file__).resolve().parent
class MaintenanceTests(unittest.TestCase):
    def test_all_archives_preserve_original_hashes(self):
        entries=json.loads((ROOT/'maintenance/20261022/actions.json').read_text(encoding='utf8'))
        for a in entries:
            if a['action'] not in ('archive','move_archive'):continue
            d=a['destination']
            if '!/' in d:
                archive,member=d.split('!/',1)
                # Recovery archives are local evidence, not runtime/test inputs.
                # Validate them when present; a fresh clone need not download them.
                if not (ROOT/archive).is_file():
                    with self.subTest(archive=archive):
                        self.skipTest('Optional local recovery archive is not distributed')
                    continue
                with zipfile.ZipFile(ROOT/archive) as z:data=z.read(member)
            else:
                if not (ROOT/d).is_file() and Path(d).suffix.lower() in ('.png','.jpg','.jpeg'):
                    with self.subTest(screenshot=d):
                        self.skipTest('Optional local screenshot is not distributed')
                    continue
                data=(ROOT/d).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),a['sha256'],a['path'])
    def test_offline_export_uses_cache_without_network(self):
        with tempfile.TemporaryDirectory() as folder, patch('requests.sessions.Session.request',side_effect=AssertionError('offline export contacted network')):
            target=Path(folder)/'index.html'
            export_alerts.main(str(target),offline=True)
            rows=json.loads(target.with_suffix('.json').read_text(encoding='utf8'))
            self.assertEqual(len(rows),len(config.TARGET_ETFS))
            self.assertFalse(any(r['status']=='error' for r in rows),rows)
            html=target.read_text(encoding='utf8')
            self.assertNotIn('本地缓存构建：未联网核实最新行情',html)
            self.assertNotIn('新账户不会自动执行这些信号',html)
            self.assertIn(rows[0]['date'],html)
            self.assertNotIn('688836',html)
            for name in ('pwa.js','sw.js','manifest.webmanifest'):self.assertTrue((Path(folder)/name).is_file())
    def test_runtime_assembly_excludes_retired_modules(self):
        source=(ROOT/'correlation_data.py').read_text(encoding='utf8')
        for name in ('investment_tools.js','portfolio_v1.js','monthly_budget.js','correlation_tools.js','stock_watch'):
            self.assertNotIn(name,source)
        self.assertFalse(any(i.get('asset_type')=='stock' for i in config.TARGET_ETFS))
