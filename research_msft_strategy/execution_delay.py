"""Compare frozen monthly signals executed later, without changing decisions.

Extra delay counts sessions after the original next-session open: 1/3/5/10
means execution at T+2/T+4/T+6/T+11. Run from any working directory.
"""
from pathlib import Path
import sys
import json
import hashlib
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import msft_monitor as monitor
bt=monitor.bt
bt.ROOT=HERE/'delay_inputs'
stock,splits,_=bt.load_chart('MSFT')
cash,_,_=bt.load_chart('BIL')
common=stock.index.intersection(cash.index)
stock=stock.loc[common]; cash=cash.loc[common]
_,targets=bt.signals(stock,bt.pit_fundamentals('MSFT',splits))
base=targets['valuation']
end=pd.Timestamp('2026-11-06')
periods={'full':('2013-01-02',end), '2013_2019':('2013-01-02','2019-12-31'),
         '2020_2026':('2020-01-01',end), '2024_2026':('2024-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
metrics=[]; trades=[]; windows=[]
for delay in (0,1,3,5,10):
    target=base.shift(delay,fill_value=False)
    for name,(start,finish) in periods.items():
        m,_,_=bt.simulate(stock,cash,target,start,finish,strategy=f'extra_{delay}')
        m.update(period=name,extra_delay=delay,signal_to_execution=delay+1); metrics.append(m)
    # Map each pre-existing decision to its delayed open. No resignal or retiming.
    changes=base.ne(base.shift(1,fill_value=False))
    for i in [i for i,v in enumerate(changes) if v]:
        j=i+delay
        if j>=len(common) or common[j]>end or common[j]<pd.Timestamp('2013-01-02'): continue
        trades.append({'signal_date':str(common[i-1].date()),'baseline_execution':str(common[i].date()),
                       'execution_date':str(common[j].date()),'action':'BUY' if base.iloc[i] else 'SELL',
                       'nominal_open':float(stock.open.iloc[j]*stock.future_split_factor.iloc[j]),'extra_delay':delay})
    for n in (1,3,5):
        for year in range(2013,2027-n):
            a=pd.Timestamp(year,1,1); z=a+pd.DateOffset(years=n)-pd.Timedelta(days=1)
            m,_,_=bt.simulate(stock,cash,target,a,z,strategy=f'extra_{delay}')
            m.update(window_years=n,extra_delay=delay); windows.append(m)
pd.DataFrame(metrics).to_csv(HERE/'delay_metrics.csv',index=False)
pd.DataFrame(trades).to_csv(HERE/'delay_trades.csv',index=False)
pd.DataFrame(windows).to_csv(HERE/'delay_windows.csv',index=False)
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((bt.ROOT/'raw').glob('*.json'))}
(HERE/'delay_provenance.json').write_text(json.dumps({'end':str(end.date()),'sha256':files,'cost_per_leg':.001,
 'semantics':'extra sessions after original next-session open; monthly decisions unchanged'},indent=2),encoding='utf8')
