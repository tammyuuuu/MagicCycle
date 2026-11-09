"""One-off local rebuild: offline ETF inputs, recently verified MSFT inputs."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_alerts
import msft_monitor
import nvda_monitor

snapshot=msft_monitor.read_snapshot()
now=datetime.now(timezone.utc)
updated=datetime.fromisoformat(snapshot['updated_at'])
if not timedelta(0) <= now-updated <= timedelta(minutes=10):
    raise RuntimeError('MSFT snapshot was not verified in the last ten minutes')
recomputed=msft_monitor.calculate(now)
for key in ('date','close','pe','percentile','filed','last_signal','last_signal_date','last_trade'):
    if recomputed[key] != snapshot[key]: raise RuntimeError(f'MSFT snapshot mismatch: {key}')
original=msft_monitor.render
def use_verified(snapshot=None, error=None, now=None):
    if error == '离线构建未核验数据': error=None
    return original(snapshot,error,now)
if '--msft-only' in sys.argv:
    # Preserve honest stale state when the latest NVDA retrieval failed.
    with patch.object(msft_monitor,'render',side_effect=use_verified):
        export_alerts.main(offline=True)
else:
    nvda_snapshot=nvda_monitor.read_snapshot()
    nvda_updated=datetime.fromisoformat(nvda_snapshot['updated_at'])
    if not timedelta(0) <= now-nvda_updated <= timedelta(minutes=10):
        raise RuntimeError('NVDA snapshot was not verified in the last ten minutes')
    nvda_recomputed=nvda_monitor.calculate(now)
    for key in ('date','close','pe','percentile','filed'):
        if nvda_recomputed[key] != nvda_snapshot[key]: raise RuntimeError(f'NVDA snapshot mismatch: {key}')
    original_nvda=nvda_monitor.render
    def use_verified_nvda(snapshot=None,error=None,now=None):
        if error=='离线构建未核验数据':error=None
        return original_nvda(snapshot,error,now)
    with patch.object(msft_monitor,'render',side_effect=use_verified), patch.object(nvda_monitor,'render',side_effect=use_verified_nvda):
        export_alerts.main(offline=True)
