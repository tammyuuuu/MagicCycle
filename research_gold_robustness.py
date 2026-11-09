"""8—15%过热阈值稳健性、信号消融及交易事件归因。"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from gold_strategy import stages
from research_sector_partial_exit import backtest_partial
from research_gold_five_year import metrics

OUT=Path('results/gold_robustness')
THRESHOLDS=range(8,16)
VARIANTS=['cool5','no_rebuy','wait20']


def signal(close,threshold,variant,start=120):
    normal=stages(close,threshold/100).target
    if variant=='cool5':return normal
    if variant=='no_rebuy':
        # 第一次减仓后一直保留现金：与完整策略之差包括所有后续买回及再减仓。
        result=normal.copy();entered=False
        for i in range(start-1,len(normal)):
            if normal.iloc[i]==1:entered=True
            if entered and normal.iloc[i]==.5:
                result.iloc[i:]=.5
                break
        return result
    if variant!='wait20':raise ValueError(variant)
    result=normal.copy();until=-1;prev=0.
    for i,x in enumerate(normal):
        if x==.5 and prev!=.5:until=i+20
        result.iloc[i]=0. if i<119 else .5 if i<until else 1.
        prev=x
    return result


def execute(data,start,threshold,variant):
    target=pd.Series(1.,index=data.index) if threshold==0 else signal(data.close,threshold,variant,start)
    stats,curve,trades=backtest_partial(data,target,start,len(data),initial_cash=100000.,limit_pct=.10)
    curve['return_pct']=(curve.equity/100000.-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=100000.)-1)*100
    for t in trades:
        i=data.index.get_loc(pd.Timestamp(t['date']));j=i-1;c=data.close
        t.update(signal_date=str(data.index[j].date()),return20_pct=float((c.iloc[j]/c.iloc[j-20]-1)*100),
                 deviation60_pct=float((c.iloc[j]/c.iloc[j-59:j+1].mean()-1)*100))
        t['reason']=('初次建仓，前日目标为全投入' if t['action']=='买入' else
                     f'20日涨幅与60日偏离均达到{threshold}%，首次减半' if t['action']=='减仓' else
                     '双指标均不高于5%，投入剩余现金' if variant=='cool5' else '距减仓信号20个交易日，投入剩余现金')
        for n in (20,60):
            t[f'forward_{n}d_price_return_pct']=float((c.iloc[i+n]/t['price']-1)*100) if i+n<len(c) else None
        t['cash_after']=float(curve.loc[t['date'],'cash']);t['quantity_after']=int(curve.loc[t['date'],'quantity'])
    return stats,curve,trades


def events(data,trades,meta):
    result=[]
    for k,t in enumerate(trades):
        if t['action']!='减仓':continue
        restore=next((v for v in trades[k+1:] if v['action']=='恢复买入'),None)
        stop=restore['date'] if restore else str(data.index[-1].date())
        path=data.loc[t['date']:stop,'close'];q=t['quantity'];sell=t['price']
        # 固定卖出份数的反事实：一直持有这部分，与卖出留现金相比。
        mark=restore['price'] if restore else float(path.iloc[-1])
        fee_back=max(5.,q*mark*.0001) if restore else 0.
        result.append(dict(**meta,sell_date=t['date'],signal_date=t['signal_date'],restore_date=restore['date'] if restore else '',
                           closed=bool(restore),quantity_sold=q,sell_price=sell,restore_or_mark_price=mark,
                           lot_timing_gain_yuan=q*(sell-mark)-t['fee']-fee_back,
                           sold_lot_avoided_worst_loss_yuan=max(0.,q*(sell-float(path.min()))),
                           sold_lot_missed_best_gain_yuan=max(0.,q*(float(path.max())-sell)),
                           holding_gap_calendar_days=(pd.Timestamp(stop)-pd.Timestamp(t['date'])).days))
    return result


def add_interpretation():
    table=pd.read_csv(OUT/'all_metrics.csv');abl=pd.read_csv(OUT/'ablation.csv');ev=pd.read_csv(OUT/'trade_events.csv')
    lines=['## 分期结果与交易归因解读','']
    for code in (518880,518850):
        for kind in ('development','partial_holdout'):
            g=table[(table.code==code)&(table.kind==kind)&(table.threshold==10)]
            if g.empty:continue
            lines += [f'### {code} / {kind} / 10%','',g[['variant','start','end','annual_return_pct','max_drawdown_pct','calmar','sharpe','trades','annual_excess_pp','drawdown_improvement_pp']].to_markdown(index=False),'']
            a=abl[(abl.code==code)&(abl.kind==kind)&(abl.threshold==10)].iloc[0]
            lines += [f"5%冷却相对永不买回的年化差为{a.cooling_vs_no_rebuy_cagr_pp:.2f}个百分点，相对固定20日买回为{a.cooling_vs_wait20_cagr_pp:.2f}个百分点；对应回撤改善为{a.cooling_vs_no_rebuy_dd_pp:.2f}、{a.cooling_vs_wait20_dd_pp:.2f}个百分点。恢复市场敞口的收益不等于5%阈值本身有效，需结合固定等待期对照判断。",'']
            e=ev[(ev.code==code)&(ev.kind==kind)&(ev.threshold==10)&(ev.variant=='cool5')]
            if len(e):
                lines += [e[['signal_date','sell_date','restore_date','closed','quantity_sold','lot_timing_gain_yuan','sold_lot_avoided_worst_loss_yuan','sold_lot_missed_best_gain_yuan']].to_markdown(index=False),'',
                          f"该段共{len(e)}次减仓，其中{int(e.closed.sum())}次已买回；正净价差事件{int((e.lot_timing_gain_yuan>0).sum())}次。负价差说明卖出后买回更贵或成本吞噬价差，不能因全策略最终赚钱就把每次减仓都算成功。",'']
    lines += ['2015—2024十年背景、固定五年、滚动五年及短期留出是不同观察口径，不混合求和。近期风险改善可能来自单次极端行情；参数跨窗口的相邻表现、实际事件数和负事件都必须同时考察。','']
    p=OUT/'report.md';text=p.read_text(encoding='utf-8')
    text=text.replace('## 全部指标和交易证据','\n'.join(lines)+'\n## 全部指标和交易证据')
    p.write_text(text,encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    rows=[];event_rows=[];manifest={};window_sections=[]
    for code,path in [('518880',Path('results/gold_extended/518880_qfq.csv')),('518850',Path('data_cache/etf_518850_tencent.csv'))]:
        data=pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
        assert not data.index.has_duplicates and np.isfinite(data[['open','high','low','close']]).all().all()
        assert (data[['open','high','low','close']]>0).all().all()
        manifest[code]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'start':str(data.index[0].date()),'end':str(data.index[-1].date()),
                        'type':'真实ETF；518850同类代理' if code=='518880' else '真实ETF原标的'}
        first=2015 if code=='518880' else 2021
        specs=[('fixed',y,y+5,'full') for y in range(first,2022,5)]
        specs += [('rolling',y,y+5,'full') for y in range(first,2022)]
        specs += [('era',2015,2025,'development')] if code=='518880' else []
        specs += [('holdout',2025,2027,'partial_holdout')]
        for mode,year,endyear,kind in specs:
            begin=pd.Timestamp(year,1,1);stop=pd.Timestamp(endyear,1,1)
            d=data.loc[data.index<stop];start=int(d.index.searchsorted(begin))
            if start<120:continue
            key=f'{code}_{mode}_{year}';folder=OUT/key;folder.mkdir(exist_ok=True)
            effective_stop=stop if stop<=pd.Timestamp('2026-01-01') else d.index[-1]+pd.Timedelta(days=1)
            curves={};trade_map={}
            base=None
            for threshold,variant in [(0,'hold')]+[(t,v) for t in THRESHOLDS for v in VARIANTS]:
                stats,curve,trades=execute(d,start,threshold,variant)
                m=metrics(curve,begin,effective_stop)
                meta=dict(code=code,mode=mode,year=year,kind=kind,threshold=threshold,variant=variant)
                row=dict(**meta,start=str(curve.index[0].date()),end=str(curve.index[-1].date()),initial_cash=100000.,
                         first_entry=trades[0]['date'] if trades else '',trades=len(trades),partial_orders=stats['partial_orders'],
                         return_pct=stats['return_pct'],**m)
                if threshold==0:base=row
                row['annual_excess_pp']=row['annual_return_pct']-base['annual_return_pct']
                row['drawdown_improvement_pp']=base['max_drawdown_pct']-row['max_drawdown_pct']
                rows.append(row);curves[(threshold,variant)]=curve;trade_map[(threshold,variant)]=trades
                prefix=f't{threshold}_{variant}'
                curve.to_csv(folder/f'{prefix}_daily.csv');pd.DataFrame(trades).to_csv(folder/f'{prefix}_trades.csv',index=False)
                event_rows+=events(d,trades,meta)
            fig,axes=plt.subplots(4,1,figsize=(14,14),sharex=True)
            b=curves[(0,'hold')]
            for ax,col in zip(axes[:2],['return_pct','drawdown_pct']):
                ax.plot(b.index,b[col],color='black',label='长期持有',linewidth=2)
                for t in THRESHOLDS:
                    c=curves[(t,'cool5')];ax.plot(c.index,c[col],label=f'{t}% + 5%冷却',alpha=.8)
                ax.legend(ncol=3,fontsize=8);ax.grid(alpha=.2)
            axes[0].set_ylabel('累计收益 (%)');axes[1].set_ylabel('回撤 (%)')
            for v in VARIANTS:
                c=curves[(10,v)];axes[2].plot(c.index,c.return_pct,label=f'10% / {v}')
            axes[2].plot(b.index,b.return_pct,color='black',label='长期持有');axes[2].set_ylabel('10%信号消融收益 (%)');axes[2].legend();axes[2].grid(alpha=.2)
            axes[3].plot(b.index,d.close.reindex(b.index),color='goldenrod',label='ETF收盘价')
            for action,color,marker in [('买入','green','^'),('减仓','red','v'),('恢复买入','blue','^')]:
                tt=[x for x in trade_map[(10,'cool5')] if x['action']==action]
                if tt:axes[3].scatter(pd.to_datetime([x['date'] for x in tt]),[x['price'] for x in tt],c=color,marker=marker,label=action)
            axes[3].set_ylabel('10%主策略成交价 (元)');axes[3].legend();axes[3].grid(alpha=.2)
            fig.suptitle(f'{code} {mode} {year}—{endyear-1} / {kind}');fig.tight_layout();fig.savefig(folder/'curves.png',dpi=110);plt.close(fig)
            window_sections += [f'### {key} / {kind}','',f'实际 {b.index[0].date()}—{b.index[-1].date()}，初始现金100,000元。',
                                f'![收益回撤与交易点]({key}/curves.png)','',f'[10%完整策略交易]({key}/t10_cool5_trades.csv) · [不买回交易]({key}/t10_no_rebuy_trades.csv) · [20日买回交易]({key}/t10_wait20_trades.csv)','']
    table=pd.DataFrame(rows);table.to_csv(OUT/'all_metrics.csv',index=False)
    pd.DataFrame(event_rows).to_csv(OUT/'trade_events.csv',index=False)
    # 冻结开发截止2024，不利用2025以后数据给参数排序。
    development=table[(table.kind=='full')&(table.end<'2025-01-01')&(table.threshold>0)]
    summary=[]
    for (code,mode,threshold,variant),g in development.groupby(['code','mode','threshold','variant']):
        summary.append(dict(code=code,mode=mode,threshold=threshold,variant=variant,n=len(g),
                            median_excess=g.annual_excess_pp.median(),worst_excess=g.annual_excess_pp.min(),
                            median_dd_improvement=g.drawdown_improvement_pp.median(),worst_dd_improvement=g.drawdown_improvement_pp.min(),
                            positive_excess=int((g.annual_excess_pp>1e-9).sum()),active_windows=int((g.partial_orders>0).sum())))
    summary=pd.DataFrame(summary);summary.to_csv(OUT/'development_stability.csv',index=False)
    main_summary=summary[(summary.code=='518880')&(summary.mode=='rolling')&(summary.variant=='cool5')].set_index('threshold').reindex(THRESHOLDS)
    heat=np.array([main_summary.median_excess,main_summary.worst_excess,main_summary.median_dd_improvement,main_summary.worst_dd_improvement])
    fig,ax=plt.subplots(figsize=(12,4));im=ax.imshow(heat,aspect='auto',cmap='RdYlGn',vmin=-max(abs(heat.min()),abs(heat.max())),vmax=max(abs(heat.min()),abs(heat.max())))
    ax.set_xticks(range(8),[f'{t}%' for t in THRESHOLDS]);ax.set_yticks(range(4),['年化超额中位数','年化超额最差','回撤改善中位数','回撤改善最差'])
    for i in range(4):
        for j in range(8):ax.text(j,i,f'{heat[i,j]:.2f}',ha='center',va='center')
    ax.set_title('518880 / 2024年底以前完整滚动5年 / 单位：百分点');fig.colorbar(im,ax=ax);fig.tight_layout();fig.savefig(OUT/'parameter_stability.png',dpi=130);plt.close(fig)
    # 所有完整窗口的参数曲线，开发与后来窗口清晰分列。
    fig,axes=plt.subplots(2,2,figsize=(13,9))
    for (code,mode,year),g in table[(table.kind=='full')&(table.threshold>0)&(table.variant=='cool5')].groupby(['code','mode','year']):
        if mode!='rolling':continue
        col=int(g.end.iloc[0]>='2025-01-01');label=f'{code}/{year}'
        axes[0,col].plot(g.threshold,g.annual_excess_pp,marker='o',label=label)
        axes[1,col].plot(g.threshold,g.drawdown_improvement_pp,marker='o',label=label)
    for col,title in enumerate(['开发期：窗口截至2024','含2025年：时间留出复核']):
        axes[0,col].set_title(title)
        for i in range(2):axes[i,col].axhline(0,color='gray');axes[i,col].legend(fontsize=8);axes[i,col].grid(alpha=.2);axes[i,col].set_xlabel('过热阈值 (%)')
    axes[0,0].set_ylabel('年化超额 (百分点)');axes[1,0].set_ylabel('回撤改善 (百分点)')
    fig.tight_layout();fig.savefig(OUT/'parameter_windows.png',dpi=120);plt.close(fig)
    # 消融差额按同窗口配对，不能当作逐笔因果效应。
    ablation=[]
    for keys,g in table[table.threshold>0].groupby(['code','mode','year','kind','threshold']):
        q=g.set_index('variant');a=q.loc['cool5']
        ablation.append(dict(zip(['code','mode','year','kind','threshold'],keys),
                             cooling_vs_no_rebuy_cagr_pp=a.annual_return_pct-q.loc['no_rebuy'].annual_return_pct,
                             cooling_vs_wait20_cagr_pp=a.annual_return_pct-q.loc['wait20'].annual_return_pct,
                             cooling_vs_no_rebuy_dd_pp=q.loc['no_rebuy'].max_drawdown_pct-a.max_drawdown_pct,
                             cooling_vs_wait20_dd_pp=q.loc['wait20'].max_drawdown_pct-a.max_drawdown_pct))
    abl=pd.DataFrame(ablation);abl.to_csv(OUT/'ablation.csv',index=False)
    lines=['# 黄金8%—15%过热策略稳健性研究','',
           '## 研究设计与证据边界','',
           '固定8%、9%、10%、11%、12%、13%、14%、15%网格，不搜索单一收益最高值。所有窗口独立从10万元现金开始，收盘信号次日开盘执行，100份取整，单边滑点0.1%，佣金万一最低5元，一字涨跌停10%近似限制，现金收益0，末日不强平。',
           '完整五年：518880固定2015—2019、2020—2024；滚动2015—2019至2021—2025。518850仅2021—2025完整周期。另列518880的2015—2024十年背景及两只ETF的2025—2026-09-30短期留出复核，不与五年窗口混排。',
           '开发期只用截至2024的完整五年窗口，参数区间判断不使用2025以后。2021—2025完整窗口作为较新周期单列；2025—2026为未满五年留出段。此前已查看这些行情和10%结果，因此所有留出结果只是回顾性时间复核，不是严格未见样本外。真正样本外需冻结本次规则后等待新增行情，本轮不虚构。',
           '窗口指标使用此前真实行情预热，持仓独立归零；过热阶段若已在起点前开始，则开窗等冷却。518880是真实ETF，对518850是同类产品代理，未拼接。数据截至2026-09-30，输入校验见manifest.json。年化、Calmar和Sharpe沿用五年报告：自然日CAGR，日收益Sharpe×√252、无风险利率0，初始现金计入回撤。',
           '## 信号消融','',
           '- cool5：过热减半一次，双指标均≤5%时买回；循环执行。',
           '- no_rebuy：首次相同减仓后永久保留现金。相对持有反映减仓留现金效果；与cool5之差包含后续买回和再减仓，不能单独解释为冷却阈值的纯因果贡献。',
           '- wait20：同样的过热事件触发减半，20交易日后恢复投入；同一过热阶段不反复减仓，用来比较5%冷却规则与固定等待期。20日是固定对照，不是优化结果。',
           '逐笔事件表按卖出份数计算卖出到买回之间的价差扣模拟双边佣金（价格已含滑点）；未买回按窗口末收盘标记，closed=False，不当作已完成盈利。风险列是被卖份数避免的最大区间损失及错过的最大涨幅，不是账户最大回撤改善。买回后20/60日价格收益仅用窗口内可得行情，末期缺失记空，不补未来数据。不同窗口同一事件会重复，不能累计成独立事件总收益。','',
           '## 参数稳定性（开发期）','', '![参数稳定性热图](parameter_stability.png)','', '![逐窗口参数曲线](parameter_windows.png)','',main_summary.reset_index().to_markdown(index=False),'',
           '预设稳健候选标准：相邻至少3个阈值，开发期全部完整滚动窗口年化不低于持有、回撤不扩大，且至少半数窗口有实际减仓。此标准仅作透明筛查，不以平均最高值定参数。']
    ok=main_summary[(main_summary.worst_excess>=-1e-9)&(main_summary.worst_dd_improvement>=-1e-9)&(main_summary.active_windows>=main_summary.n/2)].index.tolist()
    groups=[]
    for t in ok:
        if groups and t==groups[-1][-1]+1:groups[-1].append(t)
        else:groups.append([t])
    bands=[x for x in groups if len(x)>=3]
    lines += ['',f'通过筛查的连续区间：{bands if bands else "没有达到上述标准的连续区间"}。即使通过，也只是本段样本的候选，不能宣称已证明稳定有效。','',
              '## 10%信号消融：逐窗口差额','',abl[abl.threshold==10].to_markdown(index=False),'',
              '## 2025—2026短期留出复核（未满五年）','',
              table[(table.kind=='partial_holdout')&(table.variant.isin(['hold','cool5']))][['code','threshold','variant','start','end','annual_return_pct','max_drawdown_pct','annual_excess_pp','drawdown_improvement_pp','trades']].to_markdown(index=False),'',
              '## 全部指标和交易证据','',
              '[所有窗口与策略指标](all_metrics.csv) · [逐笔减仓事件收益及风险](trade_events.csv) · [信号消融差额](ablation.csv) · [开发期稳定性](development_stability.csv)','',
              '每个窗口文件夹保存全部8个阈值×3种消融方案的逐日净值及逐笔交易，命名t阈值_方案_daily/trades.csv。下图买卖点聚焦10%，其余阈值的完整成交点在对应交易CSV中。','']+window_sections
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    add_interpretation()
    print('Saved',len(table),'runs; candidate bands',bands)


if __name__=='__main__':main()
