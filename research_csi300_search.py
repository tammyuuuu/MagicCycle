"""预定小网格筛选沪深300策略；批量账户执行以复用逐月入场检验。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from broad_signal_rules import signal_frame, valuation_positions
from research_broad_valuation import load
from research_broad_individual import buffered_trend
from research_csi300_entry_windows import windows


def batch_execute(prices, target, spans, monthly=False, slippage=.001):
    """多个独立窗口并行；与execute相同的0/1许可、费用和资金规则。"""
    starts, ends = np.array(spans).T
    count = len(spans)
    cash = np.zeros(count) if monthly else np.full(count, 100000.)
    principal = cash.copy()
    units = cash.copy()
    qty = np.zeros(count, dtype=np.int64)
    peak = np.ones(count)
    drawdown = np.zeros(count)
    result_nav = np.ones(count)
    last = np.zeros(count)
    opening, closing, high, low = [prices[c].to_numpy() for c in ('open','close','high','low')]
    desired = target.to_numpy()
    months = prices.index.to_period('M')
    for i in range(starts.min(), ends.max()):
        active = (starts<=i)&(i<ends)
        deposit = active & ((starts==i)|(months[i]!=months[i-1])) if monthly else np.zeros(count,dtype=bool)
        before = cash + qty*opening[i]
        unit_price = np.divide(before, units, out=np.ones(count), where=units>0)
        units[deposit] += 1000./unit_price[deposit]
        cash[deposit] += 1000.
        principal[deposit] += 1000.
        held = desired[i-1] == 1.
        change = opening[i]/closing[i-1]-1
        one_price = high[i]==low[i]
        limit=.20 if prices.attrs.get('code')=='588000' else .10
        buy = active & held & ((qty==0)|deposit|(last==0)) & (not (one_price and change>=limit-.003))
        if buy.any():
            price = opening[i]*(1+slippage)
            quantity = (cash[buy]/(price*1.0001)//100).astype(np.int64)*100
            fee = np.maximum(5., quantity*price*.0001)
            over = (quantity>0)&(quantity*price+fee>cash[buy])
            quantity[over] -= 100
            fee = np.where(quantity>0,np.maximum(5.,quantity*price*.0001),0.)
            cash[buy] -= quantity*price+fee
            qty[buy] += quantity
        sell = active & (not held) & (qty>0) & (not (one_price and change<=-limit+.003))
        if sell.any():
            price = opening[i]*(1-slippage)
            cash[sell] += qty[sell]*price - np.maximum(5.,qty[sell]*price*.0001)
            qty[sell] = 0
        last[active] = desired[i-1]
        nav = np.divide(cash+qty*closing[i], units, out=np.ones(count), where=units>0)
        peak[active] = np.maximum(peak[active], nav[active])
        drawdown[active] = np.minimum(drawdown[active], nav[active]/peak[active]-1)
        result_nav[active] = nav[active]
    # 每个窗口结束后现金/份数冻结，但末日价格不同，利润需由其最终净值恢复。
    ending = result_nav*units
    return {'profit': (ending/principal-1)*100, 'dd': drawdown*100,
            'nav_return': (result_nav-1)*100}


def candidates(prices, history):
    close = prices.close
    averages = {n:close.rolling(n).mean() for n in (20,60,120,200)}
    rules = {}
    for years in (3,5,10):
        signal = signal_frame(prices,history,years)
        pct = signal.percentile
        for entry in (20,30,40):
            for exit_ in (70,80,90):
                for sell in (0,20,60,120):
                    key = f'pe{years}_buy{entry}_sell{exit_}_ma{sell}'
                    rules[key] = valuation_positions(pct,close,entry,exit_,bool(sell),exit_ma=sell or 60)
                    for confirm in (20,60):
                        held = False
                        states = []
                        for p,c,b,s in zip(pct,close,averages[confirm],averages[sell or 60]):
                            if np.isfinite(p):
                                if held and p>=exit_ and (not sell or c<=s):
                                    held=False
                                elif not held and p<entry and c>b:
                                    held=True
                            states.append(float(held))
                        rules[key+f'_buyma{confirm}'] = pd.Series(states,index=close.index)
        for entry in (20,30,40):
            for drop in (.10,.20):
                for sell in (0,60):
                    held=False
                    states=[]
                    for p,c,a,d in zip(pct,close,averages[60],signal.drawdown):
                        if np.isfinite(p):
                            if held and p>=90 and (not sell or c<=a): held=False
                            elif not held and p<entry and d>=drop: held=True
                        states.append(float(held))
                    rules[f'pe{years}_buy{entry}_drop{int(drop*100)}_sell90_ma{sell}']=pd.Series(states,index=close.index)
        for entry in (20,30,40):
            for ceiling in (70,90):
                for n in (60,120,200):
                    held=False
                    states=[]
                    for p,c,a in zip(pct,close,averages[n]):
                        if np.isfinite(p) and np.isfinite(a):
                            if held and p>=entry and c<=a:
                                held=False
                            elif not held and (p<entry or p<ceiling and c>a):
                                held=True
                        states.append(float(held))
                    rules[f'pe{years}_floor{entry}_ceiling{ceiling}_trend{n}'] = pd.Series(states,index=close.index)
    for n in (20,40,60,100,120,160,200,250):
        rules[f'ma{n}'] = (close>close.rolling(n).mean()).astype(float)
        for buffer in (.01,.02,.05):
            rules[f'ma{n}_buffer{int(buffer*100)}'] = buffered_trend(close,n,buffer)
    for buy,sell in ((20,10),(60,20),(120,60),(250,120)):
        upper=close.rolling(buy).max().shift(1)
        lower=close.rolling(sell).min().shift(1)
        held=False
        states=[]
        for c,u,l in zip(close,upper,lower):
            if held and c<l: held=False
            elif not held and c>u: held=True
            states.append(float(held))
        rules[f'channel{buy}_{sell}']=pd.Series(states,index=close.index)
    return rules


def summarize(values, base, mask):
    if not mask.any():
        return {'n':0, 'return_win_pct':None, 'joint_win_pct':None,
                'median_excess_pp':None, 'median_profit_pct':None,
                'worst_profit_pct':None, 'median_dd_pct':None, 'worst_dd_pct':None}
    excess=values['profit'][mask]-base['profit'][mask]
    smaller=values['dd'][mask]>base['dd'][mask]+.01
    return {'n':int(mask.sum()), 'return_win_pct':round(float((excess>.01).mean()*100),1),
            'joint_win_pct':round(float(((excess>.01)&smaller).mean()*100),1),
            'median_excess_pp':round(float(np.median(excess)),2),
            'median_profit_pct':round(float(np.median(values['profit'][mask])),2),
            'worst_profit_pct':round(float(values['profit'][mask].min()),2),
            'median_dd_pct':round(float(np.median(values['dd'][mask])),2),
            'worst_dd_pct':round(float(values['dd'][mask].min()),2)}


def write_report(result):
    chosen=result['selected_by_training']
    current='pe5_buy30_sell90_ma60'
    keys=list(dict.fromkeys([current,chosen,*result['training_top10'][:3],*result['exploratory_10year_top10'][:1]]))
    lines=['# 沪深300参数与替代策略研究','',
           f'行情截至2026-09-30，共{result["candidate_count"]}组预定候选。没有按后段结果更换前段首选。','',
           '参数：3/5/10年月度PE；买入分位20/30/40；卖出分位70/80/90；直接退出或20/60/120日均线确认；买入可加20/60日确认；价格回撤门槛10/20%；低估或60/120/200日趋势入场；20—250日纯均线、1/2/5%缓冲与价格通道突破。未穷举任意小数阈值。','',
           '每月独立现金账户起点，1/3/5年完整期限。固定10万元与每月1000元分开检验，相同起点同额资金比较持有/定投。信号只用前一收盘；100份整数、万一最低5元、单边0.1%滑点、现金收益0。等待期间现金计入账户。市场许可可由起点前的低估信号延续，与实际仓位无关。','',
           '训练窗口必须在2020年末前结束；后段窗口必须2021年之后开始，跨越分界的窗口不用于筛选或后段验证。筛选仅用训练3/5年、两种资金方式的平均同时胜出比例，平分再比利润差；1年只作检查。收益比较为利润/累计入金，回撤排除入金影响；两项至少改善0.01个百分点才算胜出。','',
           '10年估值2015-04才就绪，前段完整5年窗口只有少数，单独探索、不参加主筛选。3/5年及价格策略共用5年指标就绪后的起点。不同预热组不直接排名。','',
           f'前段首选：`{chosen}`。当前：`{current}`。','',
           '此前已看过整份历史，因此仍是回顾性留出检查，非真正未知样本外证据；大量候选与重叠窗口可能夸大优势。PE缓存无历史发布/修订版本、前复权未精确重建分红现金。没有自动修改生产规则。','',
           '## 重点候选（格式：前段 / 后段 / 全部起点）','',
           '|候选|期限|资金|同时胜出比例|后段相对基准利润差中位数|后段最差回撤|后段起点数|',
           '|---|---|---|---|---:|---:|---:|']
    for key in keys:
        for y in (1,3,5):
            for f in ('fixed','monthly'):
                d=result['candidates'][key][f'{y}_{f}']
                v=d['validation']
                proportions=' / '.join(str(d[p]['joint_win_pct'])+'%' for p in ('train','validation','full'))
                lines.append(f'|{key}|{y}年|{"固定" if f=="fixed" else "月度"}|{proportions}|{v["median_excess_pp"]}个百分点|{abs(v["worst_dd_pct"])}%|{v["n"]}|')
    lines+=['','完整450组成功/失败结果及起止日期见 results/csi300_search/results.json。', '',
            '方法参考：[CFA Institute回测与敏感性分析](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)。来源不背书本App参数。','',
            '复现：python -B research_csi300_search.py。']
    Path('csi300_parameter_search_research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    prices,history,hashes=load('510300','000300')
    rules=candidates(prices,history)
    all_groups={}
    for lookback in (5,10):
        ready=signal_frame(prices,history,lookback).ready
        groups={}
        offset=0
        for years in (1,3,5):
            spans=windows(prices,ready,years)
            dates=[(str(prices.index[s].date()),str(prices.index[e-1].date())) for s,e in spans]
            train=np.array([pd.Timestamp(e)<=pd.Timestamp('2020-12-31') for _,e in dates])
            validation=np.array([pd.Timestamp(s)>=pd.Timestamp('2021-01-01') for s,_ in dates])
            groups[str(years)]={'spans':spans,'dates':dates,'slice':slice(offset,offset+len(spans)),
                'masks':{'train':train,'validation':validation,'full':np.ones(len(spans),dtype=bool)}}
            offset+=len(spans)
        all_groups[lookback]=groups
    result={'hashes':hashes,'candidate_count':len(rules),'split':'2021-01-01','candidates':{},
            'windows':{str(lb):{k:g['dates'] for k,g in groups.items()} for lb,groups in all_groups.items()}}
    baselines={}
    combined={lb:[span for g in groups.values() for span in g['spans']] for lb,groups in all_groups.items()}
    for lb in all_groups:
        for funding in ('fixed','monthly'):
            baselines[(lb,funding)]=batch_execute(prices,pd.Series(1.,index=prices.index),combined[lb],funding=='monthly')
    for j,(key,target) in enumerate(rules.items()):
        detail={}
        lb=10 if key.startswith('pe10_') else 5
        for funding in ('fixed','monthly'):
            values=batch_execute(prices,target,combined[lb],funding=='monthly')
            for years,g in all_groups[lb].items():
                subset={k:v[g['slice']] for k,v in values.items()}
                base={k:v[g['slice']] for k,v in baselines[(lb,funding)].items()}
                detail[f'{years}_{funding}']={part:summarize(subset,base,mask) for part,mask in g['masks'].items()}
        result['candidates'][key]=detail
        if (j+1)%25==0: print(f'{j+1}/{len(rules)}',flush=True)
    # 只使用前段3/5年指标：平均同时胜出比例，其次平均利润差；1年作独立报告。
    def score(key):
        rows=[result['candidates'][key][f'{y}_{f}']['train'] for y in (3,5) for f in ('fixed','monthly')]
        return (np.mean([r['joint_win_pct'] for r in rows]), np.mean([r['median_excess_pp'] for r in rows]),key)
    ranking=sorted((k for k in rules if not k.startswith('pe10_')),key=score,reverse=True)
    result['selected_by_training']=ranking[0]
    result['training_top10']=ranking[:10]
    result['exploratory_10year_top10']=sorted((k for k in rules if k.startswith('pe10_')),key=score,reverse=True)[:10]
    out=Path('results/csi300_search');out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    write_report(result)
    print('SELECTED',ranking[0],result['candidates'][ranking[0]],flush=True)


if __name__=='__main__': main()
