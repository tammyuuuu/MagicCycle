from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
old=json.loads((R/'audit_codex_20261022/input_hashes.json').read_text(encoding='utf8'))
old={k.replace('\\','/'):v for k,v in old.items()}
protected=['docs/portfolio_data.json','research_xingxun_v1/strategy_registry.json','research_xingxun_v2/clean_v2/panel_v2.csv']
checks={name:hashlib.sha256((R/name).read_bytes()).hexdigest()==old[name] for name in protected}
assert all(checks.values()),checks
for f in ['portfolio_store.js','archive/legacy_ui/investment_tools.js','archive/legacy_ui/portfolio_v1.js']:
 import subprocess
 subprocess.run(['node','--check',f],cwd=R,check=True)
(O/'protected_inputs.json').write_text(json.dumps(checks,indent=2),encoding='utf8');print(checks)
