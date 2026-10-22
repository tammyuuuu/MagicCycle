"""标普500人民币ETF：趋势替代与现行热度参数检验。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_strategy_hold_audit import load,monthly_budget
from research_csi300_search import batch_execute,summarize
from research_csi300_entry_windows import windows
from research_star50_robustness import rules_for
from research_us_etf_extended import monthly_state
from research_us_guidance import momentum
from research_broad_individual import execute
from research_sector_partial_exit import backtest_partial
from us_guidance import guidance_frame


def main():
    p,sha=load('513500')
    frame=guidance_frame(p.close)
    start=max(int(p.index.searchsorted(pd.Timestamp('2015-03-01'))),int(np.flatnonzero(frame.ready)[0])+1)
    ready=pd.Series(False,index=p.index);ready.iloc[start-1:]=True
    rules={f'{kind}{n}_buffer{int(b*100)}':rules_for(p.close,kind,n,b)
        for kind in ('sma','ema') for n in (20,40,60,80,100,120,160,200,250) for b in (0.,.01,.02,.03)}
    rules.update({f'monthly{n}':monthly_state(p.close,n) for n in (6,10,12)})
    rules.update({f'momentum{n}':(momentum(p.close,n)>0).astype(float) for n in (6,9,12)})
    groups={};offset=0
    for years in (1,3,5):
        spans=windows(p,ready,years)
        groups[str(years)]={'spans':spans,'slice':slice(offset,offset+len(spans)),
            'train':np.array([p.index[e-1]<pd.Timestamp('2021-01-01') for s,e in spans]),
            'validation':np.array([p.index[s]>=pd.Timestamp('2021-01-01') for s,e in spans])}
        offset+=len(spans)
    combined=[span for g in groups.values() for span in g['spans']]
    baseline={f:batch_execute(p,pd.Series(1.,index=p.index),combined,f=='monthly') for f in ('fixed','monthly')}
    details={};full={}
    for j,(k,t) in enumerate(rules.items()):
        full[k]=execute(p,t,start)[0]
        d={}
        for f in ('fixed','monthly'):
            values=batch_execute(p,t,combined,f=='monthly')
            for y,g in groups.items():
                a={k:v[g['slice']] for k,v in values.items()};b={k:v[g['slice']] for k,v in baseline[f].items()}
                d[f'{y}_{f}']={part:summarize(a,b,mask) for part,mask in [('train',g['train']),('validation',g['validation']),('full',np.ones(len(g['spans']),dtype=bool))]}
        details[k]=d
        if (j+1)%25==0:print(j+1,len(rules),flush=True)
    hold=execute(p,pd.Series(1.,index=p.index),start)[0]
    def score(k):
        s=[details[k][f'{y}_{f}']['train'] for y in (3,5) for f in ('fixed','monthly')]
        return np.mean([v['joint_win_pct'] for v in s]),np.mean([v['median_excess_pp'] for v in s]),k
    ranking=sorted(rules,key=score,reverse=True)
    current=backtest_partial(p,frame.target,start,len(p),entry_allowed=frame.entry_allowed,limit_pct=.10)[0]
    heat={}
    for high in (.10,.15,.20):
        for low in (.03,.05,.08):
            f=guidance_frame(p.close,heat_threshold=high,cooling_threshold=low)
            key=f'heat{int(high*100)}_cool{int(low*100)}'
            heat[key]={'fixed':backtest_partial(p,f.target,start,len(p),entry_allowed=f.entry_allowed,limit_pct=.10)[0],
                'monthly':monthly_budget(p,f.status,start)[0],
                'late_fixed':backtest_partial(p,f.target,int(p.index.searchsorted(pd.Timestamp('2021-01-01'))),len(p),entry_allowed=f.entry_allowed,limit_pct=.10)[0]}
    both=lambda v:v['return_pct']>hold['return_pct']+.01 and v['max_drawdown_pct']>hold['max_drawdown_pct']+.01
    passes=[k for k,v in full.items() if both(v)]
    heat_passes=[k for k,v in heat.items() if both(v['fixed'])]
    result={'sha256':sha,'start':str(p.index[start].date()),'end':str(p.index[-1].date()),'hold':hold,'current':current,
        'binary_full':full,'binary_windows':details,'heat':heat,'selected_by_training':ranking[0],
        'training_top10':ranking[:10],'binary_both_better_full':passes,'heat_both_better_full':heat_passes}
    out=Path('results/sp500_robustness');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    print('FULL PASSES',passes,heat_passes,'TRAIN SELECTED',ranking[0],flush=True)
    print('TOP FULL',sorted([(k,v['return_pct'],v['max_drawdown_pct']) for k,v in full.items()],key=lambda v:v[1],reverse=True)[:5],flush=True)
    lines=['# 标普500ETF策略再次研究','',
        f'研究日2026-10-04；人民币ETF513500，{result["start"]}—{result["end"]}。{len(rules)}组趋势替代，9组热度参数；未修改生产信号。','',
        '同起点固定10万元、次日开盘、100份整数、万一最低5元、单边0.1%滑点、现金收益0。ETF前复权包含汇率及场内价格变化，但没有精确重建分红现金和历史溢价限制；不能把结果当作美元指数总回报。','',
        '逐月完整1/3/5年，固定资金与每月1000元分开对照持有/普通定投。训练窗口2021年前结束，后段2021年起开始；只按前段3/5年平均两项胜出比例挑首选。历史已被此前研究使用，属于回顾性留出，重叠起点不独立。','',
        f'趋势前段首选 `{ranking[0]}`。全区间同时胜过持有的趋势候选：{len(passes)}组；热度候选：{len(heat_passes)}组。','',
        '|方案|累计收益|最大回撤|','|---|---:|---:|',
        f'|长期持有|{hold["return_pct"]}%|{abs(hold["max_drawdown_pct"])}%|',
        f'|现行方向＋热度|{current["return_pct"]}%|{abs(current["max_drawdown_pct"])}%|']
    keys=list(dict.fromkeys([ranking[0],'sma200_buffer0','ema200_buffer0','monthly10','momentum12']))
    for k in keys:
        v=full[k];lines.append(f'|{k}|{v["return_pct"]}%|{abs(v["max_drawdown_pct"])}%|')
    lines+=['','## 前段首选的不同起点检验','',
        '|期限|资金|前段共同胜出|后段共同胜出|全部起点共同胜出|','|---|---|---:|---:|---:|']
    for y in (1,3,5):
        for f in ('fixed','monthly'):
            d=details[ranking[0]][f'{y}_{f}'];lines.append(f'|{y}年|{f}|{d["train"]["joint_win_pct"]}%|{d["validation"]["joint_win_pct"]}%|{d["full"]["joint_win_pct"]}%|')
    lines+=['','## 热度参数','',
        '|过热/冷却|固定资金收益/回撤|每月预算利润/本金|月度回撤|','|---|---|---:|---:|']
    for k,v in heat.items():
        a=v['fixed'];b=v['monthly'];lines.append(f'|{k}|{a["return_pct"]}% / {abs(a["max_drawdown_pct"])}%|{b["profit_on_contributions_pct"]}%|{abs(b["max_drawdown_pct"])}%|')
    lines+=['','热度固定资金模型使用满额进入、过热减半一次、解除后恢复；月度预算买入半份/加仓全部，是不同资金安排，不混用收益。','',
        '本轮若无候选同时改善收益与回撤，则不声称找到最优策略，不将纯降低回撤包装成全面胜出。原策略继续标为未验证优于持有；研究结果不等于长期持有适合任何价格立即买入。','',
        '复现：python -B research_sp500_robustness.py。完整候选、逐月起点与失败结果在results/sp500_robustness/results.json。']
    Path('sp500_robustness_research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
