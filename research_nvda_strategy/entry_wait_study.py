"""Research fresh-account, one-entry rules; waiting is invested in BIL."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT
stock,splits,_=bt.load_chart('NVDA');cash,_,_=bt.load_chart('BIL')
idx=stock.index.intersection(cash.index)
end=pd.Timestamp('2026-11-06');idx=idx[idx<=end]
stock,cash=stock.loc[idx],cash.loc[idx]
x,_=bt.signals(stock,bt.pit_fundamentals('NVDA',splits))
x['rank3']=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
month_end=np.array([i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month],dtype=int)
variants={'immediate':None,'pe_50':('rank3',.50),'drawdown_20':('drawdown',.20),
          'pe_30':('rank3',.30),'pe_70':('rank3',.70),
          'drawdown_15':('drawdown',.15),'drawdown_25':('drawdown',.25)}
entries={}
for name,spec in variants.items():
    if spec is None:continue
    key,threshold=spec
    values=x[key].to_numpy()[month_end]
    eligible=np.isfinite(values)&((values<=threshold) if key=='rank3' else (values>=threshold))
    entries[name]=month_end[eligible]+1

def one(name,start,finish):
    # Entries are at a monthly signal's next open, no future decisions used.
    ix=idx[(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(finish))]
    if len(ix)<2: return None
    start_pos=idx.get_loc(ix[0]); finish_pos=idx.get_loc(ix[-1])
    if name=='immediate': buy_pos=start_pos
    else:
        possibilities=entries[name]
        valid=possibilities[(possibilities>=start_pos)&(possibilities<=finish_pos)]
        buy_pos=int(valid[0]) if len(valid) else None
    target=pd.Series(False,index=idx)
    if buy_pos is not None: target.iloc[buy_pos:]=True
    m,_,_=bt.simulate(stock,cash,target,ix[0],ix[-1],ticker='NVDA',strategy=name)
    m['buy_date']=str(idx[buy_pos].date()) if buy_pos is not None else ''
    m['wait_sessions']=buy_pos-start_pos if buy_pos is not None else len(ix)
    m['signal_date']=str(idx[buy_pos-1].date()) if buy_pos is not None and name!='immediate' else ''
    m['bought']=buy_pos is not None
    return m

periods={'full':('2013-01-02',end)}
for n in (1,3,5):periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
metrics=[]
for name in variants:
    for label,(a,z) in periods.items():
        m=one(name,a,z);m['period']=label;metrics.append(m)
pd.DataFrame(metrics).to_csv(ROOT/'entry_wait_metrics.csv',index=False)

# Monthly-start windows; all are exactly the same intended calendar horizon,
# with actual end adjusted to the last available session before anniversary.
starts=[idx[i+1] for i in month_end if idx[i+1]>=pd.Timestamp('2013-01-02')]
cohorts=[]
for horizon in (1,3,5):
    for start in starts:
        finish=start+pd.DateOffset(years=horizon)-pd.Timedelta(days=1)
        if finish>end:continue
        for name in variants:
            m=one(name,start,finish);m['horizon']=horizon;cohorts.append(m)
cohorts=pd.DataFrame(cohorts)
cohorts.to_csv(ROOT/'entry_wait_cohorts.csv',index=False)

# Each annual OOS cohort is selected using only COMPLETE monthly training
# cohorts from a trailing 10-year start window. No overlapping capital: each
# cohort is a separate experiment; they must not be stitched into one NAV.
oos=[];selections=[]
for horizon in (1,3,5):
    for year in range(2018,2027-horizon):
        year_days=idx[idx.year==year]
        if not len(year_days):continue
        start=year_days[0];finish=start+pd.DateOffset(years=horizon)-pd.Timedelta(days=1)
        if finish>end:continue
        train=cohorts[(cohorts.horizon==horizon)&(cohorts.start>=str((start-pd.DateOffset(years=10)).date()))&(cohorts.end<str(start.date()))]
        choices=['immediate','pe_50','drawdown_20']
        scores=[]
        for name in choices:
            v=train[train.strategy==name]
            if len(v)<12:break
            scores.append((v.CAGR.mean(),-v.stock_orders_per_year.mean(),name,len(v)))
        if len(scores)!=len(choices):continue
        best=max(scores); chosen=best[2]
        selections.append({'horizon':horizon,'start':str(start.date()),'train_first':train.start.min(),
                           'train_last_end':train.end.max(),'chosen':chosen,'train_cagr_mean':best[0],'train_n':best[3]})
        for name in choices:
            m=one(name,start,finish);m.update(horizon=horizon,chosen=chosen,selected=(name==chosen));oos.append(m)
pd.DataFrame(oos).to_csv(ROOT/'entry_wait_oos.csv',index=False)
pd.DataFrame(selections).to_csv(ROOT/'entry_wait_oos_selections.csv',index=False)
print(f'{len(cohorts)} cohort results; {len(selections)} walk-forward selections')
