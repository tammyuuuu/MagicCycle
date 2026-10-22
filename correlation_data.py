"""Embed current research data and shared UI modules for local and static pages."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _script_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")


def investment_script(access_snapshot=None):
    """Embed only public versioned data; account data stays in the browser."""
    manifest = json.loads((ROOT / 'workspace_data' / 'manifest.json').read_text(encoding='utf-8'))
    name = manifest['current']
    if Path(name).name != name or not name.endswith('.json'):
        raise ValueError('Invalid workspace data manifest')
    payload = json.loads((ROOT / 'workspace_data' / name).read_text(encoding='utf-8'))
    encoded = _script_json(payload)
    if access_snapshot is None:
        path=ROOT/'docs/purchase_monitor.json'
        try:access_snapshot=json.loads(path.read_text(encoding='utf8')) if path.exists() else None
        except (ValueError,OSError):access_snapshot=None
    monitor=_script_json(access_snapshot)
    quote_path=ROOT/'docs/account_nav.json'
    quote_snapshot=json.loads(quote_path.read_text(encoding='utf8')) if quote_path.exists() else None
    account_quotes=_script_json(quote_snapshot)
    product_assets=_script_json(json.loads((ROOT/'product_assets.json').read_text(encoding='utf8')))
    scripts = ['window.PRODUCT_ASSETS='+product_assets+';','window.WORKSPACE_DATA=' + encoded + ';','window.FUND_ACCESS_MONITOR='+monitor+';','window.ACCOUNT_NAV_SNAPSHOT='+account_quotes+';']
    scripts.extend((ROOT / name).read_text(encoding='utf-8') for name in
                   ['strategy_labels.js', 'portfolio_store.js', 'capital_pool.js', 'portfolio_valuation.js', 'investment_planner.js', 'purchase_monitor.js', 'product_assets.js', 'asset_planner.js', 'fund_lookup.js', 'fund_picker.js', 'user_purchase_fees.js', 'account_funding.js', 'strategy_lab.js', 'review_scorecard.js', 'investment_workspace.js'])
    return chr(10).join(scripts)
