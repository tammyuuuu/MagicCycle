import json
from pathlib import Path
import unittest

from verify_pages_release import canonical, verify_local, verify_remote


ROOT = Path(__file__).resolve().parent / 'docs'


class PagesReleaseTests(unittest.TestCase):
    def fetch(self, name):
        return canonical(name, (ROOT / name).read_bytes())

    def test_complete_release_and_data(self):
        local, _ = verify_local(ROOT)
        remote, _ = verify_remote(ROOT, 'https://example.test/MagicCycle/', self.fetch)
        self.assertEqual(local, remote)

    def test_rejects_old_published_version(self):
        def fetch(name):
            content = self.fetch(name)
            if name == 'pwa-manifest.json':
                manifest = json.loads(content)
                manifest['version'] = 'old-release'
                return json.dumps(manifest).encode()
            return content
        with self.assertRaisesRegex(ValueError, 'Published release'):
            verify_remote(ROOT, '', fetch)

    def test_rejects_partial_asset_deployment(self):
        def fetch(name):
            return b'old HTML' if name == 'index.html' else self.fetch(name)
        with self.assertRaisesRegex(ValueError, 'hash mismatch: index.html'):
            verify_remote(ROOT, '', fetch)

    def test_rejects_outdated_market_snapshot(self):
        def fetch(name):
            if name == 'index.json':
                rows = json.loads(self.fetch(name))
                rows[0]['date'] = '2000-01-01'
                return json.dumps(rows).encode()
            return self.fetch(name)
        with self.assertRaisesRegex(ValueError, 'Published data differs: index.json'):
            verify_remote(ROOT, '', fetch)

    def test_rejects_old_service_worker(self):
        def fetch(name):
            return b'old worker' if name == 'sw.js' else self.fetch(name)
        with self.assertRaisesRegex(ValueError, 'service worker differs'):
            verify_remote(ROOT, '', fetch)


if __name__ == '__main__':
    unittest.main()
