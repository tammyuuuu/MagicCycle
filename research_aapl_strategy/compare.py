"""AAPL exploratory comparison; fixed historical data, no live signals."""
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
fund=bt.pit_fundamentals('AAPL',splits)
x,base=bt.signals(stock,fund)
rank=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
month_end=np.array([i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month])
conditions={'pe_50':rank.iloc[month_end].le(.5).to_numpy(),
            'drawdown_20':x.drawdown.iloc[month_end].ge(.2).to_numpy()}
entries={name:month_end[mask]+1 for name,mask in conditions.items()}

def simulate(name,start,finish,ledger=False):
    dates=idx[(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(finish))]
    a=idx.get_loc(dates[0]);z=idx.get_loc(dates[-1]);buy=None
    if name=='buy_hold':target=pd.Series(True,index=idx);buy=a
    elif name=='trend':target=base['trend']
    else:
        candidates=entries[name];candidates=candidates[(candidates>=a)&(candidates<=z)]
        target=pd.Series(False,index=idx)
        if len(candidates):buy=int(candidates[0]);target.iloc[buy:]=True
    result,_,trades=bt.simulate(stock,cash,target,dates[0],dates[-1],ticker='AAPL',strategy=name,ledger=ledger)
    result.update(buy_date=str(idx[buy].date()) if buy is not None else '',
                  wait_sessions=(buy-a if buy is not None else len(dates)) if name!='trend' else None)
    return result,trades

periods={'full':('2013-01-02',end),'2013_2019':('2013-01-02','2019-12-31'),
         '2020_2026':('2020-01-01',end)}
for n in (1,3,5):periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
rows=[];trades=[]
for name in ('buy_hold','pe_50','drawdown_20','trend'):
    for period,(a,z) in periods.items():
        m,ledger=simulate(name,a,z,ledger=period=='full')
        m['period']=period;rows.append(m);trades.extend(ledger)
pd.DataFrame(rows).to_csv(ROOT/'metrics.csv',index=False)
pd.DataFrame(trades).to_csv(ROOT/'trades.csv',index=False)
x.loc['2013-01-02':,['PE','PE_rank','period_end','share_end','filed','effective','valuation_valid']].to_csv(ROOT/'pit_audit.csv',index_label='date')
print('latest',idx[-1].date(),'valid_valuation_days',int(x.loc['2013-01-02':].valuation_valid.sum()),'total',len(x.loc['2013-01-02':]),'filings',len(fund))
