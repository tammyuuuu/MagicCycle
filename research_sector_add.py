"""固定总资金，研究均线回调加仓；不修改App。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from industry_strategy import trend_positions, partial_exit_targets
from research_sector_partial_exit import backtest_partial


def add_signals(close, proximity=.02):
    ma=close.rolling(20,min_periods=20).mean()
    near=(close>ma)&(close<=ma*(1+proximity))
    candidate=(ma>ma.shift(5))&near.shift(1,fill_value=False)&(close>close.shift(1))&(close>ma)
    # 一轮靠近均线的回调仅一次；离开附近区间后才能开始下一轮。
    used=False;result=[]
    for i in range(len(close)):
        if i and not near.iloc[i-1]:used=False
        fire=bool(candidate.iloc[i] and not used)
        if fire:used=True
        result.append(fire)
    return pd.Series(result,index=close.index,dtype=bool)


def simulate(data,start,end,base=.5,enable_add=True,proximity=.02,
             initial_cash=100000.,minimum_fee=5.,slippage=.001,limit_pct=.20):
    targets=partial_exit_targets(data.close)
    above=trend_positions(data.close)
    adds=add_signals(data.close,proximity)
    cash=float(initial_cash);qty=0;stage=0.;boosted=False
    fees=0.;trades=[];curve=[]
    for i in range(start,end):
        desired=targets.iloc[i-1];opening=float(data.open.iloc[i])
        one_price=data.high.iloc[i]==data.low.iloc[i]
        change=opening/data.close.iloc[i-1]-1
        blocked_buy=one_price and change>=limit_pct-.003
        blocked_sell=one_price and change<=-limit_pct+.003
        action=None;units=0;buy=False
        if desired==0 and qty:
            if not blocked_sell:action='退出';units=qty
        elif desired==.5 and qty and stage==1:
            if not blocked_sell:
                action='减仓';units=int(qty*.5//100)*100;stage=.5
        elif desired==1 and above.iloc[i-1] and not blocked_buy:
            allocation=None
            if not qty:boosted=False;allocation=base;action='买入'
            elif stage==.5:allocation=1. if boosted else base;action='恢复买入'
            elif enable_add and adds.iloc[i-1] and not boosted:
                allocation=1.;action='加仓'
            if allocation is not None:
                equity=cash+qty*opening
                budget=min(cash,max(0.,equity*allocation-qty*opening))
                price=opening*(1+slippage)
                units=int(budget/(price*1.0001)//100)*100
                while units and units*price+max(minimum_fee,units*price*.0001)>budget:units-=100
                buy=True
                if qty:stage=1.
        if units:
            price=opening*(1+slippage if buy else 1-slippage)
            amount=units*price;fee=max(minimum_fee,amount*.0001)
            cash+=-amount-fee if buy else amount-fee
            qty+=units if buy else -units;fees+=fee
            if buy:
                stage=1.
                if action=='加仓':boosted=True
            if qty==0:stage=0.;boosted=False
            trades.append({'date':str(data.index[i].date()),'action':action,'quantity':units,'price':price,'fee':fee})
        curve.append({'date':data.index[i],'equity':cash+qty*float(data.close.iloc[i]),'cash':cash,'quantity':qty})
    curve=pd.DataFrame(curve).set_index('date')
    values=np.r_[initial_cash,curve.equity.to_numpy()]
    stats={'return_pct':round((values[-1]/initial_cash-1)*100,2),
           'max_drawdown_pct':round(float((values/np.maximum.accumulate(values)-1).min())*100,2),
           'trades':len(trades),'add_orders':sum(t['action']=='加仓' for t in trades),'fees_yuan':round(fees,2)}
    return stats,curve,trades


def main():
    output=Path('results/sector_add');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 半导体ETF回调加仓研究','',
        '截至2026-09-30的缓存前复权行情，120日预热，收盘判断、下一交易日开盘成交。',
        '条件：20日均线高于5交易日前；昨天收盘在均线上方且距离不超过2%；今天上涨且仍在线上。同一回调只提示一次。',
        '固定10万元总资金，不追加外部资金；首次使用50%或75%，余款留给加仓。一轮持有最多用完一次余款。',
        '首次线下卖出实际份数一半，连续两日线下退出；恢复线上回到本轮已部署的资金档位，不每日再平衡。',
        '100份整数、单边0.1%滑点、万一佣金最低5元；一字涨跌停限制成交。现金收益0，不强制末日卖出。','']
    for code,limit in [('512760',.10),('588170',.20)]:
        data=pd.read_csv(f'data_cache/etf_{code}_tencent.csv',index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
        if data.index.has_duplicates or data[['open','high','low','close']].isna().any().any() or (data[['open','close']]<=0).any().any():raise ValueError('行情无效')
        start=120;split=start+(len(data)-start)//2
        rules={'当前：首次全部买入':(1.,False,.02),'半预算、不加仓':(.5,False,.02),
               '半预算、2%回调加仓':(.5,True,.02),'75%预算、2%回调加仓':(.75,True,.02),
               '半预算、1%回调加仓':(.5,True,.01),'半预算、3%回调加仓':(.5,True,.03)}
        result={'start':str(data.index[start].date()),'end':str(data.index[-1].date()),'rules':{}}
        lines += [f'## {code}',f"{result['start']}至{result['end']}",'',
                  '|规则|收益|最大回撤|交易次数|加仓次数|','|---|---:|---:|---:|---:|']
        for label,(base,enabled,proximity) in rules.items():
            def run(a,b,**kwargs):return simulate(data,a,b,base,enabled,proximity,limit_pct=limit,**kwargs)
            stats,curve,trades=run(start,len(data))
            if base==1:
                ref=backtest_partial(data,partial_exit_targets(data.close),start,len(data),entry_allowed=trend_positions(data.close),limit_pct=limit)[0]
                for key in ('return_pct','max_drawdown_pct','trades'):assert stats[key]==ref[key],(code,key,stats,ref)
            rule={'full':stats,'first_half':run(start,split)[0],'second_half':run(split,len(data))[0],
                  'small_capital':run(start,len(data),initial_cash=1000)[0],
                  'double_slippage':run(start,len(data),slippage=.002)[0],'annual':{}}
            for year in sorted(set(data.index[start:].year)):
                indices=np.flatnonzero((data.index.year==year)&(np.arange(len(data))>=start))
                rule['annual'][str(year)]=run(int(indices[0]),int(indices[-1])+1)[0]
            result['rules'][label]=rule
            curve.to_csv(output/f'{code}_{label}_curve.csv')
            pd.DataFrame(trades).to_csv(output/f'{code}_{label}_trades.csv',index=False)
            lines.append(f"|{label}|{stats['return_pct']}%|{stats['max_drawdown_pct']}%|{stats['trades']}|{stats['add_orders']}|")
        results[code]=result
        print(code,json.dumps(result,ensure_ascii=False))
    lines+=['','## 结论','',
        '2%回调加仓没有显示稳定优势，暂不启用。588170半预算不加仓收益26.42%、回撤18.66%；加入条件后收益19.98%、回撤20.29%，仅执行两次加仓。',
        '512760半预算不加仓收益120.16%、回撤16.88%；加入条件后收益191.80%、回撤30.92%。加仓提高收益的同时扩大风险，仍低于当前全部入场方案的收益300.35%、回撤29.84%。',
        '588170的1%/2%结果相同，3%收益37.53%、回撤28.99%；512760的1%/2%/3%收益分别170.80%/191.80%/164.83%，回撤32.35%/30.92%/30.62%。阈值变化会明显影响结果。',
        '1000元最低5元佣金时，588170半预算加仓收益-3.66%，不加仓6.99%；小额分拆交易负担较重。',
        '这些结果仅针对上述固定预算部署方案，不证明所有回调加仓无效，也不证明首次全部投入适合每个人。','',
        '## 限制','',
        '这是资金部署方案比较，不是同一风险暴露下的纯信号排名。留现金本身降低风险，也可能错过上涨。',
        '加仓条件独立于实际仓位；研究中的50%/75%仅决定执行金额。默认先用满预算时，没有余款执行加仓。',
        '1%/3%仅检查邻近阈值敏感性，不用于挑选收益最高参数。分段、年度均重新从现金开始。',
        '已看过这些历史样本，不属于严格未见的样本外；588170仅约一年有效测试，512760覆盖不同半导体细分。',
        '复权、佣金、成交排队及收盘回撤口径均有局限。1000元是单次总资金，不是月度定投。',
        '本研究不修改App；完整分段、年度、1000元和滑点敏感性见results.json。']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
