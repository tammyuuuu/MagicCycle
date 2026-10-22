"""固定沿用588170研究规则，在512760长历史中按年份检验。"""
import json
from pathlib import Path
import pandas as pd
from research_sector_trend import signals, backtest


def main():
    output=Path('results/sector_long_history');output.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv('data_cache/etf_512760_tencent.csv',parse_dates=['date']).set_index('date').sort_index()
    data=data[data.index<=pd.Timestamp('2026-09-30')]
    if data.index.has_duplicates or data[['open','close']].isna().any().any() or (data[['open','close']]<=0).any().any():
        raise ValueError('行情无效')
    rules=signals(data);start=120
    periods={str(year):(next(i for i in range(start,len(data)) if data.index[i].year==year),
                        max(i for i in range(start,len(data)) if data.index[i].year==year)+1)
             for year in sorted(set(data.index[start:].year))}
    result={'symbol':'512760','history_start':str(data.index[0].date()),'end':str(data.index[-1].date()),
            'days':len(data),'comparison_start':str(data.index[start].date()),'rules':{}}
    lines=['# 512760 半导体ETF长历史策略研究','',
           f"行情：{result['history_start']}至{result['end']}，{len(data)}个交易日。",
           f"统一比较从{result['comparison_start']}开始，前120日只用于均线计算。",'',
           '固定沿用此前588170研究的七种规则，不根据512760结果挑选新的参数。',
           '腾讯前复权日线；前一日收盘判断，次日开盘交易。初始10万元，佣金万一、最低5元，买卖各计0.1%滑点，100份整数交易。',
           '现金收益为零；前复权价格不精确重现历史分红现金和成交份数。末日不强制清仓，收益包括未实现盈亏。',
           '每年独立从现金开始，沿用此前可见均线；2019年只有尾段，2026年只有截至9月的数据。','',
           '| 规则 | 累计收益 | 收盘最大回撤 | 买卖次数 | 已结束亏损轮数 | 持仓时间 |','|---|---:|---:|---:|---:|---:|']
    for name,signal in rules.items():
        full,curve,trades=backtest(data,signal,start,len(data),limit_pct=.10)
        annual={year:backtest(data,signal,*limits,limit_pct=.10)[0] for year,limits in periods.items()}
        doubled=backtest(data,signal,start,len(data),slippage=.002,limit_pct=.10)[0]
        result['rules'][name]={'full':full,'annual':annual,'double_slippage':doubled}
        safe=name.replace('/','_')
        curve.to_csv(output/(safe+'_curve.csv'))
        pd.DataFrame(trades).to_csv(output/(safe+'_trades.csv'),index=False)
        lines.append(f"| {name} | {full['return_pct']}% | {full['max_drawdown_pct']}% | {full['trades']} | {full['losing_round_trips']}/{full['closed_round_trips']} | {full['invested_pct']}% |")
    lines+=['','| 年份 | 持有不择时 | 20日线 | 60日线 | 120日线 | 60日线向上 | 20/60交叉 | 60日线±2% |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for year in periods:
        lines.append('| '+year+' | '+' | '.join(f"{result['rules'][name]['annual'][year]['return_pct']}%" for name in rules)+' |')
    lines+=['','## 滑点加倍','', '| 规则 | 原累计收益 | 滑点加倍累计收益 |','|---|---:|---:|']
    for name,r in result['rules'].items():
        lines.append(f"| {name} | {r['full']['return_pct']}% | {r['double_slippage']['return_pct']}% |")
    result['sensitivity']={str(n):backtest(data,data.close>data.close.rolling(n).mean(),start,len(data),limit_pct=.10)[0] for n in (15,20,25,30)}
    lines+=['','## 短均线参数敏感性','', '| 均线 | 累计收益 | 最大回撤 | 买卖次数 |','|---|---:|---:|---:|']
    for n,x in result['sensitivity'].items():lines.append(f"| {n}日 | {x['return_pct']}% | {x['max_drawdown_pct']}% | {x['trades']} |")
    lines+=['','一字涨停不买、一字跌停不卖（按前复权价格涨跌约10%判定，容忍0.3个百分点舍入差异）。没有模拟部分成交或盘口排队。',
            '本研究是固定规则的历史比较，未模拟盘中追单或实际ETF申赎；没有推断最佳参数。',
            '512760覆盖半导体芯片行业，588170更集中于科创板材料设备；结果不能直接互相替代。当前App策略不变。']
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Research saved: '+str(output/'report.md'))


if __name__=='__main__':main()
