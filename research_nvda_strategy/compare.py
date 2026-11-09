"""Exploratory NVDA comparison; historical choices are not out of sample."""
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT
stock,splits,_=bt.load_chart('NVDA')
cash,_,_=bt.load_chart('BIL')
index=stock.index.intersection(cash.index)
stock,cash=stock.loc[index],cash.loc[index]
x,targets=bt.signals(stock,bt.pit_fundamentals('NVDA',splits))
# Predefined monthly risk controls: absolute 12-month momentum, and the
# conjunction/disjunction of momentum and the original 200-day trend.
mom=stock.close / stock.close.shift(252)-1
for name in ('momentum12','trend_and_momentum','trend_or_momentum'):
    held=False; state=[]
    for i,(date,row) in enumerate(x.iterrows()):
        state.append(held)
        if i==len(x)-1 or date.month==x.index[i+1].month: continue
        valid=pd.notna(mom.iloc[i]) and pd.notna(row.SMA)
        trend=row.close>row.SMA
        positive=mom.iloc[i]>0
        held=bool(valid and (positive if name=='momentum12' else trend and positive if name=='trend_and_momentum' else trend or positive))
    targets[name]=state
end=pd.Timestamp('2026-11-06')
periods={'full':('2013-01-02',end),'2013_2019':('2013-01-02','2019-12-31'),
         '2020_2026':('2020-01-01',end),'2024_2026':('2024-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
results=[]; trades=[]; windows=[]
for name in targets:
    for period,(a,b) in periods.items():
        m,_,ledger=bt.simulate(stock,cash,targets[name],a,b,ticker='NVDA',strategy=name,ledger=period=='full')
        m['period']=period; results.append(m); trades.extend(ledger)
    for n in (1,3,5):
        for year in range(2013,2027-n):
            start=pd.Timestamp(year,1,1); finish=start+pd.DateOffset(years=n)-pd.Timedelta(days=1)
            m,_,_=bt.simulate(stock,cash,targets[name],start,finish,ticker='NVDA',strategy=name)
            m['window_years']=n; windows.append(m)
pd.DataFrame(results).to_csv(ROOT/'metrics.csv',index=False)
pd.DataFrame(trades).to_csv(ROOT/'trades.csv',index=False)
pd.DataFrame(windows).to_csv(ROOT/'windows.csv',index=False)
(ROOT/'sources.json').write_text(json.dumps({'source':'stock_research/timing_backtest_20261107/raw',
    'research_date':'2026-11-07','sample_end':'2026-11-06',
    'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'raw').glob('*.json'))}},indent=2),encoding='utf8')
