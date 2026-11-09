"""Point-in-time factor diagnostics and annual walk-forward research.

Uses the frozen original NVDA and BIL inputs. This is exploratory research,
not a prospective out-of-sample experiment or a live signal generator.
"""
import json
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
end=pd.Timestamp('2026-11-06')
stock,cash=stock.loc[:end],cash.loc[:end]
idx=stock.index
fund=bt.pit_fundamentals('NVDA',splits)
x,_=bt.signals(stock,fund)
x['eps_pit']=x.ttm_net_income/x.diluted_shares
x.loc[(x.index-x.period_end).dt.days.gt(190)|(x.index-x.share_end).dt.days.gt(190),'eps_pit']=np.nan
# Compare with the TTM diluted EPS that was actually available one calendar
# year earlier; unlike a later restatement it cannot see future filings.
prior=pd.merge_asof(pd.DataFrame({'lookup':x.index-pd.Timedelta(days=365)}).sort_values('lookup'),
                    x[['eps_pit']].reset_index(names='date'),left_on='lookup',right_on='date',direction='backward')
previous=pd.Series(prior.eps_pit.to_numpy(),index=x.index)
x['eps_growth']=x.eps_pit/previous-1
x.loc[(previous<=0)|(x.eps_pit<=0),'eps_growth']=np.nan
x['peg']=x.PE/(100*x.eps_growth)
x.loc[(x.eps_growth<=0)|(x.PE<=0),'peg']=np.nan
# Independent of the MSFT choice: three-year history, 18 months minimum.
x['pe_rank_3y']=x.PE.rolling(756,min_periods=378).apply(
    lambda a: np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
x['trend_200']=stock.close>stock.close.rolling(200).mean()

# Month-end decisions; the final partial month is not treated as month-end.
month_indices=[i for i in range(len(idx)-1) if idx[i].month!=idx[i+1].month]
monthly=x.iloc[month_indices].copy()
monthly=monthly.loc['2013-01-01':]
monthly['entry_date']=[idx[idx.get_loc(day)+1] for day in monthly.index]
for horizon in (1,3,6,12):
    values=[]; dates=[]
    for day,entry in zip(monthly.index,monthly.entry_date):
        exit_month=day.to_period('M')+horizon
        candidates=[i for i in month_indices if idx[i].to_period('M')==exit_month]
        if not candidates or candidates[-1]+1>=len(idx): values.append(np.nan);dates.append(pd.NaT);continue
        finish=idx[candidates[-1]+1]
        values.append(stock.loc[finish,'adjopen']/stock.loc[entry,'adjopen']-1)
        dates.append(finish)
    monthly[f'return_{horizon}m']=values; monthly[f'exit_{horizon}m']=dates
monthly.index.name='signal_date'
monthly.to_csv(ROOT/'factor_observations.csv')

# Fit factor thresholds only on past observations with outcomes already known.
# Expanding training window; refit at the first signal of each calendar year.
diagnostics=[]; predictions=[]
for factor in ('PE','pe_rank_3y','eps_growth','peg'):
    for h in (1,3,6,12):
        valid=monthly[[factor,f'return_{h}m',f'exit_{h}m']].dropna()
        for year in range(2018,2027):
            cut=pd.Timestamp(year,1,1)
            train=valid[(valid.index<cut)&(valid[f'exit_{h}m']<cut)]
            test=valid[valid.index.year==year]
            if len(train)<36: continue
            lo,hi=train[factor].quantile([1/3,2/3])
            for day,row in test.iterrows():
                predictions.append(dict(factor=factor,horizon_months=h,signal_date=day,year=year,
                    value=row[factor],ret=row[f'return_{h}m'],exit_date=row[f'exit_{h}m'],
                    train_n=len(train),train_last_exit=train[f'exit_{h}m'].max(),
                    bucket='low' if row[factor]<=lo else 'high' if row[factor]>=hi else 'middle'))
pred=pd.DataFrame(predictions)
pred.to_csv(ROOT/'factor_oos_observations.csv',index=False)
for (factor,h),df in pred.groupby(['factor','horizon_months']):
    low=df[df.bucket=='low'].ret;high=df[df.bucket=='high'].ret
    diagnostics.append({'factor':factor,'horizon_months':h,'n':len(df),
       'rank_correlation':df[['value','ret']].corr(method='spearman').iloc[0,1],
       'low_n':len(low),'low_mean':low.mean(),'high_n':len(high),'high_mean':high.mean(),
       'high_minus_low':high.mean()-low.mean(),'start':str(df.signal_date.min().date()),'end':str(df.signal_date.max().date())})
pd.DataFrame(diagnostics).to_csv(ROOT/'factor_oos_summary.csv',index=False)

# Fixed candidate family specified as a diagnostic before comparing results.
# Exit/entry at month-end; missing input -> cash. Thresholds are economic
# hypotheses, not the MSFT 40/80 configuration.
def strategy(kind, low=.5, high=.9, peg_buy=1.5, peg_sell=3):
    state=False; out=[]
    for i,(day,row) in enumerate(x.iterrows()):
        out.append(state)
        if i==len(idx)-1 or day.month==idx[i+1].month: continue
        growth=row.eps_growth; pe=row.PE; rank=row.pe_rank_3y; peg=row.peg
        if kind=='trend':
            state=bool(row.close>row.SMA) if pd.notna(row.SMA) else False
        elif kind=='rank_growth':
            if pd.isna(rank) or pd.isna(growth) or growth<=0 or rank>=high: state=False
            elif rank<=low: state=True
        elif kind=='peg':
            if pd.isna(peg) or peg>=peg_sell: state=False
            elif peg<=peg_buy: state=True
        elif kind=='growth_trend':
            if pd.isna(growth) or pd.isna(row.SMA) or growth<=0 or not row.trend_200: state=False
            else: state=True
    return pd.Series(out,index=idx)

candidate={name:strategy(name) for name in ('rank_growth','peg','growth_trend','trend')}
candidate['buy_hold']=pd.Series(True,index=idx)
# Expanding walk-forward: train from 2013 through previous year; annual
# selection maximizes training CAGR, then fewer stock orders. Each Jan switch
# pays normal costs; inherited candidate states use no future information.
walks={}; selections=[]
for mode in ('expanding','rolling_5y'):
    walk=pd.Series(False,index=idx)
    for year in range(2018,2027):
        train_start=pd.Timestamp('2013-01-02') if mode=='expanding' else pd.Timestamp(year-5,1,1)
        train_end=pd.Timestamp(year-1,12,31)
        ranked=[]
        for name,target in candidate.items():
            metrics,_,_=bt.simulate(stock,cash,target,train_start,train_end,ticker='NVDA',strategy=name)
            ranked.append((metrics['CAGR'],-metrics['stock_orders_per_year'],name))
        best=max(ranked)[2]
        year_mask=walk.index.year==year
        walk.loc[year_mask]=candidate[best].loc[year_mask]
        selections.append({'mode':mode,'year':year,'chosen':best,'train_start':str(train_start.date()),'train_end':str(train_end.date()),'train_cagr':max(ranked)[0]})
    walks[mode]=walk
pd.DataFrame(selections).to_csv(ROOT/'walkforward_selections.csv',index=False)
candidate['walkforward']=walks['expanding']
candidate['walkforward_5y']=walks['rolling_5y']
pd.DataFrame(candidate).to_csv(ROOT/'factor_open_targets.csv',index_label='date')
periods={'full':('2013-01-02',end),'walk_oos':('2018-01-01',end)}
for n in (1,3,5): periods[f'{n}y']=(end-pd.DateOffset(years=n),end)
metrics=[]; ledger=[]
for name,target in candidate.items():
    for label,(start,finish) in periods.items():
        if name.startswith('walkforward') and label=='full': continue
        m,_,trades=bt.simulate(stock,cash,target,start,finish,ticker='NVDA',strategy=name,ledger=label==('walk_oos' if name.startswith('walkforward') else 'full'))
        m['period']=label;metrics.append(m);ledger.extend(trades)
pd.DataFrame(metrics).to_csv(ROOT/'factor_strategy_metrics.csv',index=False)
pd.DataFrame(ledger).to_csv(ROOT/'factor_strategy_trades.csv',index=False)

# Neighbouring thresholds are diagnostics, not re-optimized OOS choices.
sensitivity=[]
for name,target in [('rank_40_90',strategy('rank_growth',low=.4,high=.9)),
                    ('rank_50_80',strategy('rank_growth',low=.5,high=.8)),
                    ('rank_50_90',strategy('rank_growth')),
                    ('rank_60_90',strategy('rank_growth',low=.6,high=.9)),
                    ('peg_1_3',strategy('peg',peg_buy=1,peg_sell=3)),
                    ('peg_1.5_3',strategy('peg')),
                    ('peg_2_3',strategy('peg',peg_buy=2,peg_sell=3))]:
    for label,(start,finish) in periods.items():
        m,_,_=bt.simulate(stock,cash,target,start,finish,ticker='NVDA',strategy=name)
        m['period']=label;sensitivity.append(m)
pd.DataFrame(sensitivity).to_csv(ROOT/'factor_sensitivity.csv',index=False)
# Remove one specific complete cash interval, leaving all other target dates
# unchanged. These are post-hoc attribution diagnostics, not trading rules.
attribution=[]
for name,start_cash,end_cash in [('rank_growth','2022-12-01','2023-12-01'),
                                 ('peg','2022-10-03','2023-12-01'),
                                 ('trend','2018-11-01','2019-08-01')]:
    modified=candidate[name].copy()
    modified.loc[(modified.index>=pd.Timestamp(start_cash))&(modified.index<pd.Timestamp(end_cash))]=True
    for label,(start,finish) in periods.items():
        for kind,target in [('original',candidate[name]),('remove_one_cash_interval',modified)]:
            m,_,_=bt.simulate(stock,cash,target,start,finish,ticker='NVDA',strategy=name)
            m.update(period=label,scenario=kind,interval_start=start_cash,interval_end=end_cash)
            attribution.append(m)
pd.DataFrame(attribution).to_csv(ROOT/'factor_attribution.csv',index=False)
print(json.dumps({'monthly_observations':len(monthly),'oos_factor_observations':len(pred),'annual_selections':selections},ensure_ascii=False,default=str))
