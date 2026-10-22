from pathlib import Path
import sys,json,hashlib
import pandas as pd,numpy as np
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'research_xingxun_v1'),str(R/'research_xingxun_v2')]
import data_prep as dp
dp.RAW=R/'research_xingxun_v2/raw'
manifest=json.loads((R/'research_xingxun_v2/manifest_v2.json').read_text(encoding='utf8'))
checks=[]
for c in ['000015','001214','008701','161130']:
 raw=(dp.RAW/f'{c}.js').read_bytes();js=raw.decode('utf-8-sig');meta=dp.parse_meta(c,js);ev,_=dp.parse_dividends(c);s,_,_=dp.build_fund_series(c,meta,ev)
 saved=pd.read_csv(R/f'research_xingxun_v2/clean_v2/{c}.csv',parse_dates=['date']).set_index('date');fresh=s.set_index('date')
 diff=(fresh.loc[saved.index,'tr']-saved['tr']).abs().max()
 checks.append(dict(code=c,sha256=hashlib.sha256(raw).hexdigest(),manifest_match=hashlib.sha256(raw).hexdigest()==manifest[c]['sha256'],max_tr_rounding_difference=diff,source_rows=len(fresh),clean_rows=len(saved)))
(O/'data_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf8');print(checks)
d=pd.read_csv(O/'comparison.csv');print(d[(d.segment=='main')&(d['mode']=='per_portfolio_monthly')][['scheme','first','last','months','cagr','mdd']].to_string(index=False))
s=pd.read_csv(O/'supplement.csv');print(s[(s.segment=='main')&s.scheme.isin(['A','B','C','L1','L2'])].to_string(index=False))
