"""Local phone preview: python -B maintenance/mobile_preview.py (no publishing)."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / p for p in ('docs/index.html', 'templates/_styles.html', 'investment_workspace.js')]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'docs'), **kwargs)

    def send_content(self, content, mime):
        data = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = self.path.split('?', 1)[0]
        if route in ('/', '/mobile'):
            return self.send_content((ROOT / 'maintenance/mobile_preview.html').read_text(encoding='utf-8'), 'text/html')
        if route == '/__version':
            return self.send_content(json.dumps([p.stat().st_mtime_ns for p in SOURCES]), 'application/json')
        if route == '/preview/index.html':
            html = SOURCES[0].read_text(encoding='utf-8')
            html = re.sub(r'<style>.*?</style>', lambda _: SOURCES[1].read_text(encoding='utf-8'), html, count=1, flags=re.S)
            if '/* Four-page account workspace.' in html:
                start = html.index('/* Four-page account workspace.')
                end = html.index('})();', start) + len('})();')
                html = html[:start] + SOURCES[2].read_text(encoding='utf-8') + html[end:]
            # Keep preview independent of the production offline shell.
            html = html.replace('<script src="./pwa.js" defer></script>', '')
            return self.send_content(html, 'text/html')
        # Immutable bundle URLs are relative to the exported page.
        if route.startswith('/preview/'):
            self.path = self.path.replace('/preview/', '/', 1)
        return super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print('Phone preview: http://127.0.0.1:8765/mobile', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
