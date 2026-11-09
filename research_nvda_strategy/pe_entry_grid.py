"""Research-only one-time PE entry grid; fixed-horizon and walk-forward."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT
stock,splits,_=bt.load_chart('NVDA');cash,_,_=bt.load_chart('BIL')
end=pd.Timestamp('2026-11-06')
idx=stock.index.intersection(cash.index);idx=idx[idx<=end]
stock,cash=stock.loc[idx],cash.loc[idx]
x,_=bt.signals(stock,bt.pit_fundamentals('NVDA',splits))
rank=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
month_end=np.array([i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month])
thresholds=(30,40,50,60,70)
entries={t:month_end[(rank.iloc[month_end].notna()&(rank.iloc[month_end]<=t/100)).to_numpy()]+1 for t in thresholds}

def simulate(threshold,start,finish):
    dates=idx[(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(finish))]
    if len(dates)<2:return None
    a=idx.get_loc(dates[0]);z=idx.get_loc(dates[-1]);buy=a if threshold==0 else None
    if threshold:
        candidates=entries[threshold];candidates=candidates[(candidates>=a)&(candidates<=z)]
        if len(candidates):buy=int(candidates[0])
    target=pd.Series(False,index=idx)
    if buy is not None:target.iloc[buy:]=True
    m,curve,ledger=bt.simulate(stock,cash,target,dates[0],dates[-1],ticker='NVDA',strategy=f'pe_{threshold}',ledger=True)
    # Isolate the BIL waiting multiplier without changing order costs or the
    # stock leg. For no entry, zero-interest cash has a constant pre-cost NAV.
    if buy is None: bil_multiplier=cash.loc[dates[-1],'adjclose']/cash.loc[dates[0],'adjopen']
    elif buy>a: bil_multiplier=cash.loc[idx[buy],'adjopen']/cash.loc[dates[0],'adjopen']
    else: bil_multiplier=1.0
    zero_cash_nav=m['ending_NAV']/bil_multiplier
    zero_cash_cagr=zero_cash_nav**(1/m['years'])-1
    m.update(threshold=threshold,signal_date=str(idx[buy-1].date()) if threshold and buy is not None else '',
             buy_date=str(idx[buy].date()) if buy is not None else '',bought=buy is not None,
             wait_sessions=(buy-a if buy is not None else len(dates)),bil_multiplier=bil_multiplier,
             cash_effect_cagr=m['CAGR']-zero_cash_cagr,zero_cash_cagr=zero_cash_cagr)
    return m

periods={'full':('2013-01-02',end)}
for h in (1,3,5):periods[f'{h}y']=(end-pd.DateOffset(years=h),end)
metrics=[]
for threshold in (0,*thresholds):
    for period,(a,z) in periods.items():
        r=simulate(threshold,a,z);r['period']=period;metrics.append(r)
pd.DataFrame(metrics).to_csv(ROOT/'pe_entry_grid_metrics.csv',index=False)

starts=[idx[i+1] for i in month_end if idx[i+1]>=pd.Timestamp('2013-01-02')]
cohorts=[]
for h in (1,3,5):
    for start in starts:
        finish=start+pd.DateOffset(years=h)-pd.Timedelta(days=1)
        if finish>end:continue
        for threshold in (0,*thresholds):
            r=simulate(threshold,start,finish);r['horizon']=h;cohorts.append(r)
cohorts=pd.DataFrame(cohorts);cohorts.to_csv(ROOT/'pe_entry_grid_cohorts.csv',index=False)

# Annual forward tests: choose among the 5 PE parameters only, based on mean
# annualized returns of fully matured training cohorts. Compare immediate buy
# separately and never pretend overlapping cohorts form a continuous account.
selected=[];details=[]
for h in (1,3,5):
    for year in range(2018,2027-h):
        days=idx[idx.year==year]
        if not len(days):continue
        start=days[0];finish=start+pd.DateOffset(years=h)-pd.Timedelta(days=1)
        if finish>end:continue
        train=cohorts[(cohorts.horizon==h)&(cohorts.start>=str((start-pd.DateOffset(years=10)).date()))&(cohorts.end<str(start.date()))]
        scores=[]
        for t in thresholds:
            group=train[train.threshold==t]
            if len(group)<12:break
            scores.append((group.CAGR.mean(),-group.stock_orders_per_year.mean(),-t,len(group)))
        if len(scores)!=len(thresholds):continue
        winner=-max(scores)[2]
        selected.append({'horizon':h,'start':str(start.date()),'train_last_end':train.end.max(),
                         'train_first':train.start.min(),'chosen_threshold':winner,'train_n':max(scores)[3]})
        for t in (0,*thresholds):
            r=simulate(t,start,finish);r.update(horizon=h,chosen_threshold=winner,selected=(t==winner));details.append(r)
pd.DataFrame(selected).to_csv(ROOT/'pe_entry_grid_selections.csv',index=False)
pd.DataFrame(details).to_csv(ROOT/'pe_entry_grid_oos.csv',index=False)
print(f'{len(cohorts)} fixed-horizon results; {len(selected)} forward selections')
