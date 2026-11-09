"""Fixed-horizon buy-and-hold cohorts, using information before entry."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT
stock,splits,_=bt.load_chart('NVDA')
cash,_,_=bt.load_chart('BIL')
idx=stock.index.intersection(cash.index)
stock,cash=stock.loc[idx],cash.loc[idx]
x,_=bt.signals(stock,bt.pit_fundamentals('NVDA',splits))
x['rank3']=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
end=pd.Timestamp('2026-11-06')
hold=pd.Series(True,index=idx)
rows=[]
for n in (1,3,5):
    for year in range(2013,2027):
        dates=idx[(idx.year==year)&(idx<=end)]
        if not len(dates): continue
        start=dates[0]
        finish=start+pd.DateOffset(years=n)-pd.Timedelta(days=1)
        if finish>end: continue
        prev=idx[idx<start][-1]
        m,_,_=bt.simulate(stock,cash,hold,start,finish,ticker='NVDA',strategy='buy_hold')
        m.update(start_year=year,holding_years=n,valuation_date=str(prev.date()),
                 entry_pe=float(x.loc[prev,'PE']),entry_percentile=float(x.loc[prev,'rank3']))
        rows.append(m)
out=pd.DataFrame(rows)
out.to_csv(ROOT/'buy_hold_cohorts.csv',index=False)
summary=[]
for n,d in out.groupby('holding_years'):
    # Retrospective median split: descriptive, not investable thresholds.
    for factor in ('entry_pe','entry_percentile'):
        threshold=d[factor].median()
        for group,chunk in [('low',d[d[factor]<=threshold]),('high',d[d[factor]>threshold])]:
            summary.append({'years':n,'factor':factor,'group':group,'n':len(chunk),'threshold':threshold,
                            'median_cagr':chunk.CAGR.median(),'mean_cagr':chunk.CAGR.mean(),
                            'median_drawdown':chunk.max_drawdown.median(),
                            'worst_drawdown':chunk.max_drawdown.min(),
                            'correlation':d[[factor,'CAGR']].corr(method='spearman').iloc[0,1]})
pd.DataFrame(summary).to_csv(ROOT/'buy_hold_cohort_summary.csv',index=False)
