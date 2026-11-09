"""可复现黄金研究报告：逐日账户、逐笔原因、多起点与真实图表。"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from research_gold_heat import heat_targets
from research_sector_partial_exit import backtest_partial

OUT = Path('results/gold_extended')
NAMES = ['长期持有', '15%过热减半', '15%减半后转弱退出', '10%过热减半', '20%过热减半']


def targets(close):
    return [pd.Series(1., index=close.index),
            heat_targets(close, use_trend=False, exit_on_weak=False),
            heat_targets(close, use_trend=False),
            heat_targets(close, .10, use_trend=False, exit_on_weak=False),
            heat_targets(close, .20, use_trend=False, exit_on_weak=False)]


def run(data, target, start, strategy, cash):
    stats, curve, trades = backtest_partial(data, target, start, len(data), initial_cash=cash, limit_pct=.10)
    curve['return_pct'] = (curve.equity / cash - 1) * 100
    curve['drawdown_pct'] = (curve.equity / curve.equity.cummax().clip(lower=cash) - 1) * 100
    curve['exposure_pct'] = curve.quantity * data.close.reindex(curve.index) / curve.equity * 100
    for trade_no, t in enumerate(trades):
        i = data.index.get_loc(pd.Timestamp(t['date'])) - 1
        c = data.close
        t.update(signal_date=str(data.index[i].date()), return20_pct=float((c.iloc[i]/c.iloc[i-20]-1)*100),
                 deviation60_pct=float((c.iloc[i]/c.iloc[i-59:i+1].mean()-1)*100))
        t['reason'] = ('固定资金初次建仓；前日非过热且指标已就绪' if t['action']=='买入' else
                       '20日涨幅和60日均线偏离均达到过热线，首次减半' if t['action']=='减仓' else
                       '双指标均冷却至5%以内，恢复投入可用现金' if t['action']=='恢复买入' else
                       '过热阶段收盘不高于20日均线，退出剩余持仓')
        if strategy == 0: t['reason'] = '长期持有基准首次建仓'
        elif t['action']=='买入' and trade_no>0:
            t['reason']='退出后双指标冷却至5%以内，重新建仓'
        row = curve.loc[t['date']]
        t.update(cash_after=float(row.cash), quantity_after=int(row.quantity), equity_close=float(row.equity))
    return stats, curve, trades


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--years', nargs='+', type=int, default=list(range(2014,2027)))
    parser.add_argument('--initial-cash', type=float, default=100000.)
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    lines=['# 黄金ETF可复现回测报告', '',
           '固定资金、无外部追加；各起点独立从现金开始，指标使用起点以前真实历史预热120日。收盘产生信号，下一交易日开盘执行。',
           '初始资金默认10万元，100份取整，单边滑点0.1%，佣金万一且最低5元；一字涨跌停10%近似限制。现金收益0，末日不强平。',
           '长期持有与策略使用相同起止日期、资金和费用。累计收益以初始资金为分母，回撤包含初始现金净值；仓位为实际持仓市值/账户净值，并非信号目标。',
           '15%与5%来自看过样本后的假设；各起点对比不是独立样本外。当前App冷却按自由预算加仓，本报告采用固定资金恢复投入，收益不能直接代表自由预算方案。', '',
           '## 数据来源与边界', '',
           '518850为原研究真实ETF；518880为另一只真实黄金ETF，对518850属于同类产品代理，不是518850成立前实绩。分别回测，绝不拼接。',
           '518880上市日期2013-07-29：[基金公司公告](https://wap.huaan.com.cn/news/2013-07-29/175178_1.shtml)。行情来自腾讯前复权日线；原始文件与SHA256保存在manifest.json。',
           '本轮将真实境内ETF历史延长至2013年。2013年前现货、美元黄金或海外ETF涉及币种、交易日、费用和开盘时点差异，未取得并验证可比序列，本报告不伪造其ETF实绩。',
           '前复权并非精确的分红现金账本；未模拟盘口排队、盘中回撤及部分成交。', '']
    manifest={}; summary=[]
    for code,path in [('518850',Path('data_cache/etf_518850_tencent.csv')),('518880',OUT/'518880_qfq.csv')]:
        data=pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
        assert not data.index.has_duplicates
        assert np.isfinite(data[['open','high','low','close']]).all().all()
        assert (data[['open','high','low','close']]>0).all().all()
        manifest[code]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'start':str(data.index[0].date()),'end':str(data.index[-1].date()),'rows':len(data),
                        'type':'真实ETF原标的' if code=='518850' else '真实ETF；原标的同类代理',
                        'source':'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get','adjustment':'qfq'}
        ts=targets(data.close)
        starts=[('full',120)]+[(str(y),int(data.index.searchsorted(pd.Timestamp(y,1,1)))) for y in args.years]
        for tag,start in starts:
            if start<120 or start>=len(data): continue
            folder=OUT/f'{code}_{tag}';folder.mkdir(exist_ok=True)
            lines += [f'## {code} / 起点 {tag}', '',
                      f'回测区间：{data.index[start].date()}—{data.index[-1].date()}；初始资金：{args.initial_cash:,.2f}元。', '',
                      '|策略|首次建仓|累计收益%|最大回撤%|交易数|', '|---|---|---:|---:|---:|']
            runs=[]
            for k,(name,target) in enumerate(zip(NAMES,ts)):
                stats,curve,trades=run(data,target,start,k,args.initial_cash)
                curve.to_csv(folder/f's{k}_daily.csv')
                pd.DataFrame(trades).to_csv(folder/f's{k}_trades.csv',index=False)
                first=next((t['date'] for t in trades if t['action']=='买入'),'未建仓')
                summary.append(dict(code=code,start=str(data.index[start].date()),end=str(data.index[-1].date()),strategy=name,initial_cash=args.initial_cash,first_entry=first,**stats))
                lines.append(f"|{name}|{first}|{stats['return_pct']}|{stats['max_drawdown_pct']}|{stats['trades']}|")
                runs.append((curve,trades))
            for k,(curve,trades) in enumerate(runs):
                fig,axes=plt.subplots(4,1,figsize=(13,13),sharex=True)
                base=runs[0][0]
                for ax,col,title in [(axes[0],'return_pct','累计收益率 (%)'),(axes[1],'drawdown_pct','回撤 (%)')]:
                    ax.plot(base.index,base[col],label='长期持有',color='gray')
                    ax.plot(curve.index,curve[col],label=NAMES[k]);ax.set_ylabel(title);ax.legend();ax.grid(alpha=.2)
                axes[2].plot(curve.index,data.close.reindex(curve.index),color='goldenrod',label='ETF前复权收盘价')
                for action,color,marker in [('买入','green','^'),('恢复买入','blue','^'),('减仓','red','v'),('退出','purple','v')]:
                    events=[t for t in trades if t['action']==action]
                    if events: axes[2].scatter(pd.to_datetime([t['date'] for t in events]),[t['price'] for t in events],c=color,marker=marker,label=action,zorder=3)
                axes[2].set_ylabel('价格 (元)');axes[2].legend();axes[2].grid(alpha=.2)
                axes[3].plot(curve.index,curve.exposure_pct,label='实际市值仓位');axes[3].set_ylabel('仓位 (%)');axes[3].grid(alpha=.2)
                fig.suptitle(f'{code} {NAMES[k]} | {curve.index[0].date()} — {curve.index[-1].date()}')
                fig.tight_layout();fig.savefig(folder/f's{k}.png',dpi=120);plt.close(fig)
                lines += ['',f'### {NAMES[k]}', '',f'![收益、回撤、交易与仓位]({folder.name}/s{k}.png)', '',
                          f'[逐日净值及仓位CSV]({folder.name}/s{k}_daily.csv) · [逐笔交易CSV]({folder.name}/s{k}_trades.csv)', '',
                          '|信号日|成交日|动作|份数|成交价|佣金|原因|', '|---|---|---|---:|---:|---:|---|']
                for t in trades:
                    lines.append(f"|{t['signal_date']}|{t['date']}|{t['action']}|{t['quantity']}|{t['price']:.4f}|{t['fee']:.2f}|{t['reason']}；20日涨幅{t['return20_pct']:.2f}%，60日偏离{t['deviation60_pct']:.2f}%|")
    table=pd.DataFrame(summary);table.to_csv(OUT/'start_year_comparison.csv',index=False)
    lines+=['','## 不同起点汇总','','每个起点均独立重置资金，不是逐年收益，也不是连续账户的年度拆分。','',table.to_markdown(index=False)]
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Saved',OUT/'report.md',len(summary),'runs')


if __name__=='__main__': main()
