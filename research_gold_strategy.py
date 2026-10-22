"""黄金ETF初步研究：固定规则比较，不修改今日提醒。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_sector_trend import backtest


def gold_targets(close):
    averages={n:close.rolling(n,min_periods=n).mean() for n in (20,60,120,200)}
    rules={'长期持有':pd.Series(True,index=close.index)}
    for n in averages:rules[f'{n}日均线']=close>averages[n]
    rules['120日均线向上']=(close>averages[120])&(averages[120]>averages[120].shift(5))
    high=close.rolling(250,min_periods=250).max()
    held=False;targets=[]
    for price,ma,peak in zip(close,averages[120],high):
        if pd.isna(ma) or price<=ma:held=False
        elif not held and pd.notna(peak) and price/peak-1<=-.05:held=True
        targets.append(held)
    rules['回撤5%买入、跌破120日线退出']=pd.Series(targets,index=close.index)
    return rules


def main():
    output=Path('results/gold_strategy');output.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv('data_cache/etf_518850_tencent.csv',index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
    if data.index.has_duplicates or data[['open','high','low','close']].isna().any().any() or (data[['open','close']]<=0).any().any():raise ValueError('无效行情')
    start=250;split=start+(len(data)-start)//2
    result={'code':'518850','history_start':str(data.index[0].date()),'history_end':str(data.index[-1].date()),
            'days':len(data),'start':str(data.index[start].date()),'split_date':str(data.index[split].date()),'rules':{}}
    lines=['# 华夏黄金ETF：初步策略研究','',f"缓存行情：{result['history_start']}至{result['history_end']}，{len(data)}个交易日。共同比较从{result['start']}开始，预热250日。",'',
           '只比较预先固定的简单规则，不寻找历史收益最高参数。回撤策略用近250交易日最高收盘价，回撤至少5%且价格在120日线上买入；持续持有至不高于120日线。',
           '回撤规则是简化研究候选，不是当前App包含RSI、双均线、盈利减仓等条件的完整复现。',
           '10万元初始资金、无外部追加，信号收盘产生、下一交易日开盘执行。100份整数，佣金万一最低5元、单边0.1%滑点；现金收益0，末日不强制卖出。',
           '研究对一字涨跌停使用10%成交限制近似，未模拟盘口排队；收盘净值最大回撤。本轮只研究日频。','',
           '|规则|累计收益|最大回撤|买卖次数|持有天数比例|','|---|---:|---:|---:|---:|']
    for label,target in gold_targets(data.close).items():
        def run(a,b,**kwargs):return backtest(data,target,a,b,limit_pct=.10,**kwargs)
        stats,curve,trades=run(start,len(data))
        rule={'full':stats,'first_half':run(start,split)[0],'second_half':run(split,len(data))[0],
              'small_capital':run(start,len(data),initial_cash=1000)[0],
              'double_slippage':run(start,len(data),slippage=.002)[0],'annual':{}}
        for year in sorted(set(data.index[start:].year)):
            indices=np.flatnonzero((data.index.year==year)&(np.arange(len(data))>=start))
            rule['annual'][str(year)]=run(int(indices[0]),int(indices[-1])+1)[0]
        result['rules'][label]=rule
        curve.to_csv(output/f'{label}_curve.csv');pd.DataFrame(trades).to_csv(output/f'{label}_trades.csv',index=False)
        lines.append(f"|{label}|{stats['return_pct']}%|{stats['max_drawdown_pct']}%|{stats['trades']}|{stats['invested_pct']}%|")
    lines+=['','|规则|前段收益/回撤|后段收益/回撤|1000元收益|滑点加倍收益|','|---|---:|---:|---:|---:|']
    for label,rule in result['rules'].items():
        a=rule['first_half'];b=rule['second_half']
        lines.append(f"|{label}|{a['return_pct']}% / {a['max_drawdown_pct']}%|{b['return_pct']}% / {b['max_drawdown_pct']}%|{rule['small_capital']['return_pct']}%|{rule['double_slippage']['return_pct']}%|")
    lines+=['','## 限制与参考','',
            '只研究单只ETF六年左右的已知历史，不是未见样本外，不证明未来表现。各段和各年从现金重新开始。',
            '收益差异可能来自持有时间减少，而非择时更准确；没有组合数据，不能验证黄金对用户整体资产的分散效果。',
            '1000元为单次资金，不是每月定投；黄金ETF单价相对较高，100份取整可能显著影响资金利用。前复权价格不能精确重现历史分红现金与份数。',
            '当前App仍保持原规则，研究结论另记于gold_strategy_research.md。',
            '[华夏基金：518850官方产品页](https://fund.chinaamc.com/fund/518850/index.shtml)',
            '[世界黄金协会：黄金作为战略资产](https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset)',
            '上述资料说明产品与黄金属性，不提供本研究的均线周期或5%阈值，也不背书回测结果。']
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(result['start'],result['history_end'])
    for label,rule in result['rules'].items():print(label,rule['full'],rule['first_half']['return_pct'],rule['second_half']['return_pct'])


if __name__=='__main__':main()
