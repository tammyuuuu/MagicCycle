"""中证500预定参数网格及替代策略，按逐月起点比较。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load, signal_frame
from research_csi300_search import candidates, batch_execute, summarize
from research_csi300_entry_windows import windows


def guarded_value(close, pct, entry=30, ceiling=90, entry_ma=60, exit_ma=120):
    """低估且趋势恢复进入；趋势转弱或高估退出。行情许可不读取持仓。"""
    buy=close.rolling(entry_ma).mean()
    sell=close.rolling(exit_ma).mean()
    held=False
    states=[]
    for p,c,b,s in zip(pct,close,buy,sell):
        if np.isfinite(p) and np.isfinite(b) and np.isfinite(s):
            if held and (c<=s or p>=ceiling):held=False
            elif not held and p<entry and c>b:held=True
        states.append(float(held))
    return pd.Series(states,index=close.index)


def all_candidates(prices, history):
    rules=candidates(prices,history)
    for years in (3,5,10):
        pct=signal_frame(prices,history,years).percentile
        for entry in (20,30,40):
            for buy in (60,120,200):
                for sell in (60,120,200):
                    rules[f'pe{years}_guard{entry}_buyma{buy}_sellma{sell}']=guarded_value(prices.close,pct,entry,90,buy,sell)
    return rules


def make_groups(prices, ready):
    groups={};offset=0
    for years in (1,3,5):
        spans=windows(prices,ready,years)
        dates=[(str(prices.index[s].date()),str(prices.index[e-1].date())) for s,e in spans]
        groups[str(years)]={'spans':spans,'dates':dates,'slice':slice(offset,offset+len(spans)),
            'masks':{'train':np.array([pd.Timestamp(e)<=pd.Timestamp('2020-12-31') for _,e in dates]),
                     'validation':np.array([pd.Timestamp(s)>=pd.Timestamp('2021-01-01') for s,_ in dates]),
                     'full':np.ones(len(spans),dtype=bool)}}
        offset+=len(spans)
    return groups


def main():
    p,h,hashes=load('510500','000905')
    rules=all_candidates(p,h)
    groups={lb:make_groups(p,signal_frame(p,h,lb).ready) for lb in (5,10)}
    combined={lb:[span for g in gs.values() for span in g['spans']] for lb,gs in groups.items()}
    base={(lb,f):batch_execute(p,pd.Series(1.,index=p.index),combined[lb],f=='monthly')
          for lb in groups for f in ('fixed','monthly')}
    result={'hashes':hashes,'candidate_count':len(rules),'split':'2021-01-01',
        'current':'pe5_floor30_ceiling90_trend120','candidates':{},
        'windows':{str(lb):{k:g['dates'] for k,g in gs.items()} for lb,gs in groups.items()}}
    for j,(key,target) in enumerate(rules.items()):
        lb=10 if key.startswith('pe10_') else 5
        detail={}
        for f in ('fixed','monthly'):
            values=batch_execute(p,target,combined[lb],f=='monthly')
            for years,g in groups[lb].items():
                a={k:v[g['slice']] for k,v in values.items()}
                b={k:v[g['slice']] for k,v in base[(lb,f)].items()}
                detail[f'{years}_{f}']={part:summarize(a,b,mask) for part,mask in g['masks'].items()}
        result['candidates'][key]=detail
        if (j+1)%25==0:print(f'{j+1}/{len(rules)}',flush=True)
    def score(key):
        stats=[result['candidates'][key][f'{y}_{f}']['train'] for y in (3,5) for f in ('fixed','monthly')]
        return (np.mean([v['joint_win_pct'] for v in stats]),np.mean([v['median_excess_pp'] for v in stats]),key)
    ranking=sorted((k for k in rules if not k.startswith('pe10_')),key=score,reverse=True)
    result['selected_by_training']=ranking[0]
    result['training_top10']=ranking[:10]
    out=Path('results/csi500_search');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print('SELECTED',ranking[0],result['candidates'][ranking[0]],flush=True)


if __name__=='__main__':main()
