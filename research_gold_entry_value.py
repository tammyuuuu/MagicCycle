"""买入择时的仓位匹配检验、冻结跨周期检验与无前视相似状态研究。"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from research_gold_full_cycle import Rule,features,simulate,statistics

OUT=Path('results/gold_entry_value')
SOURCE=Path('results/gold_full_cycle/data')
ASOF=pd.Timestamp('2026-10-29')
CASH=100000.
RULES={
    'immediate':Rule('buy_hold'),
    'trend':Rule('entry_trend','trend','full','none'),
    'pullback':Rule('entry_pullback','pullback','full','none'),
    'stage50':Rule('stage50','immediate','half','none'),
    'trend_stage50':Rule('trend_stage50','trend','half','none'),
    'pullback_stage25':Rule('pullback_stage25','pullback','quarter','none'),
    'monthly60':Rule('monthly60',entry='monthly')}
LABELS={'immediate':'立即全额买入','trend':'趋势确认买入','pullback':'回调反弹买入','stage50':'立即50%分批','trend_stage50':'趋势50%分批',
        'pullback_stage25':'回调25%分批至75%','monthly60':'每月1/60买入','wait_ma20':'等20日线修复','wait_ma120':'等120日趋势','wait20':'固定等20交易日'}


def fixed_weight(data,start,end,weight):
    """每月首个交易日恢复固定比例，费用及100份取整与策略相同。"""
    cash=CASH;qty=0;trades=[];daily=[]
    opens=data.open.to_numpy(float);closes=data.close.to_numpy(float)
    highs=data.high.to_numpy(float);lows=data.low.to_numpy(float);idx=data.index
    for i in range(start,end):
        if i==start or idx[i].month!=idx[i-1].month:
            equity=cash+qty*opens[i]
            wanted=int(weight*equity/opens[i]//100)*100
            buy=wanted>qty;units=abs(wanted-qty);execution=opens[i]*(1.001 if buy else .999)
            one=highs[i]==lows[i]
            blocked=one and ((buy and opens[i]/closes[i-1]-1>=.097) or (not buy and opens[i]/closes[i-1]-1<=-.097))
            if blocked:units=0
            if buy:
                while units>0 and units*execution+max(5.,units*execution*.0001)>cash+1e-8:units-=100
            if units:
                fee=max(5.,units*execution*.0001)
                cash+=(-units*execution-fee) if buy else units*execution-fee
                qty+=units if buy else -units
                trades.append(dict(signal_date=str(idx[i-1].date()),date=str(idx[i].date()),action='买入/再平衡' if buy else '卖出/再平衡',
                                   quantity=units,price=execution,fee=fee,cash_after=cash,quantity_after=qty,
                                   reason=f'月初恢复固定目标比例{weight:.6f}；成交日开盘按权益确定份数'))
        equity=cash+qty*closes[i]
        daily.append((idx[i],cash,qty,equity,qty*closes[i]/equity))
    curve=pd.DataFrame(daily,columns=['date','cash','quantity','equity','exposure']).set_index('date')
    curve['return_pct']=(curve.equity/CASH-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=CASH)-1)*100
    return curve,trades


def match_exposure(data,start,end,wanted,steps=14):
    """事后诊断对照：只拟合平均仓位，不读取或优化收益。不是可实盘预知的参数。"""
    lo=0.;hi=1.;best=None
    for w in [0.,1.]+[None]*steps:
        if w is None:w=(lo+hi)/2
        curve,trades=fixed_weight(data,start,end,w)
        actual=float(curve.exposure.mean());error=abs(actual-wanted)
        if best is None or error<best[0]:best=(error,w,curve,trades)
        if actual<wanted:lo=w
        else:hi=w
    return best[1],best[2],best[3]


def gross_cagr(data,curve,trades,begin,stop):
    # 保持原份额路径，仅加回已支付佣金和滑点，不反事实再投资节省成本。
    cost=0.
    for t in trades:
        opening=float(data.loc[t['date'],'open'])
        cost+=t['fee']+t['quantity']*abs(t['price']-opening)
    years=(stop-begin).days/365.2425
    return float(((curve.equity.iloc[-1]+cost)/CASH)**(1/years)-1)*100


def get_data(code):
    d=pd.read_csv(SOURCE/f'{code}_qfq.csv',index_col='date',parse_dates=True).sort_index().loc[:ASOF]
    assert not d.index.has_duplicates
    assert np.isfinite(d[['open','high','low','close']]).all().all()
    assert (d[['open','high','low','close']]>0).all().all()
    return d


def window_research():
    rows=[];all_cases={};sections=[]
    for code,first in [('518880',2015),('518850',2021)]:
        data=get_data(code);f=features(data)
        specs=[('fixed',y,y+5,'full') for y in range(first,2022,5)]+[('rolling',y,y+5,'full') for y in range(first,2022)]+[('holdout',2025,2030,'partial')]
        for mode,year,endyear,kind in specs:
            folder=OUT/f'{code}_{mode}_{year}';folder.mkdir(exist_ok=True)
            begin=pd.Timestamp(year,1,1);stop=pd.Timestamp(endyear,1,1)
            start=int(data.index.searchsorted(begin));end=int(data.index.searchsorted(stop))
            effective_stop=stop if kind=='full' else data.index[-1]+pd.Timedelta(days=1)
            cases={};trademap={};local=[]
            for name,rule in RULES.items():
                c,t,_=simulate(data,f,rule,start,end);cases[name]=c;trademap[name]=t
            for w in (.25,.5,.75,1.):
                name=f'fixed{int(w*100)}';cases[name],trademap[name]=fixed_weight(data,start,end,w)
            for name in RULES:
                c=cases[name];m=statistics(c,begin,effective_stop,trademap[name])
                w,control,t=match_exposure(data,start,end,m['average_exposure_pct']/100)
                cm=statistics(control,begin,effective_stop,t)
                cases['matched_'+name]=control;trademap['matched_'+name]=t
                row=dict(code=code,mode=mode,year=year,kind=kind,strategy=name,start=str(c.index[0].date()),end=str(c.index[-1].date()),initial_cash=CASH,
                         matched_target=w,matched_actual_exposure_pct=cm['average_exposure_pct'],
                         exposure_error_pp=m['average_exposure_pct']-cm['average_exposure_pct'],
                         timing_cagr_pp=m['annual_return_pct']-cm['annual_return_pct'],
                         timing_calmar=m['calmar']-cm['calmar'],timing_sharpe=m['sharpe']-cm['sharpe'],
                         timing_dd_improvement_pp=cm['max_drawdown_pct']-m['max_drawdown_pct'],
                         gross_path_timing_cagr_pp=gross_cagr(data,c,trademap[name],begin,effective_stop)-gross_cagr(data,control,t,begin,effective_stop),
                         matched_cagr_pct=cm['annual_return_pct'],matched_max_drawdown_pct=cm['max_drawdown_pct'],matched_fees=cm['fees'],**m)
                rows.append(row);local.append(row)
            for name in ['fixed25','fixed50','fixed75','fixed100']:
                m=statistics(cases[name],begin,effective_stop,trademap[name])
                rows.append(dict(code=code,mode=mode,year=year,kind=kind,strategy=name,start=str(cases[name].index[0].date()),end=str(cases[name].index[-1].date()),initial_cash=CASH,**m))
            pd.DataFrame(local).to_csv(folder/'timing_comparison.csv',index=False)
            pd.concat(cases,names=['strategy','date']).to_csv(folder/'all_daily.csv.gz',compression='gzip')
            pd.DataFrame([dict(strategy=k,**v) for k,t in trademap.items() for v in t]).to_csv(folder/'all_trades.csv',index=False)
            all_cases[(code,mode,year)]=(cases,trademap,folder,data,start,end,begin,effective_stop)
            fig,axes=plt.subplots(4,1,figsize=(14,14),sharex=True)
            for name in RULES:
                c=cases[name];axes[0].plot(c.index,c.return_pct,label=LABELS[name]);axes[1].plot(c.index,c.drawdown_pct,label=LABELS[name]);axes[3].plot(c.index,c.exposure*100,label=LABELS[name])
            axes[2].plot(c.index,data.close.reindex(c.index),color='goldenrod',label='ETF价格')
            for name,color,marker in [('trend','blue','^'),('pullback','red','v'),('stage50','green','o')]:
                t=trademap[name]
                if t:axes[2].scatter(pd.to_datetime([x['date'] for x in t]),[x['price'] for x in t],c=color,marker=marker,s=30,label=LABELS[name],zorder=4)
            for ax,label in zip(axes,['累计收益 (%)','回撤 (%)','实际买入点 (元)','实际仓位 (%)']):ax.set_ylabel(label);ax.legend(fontsize=8,ncol=3);ax.grid(alpha=.2)
            fig.suptitle(f'{code} {mode} {year}—{endyear-1} / {kind}');fig.tight_layout();fig.savefig(folder/'curves.png',dpi=110);plt.close(fig)
            fig,axes=plt.subplots(2,2,figsize=(14,10),sharex=True)
            for name,ax in zip(['trend','pullback','stage50','monthly60'],axes.flat):
                for k,label in [(name,LABELS[name]),('matched_'+name,'事后平均仓位匹配对照'),('immediate','立即全额买入')]:
                    c=cases[k];ax.plot(c.index,c.return_pct,label=label)
                ax.set_title(name);ax.set_ylabel('累计收益 (%)');ax.legend(fontsize=8);ax.grid(alpha=.2)
            fig.tight_layout();fig.savefig(folder/'matched_curves.png',dpi=110);plt.close(fig)
            sections += [f'### {code} / {mode} / {year} / {kind}','',f'实际区间{local[0]["start"]}—{local[0]["end"]}；各账户初始10万元。','',
                         pd.DataFrame(local)[['strategy','annual_return_pct','max_drawdown_pct','calmar','sharpe','average_exposure_pct','matched_actual_exposure_pct','exposure_error_pp','timing_cagr_pp','timing_calmar','timing_sharpe']].to_markdown(index=False),'',
                         f'![策略收益回撤买点及仓位]({folder.name}/curves.png)','',f'![同平均仓位曲线]({folder.name}/matched_curves.png)','',
                         f'[匹配指标]({folder.name}/timing_comparison.csv) · [所有账户逐日数据]({folder.name}/all_daily.csv.gz) · [全部真实模拟成交]({folder.name}/all_trades.csv)','']
            print('Window',code,mode,year,flush=True)
    table=pd.DataFrame(rows);table.to_csv(OUT/'all_metrics.csv',index=False)
    folds=[]
    for (code,mode,year),(cases,tm,folder,data,start,end,begin,stop) in all_cases.items():
        train=table[(table.code=='518880')&(table['mode']=='rolling')&(table.year==year-5)&table.strategy.isin(RULES)]
        if train.empty:continue
        valid=train[(train.strategy!='immediate')&(train.timing_cagr_pp>0)&(train.timing_calmar>0)&(train.timing_sharpe>0)].copy()
        if valid.empty:selected='immediate'
        else:
            valid['score']=(valid.timing_calmar.rank(pct=True)+valid.timing_sharpe.rank(pct=True))/2
            selected=valid.sort_values(['score','strategy'],ascending=[False,True]).iloc[0].strategy
        tr=train[train.strategy==selected].iloc[0]
        w=float(tr.matched_target)
        control,t=fixed_weight(data,start,end,w)
        ctrl=statistics(control,begin,stop,t)
        actual=table[(table.code==code)&(table['mode']==mode)&(table.year==year)&(table.strategy==selected)].iloc[0]
        folds.append(dict(code=code,mode=mode,year=year,kind=actual.kind,training_start=tr.start,training_end=tr.end,selected=selected,
                          frozen_control_target=w,control_actual_exposure_pct=ctrl['average_exposure_pct'],strategy_actual_exposure_pct=actual.average_exposure_pct,
                          cagr_pct=actual.annual_return_pct,control_cagr_pct=ctrl['annual_return_pct'],cagr_excess_pp=actual.annual_return_pct-ctrl['annual_return_pct'],
                          calmar=actual.calmar,control_calmar=ctrl['calmar'],sharpe=actual.sharpe,control_sharpe=ctrl['sharpe'],
                          retrospective_matched_cagr_pp=actual.timing_cagr_pp))
        control.to_csv(folder/'frozen_control_daily.csv');pd.DataFrame(t).to_csv(folder/'frozen_control_trades.csv',index=False)
    pd.DataFrame(folds).to_csv(OUT/'cross_cycle.csv',index=False)
    full=table[(table.kind=='full')&table.strategy.isin(RULES)]
    aggregate=full.groupby(['code','mode','strategy']).agg(n=('strategy','size'),median_timing_cagr_pp=('timing_cagr_pp','median'),worst_timing_cagr_pp=('timing_cagr_pp','min'),median_timing_calmar=('timing_calmar','median'),median_timing_sharpe=('timing_sharpe','median'),positive_cagr=('timing_cagr_pp',lambda x:int((x>1e-7).sum()))).reset_index()
    aggregate.to_csv(OUT/'stability.csv',index=False)
    return sections


def state_features(data):
    f=features(data);c=data.close
    f['dev120']=c/f.ma120-1
    f['slope120']=f.ma120/f.ma120.shift(5)-1
    f['below20']=c<f.ma20;f['below120']=c<f.ma120
    return f


def select_analogues(data,level='primary',gap_months=12,target_state=None):
    """不读取任何前瞻收益；按时间保留每个状态簇首个样本。"""
    f=state_features(data);target=f.iloc[-1] if target_state is None else target_state
    if level=='primary':
        mask=((f.rise20-target.rise20).abs()<=.05)&((f.dev60-target.dev60).abs()<=.05)&((f.dd250-target.dd250).abs()<=.10)
        mask &= (f.below20==target.below20)&(f.below120==target.below120)&((f.slope120<=0)==(target.slope120<=0))
    elif level=='broad':
        mask=f.below20&f.below120&(f.slope120<=0)&(f.rise20<0)&(f.dd250<=-.10)
    else:raise ValueError(level)
    mask &= f.dd250.notna()&(f.index<data.index[-1])
    hits=f[mask].copy();selected=[];next_allowed=pd.Timestamp.min
    for date in hits.index:
        if date>=next_allowed:selected.append(date);next_allowed=date+pd.DateOffset(months=gap_months)
    return f,hits,pd.DatetimeIndex(selected)


def event_path(data,f,event_date,months,policy):
    i=data.index.get_loc(event_date)
    planned_end=event_date+pd.DateOffset(months=months)
    if planned_end>data.index[-1]:return None
    end=int(data.index.searchsorted(planned_end))
    if end>=len(data):return None
    if policy=='immediate':entry=i+1
    elif policy=='wait20':entry=i+21
    else:
        mask=((data.close>f.ma20)&(f.ma20>=f.ma20.shift(5))) if policy=='wait_ma20' else f.trend
        possible=np.flatnonzero(mask.to_numpy()[i+1:end])
        entry=i+1+int(possible[0])+1 if len(possible) else end+1
    cash=CASH;qty=0;trades=[];daily=[];fee=0.
    for j in range(i+1,end+1):
        if j==entry:
            opening=float(data.open.iloc[j]);execution=opening*1.001
            one=float(data.high.iloc[j])==float(data.low.iloc[j])
            blocked=one and opening/float(data.close.iloc[j-1])-1>=.097
            units=0 if blocked else int(cash/(execution*1.0001)//100)*100
            while units>0 and units*execution+max(5.,units*execution*.0001)>cash:units-=100
            if units:
                fee=max(5.,units*execution*.0001);cash-=units*execution+fee;qty=units
                trades.append(dict(date=str(data.index[j].date()),signal_date=str(data.index[j-1].date()),action='买入',quantity=units,price=execution,fee=fee,
                                   reason='事件后首日买入' if policy=='immediate' else '固定等待20交易日' if policy=='wait20' else '只使用前日收盘的均线修复条件'))
        equity=cash+qty*float(data.close.iloc[j])
        if j==end and qty:
            # 所有方案统一在预定观察期终点按收盘估计清算，双边计费；不是策略卖点。
            execution=float(data.close.iloc[j])*.999;fee=max(5.,qty*execution*.0001)
            cash+=qty*execution-fee
            trades.append(dict(date=str(data.index[j].date()),signal_date='',action='观察期清算',quantity=qty,price=execution,fee=fee,reason='预先确定的观察期终点统一估算收盘清算；非择时卖出信号'))
            qty=0;equity=cash
        daily.append((data.index[j],cash,qty,equity))
    curve=pd.DataFrame(daily,columns=['date','cash','quantity','equity']).set_index('date')
    curve['return_pct']=(curve.equity/CASH-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=CASH)-1)*100
    buy=next((t for t in trades if t['action']=='买入'),None)
    row=dict(event_date=str(event_date.date()),months=months,policy=policy,planned_end=str(planned_end.date()),actual_end=str(data.index[end].date()),
             return_pct=float(curve.return_pct.iloc[-1]),max_drawdown_pct=float(-curve.drawdown_pct.min()),
             entered=bool(buy),entry_date=buy['date'] if buy else '',wait_trading_days=entry-i-1 if buy else end-i,
             fees=float(sum(t['fee'] for t in trades)))
    return row,curve,trades


def analogue_research():
    outcomes=[];all_trades=[];counts=[];sections=[]
    for code in ('518880','518850'):
        data=get_data(code)
        for level in ('primary','broad'):
            f,hits,dates=select_analogues(data,level)
            hits.to_csv(OUT/f'{code}_{level}_all_feature_hits.csv')
            f.reindex(dates).to_csv(OUT/f'{code}_{level}_selected_events.csv')
            counts.append(dict(code=code,level=level,all_daily_hits=len(hits),selected_events=len(dates),before2025=int((dates<pd.Timestamp('2025-01-01')).sum()),
                               no_forward_12m=int(sum(d+pd.DateOffset(months=12)>data.index[-1] for d in dates))))
            for date in dates:
                folder=OUT/f'analogue_{code}_{level}_{date.date()}';folder.mkdir(exist_ok=True)
                plot_cases={};chosen_horizon=None
                for months in (1,3,6,12):
                    base=None
                    for policy in ('immediate','wait_ma20','wait_ma120','wait20'):
                        result=event_path(data,f,date,months,policy)
                        if result is None:continue
                        row,curve,trades=result
                        if policy=='immediate':base=row
                        row.update(code=code,level=level,era='pre2025' if date.year<2025 else '2025plus',
                                   waiting_cost_pp=base['return_pct']-row['return_pct'],risk_improvement_pp=base['max_drawdown_pct']-row['max_drawdown_pct'])
                        outcomes.append(row)
                        all_trades.extend([dict(code=code,level=level,event_date=str(date.date()),months=months,policy=policy,**t) for t in trades])
                        curve.to_csv(folder/f'{months}m_{policy}_daily.csv')
                        plot_cases[policy]=(curve,trades);chosen_horizon=months
                if not plot_cases:continue
                # 只按可获得的最长观察期画图，不根据收益选择观察期。
                fig,axes=plt.subplots(3,1,figsize=(13,10),sharex=True)
                for policy,(curve,trades) in plot_cases.items():
                    axes[0].plot(curve.index,curve.return_pct,label=LABELS.get(policy,policy));axes[1].plot(curve.index,curve.drawdown_pct,label=LABELS.get(policy,policy))
                    buy=[t for t in trades if t['action']=='买入']
                    if buy:axes[2].scatter(pd.to_datetime([x['date'] for x in buy]),[x['price'] for x in buy],label=LABELS.get(policy,policy),s=40,zorder=4)
                axes[2].plot(curve.index,data.close.reindex(curve.index),color='goldenrod')
                for ax,title in zip(axes,['净收益 (%)','回撤 (%)','各方案实际买入点 (元)']):ax.set_ylabel(title);ax.legend(fontsize=8);ax.grid(alpha=.2)
                fig.suptitle(f'{code} {level} / 状态日{date.date()} / {chosen_horizon}个月');fig.tight_layout();fig.savefig(folder/'curves.png',dpi=110);plt.close(fig)
                sections += [f'### {code} / {level} / 状态日 {date.date()}','',f'按可得数据绘制{chosen_horizon}个月，非按收益选取。',f'![事件后的收益回撤与买入点]({folder.name}/curves.png)','']
    out=pd.DataFrame(outcomes);out.to_csv(OUT/'analogue_outcomes.csv',index=False)
    pd.DataFrame(all_trades).to_csv(OUT/'analogue_trades.csv',index=False)
    pd.DataFrame(counts).to_csv(OUT/'analogue_counts.csv',index=False)
    summary=out.groupby(['code','level','era','months','policy']).agg(n=('return_pct','size'),entered=('entered','sum'),
                median_return_pct=('return_pct','median'),worst_return_pct=('return_pct','min'),best_return_pct=('return_pct','max'),
                median_drawdown_pct=('max_drawdown_pct','median'),worst_drawdown_pct=('max_drawdown_pct','max'),
                median_waiting_cost_pp=('waiting_cost_pp','median'),worst_waiting_cost_pp=('waiting_cost_pp','max'),median_risk_improvement_pp=('risk_improvement_pp','median')).reset_index()
    summary.to_csv(OUT/'analogue_summary.csv',index=False)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for level,ax in zip(('primary','broad'),axes):
        g=summary[(summary.code=='518880')&(summary.level==level)]
        for policy in ('immediate','wait_ma20','wait_ma120','wait20'):
            s=g[g.policy==policy]
            for era,style in [('pre2025','-'),('2025plus','--')]:
                a=s[s.era==era]
                if len(a):ax.plot(a.months,a.median_return_pct,style,marker='o',label=LABELS.get(policy,policy)+' / '+era)
        ax.set_title(level);ax.set_xlabel('观察月数');ax.set_ylabel('净收益中位数 (%)');ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(OUT/'analogue_summary.png',dpi=120);plt.close(fig)
    return sections


def report(window_sections,event_sections):
    table=pd.read_csv(OUT/'all_metrics.csv',dtype={'code':str});stability=pd.read_csv(OUT/'stability.csv',dtype={'code':str})
    folds=pd.read_csv(OUT/'cross_cycle.csv');counts=pd.read_csv(OUT/'analogue_counts.csv');summary=pd.read_csv(OUT/'analogue_summary.csv')
    f=state_features(get_data('518850'));target=f.iloc[-1]
    design={'asof':str(ASOF.date()),'average_exposure_match':'事后仅匹配平均仓位，不优化收益；不能作为可交易选型',
            'primary_tolerances':{'return20_pp':5,'dev60_pp':5,'dd250_pp':10,'below20':'same as target','below120':'same as target','slope120_sign':'same as target'},
            'broad_rule':'price<MA20, price<MA120, MA120 slope5<=0, return20<0, dd250<=-10%',
            'event_selection':'时间顺序首个符合样本，然后排除其后12个自然月；不使用未来收益或未来是否有完整12个月数据',
            'target_state':{k:float(target[k]) for k in ('rise20','dev60','dd250','slope120')}}
    (OUT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={}
    for code in ('518880','518850'):
        p=SOURCE/f'{code}_qfq.csv';manifest[code]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'data_asof':str(ASOF.date()),'type':'真实ETF，同类代理' if code=='518880' else '真实ETF原标的'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 黄金买入择时：剥离仓位影响与相似状态研究','',
           '## 检验问题和结论边界','',
           '本轮不把低仓位带来的低回撤直接称为择时能力。分别比较立即买入、趋势买入、回调反弹买入、分批建仓、每月买入和25%/50%/75%/100%固定比例（月度再平衡）。产品信号未修改。输入行情仍截至2026-10-29。',
           '完整周期、独立初始10万元、次日开盘执行、100份取整、0.1%单边滑点、万一且最低5元佣金、现金收益0等，均沿用上一轮统一规则。固定与滚动重复周期、两只高度相关ETF不当独立证据；2025以后未满五年的区间单列。',
           '## 如何区分择时与仓位','',
           '每个策略增加事后平均仓位匹配的固定比例对照：只用策略该窗口的平均收盘市值仓位拟合固定目标比例，逐日重放月度再平衡账户；包含相同交易成本和取整。实际平均仓位差单独披露，不假装严格零误差。择时贡献用策略减去此对照的年化收益、Calmar、Sharpe及回撤差表示。',
           '该匹配用到了整窗平均仓位，因此只能作为诊断反事实，不能说投资者事前知道这个固定比例。跨周期另用训练窗拟合的目标比例冻结到测试窗，测试窗不重调，使该对照可在事前实施，但测试窗实际平均仓位不再保证相等。',
           '固定比例再平衡本身也会影响收益；费用相同规则但笔数不同。额外gross_path_timing_cagr_pp保持原份额路径、仅加回直接佣金和滑点，检查差异是否被交易成本驱动；这不是重新投资节省成本后的可交易回测，也不能把任一差额当严格因果证明。',
           '入场规则不加额外卖点：趋势为价格高于120日线且该均线高于5日前；回调为250日高点回撤≥10%、价格回到20日线上且20日线不低于5日前。分批为50%开始、间隔至少20交易日在20/120日线上加25%至100%，或回调25%起步至75%；首次入场后不主动清仓，隔离买入时机。每月买入来自开窗已备好的10万元，不引入外部现金。','',
           '## 完整五年窗口：同仓位诊断的稳定性','',stability.to_markdown(index=False),'',
           'timing_cagr_pp>0才表示年化优于同平均仓位的月度固定比例对照；timing_calmar、timing_sharpe同理。仅对比满仓持有的回撤改善不作为择时有效证据。','',
           '## 跨周期冻结验证','',
           '仅用紧邻的更早完整五年518880训练。训练要求年化、Calmar、Sharpe同时优于事后匹配对照，才允许择时候选入选；在合格者中等权Calmar/Sharpe差排名，否则回退立即买入。将训练平均仓位对应的固定目标比例冻结到测试窗，且列出测试实际仓位差。历史已被查看过，属于回顾性时间留出模拟，非严格未见样本外。','',folds.to_markdown(index=False),'',
           '## 相似状态：先定义特征，再看结果','',
           '主口径按当前同只ETF的20日涨幅±5个百分点、60日偏离±5个百分点、250日高点回撤±10个百分点，同时要求20/120日线上下位置及120日均线5日斜率符号相同。宽口径另固定为：价格低于20和120日线、120日线斜率≤0、20日涨幅<0、250日高点回撤≥10%。宽口径只是敏感性对照，不能看到主口径样本少就用宽口径冒充同一状态。',
           '筛选仅读取当时及之前价格，不按事后低点、随后涨幅或是否有完整12个月挑样本。按时间取首个命中，之后12个自然月不再取样；所有逐日命中也保存。当前状态本身不作为历史样本。没有足够前瞻数据的观察期留缺，不按0收益填补。',
           '观察1/3/6/12个自然月，到期取不早于计划日期的首个交易日；立即买为状态日后下一开盘。等待方案为20日线修复、120日趋势修复、固定等待20交易日，均在确认后下一开盘成交。若期限内未触发则保持现金，仍计入统计，不删除这类机会成本。到观察期末统一按收盘加滑点及佣金估计清算；该清算只是统一评价终点，不是策略卖点。',
           '等待机会成本=立即买净收益−等待买净收益，正数表示等待错过收益，负数表示等待有利；风险改善=立即买最大回撤−等待最大回撤。收益和回撤按整个10万元含现金账户计算，不是仅对已投入部分计算。','',
           '### 相似样本数量','',counts.to_markdown(index=False),'',
           '### 分期、分观察期限统计','',summary.to_markdown(index=False),'',
           '12个月排重后样本仍可能来自同一宏观周期；518850和518880不可合并扩充独立样本。样本不足时不输出看似精确的胜率或置信区间。','',
           '![分期相似状态结果](analogue_summary.png)','',
           '[逐日特征命中与筛选规则](design.json) · [全部事件结果](analogue_outcomes.csv) · [事件买入及观察期清算记录](analogue_trades.csv) · [完整五年指标](all_metrics.csv) · [跨周期结果](cross_cycle.csv)','',
           '## 各五年窗口图表及记录','']+window_sections+['## 相似历史事件图表','']+event_sections
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')


def supplement():
    """附加对照风险图、零样本覆盖表及明确的当前结论。可单独重建。"""
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    previous_advice=(OUT/'current_advice.md').read_text(encoding='utf-8') if (OUT/'current_advice.md').exists() else ''
    table=pd.read_csv(OUT/'all_metrics.csv',dtype={'code':str})
    outcomes=pd.read_csv(OUT/'analogue_outcomes.csv',dtype={'code':str})
    counts=pd.read_csv(OUT/'analogue_counts.csv',dtype={'code':str})
    coverage=[]
    for r in counts.itertuples(index=False):
        for months in (1,3,6,12):
            g=outcomes[(outcomes.code==r.code)&(outcomes.level==r.level)&(outcomes.months==months)&(outcomes.policy=='immediate')]
            coverage.append(dict(code=r.code,level=r.level,months=months,all_selected_events=r.selected_events,available=len(g),
                                 pre2025_available=int((g.era=='pre2025').sum()),recent_available=int((g.era=='2025plus').sum()),
                                 not_matured=r.selected_events-len(g)))
    cover=pd.DataFrame(coverage);cover.to_csv(OUT/'analogue_coverage.csv',index=False)
    for folder in OUT.glob('*_*_20*'):
        if not (folder/'all_daily.csv.gz').exists():continue
        daily=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date']).set_index(['strategy','date'])
        cases={k:g.droplevel(0) for k,g in daily.groupby(level=0)}
        fig,axes=plt.subplots(2,2,figsize=(14,10),sharex=True)
        for name,ax in zip(['trend','pullback','stage50','monthly60'],axes.flat):
            for key,label in [(name,LABELS[name]),('matched_'+name,'同平均仓位对照'),('immediate','立即全买')]:
                c=cases[key];ax.plot(c.index,c.drawdown_pct,label=label)
            ax.set_title(LABELS[name]);ax.set_ylabel('回撤 (%)');ax.legend(fontsize=8);ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(folder/'matched_drawdowns.png',dpi=110);plt.close(fig)
        fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
        for w in (25,50,75,100):
            c=cases[f'fixed{w}'];axes[0].plot(c.index,c.return_pct,label=f'固定目标{w}%');axes[1].plot(c.index,c.drawdown_pct,label=f'固定目标{w}%')
        for ax,label in zip(axes,['累计收益 (%)','回撤 (%)']):ax.set_ylabel(label);ax.legend();ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(folder/'fixed_weights.png',dpi=110);plt.close(fig)
        trades=pd.read_csv(folder/'all_trades.csv')
        data=get_data(folder.name.split('_')[0])
        fig,axes=plt.subplots(len(RULES),1,figsize=(14,18),sharex=True)
        for (name,ax) in zip(RULES,axes):
            c=cases[name];ax.plot(c.index,data.close.reindex(c.index),color='goldenrod',linewidth=.8)
            t=trades[trades.strategy==name]
            if len(t):ax.scatter(pd.to_datetime(t.date),t.price,c='green',marker='^',s=20)
            ax.set_ylabel(LABELS[name]+'\n(元)');ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(folder/'all_buy_points.png',dpi=110);plt.close(fig)
    summary=pd.read_csv(OUT/'analogue_summary.csv',dtype={'code':str})
    # 主样本量不足时明确显示0，不把缺失期限默认为收益0。
    narrative=['## 本轮结论与当前建议更新','',
               '**没有发现可稳定跨五年周期的买入择时超额。此前“均线未修复，所以择时新增应为0%”只能作为谨慎执行偏好，不能再表述为已被历史证明更有利的买入建议。**',
               '在518880七个完整滚动五年窗口中，趋势确认相对同平均仓位对照的年化差中位数为0，回调买入约−0.21个百分点，立即50%分批约−0.26个百分点，趋势分批约−0.38个百分点，每月买入约−0.32个百分点。部分单窗为正，但没有跨窗稳定的Calmar和Sharpe优势。趋势在部分窗口与立即买入同日成交，不能把相同结果当作择时成功。',
               '固定2015—2019及2020—2024两个周期中，定期买入曾优于同仓位对照；但滚动窗口仅3/7年化为正。2025年至今，定期买入相对事后同仓位对照的年化差约−2.88个百分点，回调买入约−21.67个百分点；后者发生较晚建仓后下跌，显示等待并不必然买得更便宜。短区间年化会放大差异，不参加完整五年排名。',
               '跨周期冻结：2015—2019选择定期买入，2020—2024相对训练窗冻结固定比例对照年化高约1.12个百分点；但同样方法在2025年至今相对冻结对照低约8.90个百分点。近期两者平均仓位也不同（约16.39%与46.67%），该差额含仓位变化；事后再匹配平均仓位后仍落后约2.88个百分点，因此不能把近期失效完全解释为低仓位。2016—2020训练未找到三项指标同时优于匹配对照的择时规则，后续回退立即买入。',
               '### 当前状态的相似证据有多强','',
               '主口径在两只ETF中均只有2026-06-10一个排重事件，且来自同一黄金行情，不是两次独立证据。仅有1及3个月结果，6及12个月均未成熟；2025年前没有主口径事件。因而无法给出“类似当前状态随后6/12个月通常如何”的可靠结论。宽口径扩大至较轻回撤，只能作敏感性参考。','',cover.to_markdown(index=False),'',
               '518880宽口径中，2025年前6个排重状态日的12个月结果：立即买入净收益中位数约7.98%，最差−6.21%，最差最大回撤约20.46%；等待120日趋势的配对机会成本中位数约6.62个百分点，等待20日线修复约2.67个百分点。等待可能降低短期暴露，但这些样本并未证明它能降低完整12个月回撤且不牺牲收益。样本少、规则较宽、同一资产，不能用来断言本次必然反弹。pre2025按状态日划分，其观察终点可能进入2025，不能把该组都当纯开发期。',
               '### 截至2026-10-29如何执行','',
               '行情仍为518850收盘8.315元、518880收盘8.224元；518850低于20日线8.5458及120日线8.9610，反映趋势较弱。这是风险状态描述，不是已经验证的后续下跌预测；相反，机械等待均线修复也存在错过上涨的成本。',
               '**当下不建议一次性投入全部黄金预算，也不支持仅因均线走弱就断言必须全部等待。若已确定五年黄金配置计划，可按原定小额节奏投入黄金预留预算的1/60（约1.67%）一笔，不因下跌加速；若尚未确定配置期限或风险预算，可暂缓，理由是决策条件不足，而非已证明将有更低买价。**',
               '1.67%是便于固定预算执行的探索性比例，不是收益最优或已被本轮证明优于固定低仓位的数字；以10万元预算为例每笔约1666.67元，含费用且100份取整，实际买入金额可能明显更低。比例不指家庭总资产。后续按月执行，不将收复某条均线作为必然加速加仓条件；若选择等待路线，应记录每月相对小额买入基准的机会成本。',
               '证据等级：已复核的是历史账户、平均仓位匹配、冻结跨周期结果及按过去特征筛选的事件统计；弱证据包括当前深回撤类比和任一特定均线买点；未来是否上涨、现在是否低点均未验证。产品策略和自动提醒未改变。','']
    (OUT/'current_advice.md').write_text('\n'.join(narrative),encoding='utf-8')
    p=OUT/'report.md';text=p.read_text(encoding='utf-8')
    if previous_advice:text=text.replace(previous_advice,'')
    if '## 本轮结论与当前建议更新' not in text:
        title,remaining=text.split('\n',1)
        text=title+'\n\n'+'\n'.join(narrative)+'\n'+remaining
    for folder in OUT.glob('*_*_20*'):
        if not (folder/'all_daily.csv.gz').exists():continue
        needle=f'![同平均仓位曲线]({folder.name}/matched_curves.png)'
        added=f'\n\n![同平均仓位回撤]({folder.name}/matched_drawdowns.png)\n\n![固定比例对照]({folder.name}/fixed_weights.png)\n\n![各策略实际买入点]({folder.name}/all_buy_points.png)'
        if f'{folder.name}/matched_drawdowns.png' not in text:text=text.replace(needle,needle+added)
    p.write_text(text,encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    windows=window_research();events=analogue_research();report(windows,events);supplement()
    print('Saved',OUT/'report.md',flush=True)


if __name__=='__main__':main()
