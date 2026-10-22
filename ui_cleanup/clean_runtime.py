from pathlib import Path
import re,json
import zipfile
with zipfile.ZipFile('ui_cleanup/before.zip') as z:
 for f in ['templates/index.html','templates/_invest_tools.html','templates/_status_rail.html','export_alerts.py','investment_workspace.js']:
  Path(f).write_bytes(z.read(f))
root=Path.cwd();rules=json.loads(Path('ui_cleanup/css_before.json').read_text(encoding='utf8'))
dead=['.strategy-guide','.guide-table','.tabs','.two','.bignum','.posrow','.refs','.grid','.g2','.row','.conds','.pair','.rejected','.layout','.toolbar','.target-chip','.target-chips','.plan-row','.eyebrow','.section-no','.cash-split','.full','.flow-positive','.flow-negative','.research-note','.table-scroll','.review-detail','.no-trades','.t','.code','.meta','.chip','.adv']
records=[]
for r in rules:
 if r.get('raw'):continue # Retired page-enter animation; no loading mask or layout transition.
 media=r['media']
 if media and media!='(max-width: 350px)':continue # Every viewport now uses the same 460px shell.
 for sel in re.split(r',\s*(?![^()]*\))',r['selector']):
  if sel in ['body::after','header::before','nav','nav a','nav a.active','.asset-section','.asset-section > h2','.today-categories .today-category > h2']:continue
  if any(re.search(re.escape(x)+r'(?![\w-])',sel) for x in dead):continue
  decls=[d for d in r['declarations'] if d['value'] and not (sel=='.wrap' and d['name'] in ['grid-template-columns','gap','align-items']) and not d['name'].startswith('--vg-') and d['name'] not in ['--bg','--c1','--c2','--c3']]
  records.append(dict(selector=sel,media=media,declarations=decls))
# Preserve cascade order while removing properties overwritten later for the exact selector.
seen=set();pruned=[]
for r in reversed(records):
 kept=[]
 for d in r['declarations']:
  key=(r['media'],r['selector'],d['name'],d['priority'])
  globalkey=('',r['selector'],d['name'],d['priority'])
  if key in seen or globalkey in seen:continue
  kept.append(d);seen.add(key)
 if kept:pruned.append({**r,'declarations':kept})
pruned.reverse();output=[]
groups=[]
for r in pruned:
 if groups and groups[-1]['media']==r['media'] and groups[-1]['declarations']==r['declarations']:groups[-1]['selector']+=','+r['selector']
 else:groups.append(dict(r))
for r in groups:
 css=r['selector']+'{'+''.join(d['name']+':'+d['value']+('!important' if d['priority'] else '')+';' for d in r['declarations'])+'}'
 output.append('@media'+r['media']+'{'+css+'}' if r['media'] else css)
output.append('#topnav a{text-decoration:none;cursor:pointer;}')
Path('templates/_styles.html').write_text('<style>\n/* Shared critical styles: parsed in head before any application content. */\n'+'\n'.join(output)+'\n</style>\n',encoding='utf8')
# Remove embedded component styles; scripts and component markup remain separate responsibilities.
for f in ['templates/_invest_tools.html','templates/_status_rail.html']:
 p=Path(f);s=p.read_text(encoding='utf8');p.write_text(re.sub(r'<style>.*?</style>\s*','',s,flags=re.S),encoding='utf8')
p=Path('templates/index.html');s=p.read_text(encoding='utf8');s=re.sub(r'<style>.*?</style>','',s,flags=re.S).replace('{% include "_mobile_ui.html" %}','');s=s.replace('</head>','{% include "_styles.html" %}\n</head>')
start=s.index('  <!-- ================= 规则编辑');end=s.index('</main>',start);s=s[:start]+s[end:]
# Keep the current ETF loader and saved server rule inputs, remove unreachable editing/backtest UI.
start=s.index('<script>');end=s.index('</script>',start)+len('</script>');old=s[start:end]
loader=old[old.index('async function loadAlerts(){'):old.index('async function decide(')]
loader=loader.replace('collectParams()','(STATE.saved?.params||STATE.defaults)').replace('collectRules()','(STATE.saved?.sell_rules||STATE.sell_rules)').replace(', pos=getSavedHolding(it.code)','')
script='''<script>
let STATE=null;
const $=s=>document.querySelector(s);
function safeText(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
'''+loader+'''
async function init(){try{const r=await fetch('/api/state');STATE=await r.json();await loadAlerts();}catch(e){$('#todayOut').textContent='今日提醒暂不可用，请稍后刷新。';}}
init();
</script>'''
s=s[:start]+script+s[end:];p.write_text(s,encoding='utf8')
p=Path('export_alerts.py');s=p.read_text(encoding='utf8');s=re.sub(r'<style>.*?</style>','',s,flags=re.S);s=s.replace('mobile_ui = Path(BASE_DIR, "templates", "_mobile_ui.html").read_text(encoding="utf8")','page_styles = Path(BASE_DIR, "templates", "_styles.html").read_text(encoding="utf8")').replace('{mobile_ui}','');s=s.replace('</head><body>','{page_styles}</head><body>')
start=s.index('        chips = (');end=s.index('    from correlation_data import',start)
s=s[:start]+'''        # Legacy card fields are not part of the current signal UI.
        cards.append('<div class="card"><p class="err">信号摘要暂不可用，请重新生成。</p></div>')
'''+s[end:]
start=s.index('<script>\nvar REPS');end=s.index('</script>',start)+len('</script>')
s=s[:start]+'''<script>
window.STRATEGY_SUMMARIES={json.dumps([i.get("summary") for i in etfs_reps], ensure_ascii=False)};
refreshValuationPreference();
</script>'''+s[end:]
s=s.replace('    rep_json = json.dumps([i["rep"] for i in etfs_reps], ensure_ascii=False)\n','').replace('render_basis, render_guide, render_today_categories','render_basis, render_today_categories').replace('<div class="t">{code} {name}</div>','<h2>{code} {name}</h2>')
start=s.index('    labels = {');end=s.index('    return (',start);s=s[:start]+s[end:]
s=s.replace('生成一个自包含的单文件 HTML（含内嵌 JS，可填“我的持仓”做精确买卖判断）。','生成包含现有四页与关键样式的自包含 HTML。')
p.write_text(s,encoding='utf8')
p=Path('investment_workspace.js');s=p.read_text(encoding='utf8');s=s.replace("  for(const id of ['sec-guide','page-guide','sec-rules','sec-bt']){const el=$(id);if(el)el.classList.add('hidden');}\n",'').replace("window.showInvestmentTab=navigate;window.setInvestmentSummaries=()=>{};","window.showInvestmentTab=navigate;")
s=s.replace("a.setAttribute('role','button');", "a.onclick=()=>{const name=a.dataset.t||a.dataset.page;navigate(name);if(name==='today'&&window.loadAlerts)window.loadAlerts();};a.setAttribute('role','button');")
p.write_text(s,encoding='utf8')
# This optional guide generator remains covered by research tests, but is not built on each request.
p=Path('app.py');s=p.read_text(encoding='utf8').replace('STATE_CATALOG, render_guide, render_today_categories','STATE_CATALOG, render_today_categories').replace('strategy_guide=render_guide(), ','');p.write_text(s,encoding='utf8')
print('CSS rules:',len(rules),'->',len(pruned),'head-only style bytes:',Path('templates/_styles.html').stat().st_size)
