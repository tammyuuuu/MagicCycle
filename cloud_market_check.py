"""Fail closed before publishing incomplete cloud market snapshots."""
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import data_fetcher
import msft_monitor
import stock_monitor


def main():
    expected_etf = data_fetcher._expected_latest_trade_date()
    rows = json.loads(Path('docs/index.json').read_text(encoding='utf8'))
    by_symbol = {row['symbol']: row for row in rows}
    expected_symbols = {row['code'] for row in config.TARGET_ETFS}
    if len(rows) != len(expected_symbols) or set(by_symbol) != expected_symbols:
        raise ValueError('ETF snapshot symbols incomplete')
    for code, row in by_symbol.items():
        price = float(row.get('metrics', {}).get('price') or 0)
        if row.get('status') == 'error' or row.get('date') != expected_etf.isoformat() or not math.isfinite(price) or price <= 0:
            raise ValueError(f'ETF {code}: invalid or stale snapshot: {row.get("date")}')
    expected_stock = msft_monitor.expected_date(dt.datetime.now(dt.timezone.utc))
    page = Path('docs/index.html').read_text(encoding='utf8')
    for symbol in stock_monitor.INFO:
        result = json.loads((stock_monitor.ROOT / f'{symbol}.json').read_text(encoding='utf8'))['chart']['result'][0]
        if result['meta']['symbol'] != symbol:
            raise ValueError(f'{symbol}: wrong provider symbol')
        timestamps = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        adjusted = result['indicators']['adjclose'][0]['adjclose']
        if len(timestamps) != len(closes) or len(closes) != len(adjusted):
            raise ValueError(f'{symbol}: incomplete quote arrays')
        valid = [(dt.datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date(), float(c), float(a))
                 for t, c, a in zip(timestamps, closes, adjusted) if c is not None and a is not None]
        if not valid or valid[-1][0] != expected_stock or any(not math.isfinite(n) or n <= 0 for n in valid[-1][1:]):
            raise ValueError(f'{symbol}: stale or invalid stock close; expected {expected_stock}')
        if len(valid) < 1000 or len({d for d, _, _ in valid}) != len(valid):
            raise ValueError(f'{symbol}: incomplete or duplicate history')
        if f'data-asset-symbol="{symbol}"' not in page or f'行情日 {expected_stock} · 收盘 ${valid[-1][1]:.2f}' not in page:
            raise ValueError(f'{symbol}: rendered page does not match quote')
        print(f'{symbol}: {expected_stock} {valid[-1][1]:.2f}')
    print(f'ETF: {len(rows)} verified at {expected_etf}')


if __name__ == '__main__':
    main()
