"""明确记录中证500追加探索选择及成本/滚动入场检验。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_broad_valuation import load,signal_frame
from broad_signal_rules import low_value_or_trend
from research_broad_individual import execute
from research_csi300_search import batch_execute,summarize
from research_csi500_search import make_groups


def main():
    p,h,hashes=load('510500','000905');frame=signal_frame(p,h,5)
    current=low_value_or_trend(p.close,frame.percentile,120)
    selected=low_value_or_trend(p.close,frame.percentile,120,ceiling=60)
    groups=make_groups(p,frame.ready);start=int(np.flatnonzero(frame.ready)[0])+1
    result={'hashes':hashes,'selected':'pe5_floor30_ceiling60_trend120','post_hoc':True,'checks':{}}
    first=json.loads(Path('results/csi500_search/results.json').read_text(encoding='utf-8'))
    supplemental=json.loads(Path('results/csi500_search/supplement.json').read_text(encoding='utf-8'))
    for monthly in (False,True):
        result['checks'][f'full_{monthly}']={k:execute(p,t,start,monthly=1000. if monthly else None)[0]
                    for k,t in [('selected',selected),('previous',current),('hold',pd.Series(1.,index=p.index))]}
        for years,g in groups.items():
            spans=g['spans'];mask=g['masks']['full']
            for cost in (.001,.002):
                new=batch_execute(p,selected,spans,monthly,cost)
                old=batch_execute(p,current,spans,monthly,cost)
                base=batch_execute(p,pd.Series(1.,index=p.index),spans,monthly,cost)
                result['checks'][f'{years}_{monthly}_slippage{cost}']={
                    'vs_hold':summarize(new,base,mask),'vs_previous':summarize(new,old,mask),
                    'validation':summarize(new,base,g['masks']['validation'])}
    result['checks']['small_1000']={k:execute(p,t,start,initial=1000.)[0] for k,t in [('selected',selected),('previous',current),('hold',pd.Series(1.,index=p.index))]}
    Path('results/csi500_search/adopted.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    lines=['# 中证500本轮策略研究与采纳','',
        '研究日2026-10-04，行情截至2026-09-30。第一轮531组候选，之后追加192组探索；失败结果保留。规则含3/5/10年估值、买卖分位、入场/退出均线确认、回撤门槛、估值或趋势、估值且趋势、纯均线与缓冲、通道突破。','',
        '每月独立现金账户起点，比较完整1/3/5年；固定10万元对持有、每月1000元对普通定投。前一收盘信号、次日开盘、100份整数、万一最低5元、单边0.1%滑点、现金收益0；份额化净值回撤排除入金掩盖。利润率为利润/累计本金。','',
        '训练窗口须2020年末前结束，验证窗口须2021年后开始，跨界窗口不参与二者。仅前段3/5年平均共同胜出率筛选第一轮首选；10年PE预热后没有前段完整5年窗口，不能参与主筛选。','',
        f'前段首选 `{first["selected_by_training"]}` 全区间收益262%、回撤47%，但后段3/5年共同胜出比例为0%，不采用。严格趋势保护可明显减少回撤，但未保留原有收益。','',
        '本轮采用 `pe5_floor30_ceiling60_trend120`：低估（PE分位低于30%）允许买入，或分位低于60%且价格高于120日均价时允许买入；入场后保持许可，离开低估区且价格回到120日均价或下方退出。分位升到60%以上不会单独卖出。','',
        '选择理由：保留当前框架，将趋势重新入场的估值上限由90%降至60%，减少估值偏高时追入；全区间收益与回撤均改善，3/5年两种资金方式的共同胜出比例也提高。低估仍可直接入场，所以最大回撤改善有限，不能称为低风险。','',
        '|期限|资金|上一版共同胜出|新版本共同胜出|新版本后段共同胜出|滑点加倍后新版本共同胜出|','|---|---|---:|---:|---:|---:|']
    for years in (1,3,5):
        for monthly in (False,True):
            f='monthly' if monthly else 'fixed';k=f'{years}_{f}'
            old=first['candidates'][first['current']][k]['full']['joint_win_pct']
            new=result['checks'][f'{years}_{monthly}_slippage0.001']
            high=result['checks'][f'{years}_{monthly}_slippage0.002']
            lines.append(f'|{years}年|{f}|{old}%|{new["vs_hold"]["joint_win_pct"]}%|{new["validation"]["joint_win_pct"]}%|{high["vs_hold"]["joint_win_pct"]}%|')
    lines+=['','上述共同胜出均指对持有/定投收益和回撤同时改善。改善差须超过0.01个百分点；重叠窗口不独立，不是未来胜率。','',
        '## 全区间与小额执行','', '|资金方式|模型|利润/本金|最大回撤|','|---|---|---:|---:|']
    for label,key in [('固定10万元','full_False'),('每月1000元','full_True'),('固定1000元','small_1000')]:
        for model,v in result['checks'][key].items():
            lines.append(f'|{label}|{model}|{v["profit_on_contributions_pct"]}%|{abs(v["max_drawdown_pct"])}%|')
    lines+=['','## 限制与复现','',
        '这是看到第一轮后追加的探索选择，不能宣称独立验证或全局最优。5年后段只有9个重叠起点；PE缺少历史发布与修订版本，前复权仅近似分红；3/10年偏好需独立判断，默认5年业绩不能直接套用。120日邻近周期并不都有效；换为140日未保留全区间收益优势。','',
        '2026-10-04采纳为csi500_value_trend_v2，只改中证500。投资配置仍为本期新资金预算，不等于全额账户回测。原版本报告保留作对照。','',
        '复现：python -B research_csi500_search.py；python -B research_csi500_supplement.py；python -B research_csi500_selection.py。完整所有候选与失败结果在results/csi500_search。', '',
        '方法参考：[CFA Institute回测](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)，不背书具体参数。']
    Path('csi500_adopted_strategy.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(result['checks']['full_False'],result['checks']['full_True'],result['checks']['small_1000'])


if __name__=='__main__':main()
