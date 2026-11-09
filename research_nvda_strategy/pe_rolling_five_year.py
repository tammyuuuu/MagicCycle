"""Summarize equal-start/end five-year cohorts against immediate entry."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
source=pd.read_csv(ROOT/'pe_entry_grid_cohorts.csv')
data=source[source.horizon==5].copy()
keys=['start','end']
expected={0,30,40,50,60,70}
if data.duplicated(keys+['threshold']).any():raise ValueError('duplicate cohort')
for _,group in data.groupby(keys):
    if set(group.threshold)!=expected:raise ValueError('window missing a comparator')
base=data[data.threshold==0].set_index(keys)
rows=[];paired=[]
for threshold in sorted(expected):
    part=data[data.threshold==threshold].copy().set_index(keys).sort_index()
    benchmark=base.reindex(part.index)
    if benchmark.CAGR.isna().any():raise ValueError('unpaired cohort')
    part['benchmark_cagr']=benchmark.CAGR
    part['benchmark_drawdown']=benchmark.max_drawdown
    part['delta_cagr']=part.CAGR-benchmark.CAGR
    part['delta_drawdown']=part.max_drawdown-benchmark.max_drawdown
    n=len(part);eps=1e-10
    win=int((part.delta_cagr>eps).sum());loss=int((part.delta_cagr< -eps).sum());tie=n-win-loss
    rows.append({'threshold':threshold,'n':n,'first_start':part.reset_index().start.min(),'last_start':part.reset_index().start.max(),
      'mean_cagr':part.CAGR.mean(),'median_cagr':part.CAGR.median(),
      'mean_drawdown':part.max_drawdown.mean(),'median_drawdown':part.max_drawdown.median(),
      'worst_drawdown':part.max_drawdown.min(),'mean_wait_sessions':part.wait_sessions.mean(),
      'median_wait_sessions':part.wait_sessions.median(),'entered':int(part.bought.sum()),
      'not_entered':int((~part.bought).sum()),'total_stock_entries':int(part.stock_orders.sum()),
      'win':win,'loss':loss,'tie':tie,'win_rate':win/n,'median_delta_cagr':part.delta_cagr.median(),
      'less_drawdown':int((part.delta_drawdown>eps).sum()),'less_drawdown_rate':(part.delta_drawdown>eps).mean()})
    paired.append(part.reset_index())
pd.DataFrame(rows).to_csv(ROOT/'pe_rolling_5y_summary.csv',index=False)
pd.concat(paired,ignore_index=True).to_csv(ROOT/'pe_rolling_5y_paired.csv',index=False)
recent=pd.read_csv(ROOT/'pe_entry_grid_metrics.csv')
recent=recent[recent.period.isin(['1y','3y','5y'])].copy()
recent.to_csv(ROOT/'pe_recent_aligned.csv',index=False)
print(f'{len(base)} matched five-year start dates; {len(recent)} recent results')
