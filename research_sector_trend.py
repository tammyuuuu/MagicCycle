"""588170 简单趋势规则的描述性回测，不修改 App 策略。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def signals(data):
    c=data.close
    averages={n:c.rolling(n,min_periods=n).mean() for n in (20,60,120)}
    rules={'持有不择时':pd.Series(True,index=c.index)}
    for n in (20,60,120):rules[f'{n}日均线']=c>averages[n]
    rules['60日均线向上']=(c>averages[60]) & (averages[60]>averages[60].shift(5))
    rules['20/60日均线交叉']=averages[20]>averages[60]
    # 缓冲带：上穿+2%才买，下穿-2%才卖，中间保持。
    held=False;states=[]
    for price,ma in zip(c,averages[60]):
        if pd.isna(ma):held=False
        elif price>ma*1.02:held=True
        elif price<ma*.98:held=False
        states.append(held)
    rules['60日均线±2%缓冲']=pd.Series(states,index=c.index)
    return rules


def backtest(data, signal, start, end, slippage=.001, limit_pct=None,
             initial_cash=100000., minimum_fee=5.):
    """前一日收盘产生信号，次日开盘交易；每日最多一次，满足股票ETF T+1。"""
    if initial_cash<=0 or minimum_fee<0:raise ValueError('本金必须为正，最低佣金不能为负')
    cash=float(initial_cash);qty=0;fee_rate=.0001;equity=[];trades=[];closed=[];entry_cost=None
    # 买入持有在每段第一天入场；其他规则使用前一天可见信号。
    for i in range(start,end):
        desired=bool(signal.iloc[i-1]);date=data.index[i];opening=float(data.iloc[i].open)
        one_price = 'high' in data and 'low' in data and float(data.iloc[i].high)==float(data.iloc[i].low)
        previous=float(data.iloc[i-1].close)
        blocked_buy=limit_pct is not None and one_price and opening/previous-1>=limit_pct-.003
        blocked_sell=limit_pct is not None and one_price and opening/previous-1<=-limit_pct+.003
        if desired and qty==0 and not blocked_buy:
            execution=opening*(1+slippage)
            units=int(cash/(execution*(1+fee_rate))//100)*100
            while units>0 and units*execution+max(minimum_fee,units*execution*fee_rate)>cash:units-=100
            if units:
                cost=units*execution+max(minimum_fee,units*execution*fee_rate)
                cash-=cost;qty=units;entry_cost=cost
                trades.append({'date':str(date.date()),'action':'买入','price':execution,'quantity':units})
        elif not desired and qty and not blocked_sell:
            execution=opening*(1-slippage)
            proceeds=qty*execution-max(minimum_fee,qty*execution*fee_rate)
            closed.append(proceeds/entry_cost-1)
            cash+=proceeds
            trades.append({'date':str(date.date()),'action':'卖出','price':execution,'quantity':qty})
            qty=0;entry_cost=None
        equity.append({'date':date,'equity':cash+qty*float(data.iloc[i].close),'invested':bool(qty)})
    curve=pd.DataFrame(equity).set_index('date')
    values=np.r_[initial_cash,curve.equity.values]
    dd=values/np.maximum.accumulate(values)-1
    return {'return_pct':round(float(values[-1]/values[0]-1)*100,2),
            'max_drawdown_pct':round(float(dd.min()*100),2),
            'trades':len(trades),'closed_round_trips':len(closed),
            'losing_round_trips':int(sum(x<0 for x in closed)),
            'invested_pct':round(float(curve.invested.mean()*100),1)},curve,trades


def main():
    output=Path('results/sector_trend_research');output.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv('data_cache/etf_588170_tencent.csv',parse_dates=['date']).set_index('date').sort_index()
    data=data[data.index<=pd.Timestamp('2026-09-30')]
    for key in ('open','close'):
        if data[key].isna().any() or (data[key]<=0).any():raise ValueError('存在无效行情')
    other=pd.read_csv('data_cache/etf_588170_qfq.csv',parse_dates=['date']).set_index('date')
    shared=data.join(other.close.rename('other_close'),how='inner')
    max_difference=float((shared.close/shared.other_close-1).abs().max())
    rules=signals(data);start=120;split=start+(len(data)-start)//2
    result={'history_start':str(data.index[0].date()),'history_end':str(data.index[-1].date()),
            'days':len(data),'comparison_start':str(data.index[start].date()),
            'split_date':str(data.index[split].date()),'price_source_max_relative_difference':max_difference,'rules':{}}
    lines=['# 588170 简单均线策略研究','',f"行情：{result['history_start']}至{result['history_end']}，{len(data)}个交易日。",
           f"公平比较区间：{result['comparison_start']}至{result['history_end']}；此前120日仅用于计算均线。",'',
           '使用腾讯前复权ETF行情，与东方财富缓存核对重合日期；两源收盘价最大相对差异为'+f'{max_difference*100:.4f}%。',
           '收盘判断，下一交易日开盘执行；初始10万元，佣金万一且最低5元，买卖各计0.1%滑点，100份整数买入；现金收益为零。',
           '费用参数是研究假设。前复权历史不能精确重现实际分红现金和历史成交份数。',
           '前后两段均重新从现金开始，不承接前一段持仓；不用于挑选最优规则。末日不强制清仓，收益含未实现盈亏。','',
           '| 规则 | 累计收益 | 最大回撤 | 买卖次数 | 已结束交易亏损次数 | 持仓时间 |','|---|---:|---:|---:|---:|---:|']
    for name,signal in rules.items():
        full,curve,trades=backtest(data,signal,start,len(data))
        first,_,_=backtest(data,signal,start,split)
        second,_,_=backtest(data,signal,split,len(data))
        worse_costs,_,_=backtest(data,signal,start,len(data),slippage=.002)
        result['rules'][name]={'full':full,'first_half':first,'second_half':second,'double_slippage':worse_costs}
        curve.to_csv(output/(name.replace('/','_')+'_curve.csv'))
        pd.DataFrame(trades).to_csv(output/(name.replace('/','_')+'_trades.csv'),index=False)
        lines.append(f"| {name} | {full['return_pct']}% | {full['max_drawdown_pct']}% | {full['trades']} | {full['losing_round_trips']}/{full['closed_round_trips']} | {full['invested_pct']}% |")
    lines+=['','| 规则 | 前段收益 | 后段收益 | 滑点加倍收益 |','|---|---:|---:|---:|']
    for name,r in result['rules'].items():lines.append(f"| {name} | {r['first_half']['return_pct']}% | {r['second_half']['return_pct']}% | {r['double_slippage']['return_pct']}% |")
    lines+=['','## 初步结论','',
            '20日均线在本样本中降低收盘最大回撤，但发生24次买卖，12轮已结束交易中9轮亏损；降低回撤同时错过部分上涨。',
            '60日、120日及20/60交叉均未稳定改善回撤；60日均线加方向或缓冲条件，也没有改善全区间最大回撤。',
            '不能把60日均线直接认定为有效买卖点。均线可先用于解释趋势状态，交易规则还需要更多周期验证。','',
            '样本不足一年半且只有一个标的，不能验证跨周期表现。参数均在同一历史样本上比较；没有独立样本外证据。本报告不改动当前提醒规则。',
            '上市日期参考：[上交所上市交易公告书](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-04-02/588170_20250402_O5VU.pdf)。']
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
