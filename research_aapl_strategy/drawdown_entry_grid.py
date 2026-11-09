"""Daily-close drawdown entry: fresh-account, one buy, BIL while waiting.

Frozen AAPL/BIL inputs; 2013-2026 study period; no page or live changes.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt;bt.ROOT=ROOT
stock,splits,_=bt.load_chart('AAPL');cash,_,_=bt.load_chart('BIL')
end=pd.Timestamp('2026-11-06')
idx=stock.index.intersection(cash.index);idx=idx[idx<=end]
stock,cash=stock.loc[idx],cash.loc[idx]
high=stock.close.rolling(252,min_periods=252).max()
drawdown=1-stock.close/high
# Close[t] produces an order for open[t+1], including an order from the
# session before the window if it is already actionable at the first open.
thresholds=(10,15,20,25,30)
entries={t:np.flatnonzero((drawdown.iloc[:-1]>=t/100).to_numpy())+1 for t in thresholds}

def simulate(threshold,start,finish,cost=.001):
    dates=idx[(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(finish))]
    if len(dates)<2:return None
    a=idx.get_loc(dates[0]);z=idx.get_loc(dates[-1]);buy=a if threshold==0 else None
    if threshold:
        allowed=entries[threshold];allowed=allowed[(allowed>=a)&(allowed<=z)]
        if len(allowed):buy=int(allowed[0])
    target=pd.Series(False,index=idx)
    if buy is not None:target.iloc[buy:]=True
    m,_,_=bt.simulate(stock,cash,target,dates[0],dates[-1],cost=cost,ticker='AAPL',strategy=f'dd_{threshold}')
    if buy is None:bil=cash.loc[dates[-1],'adjclose']/cash.loc[dates[0],'adjopen']
    elif buy>a:bil=cash.loc[idx[buy],'adjopen']/cash.loc[dates[0],'adjopen']
    else:bil=1.
    zero_cagr=(m['ending_NAV']/bil)**(1/m['years'])-1
    m.update(threshold=threshold,buy_date=str(idx[buy].date()) if buy is not None else '',
             signal_date=str(idx[buy-1].date()) if threshold and buy is not None else '',
             signal_drawdown=float(drawdown.iloc[buy-1]) if threshold and buy is not None else None,
             bought=buy is not None,wait_sessions=(buy-a if buy is not None else len(dates)),
             bil_multiplier=float(bil),zero_cash_cagr=zero_cagr,cash_effect_cagr=m['CAGR']-zero_cagr)
    return m

periods={f'{n}y':(end-pd.DateOffset(years=n),end) for n in (1,3,5)}
recent=[]
for t in (0,*thresholds):
    for period,(a,z) in periods.items():
        m=simulate(t,a,z);m['period']=period;recent.append(m)
pd.DataFrame(recent).to_csv(ROOT/'drawdown_entry_recent.csv',index=False)

# Monthly first-session starts; matched 5-year horizons, terminal close before
# the calendar anniversary. Overlapping portfolios are separate experiments.
month_end=[i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month]
starts=[idx[i+1] for i in month_end if idx[i+1]>=pd.Timestamp('2013-01-02')]
cohorts=[]
for start in starts:
    finish=start+pd.DateOffset(years=5)-pd.Timedelta(days=1)
    if finish>end:continue
    for t in (0,*thresholds):
        cohorts.append(simulate(t,start,finish))
d=pd.DataFrame(cohorts)
base=d[d.threshold==0].set_index(['start','end'])
parts=[];summaries=[]
for t in (0,*thresholds):
    group=d[d.threshold==t].copy().set_index(['start','end']).sort_index()
    ref=base.reindex(group.index)
    if ref.CAGR.isna().any() or len(group)!=len(base):raise ValueError('unpaired windows')
    group['benchmark_cagr']=ref.CAGR
    group['benchmark_drawdown']=ref.max_drawdown
    group['delta_cagr']=group.CAGR-ref.CAGR
    group['delta_drawdown']=group.max_drawdown-ref.max_drawdown
    eps=1e-10;n=len(group)
    win=int((group.delta_cagr>eps).sum());loss=int((group.delta_cagr< -eps).sum())
    summaries.append({'threshold':t,'n':n,'mean_cagr':group.CAGR.mean(),'median_cagr':group.CAGR.median(),
      'mean_drawdown':group.max_drawdown.mean(),'median_drawdown':group.max_drawdown.median(),
      'worst_drawdown':group.max_drawdown.min(),'mean_wait_sessions':group.wait_sessions.mean(),
      'median_wait_sessions':group.wait_sessions.median(),'bought':int(group.bought.sum()),
      'not_bought':int((~group.bought).sum()),'win':win,'loss':loss,'tie':n-win-loss,
      'win_rate':win/n,'median_delta':group.delta_cagr.median(),
      'dd_improved':int((group.delta_drawdown>eps).sum())})
    parts.append(group.reset_index())
paired=pd.concat(parts,ignore_index=True)
paired.to_csv(ROOT/'drawdown_entry_5y_cohorts.csv',index=False)
pd.DataFrame(summaries).to_csv(ROOT/'drawdown_entry_5y_summary.csv',index=False)

# Exploratory event concentration: group by entry dates during selected past
# stress episodes. Windows remain overlapping; these are not causal tests.
episodes=[('2018_2019','2018-10-01','2019-03-31'),('2020','2020-02-01','2020-06-30'),
          ('2022_2023','2022-01-01','2023-03-31')]
events=[]
for t in thresholds:
    group=paired[paired.threshold==t].copy()
    group['bucket']='other_or_no_entry'
    for label,a,z in episodes:
        group.loc[group.bought&(group.buy_date>=a)&(group.buy_date<=z),'bucket']=label
    for label,sub in group.groupby('bucket'):
        events.append({'threshold':t,'entry_period':label,'n':len(sub),'wins':int((sub.delta_cagr>1e-10).sum()),
                       'losses':int((sub.delta_cagr< -1e-10).sum()),'median_delta':sub.delta_cagr.median(),
                       'mean_delta':sub.delta_cagr.mean(),'median_wait':sub.wait_sessions.median()})
pd.DataFrame(events).to_csv(ROOT/'drawdown_entry_events.csv',index=False)

# Annual chronological pseudo-OOS: choose one of the five thresholds using
# only completed 5y monthly cohorts with starts within the prior ten years.
selections=[];oos=[]
for year in range(2018,2022):
    start=idx[idx.year==year][0];finish=start+pd.DateOffset(years=5)-pd.Timedelta(days=1)
    if finish>end:continue
    train=paired[(paired.start>=str((start-pd.DateOffset(years=10)).date()))&(paired.end<str(start.date()))]
    scores=[]
    for t in thresholds:
        part=train[train.threshold==t]
        if len(part)<12:break
        scores.append((part.CAGR.mean(),-part.stock_orders_per_year.mean(),-t,len(part)))
    if len(scores)!=len(thresholds):continue
    chosen=-max(scores)[2]
    selections.append({'start':str(start.date()),'train_last_end':train.end.max(),'train_n':max(scores)[3],
                       'chosen_threshold':chosen})
    for t in (0,*thresholds):
        m=simulate(t,start,finish);m.update(chosen_threshold=chosen,selected=(t==chosen));oos.append(m)
pd.DataFrame(selections).to_csv(ROOT/'drawdown_entry_oos_selections.csv',index=False)
pd.DataFrame(oos).to_csv(ROOT/'drawdown_entry_oos.csv',index=False)

# Cost sensitivity on fixed decisions, not a fresh parameter search.
cost_results=[]
for t in (0,*thresholds):
    for cost in (0.,.001,.0025):
        for name,(a,z) in periods.items():
            m=simulate(t,a,z,cost);m['period']=name;cost_results.append(m)
pd.DataFrame(cost_results).to_csv(ROOT/'drawdown_entry_cost_sensitivity.csv',index=False)
print(f'{len(base)} matched five-year cohorts; {len(selections)} forward selections')
