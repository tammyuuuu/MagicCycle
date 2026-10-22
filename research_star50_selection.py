"""科创50事后关注方案的邻近周期、成本与资金规模检查。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load
from research_broad_individual import execute
from research_csi300_search import batch_execute,summarize
from research_csi300_entry_windows import windows
from research_star50_search import confirmed_ma


def main():
    p,h,hashes=load('588000','000688');ready=p.close.rolling(250).mean().notna()
    start=int(np.flatnonzero(ready)[0])+1
    selected=confirmed_ma(p.close,16,buffer=.02);previous=confirmed_ma(p.close,20)
    initial=json.loads(Path('results/star50_search/results.json').read_text(encoding='utf-8'))
    result={'hashes':hashes,'post_hoc':True,'selected':'ma16_days1_buffer2','checks':{},'neighbors':{}}
    for n in (14,16,18,20):
        for buffer in (.01,.02,.03):
            result['neighbors'][f'{n}_{buffer}']=execute(p,confirmed_ma(p.close,n,buffer=buffer),start)[0]
    for monthly in (False,True):
        result['checks'][f'full_{monthly}']={k:execute(p,t,start,monthly=1000. if monthly else None)[0]
            for k,t in [('selected',selected),('previous',previous),('hold',pd.Series(1.,index=p.index))]}
        for years in (1,3):
            spans=windows(p,ready,years);mask=np.ones(len(spans),dtype=bool)
            validation=np.array([p.index[s]>=pd.Timestamp('2025-01-01') for s,e in spans])
            for slip in (.001,.002):
                new=batch_execute(p,selected,spans,monthly,slip);old=batch_execute(p,previous,spans,monthly,slip)
                base=batch_execute(p,pd.Series(1.,index=p.index),spans,monthly,slip)
                result['checks'][f'{years}_{monthly}_slippage{slip}']={'vs_hold':summarize(new,base,mask),
                    'vs_previous':summarize(new,old,mask),'validation':summarize(new,base,validation)}
    result['checks']['small_1000']={k:execute(p,t,start,initial=1000.)[0] for k,t in [('selected',selected),('previous',previous),('hold',pd.Series(1.,index=p.index))]}
    Path('results/star50_search/adopted.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    report=['# 科创50本轮研究与采纳','',
        '研究日2026-10-04，行情截至2026-09-30。170组价格策略、36组3年PE策略，之后补充14/16/18/20日与1/2/3%缓冲邻近检查；完整失败结果保留。','',
        '价格方案共用250日预热后的2021-11-25起点。逐月1年47个起点，3年23个起点，没有完整5年窗口。训练1年窗口在2025年之前结束，后段1年窗口2025年起开始，共9个；3年后段没有完整窗口，不能虚构验证。估值方案2023-07才就绪，单独比较，不与价格方案混合排名。','',
        f'前段首选 `{initial["selected_by_training"]}`，后段共同胜出仅22%，不按此直接替换。本轮关注16日均线2%缓冲是看过结果后的探索选择，不是独立样本外最优。','',
        '采纳：收盘高于16日均价的102%进入买入阶段，收盘不高于均价的98%退出；中间维持市场许可。只用历史行情，不读取实际持仓，入场许可期间本期新资金可买入，已有持仓不必每天重复交易。','',
        '固定10万元与每月1000元分开；对照持有与普通定投。前一收盘、下一开盘、100份整数、万一最低5元、单边0.1%滑点，现金收益0，科创ETF20%一字限制近似。利润/累计本金与排除入金影响的净值回撤比较；重叠窗口不是未来胜率。','',
        '|资金|模型|利润/本金|最大回撤|','|---|---|---:|---:|']
    for label,key in [('固定10万元','full_False'),('每月1000元','full_True'),('固定1000元','small_1000')]:
        for model,v in result['checks'][key].items():
            report.append(f'|{label}|{model}|{v["profit_on_contributions_pct"]}%|{abs(v["max_drawdown_pct"])}%|')
    report+=['','|期限|资金|对基准同时胜出|对上一版同时胜出|后段对基准同时胜出|加倍滑点对基准同时胜出|','|---|---|---:|---:|---:|---:|']
    for years in (1,3):
        for monthly in (False,True):
            a=result['checks'][f'{years}_{monthly}_slippage0.001'];b=result['checks'][f'{years}_{monthly}_slippage0.002']
            val=a['validation']['joint_win_pct']
            report.append(f'|{years}年|{monthly}|{a["vs_hold"]["joint_win_pct"]}%|{a["vs_previous"]["joint_win_pct"]}%|{str(val)+"%" if val is not None else "无完整窗口"}|{b["vs_hold"]["joint_win_pct"]}%|')
    report+=['','邻近周期与缓冲不一定都保留收益优势；最近1年9个起点的新策略共同胜出44%，上一版本固定56%、定投44%，不能称为每个阶段都更好。小额最低佣金依然显著。前复权近似而非精确分红现金，历史短且此前已看过，不保证未来。','',
        '2026-10-04写入star50_buffer_v2试行，只改科创50。回测为全额账户执行，投资配置仍为本期预算规则。3/5/10年估值偏好不影响本价格策略。','',
        '复现：python -B research_star50_search.py；python -B research_star50_selection.py。完整结果见results/star50_search。']
    Path('star50_adopted_strategy.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(result['checks']['full_False'],result['checks']['full_True'],result['checks']['small_1000'])
    print('NEIGHBORS',[(k,v['return_pct'],v['max_drawdown_pct']) for k,v in result['neighbors'].items()])


if __name__=='__main__':main()
