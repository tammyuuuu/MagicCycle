"""Check public freshness; dispatch the existing workflow without generating local data.

Windows uses the current user's existing Git credential manager, in memory only.
The cloud catch-up check uses GITHUB_TOKEN through the workflow environment.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = 'tammyuuuu/MagicCycle'
WORKFLOW = 'market-update.yml'
SITE = 'https://tammyuuuu.github.io/MagicCycle/'
ACTIVE = {'queued', 'in_progress', 'waiting', 'pending', 'requested'}


def request(url, token=None, body=None):
    headers = {'User-Agent': 'Cycle-update-watchdog', 'Cache-Control': 'no-cache'}
    if token:
        if not url.startswith('https://api.github.com/'):
            raise ValueError('Credentials may only be sent to GitHub API')
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    # GETs can be retried; a POST timeout is ambiguous and must not be repeated.
    for attempt in range(3 if body is None else 1):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=30) as response:
                return response.read()
        except Exception:
            if body is not None or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def assess(rows, page, expected_etf, expected_us, symbols):
    if len(rows) != len(symbols) or {r.get('symbol') for r in rows} != set(symbols):
        return False, 'ETF set incomplete'
    for row in rows:
        price = float(row.get('metrics', {}).get('price') or 0)
        if row.get('date') != expected_etf or row.get('status') == 'error' or not math.isfinite(price) or price <= 0:
            return False, f'ETF {row.get("symbol")} date={row.get("date")}; expected={expected_etf}'
    for symbol in ('NVDA', 'MSFT', 'GOOGL', 'BWXT'):
        match = re.search(r'data-asset-symbol="' + symbol + r'".*?<p>(.*?)</p>', page, re.S)
        if not match or f'行情日 {expected_us} · 收盘 $' not in match[1] or '已核对最新收盘日' not in match[1]:
            return False, f'{symbol}: latest verified US close not published ({expected_us})'
    return True, f'ETF={expected_etf}; US={expected_us}; all current'


def check_online(now):
    import config
    import data_fetcher
    import msft_monitor
    china = now.astimezone(ZoneInfo('Asia/Shanghai'))
    expected_etf = data_fetcher._expected_latest_trade_date(china).isoformat()
    expected_us = msft_monitor.expected_date(now).isoformat()
    suffix = '?watchdog=' + str(time.time_ns())
    rows = json.loads(request(SITE + 'index.json' + suffix))
    html = request(SITE + 'index.html' + suffix)
    manifest = json.loads(request(SITE + 'pwa-manifest.json' + suffix))
    if hashlib.sha256(html).hexdigest() != manifest['hashes']['index.html']:
        return False, 'Published HTML does not match release manifest'
    return assess(rows, html.decode('utf8'), expected_etf, expected_us,
                  [r['code'] for r in config.TARGET_ETFS])


def credential():
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    proc = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                          text=True, capture_output=True, env=env, cwd=ROOT, timeout=30)
    fields = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
    if proc.returncode or not fields.get('password'):
        raise RuntimeError('Existing Git login unavailable; renew Git authentication')
    return fields['password']


def decision(runs, now, limit=3):
    if any(r['status'] in ACTIVE for r in runs):
        return 'active run; no duplicate dispatch'
    today = now.astimezone(ZoneInfo('Asia/Shanghai')).date()
    attempts = [r for r in runs if r['event'] == 'workflow_dispatch' and
                dt.datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).date() == today]
    if len(attempts) >= limit:
        return 'daily manual/watchdog dispatch limit reached; see Actions logs'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-check', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    print(f'watchdog_utc={now.isoformat()}', flush=True)
    if args.cloud_check:
        due = True
        if os.environ.get('TRIGGER_EVENT') == 'schedule' and os.environ.get('TRIGGER_SCHEDULE') != '30 8 * * 1-5':
            try:
                current, reason = check_online(now)
                # Verify the entire repository release, not only the visible prices.
                if current:
                    from verify_pages_release import verify_remote
                    verify_remote(ROOT / 'docs', SITE)
                due = not current
                print(reason)
            except Exception as exc:
                print(f'Catch-up required: {type(exc).__name__}: {exc}')
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf8') as out:
            out.write(f'due={str(due).lower()}\n')
        print(f'update_due={due}')
        return
    china = now.astimezone(ZoneInfo('Asia/Shanghai'))
    # Login/start-when-available checks are harmless outside the daily window.
    if china.weekday() >= 5 or (china.hour, china.minute) < (16, 30):
        print('Outside weekday catch-up window; skipped')
        return
    try:
        current, reason = check_online(now)
    except Exception as exc:
        current, reason = False, f'Online verification failed: {type(exc).__name__}: {exc}'
    print(reason, flush=True)
    if current or args.check_only:
        return
    token = credential()
    endpoint = f'https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}'
    runs = json.loads(request(endpoint + '/runs?per_page=100', token))['workflow_runs']
    skip = decision(runs, now)
    if skip:
        print(skip)
        return
    request(endpoint + '/dispatches', token, {'ref': 'main', 'inputs': {'reason': 'independent-windows-watchdog'}})
    print('Dispatch accepted by GitHub; completion must be verified by a later check', flush=True)


if __name__ == '__main__':
    main()
