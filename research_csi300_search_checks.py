"""搜索后重点候选检查：必须标为事后关注，不更换训练首选。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load, signal_frame
from research_broad_individual import execute
from research_csi300_search import candidates, batch_execute, summarize, write_report


def main():
    path=Path('results/csi300_search/results.json')
    result=json.loads(path.read_text(encoding='utf-8'))
    prices,history,_=load('510300','000300')
    rules=candidates(prices,history)
    current='pe5_buy30_sell90_ma60'
    focus=current+'_buyma60'
    result['post_hoc_focus']=focus
    result['focus_checks']={}
    for years,dates in result['windows']['5'].items():
        spans=[(prices.index.get_loc(pd.Timestamp(s)),prices.index.get_loc(pd.Timestamp(e))+1) for s,e in dates]
        mask=np.ones(len(spans),dtype=bool)
        for funding in ('fixed','monthly'):
            baseline=batch_execute(prices,pd.Series(1.,index=prices.index),spans,funding=='monthly',.002)
            old=batch_execute(prices,rules[current],spans,funding=='monthly',.002)
            candidate=batch_execute(prices,rules[focus],spans,funding=='monthly',.002)
            result['focus_checks'][f'{years}_{funding}_double_cost']={
                'vs_hold':summarize(candidate,baseline,mask),'vs_current':summarize(candidate,old,mask)}
    start=int(np.flatnonzero(signal_frame(prices,history,5).ready)[0])+1
    for funding in ('fixed','monthly'):
        result['focus_checks'][f'full_history_{funding}']={
            k:execute(prices,rules[k],start,monthly=1000. if funding=='monthly' else None)[0]
            for k in (current,focus)}
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    write_report(result)
    report=Path('csi300_parameter_search_research.md')
    with report.open('a',encoding='utf-8') as f:
        f.write('\n## 事后关注：低估后等60日均线确认\n\n')
        f.write('前段纯均线首选后段失败，保留失败结果。另一组前段前十候选、买入增加60日均线确认，在多项比较中改善；此重点在看过后段后确定，属于探索，不能宣称新的独立验证，也未替换线上策略。\n\n')
        f.write('|期限|资金|当前对基准同时胜出|确认买入后对基准同时胜出|滑点加倍后对基准同时胜出|滑点加倍后对当前同时胜出|\n|---|---|---:|---:|---:|---:|\n')
        for years in (1,3,5):
            for funding in ('fixed','monthly'):
                key=f'{years}_{funding}'
                a=result['candidates'][current][key]['full']['joint_win_pct']
                b=result['candidates'][focus][key]['full']['joint_win_pct']
                check=result['focus_checks'][key+'_double_cost']
                f.write(f'|{years}年|{funding}|{a}%|{b}%|{check["vs_hold"]["joint_win_pct"]}%|{check["vs_current"]["joint_win_pct"]}%|\n')
        f.write('\n附近条件并不都稳定：买入确认改20日、估值门槛改40%时优势减弱；退出确认改120日的部分指标反而更好，可继续比较，不能宣称60日为最优。短期仍有收益落后，不能概括为所有期限都更优。\n')
    print(json.dumps(result['focus_checks'],ensure_ascii=False,indent=2))


if __name__=='__main__': main()
