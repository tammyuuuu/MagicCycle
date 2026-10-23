"""Bind exported HTML, immutable bundles and offline shell to one release."""
import hashlib
import json
import re
from pathlib import Path


def build_release(directory):
    root=Path(directory)
    bundle_file=root/'bundle-assets.json'
    bundles=json.loads(bundle_file.read_text(encoding='utf8')) if bundle_file.exists() else []
    files=['index.html','pwa.js','manifest.webmanifest',
           'assets/brand-badge.png','assets/xingxun-serif-650.woff',
           'icons/apple-touch-icon.png','icons/icon-192.png','icons/icon-512.png','icons/favicon-32.png']
    files += [url.removeprefix('./') for url in bundles]
    files=[name for name in files if (root/name).exists()]
    digest=hashlib.sha256()
    for name in files:
        digest.update(name.encode());digest.update((root/name).read_bytes())
    if (root/'sw.js').exists():
        normalized=re.sub(r"const RELEASE = '[^']*';", "const RELEASE = 'BUILD';", (root/'sw.js').read_text(encoding='utf8'))
        digest.update(normalized.encode())
    release=digest.hexdigest()[:20]
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    (root/'pwa-manifest.json').write_text(json.dumps(dict(version=release,files=files,hashes=hashes),separators=(',',':')),encoding='utf8')
    worker=root/'sw.js'
    if worker.exists():
        worker.write_text(re.sub(r"const RELEASE = '[^']*';",f"const RELEASE = '{release}';",worker.read_text(encoding='utf8')),encoding='utf8')
    return release
