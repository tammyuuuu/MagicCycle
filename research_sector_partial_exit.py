"""减仓研究：一次跌破先减半，继续在线下才退出；不修改App。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from industry_strategy import trend_positions
from research_sector_trend import backtest


def exit_targets(close, confirmation=2, remaining=.5, window=20):
    """行情决定风险阶段；恢复线上时恢复原目标，绝不读取实际仓位。"""
    if confirmation<2 or int(confirmation)!=confirmation:raise ValueError('确认天数须为至少2的整数')
    if not 0<=remaining<=1:raise ValueError('保留比例须在0至1之间')
    average=close.rolling(window,min_periods=window).mean()
    count=0;result=[]
    for price,ma in zip(close,average):
        if pd.isna(ma):count=0;target=0.
        elif price>ma:count=0;target=1.
        else:
            count+=1
            target=0. if count>=confirmation else float(remaining)
        result.append(target)
    return pd.Series(result,index=close.index)


def backtest_partial(data,targets,start,end,slippage=.001,limit_pct=None,
                     initial_cash=100000.,minimum_fee=5.,entry_allowed=None):
    """仅在目标阶段变化时交易，避免把0.5误作每日再平衡。

    首个线下阶段不从现金买入半仓；先减半后恢复线上则买回减掉的部分。
    所有买卖收盘后决定、次日开盘执行，100份整数交易，不足一手不执行减半。
    """
    if initial_cash<=0 or minimum_fee<0:raise ValueError('本金和最低佣金无效')
    if not targets.index.equals(data.index) or targets.isna().any() or not targets.between(0,1).all():
        raise ValueError('目标序列须与行情对齐，且位于0至1之间')
    if entry_allowed is None:entry_allowed=pd.Series(True,index=data.index)
    if not entry_allowed.index.equals(data.index) or entry_allowed.isna().any():raise ValueError('进入资格序列无效')
    cash=float(initial_cash);qty=0;stage=0.;fee_rate=.0001
    fees=turnover=0.;small_partial=0;equity=[];trades=[];closed=[]
    cycle_cost=cycle_proceeds=0.
    for i in range(start,end):
        desired=float(targets.iloc[i-1]);date=data.index[i]
        opening=float(data.iloc[i].open);previous=float(data.iloc[i-1].close)
        one_price='high' in data and 'low' in data and float(data.iloc[i].high)==float(data.iloc[i].low)
        blocked_buy=limit_pct is not None and one_price and opening/previous-1>=limit_pct-.003
        blocked_sell=limit_pct is not None and one_price and opening/previous-1<=-limit_pct+.003
        before=cash+qty*opening
        if desired==1 and stage!=1 and bool(entry_allowed.iloc[i-1]) and not blocked_buy:
            execution=opening*(1+slippage)
            units=int(cash/(execution*(1+fee_rate))//100)*100
            while units>0 and units*execution+max(minimum_fee,units*execution*fee_rate)>cash:units-=100
            if units:
                action='买入' if qty==0 else '恢复买入'
                notional=units*execution;fee=max(minimum_fee,notional*fee_rate)
                cash-=notional+fee;cycle_cost+=notional+fee;qty+=units
                fees+=fee;turnover+=notional/before
                trades.append({'date':str(date.date()),'action':action,'quantity':units,'price':execution,'fee':fee})
            stage=1. if qty else 0.
        elif desired==0 and qty and not blocked_sell:
            units=qty;execution=opening*(1-slippage);notional=units*execution
            fee=max(minimum_fee,notional*fee_rate);proceeds=notional-fee
            cash+=proceeds;cycle_proceeds+=proceeds;fees+=fee;turnover+=notional/before
            closed.append(cycle_proceeds/cycle_cost-1)
            trades.append({'date':str(date.date()),'action':'退出','quantity':units,'price':execution,'fee':fee})
            qty=0;stage=0.;cycle_cost=cycle_proceeds=0.
        elif 0<desired<1 and qty and stage==1 and not blocked_sell:
            # 按实际持有份数减一次，行情条件不依赖仓位。
            units=int(qty*(1-desired)//100)*100
            if units:
                execution=opening*(1-slippage);notional=units*execution
                fee=max(minimum_fee,notional*fee_rate);proceeds=notional-fee
                cash+=proceeds;qty-=units;cycle_proceeds+=proceeds;fees+=fee;turnover+=notional/before
                trades.append({'date':str(date.date()),'action':'减仓','quantity':units,'price':execution,'fee':fee})
            else:small_partial+=1
            stage=desired
        equity.append({'date':date,'equity':cash+qty*float(data.iloc[i].close),
                       'invested':bool(qty),'quantity':qty,'cash':cash})
    curve=pd.DataFrame(equity).set_index('date')
    values=np.r_[initial_cash,curve.equity.to_numpy()]
    dd=values/np.maximum.accumulate(values)-1
    stats={'return_pct':round(float(values[-1]/initial_cash-1)*100,2),
           'max_drawdown_pct':round(float(dd.min())*100,2),'trades':len(trades),
           'closed_round_trips':len(closed),'losing_round_trips':sum(v<0 for v in closed),
           'invested_pct':round(float(curve.invested.mean())*100,1),
           'fees_yuan':round(fees,2),'turnover_equity_times':round(turnover,2),
           'partial_orders':sum(t['action']=='减仓' for t in trades),
           'restoration_orders':sum(t['action']=='恢复买入' for t in trades),
           'partial_too_small':small_partial}
    return stats,curve,trades


def candidates(close):
    return {'跌破立即退出':trend_positions(close).astype(float),
            '先减半，连续2天线下退出':exit_targets(close),
            '连续2天线下再全部退出':exit_targets(close,remaining=1.),
            '先减半，连续3天线下退出':exit_targets(close,confirmation=3)}


def main():
    output=Path('results/sector_partial_exit');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 半导体ETF：先减仓、再退出研究','',
        '2026-10-04研究。价格统一截到2026-09-30，不用休市后的日期补造行情。',
        '主候选：第一次收盘不高于20日均线，次日卖出持有份数的一半；下一交易日仍不高于均线，再于次日卖出剩余部分。',
        '若减半后收盘重新高于均线，下一交易日买回已减部分。此恢复买入是减仓方案的一部分，不能省略它的费用。',
        '另比较等两天直接退出、以及减半后等三天退出。参数预先固定，本轮不搜索收益最高的比例。',
        '相同120日预热、10万元初始现金；信号下一交易日开盘执行，单边0.1%滑点、万一佣金且最低5元、100份整数交易。',
        '不逐日再平衡；现金收益为0；一字涨停不买、一字跌停不卖；末日不强制清仓。',
        '目标比例仅是研究执行模型，行情触发条件不取决于实际持仓比例。首次开始时在线下，不从现金买入所谓半仓。','']
    for code,limit in [('512760',.10),('588170',.20)]:
        data=pd.read_csv(f'data_cache/etf_{code}_tencent.csv',parse_dates=['date']).set_index('date').sort_index()
        data=data.loc[:'2026-09-30']
        if data.index.has_duplicates or data[['open','close']].isna().any().any() or (data[['open','close']]<=0).any().any():
            raise ValueError('行情无效')
        start=120;split=start+(len(data)-start)//2
        baseline=trend_positions(data.close)
        reference=backtest(data,baseline,start,len(data),limit_pct=limit)[0]
        def run(target,a,b,**kwargs):
            return backtest_partial(data,target,a,b,entry_allowed=baseline,limit_pct=limit,**kwargs)
        result={'start':str(data.index[start].date()),'end':str(data.index[-1].date()),
                'split_date':str(data.index[split].date()),'rules':{}}
        common=max(start,int(data.index.searchsorted(pd.Timestamp('2025-09-29'))))
        lines += [f'## {code}','',f"区间：{result['start']}至{result['end']}。",'',
                  '| 规则 | 累计收益 | 最大回撤 | 买卖次数 | 减仓/恢复买入次数 |','|---|---:|---:|---:|---:|']
        for label,target in candidates(data.close).items():
            stats,curve,trades=run(target,start,len(data))
            if label=='跌破立即退出':
                for key in ('return_pct','max_drawdown_pct','trades','closed_round_trips','losing_round_trips'):
                    if stats[key]!=reference[key]:raise AssertionError('新引擎不符合原基准：'+key)
            rule={'full':stats,'first_half':run(target,start,split)[0],
                  'second_half':run(target,split,len(data))[0],
                  'common_period':run(target,common,len(data))[0],
                  'double_slippage':run(target,start,len(data),slippage=.002)[0],
                  'small_capital_min5':run(target,start,len(data),initial_cash=1000)[0],
                  'small_capital_no_minimum':run(target,start,len(data),initial_cash=1000,minimum_fee=0)[0],
                  'annual':{}}
            for year in sorted(set(data.index[start:].year)):
                indices=np.flatnonzero((data.index.year==year)&(np.arange(len(data))>=start))
                rule['annual'][str(year)]=run(target,int(indices[0]),int(indices[-1])+1)[0]
            result['rules'][label]=rule
            curve.to_csv(output/f'{code}_{label}_curve.csv')
            pd.DataFrame(trades).to_csv(output/f'{code}_{label}_trades.csv',index=False)
            lines.append(f"| {label} | {stats['return_pct']}% | {stats['max_drawdown_pct']}% | {stats['trades']} | {stats['partial_orders']}/{stats['restoration_orders']} |")
        lines+=['','| 规则 | 前段收益/回撤 | 后段收益/回撤 | 滑点加倍收益 | 1000元、最低5元佣金收益 |','|---|---:|---:|---:|---:|']
        for label,rule in result['rules'].items():
            a=rule['first_half'];b=rule['second_half']
            lines.append(f"| {label} | {a['return_pct']}% / {a['max_drawdown_pct']}% | {b['return_pct']}% / {b['max_drawdown_pct']}% | {rule['double_slippage']['return_pct']}% | {rule['small_capital_min5']['return_pct']}% |")
        lines+=['','两段及各年独立从现金开始，不承接上一段持仓；完整年度、共同区间及费用结果见results.json。','']
        lines+=['| 规则 | 1000元、不设最低佣金收益 | 减半不足一手次数 | 累计交易额/交易前账户权益 |','|---|---:|---:|---:|']
        for label,rule in result['rules'].items():
            small=rule['small_capital_min5']
            lines.append(f"| {label} | {rule['small_capital_no_minimum']['return_pct']}% | {small['partial_too_small']} | {rule['full']['turnover_equity_times']} |")
        lines+=['','累计交易额按每次交易前的账户权益归一后求和，用于比较实际换手金额；不是买卖次数。','']
        results[code]=result
    lines+=['## 本次结论','',
        '先减半、连续2天线下退出可作为备选，但不足以替换当前默认。512760累计收益305.45%变为300.35%，回撤31.51%变为29.84%；588170收益47.19%变为51.00%，回撤30.92%变为30.35%。',
        '整体回撤改善较小，且未稳定改善各年、各段：512760在2022/2023/2024年，先减半的收益和回撤均逊于立即退出；588170前半段收益也更低。',
        '交易次数增加：512760为166至228次，588170为24至35次。1000元且最低佣金5元时，两只ETF先减半后的收益都低于立即退出。',
        '因此不以补齐加仓/减仓按钮为理由改变交易规则。先保留当前20日均线直接退出，减仓条件仅作为待继续验证的研究备选。',
        '连续两天再全部退出虽然减少次数，但512760全区间回撤扩大；等待三天也没有稳定改善结果。', '',
        '## 解释与限制','',
        '减半通常降低一次错误卖出涉及的金额，但未必减少次数：确认跌破时会多出第二次卖出；假跌破后恢复买入也要付费。',
        '不足一手不能准确减半时，本研究跳过部分卖出，之后满足退出条件仍可整笔退出。实际减仓份数因100份取整偏离50%。',
        '512760与588170覆盖不同细分行业；588170样本仅约一年，不足以证明跨周期有效。',
        '前复权价格不能精确重现分红现金与历史成交份数；未模拟部分成交和盘口排队。收益与回撤按收盘衡量。',
        '研究样本已被前序研究查看，分段不是严格未见过的样本外。1000元测试是单次全部预算1000元，不是每月定投1000元。',
        '本轮研究不修改App的20日均线默认退出条件。', '',
        '方法参考：[CFA Institute：Backtesting and Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)。']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    for code,result in results.items():
        print(code,result['start'],result['end'])
        for label,rule in result['rules'].items():print(label,rule['full'])
    print('Saved',output/'report.md')


if __name__=='__main__':main()
