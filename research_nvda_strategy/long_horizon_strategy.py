"""Research-only long-horizon entries/exits and rolling historical validation."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import msft_monitor
bt=msft_monitor.bt
bt.ROOT=ROOT
stock,_,_=bt.load_chart('NVDA')
cash,_,_=bt.load_chart('BIL')
idx=stock.index.intersection(cash.index)
stock,cash=stock.loc[idx],cash.loc[idx]
end=pd.Timestamp('2026-11-06')
stock,cash=stock.loc[:end],cash.loc[:end]
idx=stock.index
obs=pd.read_csv(ROOT/'factor_observations.csv',parse_dates=['signal_date','entry_date']).set_index('signal_date')
obs=obs.loc[:end]

def rule_targets(entry, deterioration=-.5, extreme=.95, value_limit=60., pullback=.20):
    """Monthly entry, rare risk exit; missing inputs freeze existing position."""
    held=False; states=[]; decisions=[]
    for i,day in enumerate(idx):
        states.append(held)
        if day not in obs.index: continue
        r=obs.loc[day]
        growth=r.eps_growth; pe=r.PE; rank=r.pe_rank_3y; eps=r.eps_pit
        price=r.close; sma=r.SMA; dd=r.drawdown
        available=all(pd.notna(v) for v in (growth,pe,rank,eps,price,sma,dd))
        action='持有' if held else '观察';reason='条件未触发'
        # Negative earnings is observable even if growth is intentionally NaN.
        loss=pd.notna(eps) and eps<=0
        severe=pd.notna(growth) and growth<=deterioration
        expensive_weak=pd.notna(rank) and pd.notna(sma) and rank>=extreme and price<=sma
        if held and (loss or severe or expensive_weak):
            held=False;action='卖出';reason='盈利转亏' if loss else '盈利增长严重恶化' if severe else '极端高估且趋势走弱'
        elif not held and available:
            positive=growth>0
            buy=(positive and price>sma) if entry=='growth_trend' else (
                positive and rank<=.8 if entry=='value_growth' else (
                positive and dd>=pullback if entry=='pullback_growth' else
                positive and pe<=value_limit and price>sma))
            if buy: held=True;action='买入';reason=entry
        if day>=pd.Timestamp('2013-01-01'):
            decisions.append({'signal_date':str(day.date()),'action':action,'reason':reason,'held_after_signal':held,
                              'PE':pe,'PE_rank':rank,'eps_growth':growth,'price':price,'SMA':sma,'drawdown':dd,
                              'next_open':str(idx[i+1].date()) if i+1<len(idx) else ''})
    return pd.Series(states,index=idx),decisions

names=('growth_trend','value_growth','pullback_growth','balanced')
targets={};decisions=[]
for name in names:
    series,log=rule_targets(name);targets[name]=series
    decisions += [dict(strategy=name,**row) for row in log]
hold=pd.Series(True,index=idx)
periods={'full':('2013-01-02',end),'oos':('2018-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)

# Annual rolling selection of conditional rules only; buy-and-hold remains a
# comparator and cannot be selected. Switching models may trade in January.
walk=pd.Series(False,index=idx);selections=[]
for year in range(2018,2027):
    a=pd.Timestamp(year-5,1,1);z=pd.Timestamp(year-1,12,31)
    ranked=[]
    for name,series in targets.items():
        m,_,_=bt.simulate(stock,cash,series,a,z,ticker='NVDA',strategy=name)
        ranked.append((m['CAGR'],-m['stock_orders_per_year'],name))
    best=max(ranked)[2];mask=idx.year==year;walk.loc[mask]=targets[best].loc[mask]
    selections.append({'year':year,'train_start':str(a.date()),'train_end':str(z.date()),'chosen':best,'train_cagr':max(ranked)[0]})
targets['rolling_5y']=walk;targets['buy_hold']=hold
pd.DataFrame(targets).to_csv(ROOT/'long_horizon_targets.csv',index_label='date')
pd.DataFrame(decisions).to_csv(ROOT/'long_horizon_decisions.csv',index=False)
pd.DataFrame(selections).to_csv(ROOT/'long_horizon_selections.csv',index=False)
metrics=[];trades=[]
for name,target in targets.items():
    for period,(a,z) in periods.items():
        if name=='rolling_5y' and period=='full':continue
        m,_,ledger=bt.simulate(stock,cash,target,a,z,ticker='NVDA',strategy=name,
                               ledger=period==('oos' if name=='rolling_5y' else 'full'))
        m['period']=period;metrics.append(m);trades.extend(ledger)
pd.DataFrame(metrics).to_csv(ROOT/'long_horizon_metrics.csv',index=False)
pd.DataFrame(trades).to_csv(ROOT/'long_horizon_trades.csv',index=False)

# Each monthly observation initiates a fresh equal-length buy-and-hold cohort.
# Entry filters may overlap. Groups are descriptive, not independent or OOS.
hold=pd.Series(True,index=idx);cohorts=[]
for day,r in obs.iterrows():
    for n in (3,5):
        match=obs.index[obs.index.to_period('M')==day.to_period('M')+12*n]
        if len(match)!=1 or match[0]>end: continue
        start=r.entry_date;finish=match[0]
        if pd.isna(start) or start>finish:continue
        m,_,_=bt.simulate(stock,cash,hold,start,finish,ticker='NVDA',strategy='cohort')
        cohorts.append({'signal_date':str(day.date()),'start':m['start'],'end':m['end'],'years':n,
                        'PE':r.PE,'rank':r.pe_rank_3y,'growth':r.eps_growth,'drawdown':r.drawdown,
                        'above_ma':bool(r.close>r.SMA),'CAGR':m['CAGR'],'max_drawdown':m['max_drawdown']})
cohorts=pd.DataFrame(cohorts);cohorts.to_csv(ROOT/'long_horizon_cohorts.csv',index=False)
groups=[]
for n,data in cohorts.groupby('years'):
    conditions={'all':data.index==data.index,'pe_below_60':data.PE<=60,'pe_above_60':data.PE>60,
                'rank_low_half':data['rank']<=.5,'rank_high_half':data['rank']>.5,
                'growth_positive':data.growth>0,'growth_nonpositive':data.growth<=0,
                'pullback_20':data.drawdown>=.2,'not_pullback_20':data.drawdown<.2,
                'above_ma':data.above_ma,'below_ma':~data.above_ma,
                'balanced':(data.PE<=60)&(data.growth>0)&data.above_ma}
    for label,mask in conditions.items():
        subset=data[mask]
        groups.append({'years':n,'condition':label,'n':len(subset),'median_cagr':subset.CAGR.median(),
                       'median_drawdown':subset.max_drawdown.median(),'worst_drawdown':subset.max_drawdown.min(),
                       'start_min':subset.signal_date.min(),'start_max':subset.signal_date.max()})
pd.DataFrame(groups).to_csv(ROOT/'long_horizon_cohort_summary.csv',index=False)

nearby=[]
for variant,entry,kwargs in [('growth_guard_base','growth_trend',{}),
    ('growth_guard_30','growth_trend',{'deterioration':-.3}),('growth_guard_70','growth_trend',{'deterioration':-.7}),
    ('growth_guard_extreme90','growth_trend',{'extreme':.9}),('growth_guard_extreme98','growth_trend',{'extreme':.98}),
    ('balanced_pe50','balanced',{'value_limit':50}),('balanced_pe60','balanced',{}),('balanced_pe70','balanced',{'value_limit':70}),
    ('pullback15','pullback_growth',{'pullback':.15}),('pullback20','pullback_growth',{}),('pullback25','pullback_growth',{'pullback':.25})]:
    target,_=rule_targets(entry,**kwargs)
    for label,(a,z) in periods.items():
        m,_,_=bt.simulate(stock,cash,target,a,z,ticker='NVDA',strategy=variant);m['period']=label;nearby.append(m)
pd.DataFrame(nearby).to_csv(ROOT/'long_horizon_sensitivity.csv',index=False)
# Attribution: remove the complete 2023 cash interval, leaving all other
# targets unchanged. It is not a prospective signal or implementable rule.
attribution=[]
for name in names:
    entries=[row for row in decisions if row['strategy']==name and row['action']=='买入' and row['signal_date']>'2023-03-31']
    if not entries: continue
    rebuy=pd.Timestamp(entries[0]['next_open']); sold=pd.Timestamp('2023-04-03')
    alt=targets[name].copy();alt.loc[(idx>=sold)&(idx<rebuy)]=True
    for period,(a,z) in periods.items():
        for scenario,series in [('original',targets[name]),('skip_2023_exit',alt)]:
            m,_,_=bt.simulate(stock,cash,series,a,z,ticker='NVDA',strategy=name)
            m.update(period=period,scenario=scenario,sell_date=str(sold.date()),rebuy_date=str(rebuy.date()))
            attribution.append(m)
pd.DataFrame(attribution).to_csv(ROOT/'long_horizon_attribution.csv',index=False)
costs=[]
for name in ('value_growth','growth_trend','rolling_5y','buy_hold'):
    for cost in (0,.001,.0025):
        for period in ('full','oos','5y'):
            if name=='rolling_5y' and period=='full':continue
            a,z=periods[period]
            m,_,_=bt.simulate(stock,cash,targets[name],a,z,cost=cost,ticker='NVDA',strategy=name)
            m['period']=period;costs.append(m)
pd.DataFrame(costs).to_csv(ROOT/'long_horizon_costs.csv',index=False)
print(f'{len(cohorts)} complete cohorts; {len(decisions)} monthly decisions; rolling 2018-2026')
