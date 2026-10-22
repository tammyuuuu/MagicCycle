import json
from pathlib import Path
import pandas as pd
import numpy as np
from research_strategy_hold_audit import load, monthly_budget
from research_csi300_entry_windows import windows
from research_broad_individual import execute
from research_sector_partial_exit import backtest_partial
from research_csi300_search import summarize
from us_guidance import guidance_frame
p,_=load('513100'); out=Path('results/nasdaq_robustness/results.json');r=json.loads(out.read_text(encoding='utf-8'))
start=p.index.get_loc(pd.Timestamp(r['start'])); ready=pd.Series(False,index=p.index);ready.iloc[start-1:]=True
frames={k:guidance_frame(p.close,heat_threshold=int(k.split('_')[0][4:])/100,cooling_threshold=int(k.split('_')[1][4:])/100) for k in r['heat']}
validation={}
for years in (1,3,5):
 spans=windows(p,ready,years); vals={k:{f:[] for f in ('fixed','monthly')} for k in frames}; baseline={f:[] for f in ('fixed','monthly')}
 for s,e in spans:
  baseline['fixed'].append(execute(p,pd.Series(1.,index=p.index),s,e)[0]);baseline['monthly'].append(execute(p,pd.Series(1.,index=p.index),s,e,monthly=1000.)[0])
  for k,f in frames.items():
   vals[k]['fixed'].append(backtest_partial(p,f.target,s,e,entry_allowed=f.entry_allowed,limit_pct=.10)[0]);vals[k]['monthly'].append(monthly_budget(p,f.status,s,e)[0])
 def arrays(rows,f):
  return {'profit':np.array([v['return_pct'] if f=='fixed' else v['profit_on_contributions_pct'] for v in rows]),'dd':np.array([v['max_drawdown_pct'] for v in rows])}
 masks={'train':np.array([p.index[e-1]<pd.Timestamp('2021-01-01') for s,e in spans]),'validation':np.array([p.index[s]>=pd.Timestamp('2021-01-01') for s,e in spans]),'full':np.ones(len(spans),dtype=bool)}
 for k in frames:
  validation.setdefault(k,{})[str(years)]={f:{part:summarize(arrays(vals[k][f],f),arrays(baseline[f],f),mask) for part,mask in masks.items()} for f in baseline}
 print('WINDOWS',years,len(spans),flush=True)
r['heat_windows']=validation;r['hold_monthly']=execute(p,pd.Series(1.,index=p.index),start,monthly=1000.)[0]
out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print('HOLD MONTHLY',r['hold_monthly'],flush=True)
for k in ('heat15_cool5','heat20_cool3','heat20_cool5','heat20_cool8'):
 print(k,{y:{f:v['validation'] for f,v in fs.items()} for y,fs in validation[k].items()},flush=True)
