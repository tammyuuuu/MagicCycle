"""固定科创50已采用参数，验证表现与执行敏感性；不再搜索参数。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load
from research_broad_individual import execute
from broad_signal_rules import price_band_positions
from research_star50_search import confirmed_ma
from research_csi300_search import batch_execute,summarize


def daily_windows(prices,start,years):
    spans=[]
    for i in range(start,len(prices)):
        anniversary=prices.index[i]+pd.DateOffset(years=years)
        if anniversary>prices.index[-1]:break
        spans.append((i,int(prices.index.searchsorted(anniversary,side='right'))))
    return spans


def joint(a,b):
    return a['profit_on_contributions_pct']>b['profit_on_contributions_pct']+.01 and a['max_drawdown_pct']>b['max_drawdown_pct']+.01


def main():
    p,h,hashes=load('588000','000688')
    start=int(np.flatnonzero(p.close.rolling(250).mean().notna())[0])+1
    new=price_band_positions(p.close,16,.02)
    old=(p.close>p.close.rolling(20).mean()).astype(float)
    hold=pd.Series(1.,index=p.index)
    pd.testing.assert_series_equal(new,confirmed_ma(p.close,16,buffer=.02))
    for n in (300,600,900,len(p)):
        if n<=len(p):pd.testing.assert_series_equal(new.iloc[:n],price_band_positions(p.close.iloc[:n],16,.02))
    result={'hashes':hashes,'parameters':{'ma':16,'buffer':.02},'cutoff':str(p.index[-1].date()),
            'true_post_adoption_days':0,'signal_prefix_and_research_parity':True,'annual':{},'recent':{},'daily_entry':{},'delay':{},'cost':{}}
    for year in (2022,2023,2024,2025,2026):
        s=int(p.index.searchsorted(pd.Timestamp(f'{year}-01-01')))
        e=int(p.index.searchsorted(pd.Timestamp(f'{year+1}-01-01')))
        result['annual'][str(year)]={'start':str(p.index[s].date()),'end':str(p.index[e-1].date()),'partial_year':year==2026,'funding':{}}
        for monthly in (False,True):
            stats={k:execute(p,t,s,e,monthly=1000. if monthly else None)[0] for k,t in [('new',new),('old',old),('hold',hold)]}
            result['annual'][str(year)]['funding'][str(monthly)]={**stats,'joint_vs_hold':joint(stats['new'],stats['hold']),'joint_vs_old':joint(stats['new'],stats['old'])}
    recent=int(p.index.searchsorted(pd.Timestamp('2025-01-01')))
    for monthly in (False,True):
        stats={k:execute(p,t,recent,monthly=1000. if monthly else None)[0] for k,t in [('new',new),('old',old),('hold',hold)]}
        result['recent'][str(monthly)]={**stats,'joint_vs_hold':joint(stats['new'],stats['hold']),'joint_vs_old':joint(stats['new'],stats['old'])}
        for years in (1,3):
            spans=daily_windows(p,start,years);mask=np.ones(len(spans),dtype=bool)
            a=batch_execute(p,new,spans,monthly);b=batch_execute(p,hold,spans,monthly);c=batch_execute(p,old,spans,monthly)
            result['daily_entry'][f'{years}_{monthly}']={'vs_hold':summarize(a,b,mask),'vs_old':summarize(a,c,mask)}
        for delay in (1,2,5):
            stats={k:execute(p,t.shift(delay-1).fillna(0),start,monthly=1000. if monthly else None)[0] for k,t in [('new',new),('old',old)]}
            result['delay'][f'{delay}_{monthly}']={**stats,'joint_vs_old':joint(stats['new'],stats['old'])}
        for slip in (.001,.002,.005):
            stats={k:execute(p,t,start,monthly=1000. if monthly else None,slippage=slip)[0] for k,t in [('new',new),('old',old),('hold',hold)]}
            result['cost'][f'{slip}_{monthly}']={**stats,'joint_vs_hold':joint(stats['new'],stats['hold']),'joint_vs_old':joint(stats['new'],stats['old'])}
    neighbors=json.loads(Path('results/star50_search/adopted.json').read_text(encoding='utf-8'))['neighbors']
    old_stats=result['delay']['1_False']['old']
    checks=[joint(v,old_stats) for k,v in neighbors.items() if k!='16_0.02']
    result['neighbor_joint_vs_old']={'passed':sum(checks),'total':len(checks)}
    out=Path('results/star50_verification');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    report=['# 科创50固定策略验证','',
        '验证日2026-10-04，行情截至2026-09-30。固定16日均线、上下2%缓冲，不根据此次结果再次修改参数。结论：全区间及成本优势存在，但最近行情、年度与邻近参数不够稳定，尚未通过“普遍更优”的验证，只可继续作为试行。','',
        '策略此前使用过这些数据，本次为补充回顾性检查。采用日之后没有新交易数据，真正样本外天数为0，不能声称独立验证。','',
        '## 最近区间：2025年初—2026年9月','',
        '|资金|模型|利润/本金|最大回撤|','|---|---|---:|---:|']
    for f,stats in result['recent'].items():
        for model in ('new','old','hold'):
            v=stats[model];report.append(f'|{"固定10万元" if f=="False" else "每月1000元"}|{model}|{v["profit_on_contributions_pct"]}%|{abs(v["max_drawdown_pct"])}%|')
    report+=['','## 互不重叠的年度账户','',
        '|区间|新策略收益/回撤|20日均线收益/回撤|持有收益/回撤|同时胜过持有|','|---|---|---|---|---|']
    for year,group in result['annual'].items():
        s=group['funding']['False'];values=[f'{s[k]["return_pct"]}% / {abs(s[k]["max_drawdown_pct"])}%' for k in ('new','old','hold')]
        report.append('|'+('2026年前9个月' if group['partial_year'] else year)+'|'+'|'.join(values)+'|'+('是' if s['joint_vs_hold'] else '否')+'|')
    report+=['','年度账户每次从现金重新开始、允许沿用历史市场许可；不等于一个连续账户的年度收益。2026不完整，不与完整年份直接排名。月度年度对照保存在JSON。','',
        '## 每个交易日都作为入场点','',
        '|期限|资金|起点数|对持有/定投同时改善|对上一版同时改善|','|---|---|---:|---:|---:|']
    for key,v in result['daily_entry'].items():
        year,f=key.split('_');report.append(f'|{year}年|{"固定" if f=="False" else "月度"}|{v["vs_hold"]["n"]}|{v["vs_hold"]["joint_win_pct"]}%|{v["vs_old"]["joint_win_pct"]}%|')
    report+=['','每日窗口高度重叠，不能将起点数量当成独立试验数或未来胜率；也不是事先知道高低位后择时买入。','',
        '## 成本、延迟与邻近参数','',
        '|检查|资金|新收益/回撤|旧收益/回撤|两项改善|','|---|---|---|---|---|']
    for kind in ('cost','delay'):
        for key,v in result[kind].items():
            parameter,f=key.split('_');a=v['new'];b=v['old']
            report.append(f'|{kind} {parameter}|{f}|{a["profit_on_contributions_pct"]}% / {abs(a["max_drawdown_pct"])}%|{b["profit_on_contributions_pct"]}% / {abs(b["max_drawdown_pct"])}%|{"是" if v["joint_vs_old"] else "否"}|')
    report+=['',f'附近11组参数只有{sum(checks)}组同时胜过上一版；说明16日与2%这组参数较敏感。延迟检验仅改变执行信号滞后，不使用未来价格，不保证所有券商执行一致。','',
        '## 计算验证与范围','',
        '生产纯规则与独立研究规则一致；截断历史不改变此前信号。资金执行使用次日开盘、100份、万一最低5元、现金收益0、科创ETF20%一字限制近似；前复权近似分红，未精确重建成交/排队。回撤用排除入金影响的净值。','',
        '保留试行参数，本次未改买卖规则。将“不足以证明普遍更优”的结果同步研究依据。复现：python -B verify_star50_strategy.py。']
    Path('star50_strategy_verification.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print('RECENT',result['recent']);print('ANNUAL',[(k,v['funding']['False']['joint_vs_hold']) for k,v in result['annual'].items()]);print('NEIGHBORS',result['neighbor_joint_vs_old'])


if __name__=='__main__':main()
