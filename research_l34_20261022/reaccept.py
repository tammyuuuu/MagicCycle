"""Corrected research outputs only. Never writes website data or strategy registry."""
from pathlib import Path
import sys,json,ast,hashlib
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent/'results';OUT.mkdir(exist_ok=True)
sys.path[:0]=[str(R/'research_xingxun_v2'),str(R/'research_xingxun_v1')]
from engine_v2 import run_portfolio_v2
from run_v23 import load_all
from run_v2 import load_fees
from otc_engine import FundFee
fees=load_fees()
for r in pd.read_csv(R/'research_xingxun_v1/clean/fund_meta.csv',dtype={'code':str}).itertuples():
 if r.code not in fees:fees[r.code]=FundFee(r.code,ast.literal_eval(r.purchase_fee_tiers) if isinstance(r.purchase_fee_tiers,str) else None,ast.literal_eval(r.redeem_fee_tiers) if isinstance(r.redeem_fee_tiers,str) else None)
W={'L3':{'000015':1/3,'008701':1/3,'001214':1/3},'L4':{'000015':1/3,'008701':1/3,'160706':1/3}}
p=load_all();rows=[];provenance=[]
for seg,s,e in [('main','2021-11-01','2026-10-21'),('long_proxy','2017-07-03','2024-12-31'),('historical_2023','2023-01-01','2026-07-01')]:
 for name,weights in W.items():
  w={({'008701':'000216','161130':'270042'}.get(c,c) if seg=='long_proxy' else c):v for c,v in weights.items()}
  codes=list(w);needed=codes+['000198']
  # Keep pre-start information for causal decisions. No unrelated-column dropna.
  history=p.loc[:e,needed];first=max(history[c].first_valid_index() for c in needed)
  history=history.loc[first:];dates=history.index;start=int(dates.searchsorted(pd.Timestamp(s)));end=len(dates)-1
  if history.iloc[start:].isna().any().any():raise ValueError('required panel missing')
  prices={c:history[c].to_numpy() for c in codes};cr=history['000198'].pct_change(fill_method=None).fillna(0).to_numpy()
  tradeable={}
  for c in codes:
   base=R/('research_xingxun_v2/clean_v2' if c in ['000015','008701','161130','001214'] else 'research_xingxun_v1/clean')
   raw=pd.read_csv(base/f'{c}.csv',parse_dates=['date']);tradeable[c]=dates.isin(raw.date)
  confirm={c:2 if c in ['161130','270042'] else 1 for c in codes}
  settlement={c:10 if c in ['161130','270042'] else 2 for c in codes}
  scenarios=[('rebalance',False,2,settlement),('buy_hold',True,2,settlement)]
  if seg=='main':scenarios += [('lag5',False,5,settlement),('settle2',False,2,2)]
  for mode,once,lag,settle in scenarios:
   r=run_portfolio_v2(prices,dates,cr,w,2000,fees,start,end,once=once,information_lag=lag,confirm_days=confirm,settle=settle,tradable=tradeable)
   equity=pd.Series(r['equity'][start:],index=dates[start:]);yr=(equity.index[-1]-equity.index[0]).days/365.25
   np.testing.assert_allclose(r['equity'][start:],r['cash'][start:]+r['held'][start:]+r['receivable'][start:],atol=1e-8)
   assert np.all(r['cash'][start:]>=-1e-8)
   for t in r['trades']:assert t['known_through']<t['decision_date']<t['date']
   rows.append(dict(segment=seg,scheme=name,mode=mode,first=str(equity.index[0].date()),last=str(equity.index[-1].date()),days=len(equity),years=yr,cagr=(equity.iloc[-1]/2000)**(1/yr)-1,mdd=(equity/equity.cummax()-1).min(),fees=r['fees'],trades=len(r['trades']),final=equity.iloc[-1],information_lag=lag,validation='conditional_historical_not_live_approved'))
   prefix=f'{seg}_{name}_{mode}'
   pd.DataFrame({'equity':equity,'spendable_cash':r['cash'][start:],'receivable':r['receivable'][start:],'held':r['held'][start:]}).to_csv(OUT/f'{prefix}_daily.csv')
   pd.DataFrame(r['trades']).to_csv(OUT/f'{prefix}_trades.csv',index=False)
   pd.DataFrame(r['signals']).to_csv(OUT/f'{prefix}_signals.csv',index=False)
df=pd.DataFrame(rows);df.to_csv(OUT/'summary.csv',index=False)
meta={'engine':'daily_causal_v3','mode':'backtest','publication_policy':'Assumed NAV information available after two A-share proxy trading rows; lag5 sensitivity. Actual publication timestamps unavailable.','settlement_policy':'Domestic 2 proxy sessions, QDII 10 proxy sessions; sensitivity all2. Not channel-verified.','confirmation_policy':'Domestic1/QDII2 proxy sessions. Holding days start at confirmation.','fees':'Snapshot fee schedule, not historical channel point-in-time rates.','dividends':'TR automatic reinvestment, synthetic shares.','limits':'Main assumes purchasable. L3/L4 structural blocked-Nasdaq scenarios, not reconstructed historical limits.','approval':'No strategy or live advice enabled.','source_hashes':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [R/'research_xingxun_v2/engine_v2.py',R/'research_xingxun_v2/run_v23.py',R/'research_xingxun_v2/run_v21.py',R/'research_xingxun_v2/clean_v2/panel_v2.csv',R/'research_xingxun_v1/clean/tr_panel.csv',Path(__file__),R/'research_xingxun_v2/clean_v2/001214.csv',R/'research_xingxun_v1/clean/160706.csv',R/'research_xingxun_v1/clean/fund_meta.csv']}}
(OUT/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
print(df[(df['mode'].isin(['rebalance','buy_hold'])) & df.scheme.isin(['L3','L4'])].to_string(index=False))
