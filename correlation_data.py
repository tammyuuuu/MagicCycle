"""Embed current research data and shared UI modules for local and static pages."""
import json
import copy
import hashlib
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


def static_investment_scripts(access_snapshot, output_dir):
    """Content-addressed static bundles; original inline Flask entry stays compatible."""
    output=Path(output_dir)/'assets'
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'workspace_data/manifest.json').read_text(encoding='utf8'))
    payload=json.loads((ROOT/'workspace_data'/manifest['current']).read_text(encoding='utf8'))
    account=copy.deepcopy(payload)
    runs={s['id']:s.pop('runs',{}) for s in account['research']['strategies']}
    light={**account,'calendar':[],'funds':{c:{**f,'nav':f['nav'][-1:]} for c,f in account['funds'].items()}}
    quotes=json.loads((ROOT/'docs/account_nav.json').read_text(encoding='utf8'))
    products=json.loads((ROOT/'product_assets.json').read_text(encoding='utf8'))
    def bundle(label,text):
        data=text.encode('utf8');name=f'{label}.{hashlib.sha256(data).hexdigest()[:16]}.js'
        (output/name).write_bytes(data)
        return './assets/'+name
    core='\n'.join(['window.PRODUCT_ASSETS='+_script_json(products)+';',
        'window.WORKSPACE_DATA='+_script_json(light)+';',
        'window.FUND_ACCESS_MONITOR='+_script_json(access_snapshot)+';']+
        [(ROOT/f).read_text(encoding='utf8') for f in ['strategy_labels.js','portfolio_store.js']]+["try{window.XingxunStore.setContext('real','strategy')}catch{}"]+[(ROOT/f).read_text(encoding='utf8') for f in ['purchase_monitor.js','product_assets.js']])
    data=bundle('account-data','window.WORKSPACE_DATA='+_script_json(account)+';\nwindow.ACCOUNT_NAV_SNAPSHOT='+_script_json(quotes)+';')
    runtime=bundle('workspace','\n'.join((ROOT/f).read_text(encoding='utf8') for f in ['capital_pool.js','portfolio_valuation.js','investment_planner.js','asset_planner.js','fund_lookup.js','fund_picker.js','user_purchase_fees.js','account_funding.js','strategy_lab.js','review_scorecard.js','investment_workspace.js']))
    research=bundle('research','(()=>{const runs='+_script_json(runs)+';for(const s of window.WORKSPACE_DATA.research.strategies)s.runs=runs[s.id]||{};})();')
    core_url=bundle('today',core)
    loader=bundle('loader','window.XINGXUN_ASSETS='+_script_json(dict(data=data,runtime=runtime,research=research))+';\n'+(ROOT/'static_loader.js').read_text(encoding='utf8'))
    urls=[core_url,loader,data,runtime,research]
    return ''.join(f'<script src="{url}" defer></script>' for url in [core_url,loader]),urls
