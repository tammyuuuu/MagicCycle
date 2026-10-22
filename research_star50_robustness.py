"""科创50参数稳定性研究：固定门槛，允许没有合格策略。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load
from research_broad_individual import execute
from research_csi300_search import batch_execute,summarize
from research_csi300_entry_windows import windows
from research_star50_search import confirmed_ma,evaluate


CRITERIA={'neighbor_pass_fraction':.75,'minimum_neighbors':4,
          'holdout_joint_win_pct':50.,'holdout_median_excess_pp':0.,
          'full_return_margin_pp':.01,'full_drawdown_margin_pp':.01}


def rules_for(close,kind,window,buffer):
    average=close.rolling(window).mean() if kind=='sma' else close.ewm(span=window,adjust=False,min_periods=window).mean()
    held=False;values=[]
    for c,a in zip(close,average):
        if np.isfinite(a):
            if c>a*(1+buffer):held=True
            elif c<=a*(1-buffer):held=False
        values.append(float(held))
    return pd.Series(values,index=close.index)


def robust_screen(full,details,neighbors,reference):
    def improves(stats):
        return stats['return_pct']>reference['return_pct']+.01 and stats['max_drawdown_pct']>reference['max_drawdown_pct']+.01
    result={}
    for key,near in neighbors.items():
        region=[key,*near]
        fraction=sum(improves(full[n]) for n in region)/len(region)
        rows=[details[key]['1_'+f]['train'] for f in ('fixed','monthly')]
        train_ok=all(v['joint_win_pct']>=50. and v['median_excess_pp']>=0 for v in rows)
        eligible=improves(full[key]) and len(near)>=CRITERIA['minimum_neighbors'] and fraction>=CRITERIA['neighbor_pass_fraction'] and train_ok
        validation=[details[key]['1_'+f]['validation'] for f in ('fixed','monthly')]
        validation_ok=all(v['n']>0 and v['joint_win_pct']>=50. and v['median_excess_pp']>=0 for v in validation)
        result[key]={'neighbors':near,'region_pass_fraction':round(fraction,4),'training_eligible':bool(eligible),'validation_pass':bool(validation_ok)}
    return result


def main():
    p,h,hashes=load('588000','000688')
    ready=p.close.rolling(250).mean().notna();start=int(np.flatnonzero(ready)[0])+1
    periods=(10,12,14,16,18,20,22,24,26,28,30,40,60,80,100,120)
    buffers=(0.,.01,.02,.03)
    rules={};coordinates={}
    for kind in ('sma','ema'):
        for i,n in enumerate(periods):
            for j,buffer in enumerate(buffers):
                key=f'{kind}{n}_buffer{int(buffer*100)}'
                rules[key]=rules_for(p.close,kind,n,buffer)
                coordinates[key]=(kind,i,j)
    lookup={value:key for key,value in coordinates.items()}
    neighbors={key:[lookup[(kind,ni,nj)] for ni,nj in ((i-1,j),(i+1,j),(i,j-1),(i,j+1)) if (kind,ni,nj) in lookup]
               for key,(kind,i,j) in coordinates.items()}
    # 多数许可，检验是否降低对单个周期的依赖；此类暂不作为网格中心。
    for triple in ((12,16,20),(14,16,18),(16,20,24),(20,30,40),(60,80,100)):
        for b in buffers:
            members=[rules[f'sma{n}_buffer{int(b*100)}'] for n in triple]
            rules['vote'+'_'.join(map(str,triple))+f'_buffer{int(b*100)}']=(sum(members)>=2).astype(float)
    details,dates=evaluate(p,rules,ready)
    full={k:execute(p,t,start)[0] for k,t in rules.items()}
    reference=execute(p,confirmed_ma(p.close,20),start)[0]
    train_end=int(p.index.searchsorted(pd.Timestamp('2025-01-01')))
    train_full={k:execute(p,t,start,train_end)[0] for k,t in rules.items()}
    train_reference=execute(p,confirmed_ma(p.close,20),start,train_end)[0]
    screen=robust_screen(train_full,details,neighbors,train_reference)
    train_selected=[k for k,v in screen.items() if v['training_eligible']]
    train_selected.sort(key=lambda k:(screen[k]['region_pass_fraction'],np.mean([details[k]['1_'+f]['train']['joint_win_pct'] for f in ('fixed','monthly')]),k),reverse=True)
    selected=train_selected[0] if train_selected else None
    result={'criteria':CRITERIA,'hashes':hashes,'candidate_count':len(rules),'reference':reference,
        'full':full,'train_full':train_full,'train_reference':train_reference,'details':details,'windows':dates,'screen':screen,'training_eligible':train_selected,
        'selected_by_training':selected,'selected_validation_pass':screen[selected]['validation_pass'] if selected else False,
        'note':'所有历史此前已看过，是回顾性验证；本轮不按后段结果重新挑选。'}
    out=Path('results/star50_robustness');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    print('TRAIN ELIGIBLE',train_selected,'SELECTED',selected,flush=True)
    print('FULL BOTH',[(k,v['return_pct'],v['max_drawdown_pct']) for k,v in full.items() if v['return_pct']>reference['return_pct'] and v['max_drawdown_pct']>reference['max_drawdown_pct']],flush=True)
    lines=['# 科创50稳定性优先的再次研究','',
        f'研究日2026-10-04，行情截至2026-09-30。固定筛选标准后比较{len(rules)}组简单均线、指数均线及多数许可方案；本轮不根据后段结果调门槛。','',
        '目标：收益与回撤同时优于原20日均线，再看相邻周期和缓冲是否共同有效。对照普通定投/持有的逐月1年和3年比较，成本与资金规则沿用前轮。','',
        '筛选标准：仅用2025年前的固定资金区间，中心与上下周期、上下缓冲组成的区域至少75%同时优于原20日均线，至少4个相邻参数；训练1年窗口固定资金与月度资金共同胜出率均至少50%，利润差中位数非负。选定后检验2025年起1年窗口，同样要求两种资金方式均至少50%共同胜出且利润差中位数非负。','',
        '相邻周期只指本轮预定网格的相邻点；更长周期跨度较大，不代表连续每一天参数都测试过。训练窗口在2025年前结束，后段窗口2025年起开始。3年后段没有完整窗口，5年没有完整窗口。','',
        f'满足训练与区域门槛的候选数量：{len(train_selected)}。前段选定：{selected or "无"}。后段检验通过：{result["selected_validation_pass"]}。','',
        '## 部分代表方案','',
        '|方案|全区间收益|最大回撤|1年固定/定投共同胜出|后段固定/定投共同胜出|前段区域通过比例|','|---|---:|---:|---|---|---:|']
    keys=['sma16_buffer2','sma20_buffer0','ema16_buffer2','ema20_buffer2','vote14_16_18_buffer2','vote16_20_24_buffer2']
    if selected:keys.append(selected)
    for key in dict.fromkeys(keys):
        v=full[key];d=details[key]
        ratios=lambda part:' / '.join(str(d['1_'+f][part]['joint_win_pct'])+'%' for f in ('fixed','monthly'))
        region=str(round(screen[key]['region_pass_fraction']*100,1))+'%' if key in screen else '非网格中心'
        lines.append(f'|{key}|{v["return_pct"]}%|{abs(v["max_drawdown_pct"])}%|{ratios("full")}|{ratios("validation")}|{region}|')
    lines+=['','## 结论与边界','',
        '本轮如无候选通过，则不再替换买卖参数，不把另一个历史尖峰称为更优。保留16日2%作为未经稳定验证的试行观察，不能作为已证实的主要买卖依据。多数许可和指数均线也不因规则更复杂就自动更好。','',
        '全部候选与失败结果保存在results/star50_robustness/results.json。重复使用历史、大量候选与重叠窗口都可能夸大效果，达到门槛也不能保证未来。筛选门槛是本轮约定的研究标准，不是统计显著性检验。','',
        '复现：python -B research_star50_robustness.py。']
    Path('star50_robustness_research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
