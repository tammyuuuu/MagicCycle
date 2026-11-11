"""Check the existing static release locally and, optionally, on GitHub Pages.

Read-only: never regenerate snapshots or modify market caches.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


JSON_FILES = ('index.json', 'purchase_monitor.json', 'account_nav.json', 'bundle-assets.json')


def canonical(path, data):
    if Path(path).suffix in ('.html', '.js', '.webmanifest'):
        return data.replace(b'\r\n', b'\n')
    return data


def validate_manifest(manifest, read):
    files = manifest['files']
    if not files or 'index.html' not in files:
        raise ValueError('Release has no index.html')
    for name in files:
        if urlsplit(name).scheme or name.startswith('/') or '..' in name.split('/') or '\\' in name:
            raise ValueError(f'Unsafe release path: {name}')
        actual = hashlib.sha256(read(name)).hexdigest()
        if actual != manifest['hashes'][name]:
            raise ValueError(f'Release hash mismatch: {name}')


def verify_local(root):
    manifest = json.loads((root / 'pwa-manifest.json').read_text(encoding='utf-8'))
    validate_manifest(manifest, lambda name: canonical(name, (root / name).read_bytes()))
    worker = (root / 'sw.js').read_text(encoding='utf-8')
    if f"const RELEASE = '{manifest['version']}';" not in worker:
        raise ValueError('Service worker release mismatch')
    data = {name: json.loads((root / name).read_text(encoding='utf-8')) for name in JSON_FILES}
    rows = data['index.json']
    if not rows or all(row.get('status') == 'error' for row in rows):
        raise ValueError('Snapshot has no usable assets')
    return manifest, data


def verify_remote(root, base_url, fetch=None):
    manifest, expected_data = verify_local(root)
    if fetch is None:
        def fetch(name):
            url = base_url.rstrip('/') + '/' + quote(name, safe='/') + '?verify=' + str(time.time_ns())
            request = Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'Cycle-release-check'})
            with urlopen(request, timeout=30) as response:
                return response.read()
    published = json.loads(fetch('pwa-manifest.json'))
    if published != manifest:
        raise ValueError(f"Published release {published.get('version')} != expected {manifest['version']}")
    paths = list(dict.fromkeys(manifest['files'] + list(JSON_FILES) + ['sw.js']))
    with ThreadPoolExecutor(max_workers=6) as pool:
        content = dict(zip(paths, pool.map(fetch, paths)))
    # Remote bytes must match exactly: the service worker uses these same hashes.
    validate_manifest(manifest, content.__getitem__)
    for name, expected in expected_data.items():
        if json.loads(content[name]) != expected:
            raise ValueError(f'Published data differs: {name}')
    if content['sw.js'] != canonical('sw.js', (root / 'sw.js').read_bytes()):
        raise ValueError('Published service worker differs')
    return manifest, expected_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent / 'docs')
    parser.add_argument('--url', help='Published site root, including /MagicCycle/')
    parser.add_argument('--attempts', type=int, default=1)
    parser.add_argument('--interval', type=float, default=15)
    args = parser.parse_args()
    if args.attempts < 1 or args.interval < 0:
        parser.error('attempts must be positive; interval must be nonnegative')
    # Fail immediately for a broken local artifact; retries only handle publication.
    manifest, data = verify_local(args.directory)
    for attempt in range(args.attempts):
        try:
            if args.url:
                manifest, data = verify_remote(args.directory, args.url)
            break
        except Exception as error:
            print(f'Publication check {attempt + 1}/{args.attempts}: {error}', flush=True)
            if attempt + 1 == args.attempts:
                raise
            time.sleep(args.interval)
    print(json.dumps({'verified': 'online' if args.url else 'local', 'version': manifest['version'],
                      'release_files': len(manifest['files']), 'assets': len(data['index.json']),
                      'data_dates': sorted({row['date'] for row in data['index.json'] if row.get('date')})},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
