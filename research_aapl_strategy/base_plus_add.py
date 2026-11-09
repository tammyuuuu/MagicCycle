"""AAPL base-position + funded-reserve additions, research only.

The primary account is funded with 2 units on day one: 1 AAPL and 1 BIL.
Additions transfer a fixed fraction of the initial AAPL unit from BIL.
Secondary cash-flow accounting replays the same additions as external flows.
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
x,_=bt.signals(stock,bt.pit_fundamentals('AAPL',splits))
rank=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
dd=1-stock.close/stock.close.rolling(252,min_periods=252).max()
month_end=np.array([i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month],dtype=int)
so=stock.adjopen.to_numpy();sc=stock.adjclose.to_numpy();bo=cash.adjopen.to_numpy();bc=cash.adjclose.to_numpy()
conditions={}
for v in (.15,.20,.25):conditions[f'dd_{int(v*100)}']=((dd>=v)&dd.notna()).to_numpy()
for v in (.4,.5,.6):conditions[f'pe_{int(v*100)}']=((rank<=v)&rank.notna()).to_numpy()
for d in (.15,.20,.25):
    for p in (.4,.5,.6):conditions[f'both_{int(d*100)}_{int(p*100)}']=((dd>=d)&(rank<=p)&dd.notna()&rank.notna()).to_numpy()

def irr(flows,terminal,date_end):
    """Investor money-weighted XIRR: all contributions negative, terminal positive."""
    dates=np.array([(day-flows[0][0]).days/365.25 for day,_ in flows]+[(date_end-flows[0][0]).days/365.25])
    amounts=np.array([value for _,value in flows]+[terminal])
    def npv(r):return float(np.sum(amounts*np.exp(-dates*np.log1p(r))))
    lo=-.999999;hi=1.
    while npv(hi)>0 and hi<1e8:hi=2*hi+1
    if npv(hi)>0:return np.nan
    for _ in range(80):
        mid=(lo+hi)/2
        if npv(mid)>0:lo=mid
        else:hi=mid
    return (lo+hi)/2

def simulate(condition,tranche,start,finish,cost=.001,full_log=False):
    dates=idx[(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(finish))]
    if len(dates)<2:raise ValueError('empty window')
    a=idx.get_loc(dates[0]);z=idx.get_loc(dates[-1]);years=(dates[-1]-dates[0]).days/365.25
    all_in=condition=='all_in';base_plus=condition=='base_cash'
    stock_units=(2 if all_in else 1)*(1-cost)/so[a]
    cash_units=0. if all_in else (1-cost)/bo[a]
    # Isolated account with external additions: begin with a single stock unit;
    # replay exactly the funded-reserve account's executed addition schedule.
    ext_initial=2. if all_in else 1.
    ext_units=ext_initial*(1-cost)/so[a];flows=[(dates[0],-ext_initial)];ext_anchor=1-cost;ext_anchor_price=so[a]
    nav=np.empty(z-a+1);cash_nav=np.empty(z-a+1);ext_twr=np.empty(z-a+1)
    initial_cost=2*cost;spent=0.;events=[];prev=a;was_active=False
    candidate_days=month_end[(month_end+1>=a)&(month_end+1<=z)] if not (all_in or base_plus) else []
    for signal_i in candidate_days:
        active=bool(conditions[condition][signal_i])
        triggered=active and not was_active
        was_active=active
        if not triggered:continue
        i=signal_i+1
        if cash_units*bo[i]+1e-12<tranche:continue
        # Fill daily closes preceding this open using the holdings then in force.
        if i>prev:
            nav[prev-a:i-a]=stock_units*sc[prev:i]+cash_units*bc[prev:i]
            cash_nav[prev-a:i-a]=cash_units*bc[prev:i]
            ext_twr[prev-a:i-a]=ext_anchor*sc[prev:i]/ext_anchor_price
        cash_units-=tranche/bo[i]
        stock_units+=tranche*(1-cost)**2/so[i]
        pre=ext_units*so[i]; ext_before=ext_anchor*so[i]/ext_anchor_price
        ext_units+=tranche*(1-cost)/so[i]
        ext_anchor=ext_before*((pre+tranche*(1-cost))/(pre+tranche))
        ext_anchor_price=so[i]
        flows.append((idx[i],-tranche));spent+=tranche
        initial_cost+=tranche*(1-(1-cost)**2)
        events.append({'signal_date':str(idx[signal_i].date()),'trade_date':str(idx[i].date()),
                       'amount':tranche,'drawdown':float(dd.iloc[signal_i]),'pe_rank':float(rank.iloc[signal_i]) if pd.notna(rank.iloc[signal_i]) else None,
                       'reserve_after_open':float(cash_units*bo[i])})
        prev=i
    nav[prev-a:]=stock_units*sc[prev:z+1]+cash_units*bc[prev:z+1]
    cash_nav[prev-a:]=cash_units*bc[prev:z+1]
    ext_twr[prev-a:]=ext_anchor*sc[prev:z+1]/ext_anchor_price
    wealth=nav/2
    drawdown=float(np.min(wealth/np.maximum.accumulate(np.r_[1.,wealth])[1:]-1))
    twr=float(wealth[-1]**(1/years)-1)
    ext_final=float(ext_units*sc[z]);ext_irr=irr(flows,ext_final,idx[z]);ext_twr_cagr=float(ext_twr[-1]**(1/years)-1)
    m={'strategy':condition,'tranche':tranche,'start':str(dates[0].date()),'end':str(dates[-1].date()),'years':years,
       'twr_cagr':twr,'mwr_cagr':twr,'max_drawdown':drawdown,'final_nav':float(nav[-1]),
       'initial_committed':2.,'base_principal':2. if all_in else 1.,'reserve_principal':0. if all_in else 1.,
       'added_principal':spent,'add_count':len(events),'stock_orders':1+len(events),
       'all_orders':1 if all_in else 2+2*len(events),'total_cost':initial_cost,
       'mean_stock_exposure':float(np.mean(1-cash_nav/nav)), 'ending_cash':float(cash_nav[-1]),
       'external_initial':ext_initial,'external_contributed':ext_initial+spent,'external_final':ext_final,
       'external_mwr_cagr':ext_irr,'external_twr_cagr':ext_twr_cagr,
       'external_twr_drawdown':float(np.min(ext_twr/np.maximum.accumulate(np.r_[1.,ext_twr])[1:]-1))}
    return m,events if full_log else []

configs=[('all_in',0.),('base_cash',0.)]+[(name,size) for name in conditions for size in (.1,.25,.5)]
periods={'full':('2013-01-02',end)}
for n in (1,3,5):periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
metrics=[];logs=[]
for name,size in configs:
    for period,(a,z) in periods.items():
        m,events=simulate(name,size,a,z,full_log=period=='full');m['period']=period;metrics.append(m)
        logs += [dict(strategy=name,tranche=size,period=period,**event) for event in events]
pd.DataFrame(metrics).to_csv(ROOT/'base_add_metrics.csv',index=False)
pd.DataFrame(logs).to_csv(ROOT/'base_add_full_trades.csv',index=False)
starts=[idx[i+1] for i in month_end if idx[i+1]>=pd.Timestamp('2013-01-02')]
roll=[]
for start in starts:
    finish=start+pd.DateOffset(years=5)-pd.Timedelta(days=1)
    if finish>end:continue
    for name,size in configs:
        m,_=simulate(name,size,start,finish);roll.append(m)
roll=pd.DataFrame(roll);roll.to_csv(ROOT/'base_add_rolling_5y.csv',index=False)
ref=roll[roll.strategy=='base_cash'].set_index(['start','end'])
summaries=[]
for (name,size),group in roll.groupby(['strategy','tranche']):
    group=group.set_index(['start','end']);benchmark=ref.reindex(group.index)
    delta=group.twr_cagr-benchmark.twr_cagr;eps=1e-10
    summaries.append({'strategy':name,'tranche':size,'n':len(group),
       'mean_twr_cagr':group.twr_cagr.mean(),'median_twr_cagr':group.twr_cagr.median(),
       'median_max_drawdown':group.max_drawdown.median(),'worst_drawdown':group.max_drawdown.min(),
       'mean_add_count':group.add_count.mean(),'median_add_count':group.add_count.median(),
       'mean_stock_exposure':group.mean_stock_exposure.mean(),'mean_added_principal':group.added_principal.mean(),
       'mean_external_mwr':group.external_mwr_cagr.mean(),'mean_external_twr':group.external_twr_cagr.mean(),
       'wins_vs_base_cash':int((delta>eps).sum()),'losses_vs_base_cash':int((delta< -eps).sum()),
       'ties_vs_base_cash':int((delta.abs()<=eps).sum()),'median_excess_twr':delta.median()})
pd.DataFrame(summaries).to_csv(ROOT/'base_add_rolling_summary.csv',index=False)
print(f'{len(configs)} configurations; {len(starts)} candidate starts; {len(roll)//len(configs)} complete five-year cohorts')
