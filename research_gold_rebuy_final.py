"""固定15%卖点，只研究买回；不做事后参数优选。"""
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from research_gold_full_cycle import statistics
from research_gold_entry_value import get_data
from gold_strategy import stages

OUT=Path('results/gold_rebuy_final')
VARIANTS=['hold','cool5','wait10','wait20','wait60','trend20','trend120','never']
LABELS={'hold':'纯长期持有','cool5':'双指标5%冷却','wait10':'等10交易日','wait20':'等20交易日','wait60':'等60交易日',
        'trend20':'20日趋势恢复','trend120':'120日趋势恢复','never':'减半后不买回'}


def indicators(data):
    c=data.close;f=pd.DataFrame(index=data.index)
    f['rise20']=c.pct_change(20,fill_method=None)
    for n in (20,60,120):f[f'ma{n}']=c.rolling(n,min_periods=n).mean()
    f['dev60']=c/f.ma60-1
    f['hot']=(f.rise20>=.15)&(f.dev60>=.15)
    f['pulse']=f.hot&~f.hot.shift(1,fill_value=False)
    f['cold']=(f.rise20<=.05)&(f.dev60<=.05)
    for n in (20,120):f[f'trend{n}']=(c>f[f'ma{n}'])&(f[f'ma{n}']>f[f'ma{n}'].shift(5))
    return f


def run(data,f,start,end,variant,skip_sales=None,skip_buybacks=None,allowed_sales=None):
    cash=100000.;qty=0;waiting=False;sale_index=None;event=None;weakened=False;entered=False
    trades=[];orders=[];daily=[]
    skip_sales=set(skip_sales or []);skip_buybacks=set(skip_buybacks or [])
    idx=data.index;op=data.open.to_numpy(float);cl=data.close.to_numpy(float)
    hi=data.high.to_numpy(float);lo=data.low.to_numpy(float)
    values={k:f[k].to_numpy() for k in f.columns}
    for i in range(start,end):
        j=i-1;intent=None;reason='';origin=event
        if not entered:
            intent='initial';reason='独立账户预先计划立即建仓；投入全部可用现金'
        elif variant!='hold' and waiting:
            if variant.startswith('trend'):
                n=int(variant[5:])
                if cl[j]<=values[f'ma{n}'][j]:weakened=True
                ready=weakened and bool(values[f'trend{n}'][j])
                reason=f'减仓后曾跌至{n}日线或下方，现重新在线上且均线高于5日前'
            elif variant.startswith('wait'):
                n=int(variant[4:]);ready=i-sale_index>=n
                reason=f'实际减仓后持币满{n}个交易日，按既定时间买回'
            elif variant=='cool5':
                ready=bool(values['cold'][j]);reason='20日涨幅与60日均线偏离均≤5%，冷却买回'
            else:ready=False
            if ready and event not in skip_buybacks:intent='restore'
        elif variant!='hold' and j>=0:
            pulse=bool(values['pulse'][j])
            # 初始立即建仓优先；若开窗时已过热，首个持仓日收盘仍热则允许一次减仓。
            pulse |= (i==start+1 and bool(values['hot'][j]))
            signal=str(idx[j].date())
            if pulse and signal not in skip_sales and (allowed_sales is None or signal in allowed_sales):
                intent='reduce';origin=signal;reason='20日涨幅及60日均线偏离均≥15%的热区起点，已有持仓减半一次'
        if intent:
            buy=intent!='reduce';execution=op[i]*(1.001 if buy else .999)
            one=hi[i]==lo[i]
            blocked=j>=0 and one and ((buy and op[i]/cl[j]-1>=.097) or (not buy and op[i]/cl[j]-1<=-.097))
            units=0 if blocked else int(cash/(execution*1.0001)//100)*100 if buy else int(qty*.5//100)*100
            if buy:
                while units>0 and units*execution+max(5.,units*execution*.0001)>cash+1e-8:units-=100
            order=dict(date=str(idx[i].date()),signal_date=str(idx[j].date()) if j>=0 else '',preplanned=intent=='initial',
                       intent=intent,event=origin if intent!='initial' else '',reason=reason,
                       status='limit_blocked' if blocked else 'filled' if units else 'lot_or_cash_blocked')
            orders.append(order)
            if units:
                fee=max(5.,units*execution*.0001)
                cash+=-units*execution-fee if buy else units*execution-fee
                qty+=units if buy else -units
                if intent=='initial':entered=True
                elif intent=='reduce':waiting=True;sale_index=i;event=origin;weakened=False
                else:waiting=False
                trades.append(dict(**order,action={'initial':'首次建仓','reduce':'减仓','restore':'买回'}[intent],quantity=units,price=execution,fee=fee,
                                   cash_after=cash,quantity_after=qty,
                                   return20_pct=float(values['rise20'][j]*100) if j>=0 else None,
                                   dev60_pct=float(values['dev60'][j]*100) if j>=0 else None))
        equity=cash+qty*cl[i]
        daily.append((idx[i],cash,qty,equity,qty*cl[i]/equity))
    curve=pd.DataFrame(daily,columns=['date','cash','quantity','equity','exposure']).set_index('date')
    curve['return_pct']=(curve.equity/100000.-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=100000.)-1)*100
    return curve,trades,orders


def cycle_attribution(data,f,start,end,variant,curve,trades,begin,stop):
    actual=statistics(curve,begin,stop,trades);rows=[];counter={}
    for sale in (t for t in trades if t['action']=='减仓'):
        event=sale['event'];rebuy=next((t for t in trades if t['action']=='买回' and t['event']==event),None)
        si=data.index.get_loc(pd.Timestamp(sale['date']))
        bi=data.index.get_loc(pd.Timestamp(rebuy['date'])) if rebuy else end-1
        mark=rebuy['price'] if rebuy else float(data.close.iloc[end-1])
        q=sale['quantity'];buyfee=max(5.,q*mark*.0001) if rebuy else 0.
        # 买回日开盘之后的涨跌已经重新承担，不能记作持币期间避免/错过。
        segment=data.close.iloc[si:bi] if rebuy else data.close.iloc[si:bi+1]
        if rebuy:segment=pd.concat([segment,pd.Series([float(data.open.iloc[bi])])],ignore_index=True)
        omitted,ot,_=run(data,f,start,end,variant,skip_sales={event})
        no_buy,nt,_=run(data,f,start,end,variant,skip_buybacks={event})
        os=statistics(omitted,begin,stop,ot);ns=statistics(no_buy,begin,stop,nt)
        counter[f'{variant}_{event}_skip_sale']=omitted
        counter[f'{variant}_{event}_skip_buyback']=no_buy
        rows.append(dict(variant=variant,event=event,sell_date=sale['date'],rebuy_date=rebuy['date'] if rebuy else '',closed=bool(rebuy),
                         sold_quantity=q,bought_quantity=rebuy['quantity'] if rebuy else 0,sell_price=sale['price'],rebuy_or_mark_price=mark,
                         wait_trading_days=bi-si if rebuy else None,
                         fixed_quantity_timing_value_yuan=q*(sale['price']-mark)-sale['fee']-buyfee,
                         sold_lot_avoided_worst_loss_yuan=max(0.,q*(sale['price']-float(segment.min()))),
                         sold_lot_missed_best_gain_yuan=max(0.,q*(float(segment.max())-sale['price'])),
                         full_cycle_final_return_contribution_pp=actual['return_pct']-os['return_pct'],
                         full_cycle_drawdown_improvement_pp=os['max_drawdown_pct']-actual['max_drawdown_pct'],
                         buyback_and_followup_return_contribution_pp=actual['return_pct']-ns['return_pct'],
                         buyback_and_followup_drawdown_improvement_pp=ns['max_drawdown_pct']-actual['max_drawdown_pct']))
    return rows,counter


def plots(folder,data,cases,tm,title):
    fig,axes=plt.subplots(4,1,figsize=(14,14),sharex=True)
    for name,c in cases.items():
        axes[0].plot(c.index,c.return_pct,label=LABELS[name]);axes[1].plot(c.index,c.drawdown_pct,label=LABELS[name]);axes[3].plot(c.index,c.exposure*100,label=LABELS[name])
    c=cases['cool5'];axes[2].plot(c.index,data.close.reindex(c.index),color='goldenrod',label='5%冷却方案价格')
    for action,color,marker in [('首次建仓','green','^'),('减仓','red','v'),('买回','blue','^')]:
        t=[v for v in tm['cool5'] if v['action']==action]
        if t:axes[2].scatter(pd.to_datetime([v['date'] for v in t]),[v['price'] for v in t],color=color,marker=marker,label=action,s=32,zorder=4)
    for ax,label in zip(axes,['累计收益 (%)','回撤 (%)','5%方案实际买卖点 (元)','实际仓位 (%)']):ax.set_ylabel(label);ax.legend(fontsize=8,ncol=3);ax.grid(alpha=.2)
    fig.suptitle(title);fig.tight_layout();fig.savefig(folder/'overview.png',dpi=110);plt.close(fig)
    fig,axes=plt.subplots(7,1,figsize=(14,18),sharex=True)
    for name,ax in zip(VARIANTS[1:],axes):
        c=cases[name];ax.plot(c.index,data.close.reindex(c.index),color='goldenrod',linewidth=.8)
        for action,color,marker in [('首次建仓','green','^'),('减仓','red','v'),('买回','blue','^')]:
            t=[v for v in tm[name] if v['action']==action]
            if t:ax.scatter(pd.to_datetime([v['date'] for v in t]),[v['price'] for v in t],color=color,marker=marker,label=action,s=22,zorder=4)
        ax.set_ylabel(LABELS[name]+'\n(元)');ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=3)
    fig.suptitle(title+' / 全部机制实际成交');fig.tight_layout();fig.savefig(folder/'all_trades.png',dpi=110);plt.close(fig)


def common_events(data,f,code):
    rows=[];trades_all=[];sections=[]
    for date in f.index[f.pulse]:
        event=str(date.date());si=data.index.get_loc(date)+1
        if si>=len(data):continue
        planned_end=data.index[si]+pd.DateOffset(months=12)
        end=min(len(data),int(data.index.searchsorted(planned_end))+1)
        complete=planned_end<=data.index[-1]
        start=si-1;begin=data.index[start];stop=data.index[end-1]+pd.Timedelta(days=1)
        folder=OUT/f'event_{code}_{event}';folder.mkdir(exist_ok=True)
        cases={};tm={};stats={}
        for name in VARIANTS:
            c,t,_=run(data,f,start,end,name,allowed_sales={event})
            cases[name]=c;tm[name]=t;stats[name]=statistics(c,begin,stop,t)
        for name in VARIANTS:
            m=stats[name]
            row=dict(code=code,event=event,sell_date=str(data.index[si].date()),planned_end=str(planned_end.date()),actual_end=str(data.index[end-1].date()),
                     complete12m=complete,variant=name,
                     reduction_only_return_pp=stats['never']['return_pct']-stats['hold']['return_pct'] if name!='hold' else 0.,
                     buyback_increment_return_pp=m['return_pct']-stats['never']['return_pct'] if name!='hold' else 0.,
                     total_vs_hold_return_pp=m['return_pct']-stats['hold']['return_pct'],
                     total_vs_hold_drawdown_improvement_pp=stats['hold']['max_drawdown_pct']-m['max_drawdown_pct'],**m)
            rows.append(row)
            trades_all.extend([dict(code=code,common_event=event,variant=name,**t) for t in tm[name]])
        pd.concat(cases,names=['variant','date']).to_csv(folder/'all_daily.csv.gz',compression='gzip')
        plots(folder,data,cases,tm,f'{code}共同事件{event} / '+('满12个月' if complete else '未满12个月'))
        block=pd.DataFrame([r for r in rows if r['code']==code and r['event']==event])
        block.to_csv(folder/'metrics.csv',index=False)
        sections += [f'### {code}共同事件 {event} / '+('满12个月' if complete else '未满12个月'),'',
                     block[['variant','return_pct','max_drawdown_pct','reduction_only_return_pp','buyback_increment_return_pp','total_vs_hold_return_pp','total_vs_hold_drawdown_improvement_pp']].to_markdown(index=False),'',
                     f'![共同卖出事件的收益风险和仓位]({folder.name}/overview.png)','',f'![共同卖出事件全部成交]({folder.name}/all_trades.png)','']
    return rows,trades_all,sections


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    results=[];attributions=[];event_rows=[];event_trades=[];sections=[];event_sections=[];compat=[];manifest={}
    for code in ('518880','518850'):
        d=get_data(code);f=indicators(d)
        path=Path('results/gold_full_cycle/data')/f'{code}_qfq.csv'
        manifest[code]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'start':str(d.index[0].date()),'end':str(d.index[-1].date()),
                        'type':'真实ETF原标的' if code=='518850' else '真实ETF；518850同类代理'}
        s=stages(d.close)
        rawdates=list(f.index[f.pulse].strftime('%Y-%m-%d'))
        stage_dates=list(s.index[(s.target==.5)&(s.target.shift(1)==1)].strftime('%Y-%m-%d'))
        compat.append(dict(code=code,raw_hot_pulses=rawdates,existing_cold_stage_pulses=stage_dates,equal=rawdates==stage_dates))
        specs=[('longest',d.index[0],d.index[-1]+pd.Timedelta(days=1),'longest')]
        if code=='518880':
            specs += [('fixed',pd.Timestamp(y,1,1),pd.Timestamp(y+5,1,1),'full') for y in (2015,2020)]
            specs += [('rolling',pd.Timestamp(y,1,1),pd.Timestamp(y+5,1,1),'full') for y in range(2014,2022)]
            specs += [('development',pd.Timestamp('2015-01-01'),pd.Timestamp('2025-01-01'),'development')]
        else:specs += [('fixed',pd.Timestamp('2021-01-01'),pd.Timestamp('2026-01-01'),'full')]
        specs += [('recent',pd.Timestamp('2025-01-01'),d.index[-1]+pd.Timedelta(days=1),'partial')]
        for mode,begin,stop,kind in specs:
            start=int(d.index.searchsorted(begin));end=int(d.index.searchsorted(stop))
            if start>=end:continue
            folder=OUT/f'{code}_{mode}_{begin.year}';folder.mkdir(exist_ok=True)
            cases={};tm={};local=[];counter={};orders=[]
            for name in VARIANTS:
                c,t,o=run(d,f,start,end,name);cases[name]=c;tm[name]=t
                m=statistics(c,begin,stop,t)
                row=dict(code=code,mode=mode,kind=kind,start=str(c.index[0].date()),end=str(c.index[-1].date()),initial_cash=100000.,variant=name,
                         first_entry=t[0]['date'] if t else '',reductions=sum(v['action']=='减仓' for v in t),buybacks=sum(v['action']=='买回' for v in t),**m)
                local.append(row);results.append(row)
                orders.extend([dict(variant=name,**v) for v in o])
                attr,cf=cycle_attribution(d,f,start,end,name,c,t,begin,stop)
                attributions.extend([dict(code=code,mode=mode,window_start=str(c.index[0].date()),window_end=str(c.index[-1].date()),**r) for r in attr]);counter.update(cf)
            for row in local:
                row['return_vs_hold_pp']=row['return_pct']-local[0]['return_pct']
                row['drawdown_improvement_pp']=local[0]['max_drawdown_pct']-row['max_drawdown_pct']
            pd.DataFrame(local).to_csv(folder/'metrics.csv',index=False)
            pd.concat(cases,names=['variant','date']).to_csv(folder/'all_daily.csv.gz',compression='gzip')
            pd.DataFrame([dict(variant=k,**v) for k,t in tm.items() for v in t]).to_csv(folder/'all_trades.csv',index=False)
            pd.DataFrame(orders).to_csv(folder/'all_orders.csv',index=False)
            if counter:pd.concat(counter,names=['counterfactual','date']).to_csv(folder/'event_counterfactuals.csv.gz',compression='gzip')
            plots(folder,d,cases,tm,f'{code} {mode} {begin.date()}—{(stop-pd.Timedelta(days=1)).date()} / {kind}')
            sections += [f'### {code} / {mode} / {kind}','',f'实际区间{local[0]["start"]}—{local[0]["end"]}；独立初始10万元。','',
                         pd.DataFrame(local)[['variant','first_entry','return_pct','annual_return_pct','max_drawdown_pct','calmar','sharpe','average_exposure_pct','reductions','buybacks','return_vs_hold_pp','drawdown_improvement_pp']].to_markdown(index=False),'',
                         f'![收益回撤及仓位]({folder.name}/overview.png)','',f'![各机制实际买卖点]({folder.name}/all_trades.png)','',
                         f'[完整成交]({folder.name}/all_trades.csv) · [逐日账户]({folder.name}/all_daily.csv.gz) · [订单及失败原因]({folder.name}/all_orders.csv) · [指标]({folder.name}/metrics.csv)','']
            print('Window',code,mode,str(begin.date()),flush=True)
        er,et,es=common_events(d,f,code);event_rows+=er;event_trades+=et;event_sections+=es
    pd.DataFrame(results).to_csv(OUT/'all_metrics.csv',index=False)
    pd.DataFrame(attributions).to_csv(OUT/'cycle_contributions.csv',index=False)
    pd.DataFrame(event_rows).to_csv(OUT/'common_event_metrics.csv',index=False)
    pd.DataFrame(event_trades).to_csv(OUT/'common_event_trades.csv',index=False)
    (OUT/'compatibility.json').write_text(json.dumps(compat,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 黄金15%过热减半：买回机制最终历史验证','',
           '**本轮不发布最优买回参数：2015—2024没有15%双指标减仓事件，全部3个机会都来自2025—2026。完整较早周期不能为买回机制提供独立事件验证，最长区间和近年好成绩也不能弥补样本外证据缺口。**','',
           (OUT/'DESIGN.md').read_text(encoding='utf-8'),'','## 如何阅读交易贡献','',
           'cycle_contributions.csv中的固定份数净价差是局部反事实，不是完整账户已实现利润。full_cycle_final_return_contribution_pp是完整机制减去跳过该次减仓后的期末收益差；full_cycle_drawdown_improvement_pp是对应的全窗回撤改善。buyback_and_followup列与本次减仓后永不买回的完整重放比较，包含之后可能发生的买回和新交易，不是单独一笔订单的纯因果效果。各次差额有交互，不能求和重构总收益。',
           '共同事件实验将减仓日、初始资金及后续观察期固定，return_total=减仓不买回相对持有差+买回相对不买回差，期末财富差可严格核对；回撤具有路径依赖，风险差不作独立可加的原因分解。尚未买回的周期及未满12个月事件明确标记，不称已完成盈利。','',
           '[全部指标](all_metrics.csv) · [逐次交易贡献](cycle_contributions.csv) · [共同卖点事件指标](common_event_metrics.csv) · [共同事件全部成交](common_event_trades.csv) · [与既有热区口径兼容性](compatibility.json)','',
           '## 完整五年及最长历史','']+sections+['## 共同卖出事件下的独立买回比较','']+event_sections
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    summarize()
    print('Saved',len(results),'window strategy accounts;',len(event_rows),'isolated event accounts',flush=True)


def summarize():
    metrics=pd.read_csv(OUT/'all_metrics.csv',dtype={'code':str})
    contributions=pd.read_csv(OUT/'cycle_contributions.csv',dtype={'code':str})
    events=pd.read_csv(OUT/'common_event_metrics.csv',dtype={'code':str})
    table=metrics[(metrics.code=='518880')&(metrics['mode']=='longest')].copy()
    table['机制']=table.variant.map(LABELS)
    cols=['机制','return_pct','annual_return_pct','max_drawdown_pct','calmar','sharpe','average_exposure_pct','reductions','buybacks']
    curated=events[(events.code=='518880')&(events.variant=='cool5')][['event','complete12m','reduction_only_return_pp','buyback_increment_return_pp','total_vs_hold_return_pp','total_vs_hold_drawdown_improvement_pp']]
    attr=contributions[(contributions.code=='518880')&(contributions['mode']=='longest')].copy()
    attr['机制']=attr.variant.map(LABELS)
    narrative=['## 最终验证结论：可以复现，尚不能证实跨周期有效','',
               '主规则按题意立即建仓并长期持有，过热只减半；本轮仅改变买回，未加入普通下跌清仓，也未修改产品信号。完整五年、最长历史、共同事件和消融记录均已保存。所有机制按事前列定顺序展示，不按2025—2026收益或风险指标排序，也不从中指定最优参数。',
               '**2015—2024没有减仓事件，所以固定五年及截至2024的滚动窗口中，各机制与长期持有完全相同；这验证了不重复交易的实现，不能验证15%卖点或买回机制有效。最长历史虽有13年多，真正用于检验卖出和买回的仍只有2025—2026的3次底层事件。**',
               '### 最长真实ETF历史：收益与风险的取舍','',
               '518880为2013-07-29—2026-10-29，指标形成前按立即买入持有；下表以同一10万元起点计算，收益含费用。它是518880真实历史，对原标的518850仅是同类代理，不拼接。','',table[cols].to_markdown(index=False),'',
               '5%冷却在这一段的累计收益、Calmar及Sharpe均高于持有，但其全部优势来自已经看过的3个近年事件。固定等待60日在本段风险指标更高，也不能据此选60日；2025年10月那个共同事件中，60日买回反而低于长期持有。长期不买回通常降低风险，却可能错过上涨。单一完整区间排名无法替代多周期事件证据。',
               '518850最长可得区间为2020-06-05—2026-10-29，不冒充成立以来全历史：持有收益113.14%、最大回撤31.07%、Calmar约0.404、Sharpe约0.807；5%冷却收益139.10%、回撤27.05%、Calmar约0.539、Sharpe约0.985。两只ETF共同经历同3次黄金行情，不是6次独立验证。',
               '### 减仓与买回的贡献方向并不一致','',
               '以下只取518880三个共同事件、单次减仓后观察12个月；2026年事件尚未满12个月。每行收益差以相同10万元为分母，单位为百分点，严格满足“总差=减仓不买回差+买回增量”。','',curated.to_markdown(index=False),'',
               '2025年4月：只减仓不买回少赚约13.54个百分点；5%买回相对不买回增加约18.82个百分点，合计相对持有多约5.27个百分点，但该事件完整观察期最大回撤没有改善。2025年10月：减仓不买回有利，买回反而削弱保护。2026年1月：截至当前，5%买回相对不买回减少约10.93个百分点的收益保护；不能只看它最终仍胜过满仓持有，就认为买回本身是成功信号。',
               '上述12个月窗口彼此重叠，且初始条件依赖事后识别卖出事件，属于局部反事实而非可事前运行的独立策略；2026事件不能与已满12个月的事件混排。',
               '### 5%条件对相近ETF的边界敏感','',
               '2026-02-02，518880的20日涨幅约4.35%、60日偏离约4.00%，同时低于5%，次日2月3日模拟买回；518850的20日涨幅约5.11%、偏离约4.75%，只差其中一个条件，直到3月17日才模拟买回。两只高度相关ETF因此相差约六周，说明“5%”可能对小幅价格差异和边界噪声敏感，不能把它当成稳定的经济拐点。',
               '### 最长账户逐次交易及条件贡献','',
               'closed=False表示尚未买回；固定份数估值不是已实现账户盈利。全账户跳过减仓与跳过买回后的差额包含之后份额和交易路径变化，不可把各行直接相加。','',
               attr[['机制','event','sell_date','rebuy_date','closed','fixed_quantity_timing_value_yuan','full_cycle_final_return_contribution_pp','full_cycle_drawdown_improvement_pp','buyback_and_followup_return_contribution_pp']].to_markdown(index=False),'',
               '### 验证程度及执行结论','',
               '已经验证的是本轮确定状态机、费用取整、次日成交、交易路径、每次条件重放及历史结果可复现；没有足够证据验证任一买回机制的未来有效性。2025—2026已经被反复查看，不能称严格未见样本外，也不能用此前没有事件的周期为它补充胜率。',
               '本轮不建议据此改成收益排名最高或回撤最低的买回规则，不把5%、10/20/60日或某条均线定为最终最佳。若将来要在研究账户继续观察，应先冻结选择和真实新增行情起点，再收集新的过热—买回事件；此报告不启动交易或自动更新产品。','']
    new='\n'.join(narrative);summary_path=OUT/'conclusions.md'
    old=summary_path.read_text(encoding='utf-8') if summary_path.exists() else ''
    p=OUT/'report.md';text=p.read_text(encoding='utf-8')
    if old:text=text.replace(old,'')
    title,remaining=text.split('\n',1)
    p.write_text(title+'\n\n'+new+'\n'+remaining,encoding='utf-8')
    summary_path.write_text(new,encoding='utf-8')


if __name__=='__main__':main()
