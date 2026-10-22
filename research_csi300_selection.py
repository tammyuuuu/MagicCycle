"""本轮采纳前的邻近参数和明确选择记录。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from broad_signal_rules import valuation_positions, signal_frame
from research_broad_valuation import load
from research_csi300_entry_windows import windows
from research_csi300_search import batch_execute, summarize
from research_broad_individual import execute


def main():
    p,h,_=load('510300','000300')
    frame=signal_frame(p,h,5)
    result={}
    for years in (3,5):
        spans=windows(p,frame.ready,years)
        for monthly in (False,True):
            base=batch_execute(p,pd.Series(1.,index=p.index),spans,monthly)
            for buy in (40,60,80):
                for sell in (40,60,80,120):
                    target=valuation_positions(frame.percentile,p.close,confirm_exit=True,entry_ma=buy,exit_ma=sell)
                    values=batch_execute(p,target,spans,monthly)
                    result[f'{years}_{monthly}_buy{buy}_sell{sell}']=summarize(values,base,np.ones(len(spans),dtype=bool))
    Path('results/csi300_search/neighbors.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    selected=valuation_positions(frame.percentile,p.close,confirm_exit=True,entry_ma=60,exit_ma=80)
    previous=valuation_positions(frame.percentile,p.close,confirm_exit=True)
    checks={}
    start=int(np.flatnonzero(frame.ready)[0])+1
    for monthly in (False,True):
        checks[f'full_{monthly}']={
            'selected':execute(p,selected,start,monthly=1000. if monthly else None)[0],
            'previous':execute(p,previous,start,monthly=1000. if monthly else None)[0]}
        for years in (1,3,5):
            spans=windows(p,frame.ready,years)
            base=batch_execute(p,pd.Series(1.,index=p.index),spans,monthly,.002)
            new=batch_execute(p,selected,spans,monthly,.002)
            old=batch_execute(p,previous,spans,monthly,.002)
            mask=np.ones(len(spans),dtype=bool)
            validation=np.array([p.index[s]>=pd.Timestamp('2021-01-01') for s,e in spans])
            checks[f'{years}_{monthly}_double_slippage']={'vs_hold':summarize(new,base,mask),
                'vs_previous':summarize(new,old,mask),'validation':summarize(new,base,validation)}
    checks['decision']='采纳5年PE30/90、60日入场确认、80日退出确认；较60日退出有更高3/5年共同胜出比例，较120日退出有更小最差回撤。事后筛选，非独立验证或全局最优。'
    Path('results/csi300_search/adopted.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    report=['# 沪深300本轮采纳策略','',checks['decision'],'',
        '2026-10-04写入今日提醒，版本csi300_value_confirm_v2。买入许可进入后持续到退出条件，不要求每天重新满足低估和60日均线。3/10年仍可选，但默认5年结果不能推广到其他年限。','',
        '|检查|相对持有/定投同时改善|相对上一版本同时改善|后段相对基准同时改善|','|---|---:|---:|---:|']
    for key,v in checks.items():
        if 'double_slippage' in key:
            report.append(f'|{key}|{v["vs_hold"]["joint_win_pct"]}%|{v["vs_previous"]["joint_win_pct"]}%|{v["validation"]["joint_win_pct"]}%|')
    report+=['','上述为滑点加倍检查，普通成本完整结果及40/60/80/120日邻近检查在neighbors.json。5年后段只有9个重叠起点，不足以证明未来。纯均线前段首选后段失败，未改写筛选历史。','',
        '全区间固定10万元：上一版本306.46% / 回撤35.25%；采纳版本372.77% / 回撤31.43%；同期持有161.16% / 回撤52.95%。回顾性、估值发布版本缺失，不能称为实盘已验证。','',
        '只修改沪深300，不修改中证500、科创50或其他资产规则。投资配置仍按本期新资金预算计算，不能套用全额资金回测收益。','',
        '复现：python -B research_csi300_selection.py。']
    Path('csi300_adopted_strategy.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2,default=float))


if __name__=='__main__':main()
