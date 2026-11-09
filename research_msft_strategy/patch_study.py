"""Exploratory, retrospective MSFT entry patches, using the original simulator."""
import sys
from pathlib import Path
import pandas as pd

SOURCE = Path(r'D:\file\fun\code\cycle-actions-test\stock_research')
sys.path.insert(0, str(SOURCE))
import timing_backtest_20261107 as bt

OUT = Path(__file__).parent
stock, splits, _ = bt.load_chart('MSFT')
cash, _, _ = bt.load_chart('BIL')
idx = stock.index.intersection(cash.index)
stock, cash = stock.loc[idx], cash.loc[idx]
x, baseline = bt.signals(stock, bt.pit_fundamentals('MSFT', splits))

def targets(start, initial=False, reentry=False):
    """Each window is a new deployment: never use pre-deployment position."""
    dates = x.index[x.index >= pd.Timestamp(start)]
    held = False
    ever_bought = False
    result = pd.Series(False, index=x.index)
    for i, date in enumerate(dates):
        # For deployment use only previous day's available close, then open.
        if i == 0:
            previous = x.index[x.index < date]
            if initial and len(previous):
                row = x.loc[previous[-1]]
                held = bool(row.valuation_valid and row.close > row.SMA)
                ever_bought = held
        result.loc[date] = held
        if i == len(dates)-1 or date.month == dates[i+1].month:
            continue
        row=x.loc[date]
        if not row.valuation_valid or row.PE_rank >= .8:
            held=False
        elif row.PE_rank <= .4:
            held=True; ever_bought=True
        elif initial and not ever_bought and row.close > row.SMA:
            held=True; ever_bought=True
        elif reentry and ever_bought and row.close > row.SMA:
            held=True
    return result

names=['baseline','initial_trend','reentry_trend','both']
def get(name,start):
    # Original baseline is inherited, matching the published backtest. All
    # variants are independently restarted for deployment-window analysis.
    if name=='baseline': return baseline['valuation']
    return targets(start, initial=name in ('initial_trend','both'), reentry=name in ('reentry_trend','both'))

end=pd.Timestamp('2026-11-06')
periods={'full':('2013-01-02',end),'2013_2019':('2013-01-02','2019-12-31'),
         '2020_2026':('2020-01-01',end),'2024_2026':('2024-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
# For comparable period slices, inherit state from the same full deployment.
full={name:get(name,'2013-01-02') for name in names}
metrics=[]; trades=[]; rolling=[]
for name in names:
    for period,(a,z) in periods.items():
        m,_,ledger=bt.simulate(stock,cash,full[name],a,z,strategy=name,ledger=period=='full')
        m['period']=period; metrics.append(m); trades.extend(ledger)
    for years in (1,3,5):
        for year in range(2013,2027-years):
            a=pd.Timestamp(year,1,1); z=a+pd.DateOffset(years=years)-pd.Timedelta(days=1)
            m,_,_=bt.simulate(stock,cash,full[name],a,z,strategy=name)
            m['window_years']=years; rolling.append(m)
pd.DataFrame(metrics).to_csv(OUT/'patch_metrics.csv',index=False)
pd.DataFrame(trades).to_csv(OUT/'patch_trades.csv',index=False)
pd.DataFrame(rolling).to_csv(OUT/'patch_rolling.csv',index=False)
