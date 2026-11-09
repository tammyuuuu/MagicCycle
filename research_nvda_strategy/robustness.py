"""Sensitivity and attribution diagnostics; not a strategy-selection search."""
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
end=pd.Timestamp('2026-11-06')
periods={'full':('2013-01-02',end),'pre_2020':('2013-01-02','2019-12-31'),
         'post_2020':('2020-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)

def monthly(condition):
    held=False; out=[]
    for i,date in enumerate(stock.index):
        out.append(held)
        if i<len(stock.index)-1 and date.month!=stock.index[i+1].month:
            held=bool(condition.iloc[i]) if pd.notna(condition.iloc[i]) else False
    return pd.Series(out,index=stock.index)

variants={}
for days in (189,252,315):
    momentum=stock.close/stock.close.shift(days)-1
    condition=momentum.gt(0).where(momentum.notna())
    variants[f'momentum_{days}']=monthly(condition)
for days in (150,200,250):
    ma=stock.close.rolling(days).mean()
    variants[f'trend_{days}']=monthly(stock.close.gt(ma).where(ma.notna()))
# Counterfactual: remove the most recent selling event only. This is an
# attribution experiment, not an implementable strategy or a new signal.
counterfactual=variants['momentum_252'].copy()
counterfactual.loc['2026-11-02':]=True
variants['momentum_252_without_last_sale']=counterfactual
rows=[]; trade_rows=[]
for name,target in variants.items():
    for cost in (0,.001,.0025):
        for period,(start,finish) in periods.items():
            m,_,ledger=bt.simulate(stock,cash,target,start,finish,cost=cost,ticker='NVDA',strategy=name,ledger=period=='full' and cost==.001)
            m.update(period=period,variant=name);rows.append(m);trade_rows.extend(ledger)
pd.DataFrame(rows).to_csv(ROOT/'robustness_metrics.csv',index=False)
pd.DataFrame(trade_rows).to_csv(ROOT/'robustness_trades.csv',index=False)
