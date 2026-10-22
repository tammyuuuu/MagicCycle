"""短均线确认方式研究；所有规则固定比较，不自动改策略。"""
import json
from pathlib import Path
import pandas as pd
from research_sector_trend import backtest


def confirmed_signal(close, length=20, enter_days=1, exit_days=1, buffer=0):
    average=close.rolling(length,min_periods=length).mean()
    if enter_days==exit_days==1 and buffer==0:
        from industry_strategy import trend_positions
        return trend_positions(close,length)
    held=False;up=down=0;states=[]
    for price,ma in zip(close,average):
        if pd.isna(ma):held=False;up=down=0
        else:
            up=up+1 if price>ma*(1+buffer) else 0
            down=down+1 if price<ma*(1-buffer) else 0
            if not held and up>=enter_days:held=True
            elif held and down>=exit_days:held=False
        states.append(held)
    return pd.Series(states,index=close.index)


def candidates(close):
    options=[('立即判断',1,1,0),('买卖均确认2天',2,2,0),
             ('买卖均确认3天',3,3,0),('买入确认2天，卖出立即',2,1,0),
             ('上下1%缓冲',1,1,.01),('上下2%缓冲',1,1,.02)]
    return {f'{length}日·{name}':confirmed_signal(close,length,enter,exit,buffer)
            for length in (20,30) for name,enter,exit,buffer in options}


def main():
    output=Path('results/sector_confirmation');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 行业ETF短均线确认研究','',
        '沿用收盘信号、下一交易日开盘执行；10万元，佣金万一且最低5元，买卖各0.1%滑点、100份整数交易，现金收益为零。',
        '一字涨停不买、一字跌停不卖，未模拟盘口排队；前复权价格无法精确还原分红现金。',
        '确认2天：连续两个交易日收盘位于均线上／下。缓冲1%：上穿均线1%才买，下穿1%才卖，之间保持。',
        '所有规则沿用相同120日预热；没有根据结果挑选后再声称样本外有效。','']
    for code,name,limit in [('512760','半导体芯片ETF',.10),('588170','科创半导体材料设备ETF',.20)]:
        data=pd.read_csv(f'data_cache/etf_{code}_tencent.csv',parse_dates=['date']).set_index('date').sort_index()
        data=data[data.index<=pd.Timestamp('2026-09-30')]
        if data.index.has_duplicates or data[['open','close']].isna().any().any():raise ValueError('行情无效')
        start=120;rules={'持有不择时':pd.Series(True,index=data.index),**candidates(data.close)}
        result={'start':str(data.index[start].date()),'end':str(data.index[-1].date()),'rules':{}}
        common=next(i for i in range(start,len(data)) if data.index[i]>=pd.Timestamp('2025-09-29'))
        lines += [f'## {code} {name}','',f"比较区间：{result['start']}至{result['end']}。",'',
                  '| 规则 | 累计收益 | 最大回撤 | 买卖次数 | 已结束亏损轮数 |','|---|---:|---:|---:|---:|']
        for label,signal in rules.items():
            full,curve,trades=backtest(data,signal,start,len(data),limit_pct=limit)
            same_period=backtest(data,signal,common,len(data),limit_pct=limit)[0]
            expensive=backtest(data,signal,start,len(data),slippage=.002,limit_pct=limit)[0]
            annual={}
            for year in sorted(set(data.index[start:].year)):
                indices=[i for i in range(start,len(data)) if data.index[i].year==year]
                annual[str(year)]=backtest(data,signal,indices[0],indices[-1]+1,limit_pct=limit)[0]
            result['rules'][label]={'full':full,'common_period':same_period,'double_slippage':expensive,'annual':annual}
            safe=label.replace('，','_')
            curve.to_csv(output/f'{code}_{safe}_curve.csv')
            pd.DataFrame(trades).to_csv(output/f'{code}_{safe}_trades.csv',index=False)
            lines.append(f"| {label} | {full['return_pct']}% | {full['max_drawdown_pct']}% | {full['trades']} | {full['losing_round_trips']}/{full['closed_round_trips']} |")
        results[code]=result
        lines+=['','年度结果及共同区间结果见results.json；年度独立从现金开始。','']
    lines+=['## 如何理解','',
            '少交易不一定更好：等待确认会推迟买入和卖出，缓冲也会容忍更多价格下跌。',
            '两只ETF覆盖范围不同，588170样本短；它只能提供有限交叉检查。多组参数比较存在选择偏差，收益最高不代表最佳。',
            '本轮只研究确认方式，不设加仓或减仓比例，不修改当前App策略。']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Research saved: '+str(output/'report.md'))


if __name__=='__main__':main()
