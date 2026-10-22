"""科创50：短历史下分别检查价格策略与估值策略，不虚构5年验证。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load,signal_frame
from research_broad_individual import execute,buffered_trend
from research_us_etf_extended import monthly_state
from research_csi300_search import batch_execute,summarize
from research_csi300_entry_windows import windows
from broad_signal_rules import valuation_positions


def confirmed_ma(close,window=20,buy_days=1,sell_days=1,buffer=0.):
    average=close.rolling(window).mean()
    buy=(close>average*(1+buffer)).rolling(buy_days).sum()==buy_days
    sell=(close<=average*(1-buffer)).rolling(sell_days).sum()==sell_days
    held=False;states=[]
    for b,s in zip(buy,sell):
        if held and s:held=False
        elif not held and b:held=True
        states.append(float(held))
    return pd.Series(states,index=close.index)


def price_candidates(p):
    rules={}
    for n in (10,16,20,24,30,40,60,80,100,120,160,200,250):
        for days in (1,2,3):
            for buffer in (0.,.01,.02):
                rules[f'ma{n}_days{days}_buffer{int(buffer*100)}']=confirmed_ma(p.close,n,days,days,buffer)
        for buy,sell in ((2,1),(3,1),(1,2)):
            rules[f'ma{n}_buydays{buy}_selldays{sell}']=confirmed_ma(p.close,n,buy,sell)
    for short,long in ((5,20),(10,20),(10,40),(20,60),(20,120),(60,120)):
        rules[f'cross{short}_{long}']=(p.close.rolling(short).mean()>p.close.rolling(long).mean()).astype(float)
    for n in (6,10,12):
        rules[f'monthly{n}']=monthly_state(p.close,n)
    for buy,sell in ((20,10),(40,20),(60,20),(120,60),(250,120)):
        upper=p.close.rolling(buy).max().shift(1);lower=p.close.rolling(sell).min().shift(1)
        held=False;states=[]
        for c,u,l in zip(p.close,upper,lower):
            if held and c<l:held=False
            elif not held and c>u:held=True
            states.append(float(held))
        rules[f'channel{buy}_{sell}']=pd.Series(states,index=p.index)
    return rules


def evaluate(p,targets,ready,split='2025-01-01'):
    groups={};offset=0
    for years in (1,3):
        spans=windows(p,ready,years)
        if not spans:continue
        groups[str(years)]={'spans':spans,'slice':slice(offset,offset+len(spans)),
            'dates':[(str(p.index[s].date()),str(p.index[e-1].date())) for s,e in spans],
            'train':np.array([p.index[e-1]<pd.Timestamp(split) for s,e in spans]),
            'validation':np.array([p.index[s]>=pd.Timestamp(split) for s,e in spans])}
        offset+=len(spans)
    spans=[span for g in groups.values() for span in g['spans']]
    baseline={f:batch_execute(p,pd.Series(1.,index=p.index),spans,f=='monthly') for f in ('fixed','monthly')}
    result={}
    for j,(key,target) in enumerate(targets.items()):
        detail={}
        for f in ('fixed','monthly'):
            values=batch_execute(p,target,spans,f=='monthly')
            for years,g in groups.items():
                a={k:v[g['slice']] for k,v in values.items()};b={k:v[g['slice']] for k,v in baseline[f].items()}
                detail[f'{years}_{f}']={part:summarize(a,b,mask) for part,mask in
                    [('train',g['train']),('validation',g['validation']),('full',np.ones(len(g['spans']),dtype=bool))]}
        result[key]=detail
        if (j+1)%25==0:print(f'{j+1}/{len(targets)}',flush=True)
    return result,{k:g['dates'] for k,g in groups.items()}


def main():
    p,h,hashes=load('588000','000688')
    ready=p.close.rolling(250).mean().notna()
    rules=price_candidates(p)
    details,dates=evaluate(p,rules,ready)
    def score(k):
        rows=[details[k]['1_'+f]['train'] for f in ('fixed','monthly')]
        return (np.mean([v['joint_win_pct'] for v in rows]),np.mean([v['median_excess_pp'] for v in rows]),k)
    ranking=sorted(rules,key=score,reverse=True)
    start=int(np.flatnonzero(ready)[0])+1
    full={k:execute(p,t,start)[0] for k,t in rules.items()}
    pe_ready=signal_frame(p,h,3).ready
    pct=signal_frame(p,h,3).percentile
    value_rules={f'pe3_buy{entry}_sell{exit_}_ma{ma}':valuation_positions(pct,p.close,entry,exit_,bool(ma),exit_ma=ma or 60)
        for entry in (20,30,40) for exit_ in (70,80,90) for ma in (0,20,60,120)}
    value_details,value_dates=evaluate(p,value_rules,pe_ready)
    result={'hashes':hashes,'price_candidates':details,'price_full':full,'price_windows':dates,
        'value_candidates':value_details,'value_windows':value_dates,'selected_by_training':ranking[0],
        'training_top10':ranking[:10],'current':'ma20_days1_buffer0',
        'no_complete_5year_windows':not windows(p,ready,5)}
    out=Path('results/star50_search');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    print('SELECTED',ranking[0],full[ranking[0]],details[ranking[0]],flush=True)


if __name__=='__main__':main()
