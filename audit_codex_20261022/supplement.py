exec((__import__('pathlib').Path(__file__).parent/'reproduce.py').read_text().split('rows=[]; coverage=[]')[0])
from weight_engine import is_rebalance_day
out=[]
for segment,start,end in [('original_actual','2021-11-01','2025-01-31'),('main','2021-11-01','2026-10-21')]:
 d=p.loc[start:end,['000015','008701','161130','090010','001214','000198']].dropna();dates=d.index;cr=p['000198'].pct_change(fill_method=None).reindex(dates).fillna(0).to_numpy()
 schemes={**W,'K4':None}
 for name,w in schemes.items():
  codes=list(w) if w is not None else ['000015','008701','001214'];prices={c:d[c].to_numpy() for c in codes}
  wf=w if w is not None else lambda i:invvol_w(p.loc[:dates[i]],codes,120,.6)
  for mode,kw in [('engine',{}),('zero_fee',{'fee_mult':0}),('settle10',{'settle':10})]:
   rr=run_portfolio_v2(prices,dates,cr,wf,2000,fees,0,len(dates)-1,**kw);eq=pd.Series(rr['equity'],index=dates);yrs=(dates[-1]-dates[0]).days/365.25
   mo=eq.resample('ME').last();out.append(dict(segment=segment,scheme=name,mode=mode,cagr=(eq.iloc[-1]/2000)**(1/yrs)-1,mdd=(eq/eq.cummax()-1).min(),monthly_sampled_mdd=(mo/mo.cummax()-1).min(),fees=rr['fees'],final=eq.iloc[-1]))
pd.DataFrame(out).to_csv(OUT/'supplement.csv',index=False)
quality=[]
for c in ['000015','008701','161130','090010','000198']:
 base=ROOT/('research_xingxun_v2/clean_v2' if c in ['000015','008701','161130'] else 'research_xingxun_v1/clean')
 raw=pd.read_csv(base/f'{c}.csv',parse_dates=['date']).set_index('date');cal=p.loc['2021-11-01':'2026-10-21'].index
 missing=cal.difference(raw.index)
 quality.append(dict(code=c,first=str(raw.index.min()),last=str(raw.index.max()),duplicates=int(raw.index.duplicated().sum()),missing_on_calendar=len(missing),missing_dates=[str(x.date()) for x in missing],dividends=int((raw['div']>0).sum()) if 'div' in raw else None))
(OUT/'raw_coverage.json').write_text(json.dumps(quality,indent=2),encoding='utf8')
print(pd.DataFrame(out).query("scheme in ['A','B','C','L1','L2','K4'] and mode=='engine'").to_string(index=False))
