"""Read-only source audit; writes only into this audit directory. Run python -B."""
from pathlib import Path
import sys, json, ast, hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'research_xingxun_v2'),str(ROOT/'research_xingxun_v1')]
from run_v23 import load_all, month_ret, run, invvol_w
from engine_v2 import run_portfolio_v2
from otc_engine import FundFee
from run_v2 import load_fees
W={'A':{'000015':1/3,'008701':1/3,'161130':1/3},'B':{'000015':.4,'008701':.3,'161130':.3},'C':{'000015':.6,'008701':.2,'161130':.2},'L1':{'000015':.5,'008701':.5},'L2':{'000015':1/3,'008701':1/3,'090010':1/3},'L3':{'000015':.5,'008701':.3},'bond':{'000015':1},'gold':{'008701':1},'cash':{}}
fees=load_fees()
meta=pd.read_csv(ROOT/'research_xingxun_v1/clean/fund_meta.csv',dtype={'code':str})
for r in meta.itertuples():
 if r.code not in fees:
  fees[r.code]=FundFee(r.code,ast.literal_eval(r.purchase_fee_tiers) if isinstance(r.purchase_fee_tiers,str) else None,ast.literal_eval(r.redeem_fee_tiers) if isinstance(r.redeem_fee_tiers,str) else None)
p=load_all(); mr=month_ret(p)
segments={'main':('2021-11-01','2026-10-21'),'oos_label_only':('2023-01-01','2026-07-01'),'long_proxy':('2017-07-03','2024-12-31')}
rows=[]; coverage=[]
for seg,(start,end) in segments.items():
 for name,orig in W.items():
  w={({'008701':'000216','161130':'270042'}.get(c,c) if seg=='long_proxy' else c):v for c,v in orig.items()}
  codes=list(w)+['000198']
  rets=month_ret(p[codes]) if seg=='long_proxy' else mr
  for mode,rr in [('original_global_dropna',rets),('per_portfolio_monthly',month_ret(p[codes]))]:
   m,pack=run(p,rr,lambda h,dt:w,start,end)
   if m:
    rows.append(dict(segment=seg,scheme=name,mode=mode,first=str(pack[0].index[0].date()),last=str(pack[0].index[-1].date()),months=len(pack[0]),**m))
  sub=p.loc[start:end,codes].copy()
  coverage.append(dict(segment=seg,scheme=name,rows=len(sub),missing=sub.isna().sum().to_dict()))
  sub=sub.dropna(); dates=sub.index
  cr=p['000198'].pct_change(fill_method=None).reindex(dates).fillna(0).to_numpy()
  prices={c:sub[c].to_numpy() for c in w}
  for mode,kw in [('daily_engine',{}),('buy_hold',{'once':True}),('daily_zero_fee',{'fee_mult':0}),('daily_settle5',{'settle':5})]:
   res=run_portfolio_v2(prices,dates,cr,w,2000,fees,0,len(dates)-1,**kw)
   eq=pd.Series(res['equity'],index=dates); years=(dates[-1]-dates[0]).days/365.25
   rows.append(dict(segment=seg,scheme=name,mode=mode,first=str(dates[0].date()),last=str(dates[-1].date()),years=years,cagr=(eq.iloc[-1]/2000)**(1/years)-1,mdd=(eq/eq.cummax()-1).min(),final=eq.iloc[-1],fees=res['fees'],trades=len(res['trades'])))
   if mode=='daily_engine':
    eq.to_csv(OUT/f'equity_{seg}_{name}.csv',header=['equity'])
    pd.DataFrame(res['trades']).to_csv(OUT/f'trades_{seg}_{name}.csv',index=False)
pd.DataFrame(rows).to_csv(OUT/'comparison.csv',index=False)
(OUT/'coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf8')
info={'global_months':[str(x.date()) for x in mr.index],'panel_range':[str(p.index.min()),str(p.index.max())],'monthly_missing':p.resample('ME').last().isna().sum().to_dict(),'versions':{'python':sys.version,'pandas':pd.__version__,'numpy':np.__version__}}
(OUT/'data_diagnostics.json').write_text(json.dumps(info,indent=2),encoding='utf8')
print(pd.DataFrame(rows).query("scheme in ['A','B','C','L1','L2'] and mode in ['original_global_dropna','daily_engine','buy_hold']").to_string(index=False))
print('GLOBAL MONTHS',len(mr),mr.index.min(),mr.index.max())
