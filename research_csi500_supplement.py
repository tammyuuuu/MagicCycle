"""第一轮结果后的追加探索：放宽估值入场、低估入场也加趋势保护。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load,signal_frame
from research_broad_individual import execute
from research_csi500_search import guarded_value,make_groups
from research_csi300_search import batch_execute,summarize


def supplementary_rules(p,h):
    rules={}
    for years in (3,5):
        pct=signal_frame(p,h,years).percentile
        for entry in (60,70,80,90):
            for buy in (40,60,120):
                for sell in (60,120,200):
                    rules[f'pe{years}_guard{entry}_buyma{buy}_sellma{sell}']=guarded_value(p.close,pct,entry,90,buy,sell)
        for floor in (10,20,30):
            for ceiling in (60,70,80,90):
                for window in (80,100,120,140,160):
                    ma=p.close.rolling(window).mean()
                    held=False;states=[]
                    for q,c,a in zip(pct,p.close,ma):
                        if np.isfinite(q) and np.isfinite(a):
                            if held and q>=floor and c<=a:held=False
                            elif not held and (q<floor or q<ceiling and c>a):held=True
                        states.append(float(held))
                    rules[f'pe{years}_floor{floor}_ceiling{ceiling}_trend{window}']=pd.Series(states,index=p.index)
    return rules


def main():
    p,h,_=load('510500','000905');frame=signal_frame(p,h,5)
    rules=supplementary_rules(p,h);start=int(np.flatnonzero(frame.ready)[0])+1
    full={k:execute(p,t,start)[0] for k,t in rules.items()}
    eligible=[k for k,v in full.items() if v['return_pct']>216.62 and v['max_drawdown_pct']> -59.36]
    print('FULL BOTH IMPROVED',[(k,full[k]['return_pct'],full[k]['max_drawdown_pct']) for k in eligible],flush=True)
    groups=make_groups(p,frame.ready)
    spans=[span for g in groups.values() for span in g['spans']]
    base={f:batch_execute(p,pd.Series(1.,index=p.index),spans,f=='monthly') for f in ('fixed','monthly')}
    details={}
    for key in eligible:
        d={}
        for f in ('fixed','monthly'):
            values=batch_execute(p,rules[key],spans,f=='monthly')
            for years,g in groups.items():
                a={k:v[g['slice']] for k,v in values.items()}
                b={k:v[g['slice']] for k,v in base[f].items()}
                d[f'{years}_{f}']={part:summarize(a,b,mask) for part,mask in g['masks'].items()}
        details[key]=d
    result={'post_hoc':True,'full':full,'eligible_details':details}
    Path('results/csi500_search/supplement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    print('DONE',len(eligible),flush=True)


if __name__=='__main__':main()
