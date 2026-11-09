"""按可用时间对齐的黄金外部指标研究；只生成研究产物。"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from research_gold_full_cycle import Rule,features,simulate,statistics
from research_gold_entry_value import get_data,fixed_weight,match_exposure
from research_sector_partial_exit import backtest_partial
from gold_strategy import stages

OUT=Path('results/gold_macro')
SERIES={'real':('DFII10',2),'dollar':('DXY',2),'yuan':('DEXCHUS',14),'gvz':('GVZCLS',2)}
NEEDS={'real':['real'],'dollar':['dollar'],'yuan':['yuan'],'gvz':['gvz'],
       'rates_dollar':['real','dollar'],'macro_vote':['real','dollar','yuan'],
       'macro_vol':['real','dollar','yuan','gvz'],'trend_real':['real'],
       'trend_macro':['real','dollar','yuan'],'trend_gvz':['gvz']}
TARGETS=['price_trend','price_rv','trend_rv']+list(NEEDS)
BASES=['hold','fixed50','fixed75','monthly60','price_heat15']
ALL=BASES+TARGETS
LABELS={'hold':'长期持有','fixed50':'固定50%','fixed75':'固定75%','monthly60':'每月1/60',
        'price_heat15':'价格15%过热减半','price_trend':'价格趋势','price_rv':'ETF实现波动率','trend_rv':'趋势+实现波动率',
        'real':'实际利率','dollar':'DXY','yuan':'美元兑人民币','gvz':'GVZ',
        'rates_dollar':'实际利率+DXY','macro_vote':'宏观三项投票','macro_vol':'宏观投票+GVZ',
        'trend_real':'趋势+实际利率','trend_macro':'趋势+宏观投票','trend_gvz':'趋势+GVZ'}
PARENTS={k:'hold' for k in NEEDS}
PARENTS.update(gvz='price_rv',trend_real='price_trend',trend_macro='price_trend',trend_gvz='trend_rv')


def raw_signal(name,source=None,extra_lag=0):
    series,lag=SERIES[name]
    raw=pd.read_csv(OUT/'data'/f'{series}_raw.csv') if source is None else source.copy()
    raw.columns=['observation_date','value']
    raw.observation_date=pd.to_datetime(raw.observation_date)
    raw.value=pd.to_numeric(raw.value,errors='coerce')
    raw=raw.dropna().sort_values('observation_date').drop_duplicates('observation_date',keep='last')
    raw['change20']=raw.value.diff(20) if name=='real' else raw.value.pct_change(20,fill_method=None)
    raw['median252']=raw.value.rolling(252,min_periods=252).median()
    if name=='gvz':raw['good']=(raw.value<=raw.median252).where(raw.median252.notna())
    else:raw['good']=(raw.change20>=0 if name=='yuan' else raw.change20<=0).where(raw.change20.notna())
    raw['available_at']=raw.observation_date+pd.Timedelta(days=lag+extra_lag,hours=8)
    return raw


def align_external(index,extra_lag=0,sources=None):
    result=pd.DataFrame(index=index)
    left=pd.DataFrame({'decision_at':index+pd.Timedelta(hours=15)})
    for name in SERIES:
        raw=raw_signal(name,None if sources is None else sources[name],extra_lag)
        joined=pd.merge_asof(left,raw,left_on='decision_at',right_on='available_at',direction='backward')
        joined['age_days']=(joined.decision_at-joined.observation_date).dt.total_seconds()/86400
        joined['valid']=joined.good.notna()&(joined.age_days<=45)
        for col in ['observation_date','available_at','value','change20','median252','good','age_days','valid']:
            result[f'{name}_{col}']=joined[col].to_numpy()
    return result


def policies(data,aligned):
    f=features(data)
    rv=data.close.pct_change(fill_method=None).rolling(20,min_periods=20).std()*np.sqrt(252)
    median=rv.rolling(252,min_periods=252).median()
    rv_good=(rv<=median)&median.notna()
    price=f.trend.astype(float)*.5+.5
    good={k:aligned[f'{k}_good'].eq(True) for k in SERIES}
    vote=(good['real'].astype(int)+good['dollar'].astype(int)+good['yuan'].astype(int))>=2
    result=pd.DataFrame(index=data.index)
    result['price_trend']=price
    result['price_rv']=np.where(rv_good,1.,.5)
    result['trend_rv']=price*np.where(rv_good,1.,.5)
    for name in SERIES:result[name]=np.where(good[name],1.,.5)
    result['rates_dollar']=np.where(good['real']&good['dollar'],1.,.5)
    result['macro_vote']=np.where(vote,1.,.5)
    result['macro_vol']=result.macro_vote*np.where(good['gvz'],1.,.5)
    result['trend_real']=np.where(f.trend&good['real'],1.,.5)
    result['trend_macro']=np.where(f.trend&vote,1.,.5)
    result['trend_gvz']=price*np.where(good['gvz'],1.,.5)
    for policy,names in NEEDS.items():
        valid=pd.Series(True,index=data.index)
        for name in names:valid &= aligned[f'{name}_valid']
        result.loc[~valid,policy]=0.
    return result


def target_backtest(data,aligned,target,name,start,end):
    cash=100000.;qty=0;trades=[];daily=[];invalid=0
    opening=data.open.to_numpy(float);closing=data.close.to_numpy(float)
    high=data.high.to_numpy(float);low=data.low.to_numpy(float);index=data.index
    weights=target.to_numpy(float)
    for i in range(start,end):
        j=i-1
        if i==start or index[j].weekday()==4:
            w=float(weights[j]);equity=cash+qty*opening[i]
            names=NEEDS.get(name,[])
            if names and not all(bool(aligned.iloc[j][f'{k}_valid']) for k in names):invalid+=1
            wanted=int(w*equity/opening[i]//100)*100
            buy=wanted>qty;units=abs(wanted-qty);execution=opening[i]*(1.001 if buy else .999)
            blocked=high[i]==low[i] and ((buy and opening[i]/closing[j]-1>=.097) or (not buy and opening[i]/closing[j]-1<=-.097))
            if blocked:units=0
            if buy:
                while units>0 and units*execution+max(5.,units*execution*.0001)>cash+1e-8:units-=100
            if units:
                fee=max(5.,units*execution*.0001)
                action='首次建仓' if buy and qty==0 else '加仓' if buy else '清仓' if units==qty else '减仓'
                cash+=-units*execution-fee if buy else units*execution-fee
                qty+=units if buy else -units
                t=dict(date=str(index[i].date()),signal_date=str(index[j].date()),decision_at=str(index[j]+pd.Timedelta(hours=15)),
                       action=action,quantity=units,price=execution,fee=fee,target_fraction=w,cash_after=cash,quantity_after=qty,
                       reason=f'{LABELS[name]}周频恢复目标仓位{w:.0%}，只用前日收盘前可用数据')
                for k in names:
                    for col in ['observation_date','available_at','value','change20','good']:
                        value=aligned.iloc[j][f'{k}_{col}']
                        t[f'{k}_{col}']=str(value) if col.endswith('date') or col=='available_at' else value
                trades.append(t)
        equity=cash+qty*closing[i]
        daily.append((index[i],cash,qty,equity,qty*closing[i]/equity))
    curve=pd.DataFrame(daily,columns=['date','cash','quantity','equity','exposure']).set_index('date')
    curve['return_pct']=(curve.equity/100000.-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=100000.)-1)*100
    return curve,trades,invalid


def price_baselines(data,f,start,end):
    cases={};trades={}
    for name,rule in [('hold',Rule('buy_hold')),('monthly60',Rule('monthly60',entry='monthly'))]:
        cases[name],trades[name],_=simulate(data,f,rule,start,end)
    for w in (.5,.75):cases[f'fixed{int(w*100)}'],trades[f'fixed{int(w*100)}']=fixed_weight(data,start,end,w)
    _,curve,t=backtest_partial(data,stages(data.close).target,start,end,initial_cash=100000.,limit_pct=.10)
    curve['exposure']=curve.quantity*data.close.reindex(curve.index)/curve.equity
    curve['return_pct']=(curve.equity/100000.-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=100000.)-1)*100
    for v in t:
        k=data.index.get_loc(pd.Timestamp(v['date']))
        v['signal_date']=str(data.index[k-1].date());v['reason']='既有15%双指标过热减半/5%双指标冷却恢复；日频固定资金基准'
    cases['price_heat15']=curve;trades['price_heat15']=t
    return cases,trades


def ranked(g):
    x=g.copy();valid=x.calmar.notna()&x.sharpe.notna()&(x.trades>0)
    x['score']=-1.
    x.loc[valid,'score']=(x.loc[valid,'calmar'].rank(pct=True)+x.loc[valid,'sharpe'].rank(pct=True))/2
    x['complexity']=x.strategy.map(lambda k:0 if k in BASES else 1 if k not in NEEDS else 2+len(NEEDS[k]))
    return x.sort_values(['score','complexity','strategy'],ascending=[False,True,True])


def predictive_test(data,aligned,train_start,test_start,test_end):
    # 所有标签单独带end日期，禁止训练端偷用跨界20日收益。
    f=features(data);x=pd.DataFrame(index=data.index)
    x['p_return20']=f.rise20;x['p_dev60']=f.dev60
    x['p_vol20']=data.close.pct_change(fill_method=None).rolling(20).std()*np.sqrt(252)
    x['m_real']=aligned.real_change20;x['m_dxy']=aligned.dollar_change20;x['m_yuan']=aligned.yuan_change20
    x['m_gvz']=aligned.gvz_value/aligned.gvz_median252-1
    x['y']=(data.close.shift(-20)/data.close-1)*100
    x['label_end']=pd.Series(data.index,index=data.index).shift(-20)
    valid=x.notna().all(axis=1)
    for name in SERIES:valid &= aligned[f'{name}_valid']
    train=x[valid&(x.index>=train_start)&(x.index<test_start)&(x.label_end<test_start)]
    test=x[valid&(x.index>=test_start)&(x.index<test_end)&(x.label_end<test_end)]
    if len(train)<100 or len(test)<20:return None
    results={};predictions={}
    for model,cols in [('price',['p_return20','p_dev60','p_vol20']),('price_macro',['p_return20','p_dev60','p_vol20','m_real','m_dxy','m_yuan','m_gvz'])]:
        mu=train[cols].mean();sd=train[cols].std().replace(0,1)
        a=np.column_stack([np.ones(len(train)),(train[cols]-mu)/sd])
        b=np.column_stack([np.ones(len(test)),(test[cols]-mu)/sd])
        penalty=np.eye(a.shape[1]);penalty[0,0]=0
        beta=np.linalg.solve(a.T@a+penalty,a.T@train.y.to_numpy())
        predictions[model]=b@beta
        mse=float(np.mean((test.y.to_numpy()-predictions[model])**2))
        benchmark=float(np.mean((test.y.to_numpy()-train.y.mean())**2))
        results[f'{model}_mse']=mse;results[f'{model}_r2_vs_train_mean']=1-mse/benchmark
    results.update(train_n=len(train),test_n=len(test),last_train_label_end=str(train.label_end.max().date()),
                   first_test_date=str(test.index[0].date()),incremental_oos_r2=1-results['price_macro_mse']/results['price_mse'])
    pred=pd.DataFrame({'actual_20d_pct':test.y,'price_forecast':predictions['price'],'macro_forecast':predictions['price_macro'],'label_end':test.label_end})
    return results,pred


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    rows=[];windows={};manifest={};sections=[]
    for code,first in [('518880',2015),('518850',2021)]:
        d=get_data(code);f=features(d);a=align_external(d.index);p=policies(d,a)
        a.to_csv(OUT/f'{code}_availability_audit.csv');p.to_csv(OUT/f'{code}_targets.csv')
        specs=[('fixed',y,y+5,'full') for y in range(first,2022,5)]+[('rolling',y,y+5,'full') for y in range(first,2022)]+[('holdout',2025,2030,'partial')]
        for mode,year,endyear,kind in specs:
            begin=pd.Timestamp(year,1,1);stop=pd.Timestamp(endyear,1,1)
            start=int(d.index.searchsorted(begin));end=int(d.index.searchsorted(stop))
            effective_stop=stop if kind=='full' else d.index[-1]+pd.Timedelta(days=1)
            folder=OUT/f'{code}_{mode}_{year}';folder.mkdir(exist_ok=True)
            cases,tm=price_baselines(d,f,start,end);stats={};local=[]
            for name in TARGETS:
                cases[name],tm[name],missing=target_backtest(d,a,p[name],name,start,end)
                stats[name]={'invalid_decisions':missing}
            for name in ALL:
                m=statistics(cases[name],begin,effective_stop,tm[name])
                row=dict(code=code,mode=mode,year=year,kind=kind,strategy=name,start=str(cases[name].index[0].date()),end=str(cases[name].index[-1].date()),initial_cash=100000.,
                         first_entry=tm[name][0]['date'] if tm[name] else '',invalid_decisions=stats.get(name,{}).get('invalid_decisions',0),**m)
                if name not in ('hold','fixed50','fixed75'):
                    w,c,t=match_exposure(d,start,end,m['average_exposure_pct']/100)
                    cm=statistics(c,begin,effective_stop,t)
                    cases['matched_'+name]=c;tm['matched_'+name]=t
                    row.update(matched_target=w,matched_actual_exposure_pct=cm['average_exposure_pct'],exposure_error_pp=m['average_exposure_pct']-cm['average_exposure_pct'],
                               matched_cagr_excess_pp=m['annual_return_pct']-cm['annual_return_pct'],matched_calmar_excess=m['calmar']-cm['calmar'],matched_sharpe_excess=m['sharpe']-cm['sharpe'])
                else:row.update(matched_target=1. if name=='hold' else float(name[-2:])/100)
                stats[name]=row;local.append(row)
            for name in NEEDS:
                parent=PARENTS[name]
                stats[name].update(parent=parent,parent_calmar_delta=stats[name]['calmar']-stats[parent]['calmar'],parent_sharpe_delta=stats[name]['sharpe']-stats[parent]['sharpe'],
                                   parent_cagr_delta_pp=stats[name]['annual_return_pct']-stats[parent]['annual_return_pct'])
            rows.extend(local)
            pd.DataFrame(local).to_csv(folder/'metrics.csv',index=False)
            pd.concat(cases,names=['strategy','date']).to_csv(folder/'all_daily.csv.gz',compression='gzip')
            pd.DataFrame([dict(strategy=k,**v) for k,t in tm.items() for v in t]).to_csv(folder/'all_trades.csv',index=False)
            windows[(code,mode,year)]=(folder,d,a,p,cases,tm,start,end,begin,effective_stop,stats)
            print('Computed',code,mode,year,flush=True)
    table=pd.DataFrame(rows);table.to_csv(OUT/'all_metrics.csv',index=False)
    folds=[];sensitivity=[];predictions=[]
    for (code,mode,year),(folder,d,a,p,cases,tm,start,end,begin,stop,stats) in windows.items():
        train=table[(table.code=='518880')&(table['mode']=='rolling')&(table.year==year-5)]
        selected=None;selected_price=None
        if len(train):
            ranking=ranked(train);selected=ranking.iloc[0].strategy
            selected_price=ranking[~ranking.strategy.isin(NEEDS)].iloc[0].strategy
            ranking.to_csv(folder/'training_ranking.csv',index=False)
            for name in dict.fromkeys([selected,selected_price]):
                r=stats[name];tr=train[train.strategy==name].iloc[0];w=float(tr.matched_target)
                c,t=fixed_weight(d,start,end,w);cm=statistics(c,begin,stop,t)
                c.to_csv(folder/f'frozen_control_{name}.csv')
                pd.DataFrame(t).to_csv(folder/f'frozen_control_{name}_trades.csv',index=False)
                folds.append(dict(code=code,mode=mode,year=year,kind=r['kind'],training_start=tr.start,training_end=tr.end,
                                  selected_all=selected,selected_price=selected_price,evaluated=name,
                                  cagr_pct=r['annual_return_pct'],calmar=r['calmar'],sharpe=r['sharpe'],max_drawdown_pct=r['max_drawdown_pct'],
                                  average_exposure_pct=r['average_exposure_pct'],frozen_target=w,control_actual_exposure_pct=cm['average_exposure_pct'],
                                  frozen_control_cagr_excess_pp=r['annual_return_pct']-cm['annual_return_pct'],
                                  price_selected_calmar=stats[selected_price]['calmar'],price_selected_sharpe=stats[selected_price]['sharpe']))
            if any(k in NEEDS for k in (selected,selected_price)):
                a5=align_external(d.index,extra_lag=5);p5=policies(d,a5)
                for name in dict.fromkeys([selected,selected_price]):
                    if name in TARGETS:c,t,_=target_backtest(d,a5,p5[name],name,start,end)
                    else:c,t=cases[name],tm[name]
                    m=statistics(c,begin,stop,t)
                    sensitivity.append(dict(code=code,mode=mode,year=year,kind=stats[name]['kind'],strategy=name,
                                            base_calmar=stats[name]['calmar'],extra5d_calmar=m['calmar'],base_sharpe=stats[name]['sharpe'],extra5d_sharpe=m['sharpe'],
                                            base_cagr=stats[name]['annual_return_pct'],extra5d_cagr=m['annual_return_pct']))
                    c.to_csv(folder/f'extra5d_{name}_daily.csv');pd.DataFrame(t).to_csv(folder/f'extra5d_{name}_trades.csv',index=False)
            # 预测模型也只在完整更早训练窗上估计。
            # 跨产品预测：训练/测试使用同只ETF以防错误混接价格；518850无早期五年，因此不伪造该模型训练。
            if code=='518880':
                pred=predictive_test(d,a,pd.Timestamp(year-5,1,1),begin,stop)
                if pred:
                    m,pr=pred;predictions.append(dict(code=code,mode=mode,year=year,kind=stats['hold']['kind'],**m));pr.to_csv(folder/'return_forecasts.csv')
        plotted=list(dict.fromkeys(['hold','fixed50','price_trend','real','dollar','yuan','gvz','macro_vote']+([selected] if selected else [])))
        fig,axes=plt.subplots(4,1,figsize=(15,15),sharex=True)
        for name in plotted:
            c=cases[name];axes[0].plot(c.index,c.return_pct,label=LABELS[name]);axes[1].plot(c.index,c.drawdown_pct,label=LABELS[name]);axes[3].plot(c.index,c.exposure*100,label=LABELS[name])
        focus=selected if selected in NEEDS else 'macro_vote'
        c=cases[focus];axes[2].plot(c.index,d.close.reindex(c.index),color='goldenrod',label=LABELS[focus])
        for actions,color,marker in [(['首次建仓','加仓'],'green','^'),(['减仓','清仓'],'red','v')]:
            t=[v for v in tm[focus] if v['action'] in actions]
            if t:axes[2].scatter(pd.to_datetime([v['date'] for v in t]),[v['price'] for v in t],c=color,marker=marker,s=20,label='/'.join(actions))
        for ax,title in zip(axes,['累计收益 (%)','回撤 (%)','聚焦策略实际买卖点 (元)','实际仓位 (%)']):ax.set_ylabel(title);ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=3)
        fig.suptitle(f'{code} {mode} {year} / '+stats['hold']['kind']+' / 聚焦 '+LABELS[focus]);fig.tight_layout();fig.savefig(folder/'overview.png',dpi=110);plt.close(fig)
        # 所有少量组合及价格基准分别成图，避免只展示表现较好的个例。
        fig,axes=plt.subplots(2,2,figsize=(14,10),sharex=True)
        for ax,names,col in [(axes[0,0],['price_trend','trend_real','trend_macro'],'return_pct'),(axes[1,0],['price_trend','trend_real','trend_macro'],'drawdown_pct'),
                             (axes[0,1],['price_rv','gvz','trend_rv','trend_gvz','rates_dollar','macro_vol'],'return_pct'),(axes[1,1],['price_rv','gvz','trend_rv','trend_gvz','rates_dollar','macro_vol'],'drawdown_pct')]:
            for name in names:c=cases[name];ax.plot(c.index,c[col],label=LABELS[name])
            ax.set_ylabel('收益 (%)' if col=='return_pct' else '回撤 (%)');ax.legend(fontsize=7);ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(folder/'incremental.png',dpi=110);plt.close(fig)
        sections += [f'### {code} / {mode} / {year} / {stats["hold"]["kind"]}','',f'实际 {stats["hold"]["start"]}—{stats["hold"]["end"]}；独立初始10万元。冻结选择：{selected or "无更早完整五年训练窗"}；价格基准冻结选择：{selected_price or "不适用"}。','',
                     pd.DataFrame(list(stats.values()))[['strategy','annual_return_pct','max_drawdown_pct','calmar','sharpe','trades','average_exposure_pct','matched_cagr_excess_pp','parent_calmar_delta','parent_sharpe_delta']].to_markdown(index=False),'',
                     f'![收益回撤买卖及仓位]({folder.name}/overview.png)','',f'![外部指标的条件增量]({folder.name}/incremental.png)','',
                     f'[所有策略逐日账户]({folder.name}/all_daily.csv.gz) · [完整成交及所用信息时间]({folder.name}/all_trades.csv) · [窗口全部指标]({folder.name}/metrics.csv)','']
    pd.DataFrame(folds).to_csv(OUT/'cross_cycle.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(OUT/'delay_sensitivity.csv',index=False)
    pd.DataFrame(predictions).to_csv(OUT/'predictive_oos.csv',index=False)
    stability=table[(table.kind=='full')&table.strategy.isin(NEEDS)].groupby(['code','mode','strategy']).agg(n=('strategy','size'),
                median_matched_cagr=('matched_cagr_excess_pp','median'),worst_matched_cagr=('matched_cagr_excess_pp','min'),
                median_parent_calmar=('parent_calmar_delta','median'),worst_parent_calmar=('parent_calmar_delta','min'),
                median_parent_sharpe=('parent_sharpe_delta','median'),positive_matched_cagr=('matched_cagr_excess_pp',lambda x:int((x>0).sum()))).reset_index()
    stability.to_csv(OUT/'stability.csv',index=False)
    latest=[]
    for code in ('518850','518880'):
        d=get_data(code);a=align_external(d.index);p=policies(d,a)
        latest.append(dict(code=code,etf_date=str(d.index[-1].date()),etf_close=float(d.close.iloc[-1]),
                           available={name:{col:str(a.iloc[-1][f'{name}_{col}']) for col in ['observation_date','available_at','value','change20','good','valid']} for name in SERIES},
                           hypothetical_targets={name:float(p[name].iloc[-1]) for name in TARGETS},
                           last_friday_signal=str(d.index[d.index.weekday==4][-1].date())))
        for series,_ in SERIES.values():
            path=OUT/'data'/f'{series}_raw.csv';manifest[series]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        path=Path('results/gold_full_cycle/data')/f'{code}_qfq.csv';manifest[code]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (OUT/'latest_state.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    design=(OUT/'DESIGN.md').read_text(encoding='utf-8')
    lines=['# 黄金外部指标：经济逻辑、可用时间与五年验证','',
           '## 本轮证据边界','',
           '本研究已先冻结设计，再下载外部指标、进行回测。关键限制：缺少逐日不可修改的首次发布版本，故已防范观测日误用、时区及已知公布频率泄漏，但历史修订风险仍存在。所有结果只属于带延迟约束的探索性历史检验，不是严格点时已验证预测。产品信号不变。','',
           design,'','## 完整五年稳定性','',stability.to_markdown(index=False),'',
           '## 跨周期冻结选择','',pd.DataFrame(folds).to_markdown(index=False),'',
           '同一训练窗分别冻结“含外部指标的全部候选”与“只含价格及固定仓位的候选”；测试期不重选。若两者同一策略，不把重复结果说成外部指标增益。训练平均仓位冻结到测试窗的固定比例对照另列，不保证测试平均仓位相同；matched字段为事后同仓位诊断，不是可交易择时策略。','',
           '## 发布延迟额外增加5天','',pd.DataFrame(sensitivity).to_markdown(index=False),'',
           '## 未来20交易日收益的预测增量','',pd.DataFrame(predictions).to_markdown(index=False),'',
           'incremental_oos_r2=1−外部模型MSE/价格模型MSE，正数表示在共同测试样本上预测误差更小。20日标签重叠、测试窗重叠，因此不输出简单独立样本p值。这个回归诊断不用于事后改写买卖规则；518850没有早期五年历史，不伪造其回归训练。','',
           '## 最新可用数据而非最新观测日','',
           '外部可用日期和当前条件保存在[latest_state.json](latest_state.json)。2026-10-29是周四，周频策略本周尚未形成周五收盘新单；当前状态仅供观察，不能把周四最新数值说成已成交信号。',
           '[全部窗口指标](all_metrics.csv) · [冻结验证](cross_cycle.csv) · [预测增量](predictive_oos.csv) · [来源与哈希](manifest.json) · [下载时间及数据来源](data/fetch.json)','',
           '## 各窗口全部证据','']+sections
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    supplement()
    print('Saved',len(table),'strategy runs',flush=True)


def supplement():
    """重建所有策略的离线曲线浏览器及结论，不重新拟合策略。"""
    from research_gold_full_cycle import explorer,clean_records
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    table=pd.read_csv(OUT/'all_metrics.csv',dtype={'code':str})
    stability=pd.read_csv(OUT/'stability.csv',dtype={'code':str})
    state=json.loads((OUT/'latest_state.json').read_text(encoding='utf-8'))[0]
    state_rows=[]
    for name,values in state['available'].items():state_rows.append(dict(indicator=LABELS[name],**values))
    current=pd.DataFrame(state_rows)
    narrative=['## 研究结论与当前买入判断','',
               '**在本轮固定规则、保守公布延迟和有限完整五年周期下，尚未找到可稳定提高风险调整后收益的外部指标买卖策略。不能因为宏观叙事合理，就把它升级为可靠买点。**',
               '实际利率、DXY、人民币及GVZ各有经济含义，但实际利率和人民币都只是某些周期有利；DXY单指标及实际利率+DXY组合在518880七个完整滚动窗口中均未跑赢事后同平均仓位对照。GVZ有4/7窗口年化跑赢匹配对照，相对ETF自身实现波动率的Calmar和Sharpe中位差为正，但最差周期为负，仍不能称稳定有效；它首先是风险信息，不是上涨方向信号。',
               '### 冻结到后续周期后发生了什么','',
               '2015—2019训练选出宏观三项投票；测试2020—2024，其Calmar约0.474、Sharpe约0.673，低于同一训练窗冻结选出的定期买入1.011、1.077。该宏观策略相对训练仓位冻结的固定比例对照，年化落后约2.58个百分点。',
               '2016—2020训练选出宏观投票+GVZ；测试2021—2025，518880 Calmar约1.056、Sharpe约1.199，低于冻结价格基准长期持有1.646、1.391。虽然回撤降至8.37%（持有11.52%），收益损失没有被风险下降充分补偿；同平均仓位和固定仓位对照表明，不能把缩仓直接当额外预测价值。518850验证方向相同。',
               '2020—2024训练时，含外部指标候选与价格候选都选中定期买入，故2025以后没有可归因于宏观指标的新增选型价值。该短期留出仍不满五年，不能与完整五年混合排名。',
               '额外增加5天延迟后部分结果反而改善，说明对执行时点敏感；不能事后改用更漂亮的延迟设定宣称稳健。固定和滚动重复窗口及两只同类ETF均不当独立样本。',
               '### 是否真的增加了收益预测信息','',
               '与相同训练/测试样本的价格特征岭模型比较，加入四项外部特征后，2020—2024、2021—2025未来20交易日收益预测MSE分别增加约6.39%、7.13%；2025至今成熟样本误差下降约5.08%，方向不稳定，且该段不满五年。20日标签重叠，不能把420或1192个日标签当等量独立证据。模型并非所有可能预测器的穷举，负结果只适用于本轮固定设计。',
               '### 截至2026-10-29当前真正可用的输入','',current.to_markdown(index=False),'',
               'available_at列是本研究保守估计的可用时间，不是逐条核实的历史发布时间。实际利率用10月27日2.64%，较20个有效观测前下降0.26个百分点；DXY同期上涨约0.94%，美元兑人民币20观测约下降0.23%（人民币升值），对人民币黄金的简单经济逻辑相互抵消。GVZ为10月27日22.58，低于其滚动中位数，仅表示本规则风险上限放宽，不表示金价应上涨。人民币输入为10月15日，明确不是今天市场报价。',
               '行情仍为518850收盘8.315元、518880收盘8.224元。模型假设目标50%或100%只是研究账户状态，不是家庭黄金配置建议；周频规则本周还需等待10月30日周五收盘，再决定下个交易日订单，当前没有已执行的新宏观买入信号。',
               '**当前建议：不因实际利率下降或GVZ回落而加速买入，也不把宏观投票结果作为必须空仓的证据。若已有五年黄金预算，可维持原定的小额月度投入；若没有明确预算和持有期限，先暂缓确定投入比例。没有足够证据支持一次性大额买入。**',
               '若采用原先每月黄金预算1/60（约1.67%）的路径，本轮不提高这个额度；它仍是固定预算执行选择，不是已证实最优的比例。该预算不是家庭全部资产，100份取整及费用可能使实际投入更低。',
               '证据等级：已经核查的是观测→保守可用时间→中国信号收盘→次日交易的顺序、账本与冻结历史结果。尚未完成逐日首次发布版本核对，历史纠错/修订风险未消除；因此不是严格点时验证，也不是已验证的未来预测优势。产品策略及自动提醒未修改。','']
    advice_path=OUT/'current_advice.md';old=advice_path.read_text(encoding='utf-8') if advice_path.exists() else ''
    advice_path.write_text('\n'.join(narrative),encoding='utf-8')
    p=OUT/'report.md';text=p.read_text(encoding='utf-8')
    if old:text=text.replace(old,'')
    if '## 研究结论与当前买入判断' not in text:
        title,rest=text.split('\n',1);text=title+'\n\n'+'\n'.join(narrative)+'\n'+rest
    # 图中逐个窗口展示外部信息的同仓位增量，避免只选平均正收益。
    subset=table[(table.code=='518880')&(table['mode']=='rolling')&(table.kind=='full')&table.strategy.isin(NEEDS)]
    fig,axes=plt.subplots(1,2,figsize=(15,7))
    for ax,col,title in [(axes[0],'matched_cagr_excess_pp','相对同平均仓位的年化差 (百分点)'),(axes[1],'parent_calmar_delta','相对指定价格父策略的Calmar差')]:
        matrix=subset.pivot(index='strategy',columns='year',values=col).reindex(NEEDS)
        z=matrix.to_numpy();bound=max(abs(np.nanmin(z)),abs(np.nanmax(z)),.01)
        im=ax.imshow(z,aspect='auto',cmap='RdYlGn',vmin=-bound,vmax=bound)
        ax.set_xticks(range(len(matrix.columns)),[f'{y}—{y+4}' for y in matrix.columns],rotation=45,ha='right')
        ax.set_yticks(range(len(matrix)),[LABELS[x] for x in matrix.index]);ax.set_title(title)
        for i in range(len(matrix)):
            for j in range(len(matrix.columns)):ax.text(j,i,f'{z[i,j]:.2f}',ha='center',va='center',fontsize=8)
        fig.colorbar(im,ax=ax)
    fig.tight_layout();fig.savefig(OUT/'external_increment.png',dpi=120);plt.close(fig)
    if 'external_increment.png' not in text:text=text.replace('## 完整五年稳定性','![外部指标逐窗口增量](external_increment.png)\n\n## 完整五年稳定性')
    for folder in OUT.glob('*_*_20*'):
        if not (folder/'all_daily.csv.gz').exists():continue
        code=folder.name.split('_')[0];d=get_data(code)
        raw=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date']).set_index(['strategy','date'])
        cases={k:g.droplevel(0) for k,g in raw.groupby(level=0)}
        trades=pd.read_csv(folder/'all_trades.csv')
        tm={k:clean_records(trades[trades.strategy==k].drop(columns='strategy').to_dict('records')) for k in cases}
        renamed={('buy_hold' if k=='hold' else k):v for k,v in cases.items()}
        renamed_trades={('buy_hold' if k=='hold' else k):v for k,v in tm.items()}
        begin=pd.Timestamp(int(folder.name.split('_')[-1]),1,1)
        stop=begin+pd.DateOffset(years=5)
        if stop>d.index[-1]:stop=d.index[-1]+pd.Timedelta(days=1)
        metrics=[]
        for k,c in cases.items():metrics.append(dict(rule='buy_hold' if k=='hold' else k,**statistics(c,begin,stop,tm[k])))
        explorer(folder,code,renamed,renamed_trades,clean_records(metrics),d)
        needle=f'[所有策略逐日账户]({folder.name}/all_daily.csv.gz)'
        link=f'[所有策略及匹配对照的交互曲线与交易]({folder.name}/explorer.html) · '
        if f'{folder.name}/explorer.html' not in text:text=text.replace(needle,link+needle)
    p.write_text(text,encoding='utf-8')


if __name__=='__main__':main()
