from pathlib import Path
import sys,json,ast
from collections import defaultdict
import pandas as pd
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent/'results'
sys.path[:0]=[str(R/'research_xingxun_v2'),str(R/'research_xingxun_v1')]
from run_v23 import load_all
from run_v2 import load_fees
from otc_engine import FundFee
from cost_model import buy_rate,redeem_rate
p=load_all();fees=load_fees()
for r in pd.read_csv(R/'research_xingxun_v1/clean/fund_meta.csv',dtype={'code':str}).itertuples():
 if r.code not in fees:fees[r.code]=FundFee(r.code,ast.literal_eval(r.purchase_fee_tiers) if isinstance(r.purchase_fee_tiers,str) else None,ast.literal_eval(r.redeem_fee_tiers) if isinstance(r.redeem_fee_tiers,str) else None)
checks=[]
for row in pd.read_csv(O/'summary.csv').itertuples():
 prefix=f'{row.segment}_{row.scheme}_{row.mode}';daily=pd.read_csv(O/f'{prefix}_daily.csv',index_col=0,parse_dates=True)
 try:trades=pd.read_csv(O/f'{prefix}_trades.csv',dtype={'code':str})
 except pd.errors.EmptyDataError:trades=pd.DataFrame(columns=['date'])
 for col in ['date','confirmation_date','settlement_date']:
  trades[col]=pd.to_datetime(trades[col]) if col in trades else pd.NaT
 grouped=defaultdict(list)
 for t in trades.itertuples():grouped[t.date].append(t)
 cash=2000.;recv=[];lots=defaultdict(list);totalfee=0.;error=0.
 for j,dt in enumerate(daily.index):
  if j:
   i=p.index.get_loc(dt);cash*=p['000198'].iloc[i]/p['000198'].iloc[i-1]
  cash+=sum(a for d,a in recv if pd.notna(d) and d<=dt);recv=[(d,a) for d,a in recv if pd.isna(d) or d>dt]
  for t in grouped[dt]:
   px=p.at[dt,t.code]
   if t.side=='buy':
    cash-=t.amount;lots[t.code].append([t.shares,t.confirmation_date]);fee=t.amount-t.amount/(1+buy_rate(fees[t.code].buy_tiers,t.amount)/100)
   else:
    q=t.shares;fee=0.
    for lot in lots[t.code]:
     if q<=1e-9:break
     assert pd.notna(lot[1]) and lot[1]<=dt
     take=min(q,lot[0]);fee+=take*px*redeem_rate(fees[t.code].redeem_tiers,(dt-lot[1]).days)/100;lot[0]-=take;q-=take
    assert q<1e-7
    recv.append((t.settlement_date,t.amount))
   assert abs(fee-t.fee)<1e-7;totalfee+=t.fee
  held=sum(sum(q for q,_ in ls)*p.at[dt,c] for c,ls in lots.items());receivable=sum(a for _,a in recv)
  error=max(error,abs(cash-daily.loc[dt,'spendable_cash']),abs(receivable-daily.loc[dt,'receivable']),abs(cash+held+receivable-daily.loc[dt,'equity']))
  assert cash>=-1e-7
 assert error<1e-7 and abs(totalfee-row.fees)<1e-7
 checks.append({'run':prefix,'max_error':error,'fee_total':totalfee})
(O/'independent_replay.json').write_text(json.dumps(checks,indent=2),encoding='utf8');print('PASS',len(checks),'independent replays; max error',max(x['max_error'] for x in checks))
