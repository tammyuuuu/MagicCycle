from pathlib import Path
import json,hashlib,shutil,zipfile
R=Path.cwd().resolve(); A=R/'archive/20261022'; M=R/'maintenance/20261022'; actions=json.loads((M/'actions.json').read_text())
def record(kind,p,d=None):
 actions.append({'action':kind,'path':p.relative_to(R).as_posix(),'destination':d,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
def archive(paths,name):
 paths=[p for p in paths if p.is_file()];dest=A/name
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in paths:z.write(p,p.relative_to(R).as_posix())
 with zipfile.ZipFile(dest) as z:
  for p in paths:
   assert hashlib.sha256(z.read(p.relative_to(R).as_posix())).digest()==hashlib.sha256(p.read_bytes()).digest()
 for p in paths:
  assert p.resolve().is_relative_to(R) and '.git' not in p.parts
  record('archive',p,str(dest.relative_to(R)).replace('\\','/')+'!/'+p.relative_to(R).as_posix());p.unlink()
# Only confirmed regeneratable files are permanently removed.
keep={'def_static_1440_today.png','def_static_375_today.png','def_static_1440_comparison.png','def_static_375_comparison.png','simple_static_1440.png','simple_static_375.png','static_1440_review_viewport.png','static_375_review_viewport.png'}
before=json.loads((M/'before_inventory.json').read_text(encoding='utf8'))
# Whitelist from the accepted inventory; do not remove newly generated evidence.
entries=before if isinstance(before,list) else before.get('files',[])
known={e['path'] for e in entries} if entries else set()
for p in list(R.rglob('*.pyc')):
 if '.git' not in p.parts:record('delete_regeneratable',p);p.unlink()
for p in (R/'workspace_ui_20261022').glob('*.png'):
 if p.name not in keep and not ('official' in p.name):record('delete_regeneratable',p);p.unlink()
for name in ['workspace_ui_20261022/flask_preview.html','workspace_ui_20261022/regression_export.html','mobile-preview.jpg','_ping.txt']:
 p=R/name
 if p.exists():record('delete_regeneratable',p);p.unlink()
# Preserve history as verified archives, with original paths inside each ZIP.
versions=['daily_causal_v3_20261022.json','daily_causal_v3_20261022_715379601b.json','daily_causal_v3_def_20261022_b2636a3d68.json','daily_causal_v3_def_20261022_f650d8eccb.json','daily_causal_v3_l34_20261022_a8d85f1d41.json','daily_causal_v3_l34_20261022_fb15557c19.json']
archive([R/'workspace_data'/n for n in versions],'superseded_workspace_data.zip')
patches=['workspace_upgrade.py','workspace_layout.html']
patches += ['correctness_20261022/'+n+'.py' for n in ['edit_ledger','edit_research','edit_ui','cleanup_ui','final_adjustments','finish_ui']]
archive([R/n for n in patches],'one_time_patches.zip')
# Keep results referenced by tests or runtime at original paths; archive only research outputs without literal path references.
source=[]
for p in R.rglob('*'):
 if p.is_file() and p.suffix in ('.py','.js','.ps1','.bat','.vbs') and not any(x in p.parts for x in ('.git','archive','results','maintenance')):
  source.append(p.read_text(encoding='utf8',errors='replace'))
text='\n'.join(source)
outputs=[]
for p in (R/'results').rglob('*'):
 if p.is_file():
  rel=p.relative_to(R).as_posix()
  if rel in text or rel.replace('/','\\') in text or p.name in text:continue
  outputs.append(p)
archive(outputs,'historical_results.zip')
(M/'actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding='utf8')
print('Recorded',len(actions),'actions; all archived members verified by SHA256.')
