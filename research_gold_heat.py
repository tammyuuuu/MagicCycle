"""黄金大涨后分段卖出研究，不修改App策略。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_sector_partial_exit import backtest_partial
from research_gold_strategy import gold_targets


def heat_targets(close, threshold=.15, exit_on_weak=True, mode='both', cooling=.05, use_trend=True):
    """热度锁定，先减半；过热后20日线转弱退出，冷却前不追买。

    入场基线：收盘高于120日均线；跌至120日线或下方直接退出。
    冷却：20日涨幅和60日偏离均不高于5%，恢复后才重新入场/买回。
    """
    if mode not in ('both','return','deviation'):raise ValueError('未知过热指标')
    if not 0<=cooling<threshold:raise ValueError('冷却值须小于过热值')
    if not use_trend and not exit_on_weak and mode=='both':
        from gold_strategy import stages
        return stages(close,threshold,cooling).target
    ma20=close.rolling(20,min_periods=20).mean()
    ma60=close.rolling(60,min_periods=60).mean()
    ma120=close.rolling(120,min_periods=120).mean()
    rise=close.pct_change(20,fill_method=None);deviation=close/ma60-1
    hot={'both':(rise>=threshold)&(deviation>=threshold),
         'return':rise>=threshold,'deviation':deviation>=threshold}[mode]
    cold=(rise<=cooling)&(deviation<=cooling)
    targets=[];heated=False
    for i,price in enumerate(close):
        was_heated=heated
        if cold.iloc[i]:heated=False
        if hot.iloc[i]:heated=True
        if pd.isna(ma120.iloc[i]) or (use_trend and price<=ma120.iloc[i]):target=0.
        elif exit_on_weak and was_heated and price<=ma20.iloc[i]:target=0.
        elif heated:
            target=0. if exit_on_weak and price<=ma20.iloc[i] else .5
        else:target=1.
        targets.append(target)
    # 退出后仍未冷却，不在价格短暂站回20日线时重新买入。
    # 引擎仅从现金进入target=1；target=.5仅减已有持仓。
    return pd.Series(targets,index=close.index,dtype=float)


def main():
    output=Path('results/gold_heat');output.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv('data_cache/etf_518850_tencent.csv',index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
    if data.index.has_duplicates or data[['open','high','low','close']].isna().any().any() or (data[['open','close']]<=0).any().any():raise ValueError('行情无效')
    start=250;split=start+(len(data)-start)//2
    candidates={'长期持有':pd.Series(1.,index=data.index),
                '普通120日均线':gold_targets(data.close)['120日均线'].astype(float),
                '双指标15%只减半':heat_targets(data.close,exit_on_weak=False),
                '双指标15%减半后转弱退出':heat_targets(data.close),
                '双指标10%减半后转弱退出':heat_targets(data.close,.10),
                '双指标20%减半后转弱退出':heat_targets(data.close,.20),
                '仅20日涨幅15%':heat_targets(data.close,mode='return'),
                '仅60日偏离15%':heat_targets(data.close,mode='deviation'),
                '长期持有加15%过热减半':heat_targets(data.close,exit_on_weak=False,use_trend=False),
                '长期持有加15%过热减半转弱退出':heat_targets(data.close,use_trend=False),
                '长期持有加10%过热减半':heat_targets(data.close,.10,exit_on_weak=False,use_trend=False),
                '长期持有加20%过热减半':heat_targets(data.close,.20,exit_on_weak=False,use_trend=False)}
    result={'start':str(data.index[start].date()),'end':str(data.index[-1].date()),
            'split_date':str(data.index[split].date()),'rules':{}}
    lines=['# 黄金：大涨过热减仓、转弱退出','',
        f"共同比较区间{result['start']}至{result['end']}，518850缓存前复权行情，预热250交易日。",'',
        '固定假设：买入与重新入场以价格高于120日均线为前提，跌至120日线或下方直接退出。',
        '主候选：20交易日涨幅至少15%，且价格高于60日均价至少15%，减持当时实际份数一半，仅一次；过热状态中收盘不高于20日线时退出剩余部分。',
        '过热状态保持至20交易日涨幅和60日偏离均不高于5%；冷却后若仍高于120日线，可恢复买入；未冷却前空仓不追买。',
        '若同一天既转弱又冷却，先执行退出，下一交易日的收盘条件再决定重新入场。',
        '这是包含买回/再入场的完整测试规则，5%冷却条件也属于待验证假设，不能省略再入场成本。',
        '同时比较只减半、10%/20%敏感性及单指标。已看过今年高点与同一历史，参数是回顾性研究假设，不是样本外。',
        '另有长期持有型：取消120日线退出条件，普通波动不卖；冷却后允许买回，无其他下跌保护。与趋势型风险不同。',
        '10万元初始资金，100份整数；收盘信号下一交易日开盘执行，滑点单边0.1%，佣金万一最低5元，一字涨跌停采用10%限制近似。',
        '现金收益0，不每日再平衡，末日不强制卖出，回撤按收盘账户净值。0.5表示卖出已有份数一半，不从现金买半仓。','',
        '|方案|累计收益|最大回撤|买卖次数|减半次数|','|---|---:|---:|---:|---:|']
    for label,target in candidates.items():
        def run(a,b,**kwargs):return backtest_partial(data,target,a,b,limit_pct=.10,**kwargs)
        stats,curve,trades=run(start,len(data))
        rule={'full':stats,'first_half':run(start,split)[0],'second_half':run(split,len(data))[0],
              'small_capital':run(start,len(data),initial_cash=1000)[0],
              'double_slippage':run(start,len(data),slippage=.002)[0],'annual':{},
              '2026_events':[t for t in trades if t['date'].startswith('2026')]}
        for year in sorted(set(data.index[start:].year)):
            indices=np.flatnonzero((data.index.year==year)&(np.arange(len(data))>=start))
            rule['annual'][str(year)]=run(int(indices[0]),int(indices[-1])+1)[0]
        result['rules'][label]=rule
        curve.to_csv(output/f'{label}_curve.csv');pd.DataFrame(trades).to_csv(output/f'{label}_trades.csv',index=False)
        lines.append(f"|{label}|{stats['return_pct']}%|{stats['max_drawdown_pct']}%|{stats['trades']}|{stats['partial_orders']}|")
    lines+=['','|方案|前段收益/回撤|后段收益/回撤|1000元收益|滑点加倍收益|','|---|---:|---:|---:|---:|']
    for label,rule in result['rules'].items():
        a=rule['first_half'];b=rule['second_half']
        lines.append(f"|{label}|{a['return_pct']}% / {a['max_drawdown_pct']}%|{b['return_pct']}% / {b['max_drawdown_pct']}%|{rule['small_capital']['return_pct']}%|{rule['double_slippage']['return_pct']}%|")
    lines+=['','## 2026年主候选实际模拟交易','']
    for event in result['rules']['双指标15%减半后转弱退出']['2026_events']:
        lines.append(f"- {event['date']} {event['action']}，{event['quantity']}份，模拟成交价{event['price']:.4f}。")
    lines+=['','## 初步结论','',
        '长期持有加15%过热减半是值得保留的候选：收益159.33%、最大回撤26.18%、7次买卖，对照长期持有131.28%、30.32%、1次买入。',
        '加入过热后转弱全部退出，收益150.53%、回撤27.27%、10次交易，本样本未进一步改善。',
        '长期持有型10%/20%减半候选收益134.86%/145.49%、回撤26.42%/27.77%。这不证明15%最优，不能按当前排名直接上线。',
        '15%减半方案全段仅3次减仓，前半段没有减仓事件，改善集中在2025至2026。2026年1月28日收盘触发，1月29日开盘模拟减半；3月16日收盘冷却，3月17日开盘买回。',
        '在120日趋势入场版本中，仅20日涨幅15%的过热条件与双指标15%结果一致；第二指标是否值得保留需更多独立事件。',
        '1000元总资金时长期持有收益98.58%、15%减半方案117.49%，但取整影响大，不代表所有小额执行情况。',
        'App暂不改动，保留“大涨时部分卖出”的研究方向；单独买入条件与退出保护尚需讨论。','',
        '## 解释与限制','',
        '15%与10%/20%仅比较合理邻域，不按收益最高值挑选参数。指标高度相关，单指标对照用于检查第二个条件是否有额外价值。',
        '各段和各年从现金开始，未承接前段实际持仓。小额测试为一次1000元总资金，非月度定投，100份取整及最低佣金影响显著。',
        '过热可能长期延续；提前减半会错过上涨，冷却后买回也可能高于减仓价格。当前样本不足以证明跨周期有效。',
        '前复权、分红、盘口排队和部分成交未精确复现；基于收盘的回撤不反映全部盘中风险。研究规则不是当前App黄金策略的复现。',
        'App暂不修改，结论另记于gold_strategy_research.md。',
        '[Fidelity：均线的趋势与信号用途](https://www.fidelity.com/viewpoints/active-investor/moving-averages)',
        '[CFA Institute：回测与敏感性分析](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)',
        '参考资料说明方法，不背书15%、5%、20/60/120日参数或本回测结果。']
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    for label,rule in result['rules'].items():print(label,rule['full'])
    print('2026',result['rules']['双指标15%减半后转弱退出']['2026_events'])


if __name__=='__main__':main()
