"""Offline PIT two-stock timing experiment. No parameter optimization.

Inputs are immutable Yahoo chart and SEC companyfacts downloads; rules are frozen.
Run: python -X utf8 stock_research/timing_backtest_20261107.py
"""
import hashlib
import json
import datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
RULES=json.loads((ROOT/'rules.json').read_text(encoding='utf8'))
STRATEGIES=['buy_hold','valuation','drawdown','trend','valuation_trend']


def load_chart(ticker):
    raw=json.loads((ROOT/'raw'/f'{ticker}_chart.json').read_text(encoding='utf8'))['chart']['result'][0]
    q=raw['indicators']['quote'][0]
    d=pd.DataFrame({k:q[k] for k in ['open','close']},index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize())
    d['adjclose']=raw['indicators']['adjclose'][0]['adjclose']
    d['adjopen']=d.open*d.adjclose/d.close
    assert d.index.is_unique and d[['open','close','adjopen','adjclose']].notna().all().all()
    assert (d>0).all().all()
    splits=[]
    for event in raw.get('events',{}).get('splits',{}).values():
        date=pd.Timestamp(event['date'],unit='s',tz='UTC').tz_convert('America/New_York').tz_localize(None).normalize()
        splits.append((date,event['numerator']/event['denominator']))
    d['future_split_factor']=[np.prod([f for day,f in splits if day>x]) for x in d.index]
    return d,sorted(splits),raw.get('events',{})


def pit_fundamentals(ticker,splits):
    facts=json.loads((ROOT/'raw'/f'{ticker}_facts.json').read_text(encoding='utf8'))['facts']['us-gaap']
    def records(tag,unit):
        out=[]
        for x in facts[tag]['units'][unit]:
            if x.get('form') not in ['10-K','10-Q','10-K/A','10-Q/A'] or not x.get('start'):
                continue
            z={k:x.get(k) for k in ['start','end','filed','val','accn','form']}
            for k in ['start','end','filed']:
                z[k]=pd.Timestamp(z[k])
            z['days']=(z['end']-z['start']).days+1
            if z['days']<=380:
                out.append(z)
        return out
    income=records('NetIncomeLoss','USD')
    shares=records('WeightedAverageNumberOfDilutedSharesOutstanding','shares')
    all_filed=sorted(set(x['filed'] for x in income+shares))
    rows=[]
    for filed in all_filed:
        # A newer filing may revise past facts, but only affects subsequent signals.
        def available(xs):
            latest={}
            for x in sorted((x for x in xs if x['filed']<=filed),key=lambda x:x['filed']):
                latest[(x['start'],x['end'])]=x
            return list(latest.values())
        ni=available(income); sh=available(shares)
        if not ni or not sh:
            continue
        end=max(x['end'] for x in ni)
        current=sorted((x for x in ni if x['end']==end),key=lambda x:x['days'],reverse=True)[0]
        sources=[current]
        ttm=None
        if 330<=current['days']<=380:
            ttm=current['val']
        else:
            annuals=[x for x in ni if 330<=x['days']<=380 and abs((current['start']-x['end']).days-1)<=8]
            if annuals:
                annual=max(annuals,key=lambda x:x['end'])
                previous=[x for x in ni if abs((x['start']-annual['start']).days)<=8 and
                          abs((current['end']-x['end']).days-365)<=10 and abs(x['days']-current['days'])<=10]
                if previous:
                    prev=min(previous,key=lambda x:abs(x['days']-current['days']))
                    ttm=current['val']+annual['val']-prev['val']
                    sources += [annual,prev]
        quarterly_sh=[x for x in sh if (60<=x['days']<=110 or 330<=x['days']<=380) and x['end']<=end]
        if ttm is None or not quarterly_sh:
            continue
        share=max(quarterly_sh,key=lambda x:(x['end'],-x['days'],x['filed']))
        # Yahoo prices are retrospectively split-normalized. Normalize current
        # reported weighted shares to the same units. Future scaling cancels in PE.
        split=np.prod([factor for date,factor in splits if date>share['filed']])
        effective=filed+pd.offsets.BDay(2)
        rows.append(dict(effective=effective,filed=filed,period_end=end,ttm_net_income=ttm,
                         diluted_shares=share['val']*split,share_end=share['end'],
                         share_reported=share['val'],share_filed=share['filed'],future_share_factor=split,
                         share_duration_days=share['days'],
                         income_accessions=';'.join(x['accn'] for x in sources),
                         share_accession=share['accn'],latest_source_filed=max([x['filed'] for x in sources]+[share['filed']])))
    result=pd.DataFrame(rows).sort_values(['effective','filed']).drop_duplicates('effective',keep='last')
    assert (result.latest_source_filed<result.effective).all()
    return result


def signals(d,fundamentals,ma=200,buy_rank=.4,sell_rank=.8,dd_entry=.20,dd_exit=.05):
    x=pd.merge_asof(d.reset_index(names='date'),fundamentals,left_on='date',right_on='effective',direction='backward').set_index('date')
    stale=(x.index-x.period_end).dt.days.gt(190)|(x.index-x.share_end).dt.days.gt(190)
    x['PE']=x.close*x.diluted_shares/x.ttm_net_income
    x.loc[stale|(x.ttm_net_income<=0),'PE']=np.nan
    x['PE_rank']=x.PE.rolling(1260,min_periods=504).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
    x['SMA']=x.close.rolling(ma).mean()
    x['drawdown']=1-x.close/x.close.rolling(252).max()
    x['valuation_valid']=x.PE.notna()&x.PE_rank.notna()
    states={k:False for k in STRATEGIES};states['buy_hold']=True
    targets=[]
    # Signals computed at t close become target only at t+1 open.
    for i,(date,row) in enumerate(x.iterrows()):
        targets.append(states.copy())
        if i==len(x)-1 or date.month==x.index[i+1].month:
            continue
        valid=bool(row.valuation_valid)
        trend=bool(row.close>row.SMA)
        if not valid or row.PE_rank>=sell_rank:
            states['valuation']=False
        elif row.PE_rank<=buy_rank:
            states['valuation']=True
        if row.drawdown>=dd_entry:
            states['drawdown']=True
        elif row.drawdown<=dd_exit:
            states['drawdown']=False
        states['trend']=trend
        if not valid or row.PE_rank>=sell_rank or not trend:
            states['valuation_trend']=False
        elif row.PE_rank<=buy_rank and trend:
            states['valuation_trend']=True
    targets=pd.DataFrame(targets,index=x.index)
    return x,targets


def simulate(stock,cash,target,start,end,cost=.001,ticker='MSFT',strategy='',ledger=False):
    ix=stock.index[(stock.index>=pd.Timestamp(start))&(stock.index<=pd.Timestamp(end))]
    assert len(ix)>1
    s=stock.loc[ix];b=cash.loc[ix];t=target.loc[ix].astype(bool)
    equity=1.;held=None;nav=[];trades=[];cost_total=0;stock_orders=0;all_orders=0
    for i,date in enumerate(ix):
        wanted=bool(t.iloc[i])
        if wanted!=held:
            legs=1 if held is None else 2
            before=equity
            equity*=(1-cost)**legs
            cost_total+=before-equity
            all_orders+=legs
            if held is not None:
                old_asset=ticker if held else 'BIL'
                old=stock if held else cash
                trades.append(dict(date=str(date.date()),ticker=ticker,strategy=strategy,action='SELL',asset=old_asset,
                                   yahoo_split_adjusted_open=float(old.loc[date,'open']),
                                   reconstructed_nominal_open=float(old.loc[date,'open']*old.loc[date,'future_split_factor']),
                                   portfolio_NAV_before_switch=before,leg_cost_NAV=before*cost,
                                   reason='monthly_signal',signal_cutoff=str(stock.index[stock.index<date][-1].date())))
                if held:stock_orders+=1
            new=stock if wanted else cash
            trades.append(dict(date=str(date.date()),ticker=ticker,strategy=strategy,action='BUY',asset=ticker if wanted else 'BIL',
                               yahoo_split_adjusted_open=float(new.loc[date,'open']),
                               reconstructed_nominal_open=float(new.loc[date,'open']*new.loc[date,'future_split_factor']),
                               portfolio_NAV_before_switch=before,leg_cost_NAV=before*(1 if held is None else 1-cost)*cost,
                               reason='initial' if held is None else 'monthly_signal',
                               signal_cutoff=str(stock.index[stock.index<date][-1].date())))
            if wanted:stock_orders+=1
            held=wanted
        active=s if held else b
        close_nav=equity*active.adjclose.iloc[i]/active.adjopen.iloc[i]
        nav.append(close_nav)
        if i<len(ix)-1:
            equity*=active.adjopen.iloc[i+1]/active.adjopen.iloc[i]
    curve=pd.Series(nav,index=ix,name='NAV')
    years=((ix[-1]-ix[0]).days+1)/365.25
    peak=np.maximum.accumulate(np.r_[1.,curve.values])
    dd=np.r_[1.,curve.values]/peak-1
    metrics=dict(ticker=ticker,strategy=strategy,start=str(ix[0].date()),end=str(ix[-1].date()),years=years,
                 CAGR=curve.iloc[-1]**(1/years)-1,max_drawdown=float(dd.min()),ending_NAV=float(curve.iloc[-1]),
                 stock_orders=stock_orders,stock_orders_per_year=stock_orders/years,
                 all_orders=all_orders,all_orders_per_year=all_orders/years,stock_exposure=float(t.mean()),
                 cumulative_cost_NAV=cost_total,cost_per_leg=cost)
    return metrics,curve,trades if ledger else []


def main():
    data={};events={};split_events={}
    for symbol in ['MSFT','NVDA','QQQ','BIL']:
        data[symbol],split_events[symbol],events[symbol]=load_chart(symbol)
    common=data['MSFT'].index
    for d in data.values():common=common.intersection(d.index)
    for k in data:data[k]=data[k].loc[common]
    end=min(pd.Timestamp(RULES['requested_sample'][1]),common[-1])
    start=pd.Timestamp(RULES['requested_sample'][0])
    periods={'full':(start,end),'development_2013_2019':(start,pd.Timestamp('2019-12-31')),
             'pseudo_OOS_2020_end':(pd.Timestamp('2020-01-01'),end),
             'segment_2020_2023':(pd.Timestamp('2020-01-01'),pd.Timestamp('2023-12-31')),
             'late_holdout_2024_end':(pd.Timestamp('2024-01-01'),end)}
    for n in [1,3,5]:periods[f'trailing_{n}y']=(end-pd.DateOffset(years=n),end)
    all_metrics=[];all_trades=[];curves={};audit={};sensitivity=[];rolling=[]
    for ticker in ['MSFT','NVDA']:
        f=pit_fundamentals(ticker,split_events[ticker]);f.to_csv(ROOT/f'{ticker}_filing_snapshots.csv',index=False)
        x,targets=signals(data[ticker],f)
        x.to_csv(ROOT/f'{ticker}_daily_PIT_signals.csv',index_label='date')
        targets.to_csv(ROOT/f'{ticker}_open_targets.csv',index_label='date')
        used=x.loc[start:end]
        audit[ticker]=dict(snapshots=len(f),daily_rows=len(used),valid_valuation_days=int(used.valuation_valid.sum()),
                           missing_or_stale_days=int((~used.valuation_valid).sum()),
                           min_PE=float(used.PE.min()),max_PE=float(used.PE.max()),
                           last_PE=float(used.PE.iloc[-1]),last_ttm_profit=float(used.ttm_net_income.iloc[-1]),
                           last_shares=float(used.diluted_shares.iloc[-1]),splits=[(str(d.date()),v) for d,v in split_events[ticker]])
        for period,(a,z) in periods.items():
            for strategy in STRATEGIES:
                m,c,tr=simulate(data[ticker],data['BIL'],targets[strategy],a,z,ticker=ticker,strategy=strategy,ledger=period=='full')
                m['period']=period;all_metrics.append(m)
                if period=='full':
                    curves[ticker+'_'+strategy]=c
                    for trade in tr:
                        signal=x.loc[trade['signal_cutoff']]
                        for key in ['PE','PE_rank','SMA','drawdown','income_accessions','share_accession','filed']:
                            trade['signal_'+key]=signal[key]
                    all_trades+=tr
            # Same price and cost accounting for QQQ and cash baselines.
            for symbol in ['QQQ','BIL']:
                m,_,_=simulate(data[symbol],data['BIL'],pd.Series(True,index=common),a,z,ticker=ticker,strategy=symbol)
                m['period']=period;all_metrics.append(m)
        for cost in RULES['cost_sensitivity']:
            for strategy in STRATEGIES:
                m,_,_=simulate(data[ticker],data['BIL'],targets[strategy],start,end,cost,ticker,strategy)
                m['kind']='cost';sensitivity.append(m)
        # Neighbor checks are reported, never used to select production parameters.
        for ma in [150,250]:
            _,alt=signals(data[ticker],f,ma=ma)
            for strategy in ['trend','valuation_trend']:
                m,_,_=simulate(data[ticker],data['BIL'],alt[strategy],start,end,ticker=ticker,strategy=strategy)
                m.update(kind='MA_neighbor',parameter=ma);sensitivity.append(m)
        for rank in [.3,.5]:
            _,alt=signals(data[ticker],f,buy_rank=rank)
            for strategy in ['valuation','valuation_trend']:
                m,_,_=simulate(data[ticker],data['BIL'],alt[strategy],start,end,ticker=ticker,strategy=strategy)
                m.update(kind='PE_rank_neighbor',parameter=rank);sensitivity.append(m)
        for year in range(2013,end.year+1):
            a=pd.Timestamp(f'{year}-01-01')
            for n in [1,3,5]:
                z=pd.Timestamp(dt.date(year+n,1,1)-dt.timedelta(days=1))
                if z>end:continue
                for strategy in STRATEGIES:
                    m,_,_=simulate(data[ticker],data['BIL'],targets[strategy],a,z,ticker=ticker,strategy=strategy)
                    m['horizon_years']=n;rolling.append(m)
    metrics=pd.DataFrame(all_metrics)
    metrics['excess_CAGR_vs_buyhold']=metrics.CAGR-metrics.set_index(['ticker','period','strategy']).CAGR.reindex(pd.MultiIndex.from_arrays([metrics.ticker,metrics.period,['buy_hold']*len(metrics)])).values
    for benchmark in ['QQQ','BIL']:
        lookup=metrics[metrics.strategy==benchmark].set_index(['ticker','period']).CAGR
        metrics['excess_CAGR_vs_'+benchmark]=metrics.CAGR-lookup.reindex(pd.MultiIndex.from_frame(metrics[['ticker','period']])).values
    metrics.to_csv(ROOT/'metrics.csv',index=False)
    pd.DataFrame(all_trades).to_csv(ROOT/'trades.csv',index=False)
    pd.DataFrame(rolling).to_csv(ROOT/'rolling_windows.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(ROOT/'sensitivity.csv',index=False)
    pd.DataFrame(curves).to_csv(ROOT/'equity_curves.csv',index_label='date')
    (ROOT/'data_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for ticker in ['MSFT','NVDA']:
        fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,gridspec_kw={'height_ratios':[3,1]})
        for strategy in STRATEGIES:
            c=curves[ticker+'_'+strategy]
            axes[0].plot(c.index,c.values,label=strategy)
            axes[1].plot(c.index,c/np.maximum(1,c.cummax())-1,label=strategy)
        _,q,_=simulate(data['QQQ'],data['BIL'],pd.Series(True,index=common),start,end,ticker=ticker,strategy='QQQ')
        axes[0].plot(q.index,q.values,'--',color='gray',label='QQQ')
        axes[0].set_yscale('log');axes[0].set_ylabel('NAV (log scale)');axes[1].set_ylabel('Drawdown')
        axes[0].set_title(f'{ticker}: monthly timing, dividends + BIL cash, 10bp per leg')
        axes[0].legend(ncol=3);axes[0].grid(alpha=.25);axes[1].grid(alpha=.25)
        fig.tight_layout();fig.savefig(ROOT/f'{ticker}_returns.png',dpi=160);plt.close(fig)
    # Hash reproducible outputs, excluding manifest timestamp and the hash file itself.
    names=['rules.json','metrics.csv','trades.csv','rolling_windows.csv','sensitivity.csv','equity_curves.csv','data_audit.json']
    names += [ticker+suffix for ticker in ['MSFT','NVDA'] for suffix in ['_filing_snapshots.csv','_daily_PIT_signals.csv','_open_targets.csv','_returns.png']]
    outputs=[ROOT/name for name in names]
    (ROOT/'output_hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(outputs)},indent=2)+'\n',encoding='utf8')
    print(metrics[metrics.period.isin(['full','pseudo_OOS_2020_end'])][['ticker','strategy','period','CAGR','max_drawdown','stock_orders_per_year','stock_exposure']].to_string(index=False))
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
