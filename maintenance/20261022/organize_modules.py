from pathlib import Path
import re,json,hashlib,shutil
R=Path.cwd();M=R/'maintenance/20261022';actions=json.loads((M/'actions.json').read_text(encoding='utf8'))
def move(src,dst):
 p=R/src;q=R/dst;q.parent.mkdir(parents=True,exist_ok=True)
 assert p.resolve().is_relative_to(R.resolve()) and q.resolve().is_relative_to(R.resolve())
 actions.append({'action':'move_archive','path':src,'destination':dst,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});shutil.move(p,q)
for n in ['portfolio_v1.js','investment_tools.js','correlation_tools.js','monthly_budget.js']:
 move(n,'archive/legacy_ui/'+n)
for n in ['_portfolio_v1.html','_asset_guide.html','_strategy_guide.html']:
 if (R/'templates'/n).exists():move('templates/'+n,'archive/legacy_ui/templates/'+n)
for name in ['test_journal_integration.js','test_strategy_preferences.js','test_correlation_tools.js','test_monthly_budget.js','correctness_20261022/check_boundaries.py','results/check_investment_tools.js']:
 p=R/name
 if p.exists():
  s=p.read_text(encoding='utf8')
  for n in ['portfolio_v1.js','investment_tools.js','correlation_tools.js','monthly_budget.js']:
   # Keep assertions that old modules are absent from runtime assembly unchanged.
   s=s.replace("readFileSync('"+n+"'","readFileSync('archive/legacy_ui/"+n+"'")
  if name.endswith('check_boundaries.py'):s=s.replace("'investment_tools.js','portfolio_v1.js'","'archive/legacy_ui/investment_tools.js','archive/legacy_ui/portfolio_v1.js'")
  p.write_text(s,encoding='utf8')
p=R/'research_xingxun_v1/make_preview.py';s=p.read_text(encoding='utf8').replace('../../portfolio_v1.js','../../archive/legacy_ui/portfolio_v1.js').replace("'templates' / '_portfolio_v1.html'","'archive' / 'legacy_ui' / 'templates' / '_portfolio_v1.html'").replace('templates/_portfolio_v1.html','archive/legacy_ui/templates/_portfolio_v1.html');p.write_text(s,encoding='utf8')
# Stock-only assets are recoverable archives, never permanently deleted.
for n in ['stock_watch.py','stock_strategy_research.md','data_cache/etf_688836_qfq.csv','data_cache/etf_688836_tencent.csv']:
 if (R/n).exists():move(n,'archive/stock/'+n)
p=R/'config.py';s=p.read_text(encoding='utf8');s='\n'.join(line for line in s.split('\n') if '"code": "688836"' not in line);p.write_text(s,encoding='utf8')
p=R/'strategy_config.py';s=p.read_text(encoding='utf8');s=re.sub(r'    "stock": \{.*?"confirm_days": 10\},\n','',s,flags=re.S);p.write_text(s,encoding='utf8')
p=R/'strategies.py';s=p.read_text(encoding='utf8');s=re.sub(r"    if asset == 'stock' and item.get\('strategy_mode'\) == 'research_watch':.*?    status, action",'    status, action',s,flags=re.S);s=re.sub(r"    elif asset == 'stock':.*?    details\['legacy'\]", "    details['legacy']",s,flags=re.S)
s=re.sub(r"    else:\n        record\(f\"上市至少.*?    # 仅调整解释顺序",'    # 仅调整解释顺序',s,flags=re.S)
s=re.sub(r"        'stock': \[.*?\],\n",'',s);s=re.sub(r"    if asset == 'stock' and held:\n        basis_order = .*?\n",'',s);s=s.replace("leading = [0, 1] if asset == 'stock' else [0]","leading = [0]");s=s.replace("'fundamental_data_available': False if asset == 'stock' else None","'fundamental_data_available': None");p.write_text(s,encoding='utf8')
p=R/'asset_states.py';s=p.read_text(encoding='utf8');s=re.sub(r' "stock": \[.*?\],\n','',s,flags=re.S);s=re.sub(r"^.*(?:DISPLAY_STATUS_MAP\['stock'\]|STATE_CATALOG\['stock'\]=\[\(code).*$\n?",'',s,flags=re.M);s=re.sub(r"STATE_CATALOG\['stock'\]=\[\n.*?\]\n",'',s,flags=re.S);s=re.sub(r"^ 'stock':.*\n",'',s,flags=re.M);s=re.sub(r"^ risk_badge=.*$"," risk_badge=''",s,flags=re.M);s=s.replace(",('stock','个股')",'').replace(";t=STRATEGY_CONFIG['stock']",'');s=re.sub(r"  \('个股',\[.*?研究观察型：尚未确定买卖条件。.*?'\)\]",' ]',s,flags=re.S);s=re.sub(r", '个股': '<p>.*?</p>'\}",'}',s);s=s.replace(",'个股'",'');s=re.sub(r"^  if title=='个股':.*\n",'',s,flags=re.M);p.write_text(s,encoding='utf8')
p=R/'data_fetcher.py';s=p.read_text(encoding='utf8').replace('(ak.stock_zh_a_hist if item.get("asset_type") == "stock" else ak.fund_etf_hist_em)','ak.fund_etf_hist_em').replace('(ak.stock_zh_a_daily if item.get("asset_type") == "stock" else ak.fund_etf_hist_sina)','ak.fund_etf_hist_sina');p.write_text(s,encoding='utf8')
p=R/'export_alerts.py';s=p.read_text(encoding='utf8');s=re.sub(r'^GUIDE_PATH = .*\n','',s,flags=re.M);s=s.replace(", 'stock': []",'').replace(", 'stock': 'stock'",'');p.write_text(s,encoding='utf8')
p=R/'app.py';s=p.read_text(encoding='utf8').replace('"macro_asset", "stock", "sector_etf"','"macro_asset", "sector_etf"');p.write_text(s,encoding='utf8')
p=R/'templates/index.html';s=p.read_text(encoding='utf8').replace("meta.asset_type==='stock'?$('#stockList'):",'');p.write_text(s,encoding='utf8')
(M/'actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding='utf8')
import ast
for p in R.glob('*.py'):ast.parse(p.read_text(encoding='utf8-sig'))
print('Stock removal and legacy UI path updates parse successfully')
