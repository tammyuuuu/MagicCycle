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
W={'A':{'000015':1/3,'008701':1/3,'161130':1/3},'B':{'000015':.4,'008701':.3,'161130':.3},'C':{'000015':.6,'008701':.2,'161130':.2},'L1':{'000015':.5,'008701':.5},'L2':{'000015':1/3,'008701':1/3,'090010':1/3},'L3':{'000015':1/3,'008701':1/3,'001214':1/3},'L4':{'000015':1/3,'008701':1/3,'160706':1/3}}
for a,b in [('A','D'),('B','E'),('C','F')]:W[b]={('050025' if c=='161130' else c):v for c,v in W[a].items()}
p=load_all();rows=[];unavailable=[]
# The old 050025 clean series omitted three cash dividends. Correct only the new research input.
raw_sp=pd.read_csv(R/'research_xingxun_v1/clean/050025.csv',parse_dates=['date'])
events=json.loads((Path(__file__).parent/'050025_dividends.json').read_text(encoding='utf8'))
raw_sp['div']=raw_sp.date.map({pd.Timestamp(e['ex_date']):e['per_share'] for e in events}).fillna(0)
np.testing.assert_allclose((raw_sp.acc_nav-raw_sp.nav).diff().fillna(0),raw_sp['div'],atol=1e-6)
raw_sp['ret']=(raw_sp.nav+raw_sp['div'])/raw_sp.nav.shift(1)-1;raw_sp.loc[0,'ret']=0
raw_sp['tr']=(1+raw_sp.ret).cumprod();raw_sp.to_csv(OUT/'050025_corrected.csv',index=False)
p['050025']=raw_sp.set_index('date').tr.reindex(p.index).ffill(limit=5)
segments=[('main','2021-11-01','2026-10-21','actual_fund'),('long_proxy','2017-07-03','2024-12-31','index_proxy'),('historical_2023','2023-01-01','2026-07-01','actual_fund'),('real_2020','2020-07-16','2026-10-21','actual_fund'),('real_2013','2013-01-01','2026-10-21','actual_fund'),('real_2017','2017-07-03','2024-12-31','actual_fund'),('real_2019','2019-04-01','2026-10-21','actual_fund'),('proxy_2013','2013-08-22','2026-10-21','index_proxy'),('proxy_2019','2019-04-01','2026-10-21','index_proxy')]
for seg,s,e,data_type in segments:
 for name,weights in W.items():
  substitutions=({'008701':'000216','161130':'270042'} if seg=='long_proxy' else {'008701':'000216','161130':'270042','001214':'160119'} if seg=='proxy_2013' else {'008701':'000216'} if seg=='proxy_2019' else {})
  w={substitutions.get(c,c):v for c,v in weights.items()}
  codes=list(w);needed=codes+['000198']
  # Keep pre-start information for causal decisions. No unrelated-column dropna.
  history=p.loc[:e,needed];first=max(history[c].first_valid_index() for c in needed)
  requested=history.index[history.index.searchsorted(pd.Timestamp(s))]
  if first>requested:
   missing={c:str(history[c].first_valid_index().date()) for c in needed if history[c].first_valid_index()>requested}
   unavailable.append(dict(segment=seg,scheme=name,reason='指定起点早于所需基金可用净值起点：'+str(missing),requested_first=s,data_type=data_type));continue
  history=history.loc[first:];dates=history.index;start=int(dates.searchsorted(pd.Timestamp(s)));end=len(dates)-1
  if history.iloc[start:].isna().any().any():raise ValueError('required panel missing')
  prices={c:history[c].to_numpy() for c in codes};cr=history['000198'].pct_change(fill_method=None).fillna(0).to_numpy()
  tradeable={}
  for c in codes:
   base=R/('research_xingxun_v2/clean_v2' if c in ['000015','008701','161130','001214'] else 'research_xingxun_v1/clean')
   raw=pd.read_csv(base/f'{c}.csv',parse_dates=['date']);tradeable[c]=dates.isin(raw.date)
  confirm={c:2 if c in ['161130','270042','050025'] else 1 for c in codes}
  settlement={c:10 if c in ['161130','270042','050025'] else 2 for c in codes}
  scenarios=[('rebalance',False,2,settlement),('buy_hold',True,2,settlement)]
  if seg=='main':scenarios += [('lag5',False,5,settlement),('settle2',False,2,2)]
  for mode,once,lag,settle in scenarios:
   r=run_portfolio_v2(prices,dates,cr,w,2000,fees,start,end,once=once,information_lag=lag,confirm_days=confirm,settle=settle,tradable=tradeable)
   equity=pd.Series(r['equity'][start:],index=dates[start:]);yr=(equity.index[-1]-equity.index[0]).days/365.25
   np.testing.assert_allclose(r['equity'][start:],r['cash'][start:]+r['held'][start:]+r['receivable'][start:],atol=1e-8)
   assert np.all(r['cash'][start:]>=-1e-8)
   for t in r['trades']:assert t['known_through']<t['decision_date']<t['date']
   rows.append(dict(segment=seg,scheme=name,mode=mode,first=str(equity.index[0].date()),last=str(equity.index[-1].date()),days=len(equity),years=yr,cagr=(equity.iloc[-1]/2000)**(1/yr)-1,mdd=(equity/equity.cummax()-1).min(),fees=r['fees'],trades=len(r['trades']),final=equity.iloc[-1],information_lag=lag,validation='conditional_historical_not_live_approved',data_type=data_type,actual_weights=json.dumps(w),substitutions=json.dumps({c:substitutions[c] for c in weights if c in substitutions}),source='research_def_20261022/results'))
   prefix=f'{seg}_{name}_{mode}'
   pd.DataFrame({'equity':equity,'spendable_cash':r['cash'][start:],'receivable':r['receivable'][start:],'held':r['held'][start:]}).to_csv(OUT/f'{prefix}_daily.csv')
   pd.DataFrame(r['trades']).to_csv(OUT/f'{prefix}_trades.csv',index=False)
   pd.DataFrame(r['signals']).to_csv(OUT/f'{prefix}_signals.csv',index=False)
(OUT/'availability.json').write_text(json.dumps(unavailable,ensure_ascii=False,indent=2),encoding='utf8')
df=pd.DataFrame(rows);df.to_csv(OUT/'summary.csv',index=False)
meta={'engine':'daily_causal_v3','mode':'backtest','publication_policy':'Assumed NAV information available after two A-share proxy trading rows; lag5 sensitivity. Actual publication timestamps unavailable.','settlement_policy':'Domestic 2 proxy sessions, QDII 10 proxy sessions; sensitivity all2. Not channel-verified.','confirmation_policy':'Domestic1/QDII2 proxy sessions. Holding days start at confirmation.','fees':'Snapshot fee schedule, not historical channel point-in-time rates.','dividends':'TR automatic reinvestment, synthetic shares.','limits':'Main assumes purchasable. L3/L4 structural blocked-Nasdaq scenarios, not reconstructed historical limits.','approval':'No strategy or live advice enabled.','source_hashes':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [R/'research_xingxun_v2/engine_v2.py',R/'research_xingxun_v2/run_v23.py',R/'research_xingxun_v2/run_v21.py',R/'research_xingxun_v2/clean_v2/panel_v2.csv',R/'research_xingxun_v1/clean/tr_panel.csv',Path(__file__),R/'research_xingxun_v2/clean_v2/001214.csv',R/'research_xingxun_v1/clean/160706.csv',R/'research_xingxun_v1/clean/fund_meta.csv',R/'research_xingxun_v1/clean/050025.csv',R/'research_xingxun_v1/raw/050025.js',Path(__file__).parent/'050025_dividends.json']}}
source_codes=set(c for w in W.values() for c in w)|{'000216','270042','160119','000198'}
source_files=[R/('research_xingxun_v2/clean_v2' if c in ['000015','008701','161130','001214'] else 'research_xingxun_v1/clean')/f'{c}.csv' for c in sorted(source_codes)]
source_files += [R/'research_xingxun_v2/clean_v2/fund_meta_v2.csv',R/'research_xingxun_v2/run_v2.py',R/'research_xingxun_v1/cost_model.py',R/'research_xingxun_v1/weight_engine.py']
meta['source_hashes'].update({str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files})
meta['sp500_dividend_policy']='050025 omitted cash dividends repaired from issuer notices; original clean file preserved. Corrected input stored beside new research results.'
meta['proxy_policy']='Proxy research uses substitute fund TR including fund expenses, not raw index levels; actual codes recorded per run.'
(OUT/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
print(df[(df['mode'].isin(['rebalance','buy_hold'])) & df.scheme.isin(['D','E','F'])].to_string(index=False))
