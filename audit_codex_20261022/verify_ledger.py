from pathlib import Path
import sys,json,ast
import pandas as pd
import numpy as np
R=Path(__file__).resolve().parents[1]; O=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'research_xingxun_v2'),str(R/'research_xingxun_v1')]
from cost_model import buy_rate,redeem_rate
from run_v2 import load_fees
from otc_engine import FundFee
from run_v23 import load_all
from engine_v2 import run_portfolio_v2
p=load_all(); fees=load_fees()
for r in pd.read_csv(R/'research_xingxun_v1/clean/fund_meta.csv',dtype={'code':str}).itertuples():
 if r.code not in fees:fees[r.code]=FundFee(r.code,ast.literal_eval(r.purchase_fee_tiers) if isinstance(r.purchase_fee_tiers,str) else None,ast.literal_eval(r.redeem_fee_tiers) if isinstance(r.redeem_fee_tiers,str) else None)
checks=[]
for f in sorted(O.glob('trades_*.csv')):
 try:t=pd.read_csv(f,parse_dates=['date'],dtype={'code':str})
 except pd.errors.EmptyDataError:t=pd.DataFrame(columns=['date','code','side','amount','shares','fee'])
 eq=pd.read_csv(O/f.name.replace('trades_','equity_'),index_col=0,parse_dates=True)['equity']; dates=eq.index
 cash=2000.;recv=[]; lots={};maxdiff=0.;fee_sum=0.;mincash=2000.;maxfeeerr=0.
 for i,dt in enumerate(dates):
  loc=p.index.get_loc(dt); cr=p['000198'].iloc[loc]/p['000198'].iloc[loc-1]-1 if loc else 0
  cash*=1+cr
  cash+=sum(v for due,v in recv if due<=i);recv=[(due,v) for due,v in recv if due>i]
  for tr in t[t.date==dt].itertuples():
   px=p.at[dt,tr.code]; stack=lots.setdefault(tr.code,[])
   if tr.side=='buy':
    cash-=tr.amount; stack.append([tr.shares,dt]); expected=tr.amount-tr.amount/(1+buy_rate(fees[tr.code].buy_tiers,tr.amount)/100)
    assert abs(tr.shares*px+tr.fee-tr.amount)<1e-7
   else:
    remain=tr.shares;expected=0
    for lot in stack:
     q=min(lot[0],remain);expected+=q*px*redeem_rate(fees[tr.code].redeem_tiers,(dt-lot[1]).days)/100;lot[0]-=q;remain-=q
    assert remain<1e-7
    assert abs(tr.shares*px-tr.fee-tr.amount)<1e-7
    recv.append((i+2,tr.amount))
   maxfeeerr=max(maxfeeerr,abs(expected-tr.fee));fee_sum+=tr.fee
  mincash=min(mincash,cash)
  val=cash+sum(v for _,v in recv)+sum(sum(q for q,_ in ls)*p.at[dt,c] for c,ls in lots.items())
  maxdiff=max(maxdiff,abs(val-eq.loc[dt]))
 checks.append(dict(file=f.name,max_equity_difference=maxdiff,min_spendable_cash=mincash,fee_sum=fee_sum,max_fee_difference=maxfeeerr))
 assert maxdiff<1e-7 and mincash>=-1e-7 and maxfeeerr<1e-7
# Controlled FIFO under-7-day redemption, and delayed proceeds used only when due.
dates=pd.bdate_range('2026-01-28',periods=12);prices={'000015':np.ones(12),'008701':np.ones(12)}
w=lambda i: {'000015':1} if i==0 else {'008701':1}
r=run_portfolio_v2(prices,dates,np.zeros(12),w,2000,fees,0,11)
synthetic=[{**x,'date':str(x['date'].date())} for x in r['trades']]
assert any(x['side']=='sell' and x['hold_days']<7 and x['fee']>29 for x in synthetic)
(O/'ledger_checks.json').write_text(json.dumps({'replays':checks,'synthetic':synthetic},indent=2),encoding='utf8')
print('PASS',len(checks),'daily ledgers; max equity difference',max(x['max_equity_difference'] for x in checks));print(synthetic)
