"""Exploratory MSFT comparison using the frozen 2026-11-07 research engine."""
import sys
from pathlib import Path
import pandas as pd

SOURCE = Path(r'D:\file\fun\code\cycle-actions-test\stock_research')
sys.path.insert(0, str(SOURCE))
import timing_backtest_20261107 as bt

stock, splits, _ = bt.load_chart('MSFT')
cash, _, _ = bt.load_chart('BIL')
common = stock.index.intersection(cash.index)
stock, cash = stock.loc[common], cash.loc[common]
x, targets = bt.signals(stock, bt.pit_fundamentals('MSFT', splits))
# Momentum override: enter when a strong twelve-month advance suggests that
# waiting for cheap valuation may be costly; exit only at high valuation AND
# negative twelve-month momentum. Monthly decisions, next-open execution.
momentum = stock.close / stock.close.shift(252) - 1
states = []
held = False
for i, (date, row) in enumerate(x.iterrows()):
    states.append(held)
    if i == len(x)-1 or date.month == x.index[i+1].month:
        continue
    mom = momentum.iloc[i]
    if not row.valuation_valid or pd.isna(mom):
        held = False
    elif row.PE_rank >= .8 and mom < 0:
        held = False
    elif row.PE_rank <= .4 or mom > .2:
        held = True
targets['valuation_momentum'] = states
# A trend filter prevents selling solely because valuation is high; a return
# to a rising trend permits re-entry without waiting for cheap valuation.
for mode in ('expensive_downtrend', 'valuation_or_trend'):
    states=[]; held=False
    for i,(date,row) in enumerate(x.iterrows()):
        states.append(held)
        if i == len(x)-1 or date.month == x.index[i+1].month: continue
        if not row.valuation_valid or pd.isna(row.SMA): held=False; continue
        trend = row.close > row.SMA
        if row.PE_rank >= .8 and not trend: held=False
        elif row.PE_rank <= .4 or (mode == 'valuation_or_trend' and trend): held=True
    targets[mode]=states
end = pd.Timestamp('2026-11-06')
periods = {'full': ('2013-01-02', end), '2013_2019': ('2013-01-02','2019-12-31'),
           '2020_2023': ('2020-01-01','2023-12-31'), '2024_2026': ('2024-01-01',end),
           '2020_2026': ('2020-01-01',end)}
for n in (1,3,5): periods[f'{n}y'] = (end-pd.DateOffset(years=n),end)
rows=[]
for period,(start,finish) in periods.items():
    for name in targets:
        m,_,_ = bt.simulate(stock,cash,targets[name],start,finish,strategy=name)
        m['period']=period
        rows.append(m)
pd.DataFrame(rows).to_csv(Path(__file__).with_name('comparison.csv'),index=False)
trades=[]; rolling=[]
for name in targets:
    _,_,ledger=bt.simulate(stock,cash,targets[name],'2013-01-02',end,strategy=name,ledger=True)
    trades.extend(ledger)
    for years in (1,3,5):
        for year in range(2013, 2027-years):
            a=pd.Timestamp(year,1,1); z=a+pd.DateOffset(years=years)-pd.Timedelta(days=1)
            if z>end: continue
            m,_,_=bt.simulate(stock,cash,targets[name],a,z,strategy=name)
            m['window_years']=years; rolling.append(m)
pd.DataFrame(trades).to_csv(Path(__file__).with_name('trades.csv'),index=False)
pd.DataFrame(rolling).to_csv(Path(__file__).with_name('rolling.csv'),index=False)
