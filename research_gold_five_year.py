"""黄金ETF固定及滚动五年检验；只写研究产物，不修改产品信号。"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from research_gold_extended import NAMES, targets, run

OUT=Path('results/gold_five_year')
CASH=100000.


def fmt(value):
    return 'NA' if value is None or pd.isna(value) else f'{value:.3f}'


def windows(index):
    # 从预热完成后的首个完整自然年开始；结束边界采用半开区间。
    ready=index[120]
    first=ready.year + int(ready != pd.Timestamp(ready.year,1,1))
    for mode,step in [('fixed',5),('rolling',1)]:
        for year in range(first,index[-1].year+1,step):
            begin=pd.Timestamp(year,1,1);stop=begin+pd.DateOffset(years=5)
            full=index[-1]>=stop-pd.Timedelta(days=1)
            yield mode,year,begin,stop,full


def metrics(curve,begin,stop):
    years=(stop-begin).days/365.2425
    cagr=(curve.equity.iloc[-1]/CASH)**(1/years)-1
    returns=pd.Series(np.r_[CASH,curve.equity.to_numpy()]).pct_change().dropna()
    std=returns.std(ddof=1)
    dd=-float(curve.drawdown_pct.min())/100
    return {'annual_return_pct':cagr*100,'max_drawdown_pct':dd*100,
            'calmar':cagr/dd if dd>0 else None,
            'sharpe':float(returns.mean()/std*np.sqrt(252)) if std>0 else None}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    rows=[];manifest={};sections={True:[],False:[]}
    for code,path in [('518850',Path('data_cache/etf_518850_tencent.csv')),('518880',Path('results/gold_extended/518880_qfq.csv'))]:
        data=pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
        assert not data.index.has_duplicates
        assert np.isfinite(data[['open','high','low','close']]).all().all()
        assert (data[['open','high','low','close']]>0).all().all()
        manifest[code]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'start':str(data.index[0].date()),'end':str(data.index[-1].date()),'rows':len(data),
                        'type':'真实ETF原标的' if code=='518850' else '真实ETF；518850同类产品代理',
                        'source':'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get','adjustment':'qfq'}
        for mode,year,begin,stop,full in windows(data.index):
            truncated=data.loc[data.index<stop]
            start=int(truncated.index.searchsorted(begin))
            if start>=len(truncated):continue
            key=f'{code}_{mode}_{year}';folder=OUT/key;folder.mkdir(exist_ok=True)
            # 每个窗口重新构造行情状态，不承接上个窗口持仓；信号仍可读取此前历史。
            ts=targets(truncated.close)
            end=stop if full else truncated.index[-1]+pd.Timedelta(days=1)
            section=[f'### {code} {mode} {year}—{year+4}'+('（完整5年）' if full else '（未满5年）'),'',
                     f'计划边界 [{begin.date()}, {stop.date()})；实际交易日 {truncated.index[start].date()}—{truncated.index[-1].date()}；各策略初始现金100,000元。','',
                     '|策略|首次建仓|年化收益%|最大回撤%|Calmar|Sharpe|交易次数|','|---|---|---:|---:|---:|---:|---:|']
            fig,axes=plt.subplots(7,1,figsize=(14,20),sharex=True)
            for k,(name,target) in enumerate(zip(NAMES,ts)):
                stats,curve,trades=run(truncated,target,start,k,CASH)
                m=metrics(curve,begin,end)
                first=next((t['date'] for t in trades if t['action']=='买入'),'未建仓')
                row=dict(code=code,mode=mode,year=year,complete=full,planned_start=str(begin.date()),planned_end_exclusive=str(stop.date()),
                         actual_start=str(curve.index[0].date()),actual_end=str(curve.index[-1].date()),strategy=name,
                         initial_cash=CASH,first_entry=first,trades=len(trades),return_pct=stats['return_pct'],**m)
                rows.append(row)
                curve.to_csv(folder/f's{k}_daily.csv')
                pd.DataFrame(trades).to_csv(folder/f's{k}_trades.csv',index=False)
                section.append(f"|{name}|{first}|{m['annual_return_pct']:.2f}|{m['max_drawdown_pct']:.2f}|{fmt(m['calmar'])}|{fmt(m['sharpe'])}|{len(trades)}|")
                # 显示期初现金点，使首次成交费用进入曲线。
                x=[begin-pd.Timedelta(seconds=1)]+list(curve.index)
                axes[0].plot(x,[0.]+list(curve.return_pct),label=name)
                axes[1].plot(x,[0.]+list(curve.drawdown_pct),label=name)
                ax=axes[k+2];ax.plot(curve.index,truncated.close.reindex(curve.index),color='goldenrod',linewidth=.8)
                for action,color,marker in [('买入','green','^'),('恢复买入','blue','^'),('减仓','red','v'),('退出','purple','v')]:
                    events=[t for t in trades if t['action']==action]
                    if events:ax.scatter(pd.to_datetime([t['date'] for t in events]),[t['price'] for t in events],color=color,marker=marker,label=action,s=25,zorder=3)
                ax.set_ylabel(name+'\n价格(元)');ax.legend(fontsize=8,loc='upper left');ax.grid(alpha=.2)
            for ax,label in zip(axes[:2],['累计收益率 (%)','回撤 (%)']):
                ax.set_ylabel(label);ax.legend(fontsize=8);ax.grid(alpha=.2)
            fig.suptitle(f'{code} / {mode} / {year}—{year+4} / '+('完整5年' if full else '未满5年'))
            fig.tight_layout();fig.savefig(folder/'curves.png',dpi=110);plt.close(fig)
            section+=['',f'![窗口收益、回撤与各策略买卖点]({key}/curves.png)','',
                      '买卖标记为实际模拟成交日及含滑点成交价；逐笔CSV包含信号日、指标、原因、佣金和成交后账户。','']
            for k,name in enumerate(NAMES):section.append(f'- {name}：[逐日账户]({key}/s{k}_daily.csv) · [逐笔交易及原因]({key}/s{k}_trades.csv)')
            sections[full]+=(section+[''])
    table=pd.DataFrame(rows);table.to_csv(OUT/'all_windows.csv',index=False)
    complete=table[table.complete];partial=table[~table.complete]
    complete.to_csv(OUT/'complete_windows.csv',index=False);partial.to_csv(OUT/'partial_windows.csv',index=False)
    lines=['# 黄金ETF：以五年为主要检验周期','',
           '## 统一口径','',
           '固定分段：从120交易日预热完成后的首个完整自然年起，每5年分段。518880从2015年起，518850从2021年起。2014年初518880尚未完成120交易日预热，因此不作为完整自然年起点。滚动窗口：同一起点逐年移动，每个计划窗口均为1月1日至第五年12月31日。',
           '每个窗口独立从10万元现金开始；不承接仓位、成本或盈亏。指标及过热阶段可以读取起点以前的真实历史，仅用于预热。策略若起始已过热则从现金等待冷却，不强制建仓。',
           '长期持有、双指标15%减半、15%减半后转弱清仓、10%及20%减半，均沿用同一引擎：收盘信号次日开盘成交；100份取整；单边滑点0.1%；佣金万一最低5元；一字涨跌停10%近似限制；现金收益0；末日按收盘估值且不强平。',
           '过热线要求20日涨幅及60日均线偏离同时达阈值；冷却要求两者均不高于5%。减半仅一次；冷却投入剩余现金。转弱退出指过热后不高于20日均线。没有120日趋势退出。产品信号未修改，自由预算加仓不属于本固定资金实验。',
           '年化收益=CAGR，按计划自然日起止的实际日数/365.2425计算；完整五年休市日不影响完整性。短区间算至最后行情日次日并标注未满5年。最大回撤含期初现金；Calmar=CAGR/最大回撤绝对值；Sharpe=日均收益/样本日收益标准差×√252，无风险利率设0，首日费用计入日收益。分母为0时记NA。交易次数为已成交订单数，减仓和恢复均计数。',
           '## 数据与检验边界','',
           '数据统一截至2026-09-30。518850是真实原标的；518880为另一只真实ETF，对518850是同类代理，两者不拼接。来源为腾讯前复权缓存，manifest.json记录区间与SHA256。518880上市日期见[基金公司公告](https://wap.huaan.com.cn/news/2013-07-29/175178_1.shtml)。',
           '前复权无法精确复原分红份额与现金；未模拟盘口排队及盘中风险。参数已看过历史，不是未见样本外。滚动窗口高度重叠，两只ETF也高度相关，胜出比例是描述统计，不能当独立样本显著性。','',
           '## 完整五年周期的稳定性','']
    stability=[]
    for (code,mode),g in complete.groupby(['code','mode']):
        base=g[g.strategy==NAMES[0]].set_index('year')
        lines += [f'### {code} / {mode}（{len(base)}个完整窗口）','',
                  '|策略|年化中位数%|年化最差%|回撤最差%|Calmar中位数|Sharpe中位数|年化胜过持有|回撤小于持有|无减仓窗口|','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for name,s in g.groupby('strategy',sort=False):
            s=s.set_index('year');wins=int((s.annual_return_pct>base.annual_return_pct+1e-9).sum());risk=int((s.max_drawdown_pct<base.max_drawdown_pct-1e-9).sum())
            zero=0
            for year in s.index:
                trades=pd.read_csv(OUT/f'{code}_{mode}_{year}'/f's{NAMES.index(name)}_trades.csv')
                zero+=int(trades.empty or not (trades.action=='减仓').any())
            stability.append(dict(code=code,mode=mode,strategy=name,windows=len(s),cagr_wins=wins,lower_drawdown=risk,no_reduction_windows=zero))
            lines.append(f'|{name}|{s.annual_return_pct.median():.2f}|{s.annual_return_pct.min():.2f}|{s.max_drawdown_pct.max():.2f}|{s.calmar.median():.3f}|{s.sharpe.median():.3f}|{wins}/{len(s)}|{risk}/{len(s)}|{zero}/{len(s)}|')
        candidate=g[g.strategy==NAMES[1]].set_index('year')
        delta=candidate.annual_return_pct-base.annual_return_pct
        lines+=['',f'15%减半相对持有的年化收益差范围为{delta.min():.2f}至{delta.max():.2f}个百分点。没有过热减仓的窗口不能证明择时有效；应结合上表无减仓窗口数及逐笔记录解释。','']
    lines+=['完整周期按ETF和窗口类型分别分析，不将同类代理、重叠窗口合并排名。518850完整周期数量少；518880虽延长历史，固定分段也只有少量独立五年周期，仍不足以证明跨周期稳定。',
            '当前数据中的15%策略在518880两个固定完整周期均未减仓，七个滚动完整周期有六个未减仓，其改善集中在包含2025年的最近窗口。10%策略在七个滚动周期年化收益均较高、六个周期回撤较小，也在两个固定周期年化胜出，但这些窗口共享大量行情，且参数来自回顾性比较，不能据此确定10%最优。518850只有2021—2025一个完整周期，固定和滚动重复展示同一周期，不是两份独立证据。2026年大幅波动仅在未满五年区间中展示，未进入完整周期排名。','',
            '## 完整五年窗口明细','']+sections[True]+['## 未满五年的区间（仅展示，不参与上述比较）','']+sections[False]
    pd.DataFrame(stability).to_csv(OUT/'stability.csv',index=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Saved {OUT}/report.md; {len(complete)//5} complete windows; {len(partial)//5} partial windows')


if __name__=='__main__':main()
