"""其他现行策略与买入持有的统一核验；不搜索或修改策略参数。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from gold_strategy import stages
from industry_strategy import partial_exit_targets, trend_positions
from research_sector_partial_exit import backtest_partial
from research_broad_individual import execute
from research_broad_valuation import xirr
from us_guidance import guidance_frame

END = '2026-09-30'


def verdict(candidate, hold):
    gain = candidate['return_pct'] > hold['return_pct']
    risk = candidate['max_drawdown_pct'] > hold['max_drawdown_pct']
    return {'return_better': gain, 'drawdown_better': risk, 'both_better': gain and risk,
            'label': '两项均改善' if gain and risk else '仅收益改善' if gain else '仅回撤改善' if risk else '两项均未改善'}


def gold_actions(close):
    frame = stages(close)
    previous = frame.target.shift(1, fill_value=0.)
    action = pd.Series('watch', index=close.index)
    action.loc[(frame.target == 1) & (previous != 1)] = 'buy'
    action.loc[(frame.target == 1) & (previous == .5)] = 'add'
    action.loc[(frame.target == .5) & (previous == 1)] = 'reduce'
    return frame, action


def sector_actions(close):
    above = trend_positions(close)
    average = close.rolling(20).mean()
    ready = average.notna()
    previous_above = above.shift(1, fill_value=False)
    target = partial_exit_targets(close)
    actions = pd.Series('watch', index=close.index)
    actions.loc[ready & above & ~previous_above] = 'buy'
    actions.loc[ready & ~above & previous_above] = 'reduce'
    actions.loc[ready & ~above & ~previous_above & average.shift(1).notna()] = 'exit'
    return target, actions


def monthly_budget(prices, actions, start, end=None, monthly=1000., slippage=.001,
                   buy_fraction=.5, minimum_fee=5.):
    """条件预算模型：每月同额入金，买入用一半现金，加仓用全部可用现金。

    买入每月最多一次、加仓按新事件执行，减仓半份、退出全部；未投入现金和卖出款
    可累积至下次动作。此资金假设不是用户实际预算，不能替代个体投资表现。
    """
    end = len(prices) if end is None else end
    if (not actions.index.equals(prices.index) or actions.isna().any() or monthly <= 0
            or not 1 <= start < end <= len(prices) or not 0 < buy_fraction <= 1
            or not 0 <= slippage < 1 or minimum_fee < 0):
        raise ValueError('无效预算模型参数')
    cash = principal = units = fees = 0.
    qty = 0
    bought_this_month = False
    months = prices.index.to_period('M')
    opening, closing, high, low = [prices[col].to_numpy() for col in ('open','close','high','low')]
    signals = actions.to_numpy()
    rows, trades, flows = [], [], []
    for i in range(start, end):
        date = prices.index[i]
        if i == start or months[i] != months[i-1]:
            before = cash + qty * opening[i]
            nav = before / units if units else 1.
            units += monthly / nav
            cash += monthly
            principal += monthly
            bought_this_month = False
            flows.append((date, -monthly))
        action = signals[i-1]
        one_price = high[i] == low[i]
        limit = .20 if prices.attrs.get('code') == '588170' else .10
        change = opening[i] / closing[i-1] - 1
        blocked_buy = one_price and change >= limit - .003
        blocked_sell = one_price and change <= -limit + .003
        sell_qty = qty if action == 'exit' else qty // 200 * 100 if action == 'reduce' else 0
        if sell_qty and not blocked_sell:
            price = opening[i] * (1-slippage)
            fee = max(minimum_fee, sell_qty * price * .0001)
            cash += sell_qty * price - fee
            qty -= sell_qty
            fees += fee
            trades.append({'date':str(date.date()),'action':action,'quantity':-sell_qty,'price':price,'fee':fee})
        elif (action == 'add' or action == 'buy' and not bought_this_month) and not blocked_buy:
            budget = cash if action == 'add' else cash * buy_fraction
            price = opening[i] * (1+slippage)
            quantity = int(budget/(price*1.0001)//100)*100
            while quantity and quantity * price + max(minimum_fee, quantity * price * .0001) > budget:
                quantity -= 100
            if quantity:
                fee = max(minimum_fee, quantity * price * .0001)
                cash -= quantity * price + fee
                qty += quantity
                fees += fee
                bought_this_month = True
                trades.append({'date':str(date.date()),'action':action,'quantity':quantity,'price':price,'fee':fee})
        equity = cash + qty * closing[i]
        assert cash >= -1e-7 and qty >= 0 and qty % 100 == 0
        rows.append({'date':date,'equity':equity,'nav':equity/units,'cash':cash,'quantity':qty,'principal':principal})
    curve = pd.DataFrame(rows).set_index('date')
    nav = np.r_[1.,curve.nav.to_numpy()]
    flows.append((curve.index[-1],float(curve.equity.iloc[-1])))
    result = {'return_pct':round(float(nav[-1]-1)*100,2),
              'max_drawdown_pct':round(float((nav/np.maximum.accumulate(nav)-1).min())*100,2),
              'principal_yuan':round(principal,2),'ending_yuan':round(float(curve.equity.iloc[-1]),2),
              'profit_on_contributions_pct':round(float(curve.equity.iloc[-1]/principal-1)*100,2),
              'xirr_pct':xirr(flows),'trades':len(trades),'fees_yuan':round(fees,2)}
    return result,curve,trades


def load(code):
    path = Path(f'data_cache/etf_{code}_tencent.csv')
    data = pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:END]
    values = data[['open','close','high','low']]
    if data.index.has_duplicates or not np.isfinite(values.to_numpy()).all() or (values<=0).any().any():
        raise ValueError('无效价格缓存')
    data.attrs['code'] = code
    return data,hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out=Path('results/strategy_hold_audit');out.mkdir(parents=True,exist_ok=True)
    results={}
    for code,name,kind in [('513500','博时标普500ETF','us'),('513100','国泰纳指100ETF','us'),
                           ('518850','华夏黄金ETF','gold'),('588170','科创半导体ETF华夏','sector'),
                           ('512760','半导体ETF参考样本','sector_reference')]:
        data,sha=load(code)
        if kind=='us':
            frame=guidance_frame(data.close)
            target=frame.target;eligible=frame.entry_allowed;actions=frame.status
            start=max(int(data.index.searchsorted(pd.Timestamp('2015-03-01'))),int(np.flatnonzero(frame.ready)[0])+1)
        elif kind=='gold':
            frame,actions=gold_actions(data.close)
            target=frame.target;eligible=actions.isin(['buy','add'])
            start=120
        else:
            target,actions=sector_actions(data.close)
            eligible=actions.eq('buy')
            start=20
        hold=pd.Series(1.,index=data.index)
        limit=.20 if code=='588170' else .10
        def run(a,b,**kwargs):
            return backtest_partial(data,target,a,b,entry_allowed=eligible,limit_pct=limit,**kwargs)
        candidate,curve,trades=run(start,len(data))
        baseline=backtest_partial(data,hold,start,len(data),limit_pct=limit)[0]
        split=start+(len(data)-start)//2
        result={'name':name,'kind':kind,'sha256':sha,'start':str(data.index[start].date()),'end':END,
                'signal_days':actions.iloc[start-1:-1].value_counts().to_dict(),
                'candidate':candidate,'hold':baseline,'verdict':verdict(candidate,baseline),
                'segments':{segment:{'candidate':run(a,b)[0],
                                     'hold':backtest_partial(data,hold,a,b,limit_pct=limit)[0]}
                            for segment,a,b in [('first',start,split),('second',split,len(data))]},
                'execution_checks':{},'rolling_750':[]}
        for label,kwargs in [('double_slippage',{'slippage':.002}),('small_1000',{'initial_cash':1000.})]:
            s=run(start,len(data),**kwargs)[0]
            h=backtest_partial(data,hold,start,len(data),limit_pct=limit,**kwargs)[0]
            result['execution_checks'][label]={'candidate':s,'hold':h,'verdict':verdict(s,h)}
        budget=monthly_budget(data,actions,start,buy_fraction=1. if kind.startswith('sector') else .5)[0]
        dca=execute(data,hold,start,monthly=1000.)[0]
        result['monthly_budget']={'candidate':budget,'ordinary_dca':dca,
                                 'verdict':verdict(budget,dca)}
        for year in sorted(set(data.index[start:].year)):
            a=max(start,int(data.index.searchsorted(pd.Timestamp(year,1,1))))
            b=a+750
            if b<=len(data):
                s=run(a,b)[0];h=backtest_partial(data,hold,a,b,limit_pct=limit)[0]
                result['rolling_750'].append({'start':str(data.index[a].date()),'candidate':s,'hold':h,'verdict':verdict(s,h)})
        curve.to_csv(out/f'{code}_curve.csv')
        pd.DataFrame(trades).to_csv(out/f'{code}_trades.csv',index=False)
        # 重现旧报告共同起点，并保留黄金“阶段恢复”与现行事件入场的差别。
        comparison_start=250 if kind=='gold' else 120 if kind.startswith('sector') else start
        if comparison_start<len(data):
            result['previous_report_period']={
                'start':str(data.index[comparison_start].date()),
                'actual_event_entry':run(comparison_start,len(data))[0],
                'stage_entry':backtest_partial(data,target,comparison_start,len(data),limit_pct=limit,
                    entry_allowed=frame.entry_allowed if kind=='us' else None)[0],
                'hold':backtest_partial(data,hold,comparison_start,len(data),limit_pct=limit)[0]}
        results[code]=result
        print(code,result['start'],candidate['return_pct'],candidate['max_drawdown_pct'],
              baseline['return_pct'],baseline['max_drawdown_pct'],result['verdict']['label'],flush=True)
    results['688836']={'name':'宇树科技','kind':'research_watch','verdict':{'both_better':None,'label':'尚无买卖策略，不能验证'},
                      'reason':'仅约30个交易日行情，营收、扣非利润和趋势为观察项，未确定交易规则；不把一直持有现金当成有效投资策略。'}
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    write_report(results)


def write_report(results):
    def pair(stats):return f"{stats['return_pct']}% / {abs(stats['max_drawdown_pct'])}%"
    lines=['# 其他现行策略是否优于长期持有', '', '研究日期2026-10-04；行情截止2026-09-30。本轮核验现行规则，不按结果搜索新的最高收益参数。', '',
           '## 结论先看', '',
           '标普500、纳指100及当前监测588170半导体策略均未同时胜过持有。美股收益较低，标普回撤几乎没改善；588170以更低收益换取较小回撤。较长的512760参考样本两项改善，但不能当作588170的验证，也不能据此替换监测ETF。', '',
           '黄金从最早首次买点参与的固定10万元模型两项改善，但总共只有3次减仓，前半段与持有相同。从2021-06中途以现金加入并等待真实新买点，则收益明显低于持有；每月1000元预算模型也低于普通定投。不能把早期已参与的好结果概括为当前空仓用户或自由预算加仓都达标。', '',
           '宇树目前只有研究观察，没有买卖策略可验证。本轮将这些结论同步到策略说明的研究依据，不修改买卖信号。', '',
           '## 统一标准', '',
           '相同资金、日期与成本下，累计收益严格更高且最大回撤绝对值更小，才记为“两项均改善”。只改善一项单独注明。主表是固定10万元、阶段买卖模型；不是未知实际预算下的真实收益。', '',
           '美股复用12个月方向、15%过热、5%冷却与20日恢复的现行纯规则；行业复用20日均线分段退出；黄金复用15%双指标过热和5%冷却。首个交易日使用此前已就绪信号，下一开盘执行，100份整数，佣金万一最低5元、单边0.1%滑点、现金收益0。一字涨跌停采用ETF限制近似，末日不强制清仓。', '',
           '入场资格与现行提醒一致：黄金仅首次就绪/冷却新事件允许进入；行业只在上穿事件进入或恢复。美股正常买入许可可持续。固定资金模型在允许入场时花可用现金，减半一次、恢复时花剩余现金；与投资配置“本期新资金配比”不是同一资金安排。', '',
           '行业从20日指标就绪后检验，黄金从120日就绪后检验；美股沿用2015-03共同起点。各标的起点不同，只与各自同期持有比较，不跨标的排名。价格为缓存前复权，未精确重建分红现金、历史真实份数或排队。', '',
           '## 主结果：固定本金', '',
           '|标的与区间|现行规则收益/回撤|持有收益/回撤|是否两项改善|', '|---|---|---|---|']
    for code,r in results.items():
        if 'candidate' in r:
            lines.append(f"|{r['name']} {r['start']}—{r['end']}|{pair(r['candidate'])}|{pair(r['hold'])}|{r['verdict']['label']}|")
    lines+=['', '512760只作为半导体较长样本参考，不是588170的替代回测；持有收益和成分范围不同。宇树尚无买卖规则且历史很短，不参与达标排名。', '',
            '## 分段与执行成本', '',
            '|标的|检查|规则收益/回撤|持有收益/回撤|两项改善|', '|---|---|---|---|---|']
    for r in results.values():
        if 'candidate' not in r:continue
        checks={**r['segments'],**r['execution_checks']}
        for label,values in checks.items():
            lines.append(f"|{r['name']}|{label}|{pair(values['candidate'])}|{pair(values['hold'])}|{'是' if verdict(values['candidate'],values['hold'])['both_better'] else '否'}|")
    lines+=['', '各分段从现金重新开始，黄金和行业必须等待下一真实入场事件；不能把阶段已允许持有当成新买点。这会与旧报告“起始直接进入允许持有阶段”的数字不同。分段和重叠的750交易日窗口是回顾性稳健性检查，不是独立样本外证据。', '',
            '## 每月1000元的预算假设', '',
            '每月首个交易日同额入金；首次遇到买入许可时，美股/黄金用一半累积可用现金，行业用全部；每月普通买入最多一次，加仓新事件用全部现金。减仓卖半份，退出卖剩余。未用资金与卖出款累积，后续允许入场才再投入。这是明确的研究资金假设，不是已知的用户预算，也不是根据实际仓位触发信号。', '',
            '|标的|条件预算利润/本金|普通定投利润/本金|预算净值回撤|定投净值回撤|', '|---|---:|---:|---:|---:|']
    for r in results.values():
        if 'candidate' not in r:continue
        c=r['monthly_budget']['candidate'];h=r['monthly_budget']['ordinary_dca']
        lines.append(f"|{r['name']}|{c['profit_on_contributions_pct']}%|{h['profit_on_contributions_pct']}%|{abs(c['max_drawdown_pct'])}%|{abs(h['max_drawdown_pct'])}%|")
    lines+=['', '净值份额化排除追加本金对回撤的掩盖；累计利润/本金与固定本金收益不直接比较。JSON另列XIRR与净值回报。尤其黄金自由预算加仓的业绩，不能套用旧固定资金买回模型159.33%的结果。', '',
            '## 与旧报告起点和入场假设核对', '',
            '|标的|共同起点|现行新事件才入场|允许持有阶段直接入场|持有|', '|---|---|---|---|---|']
    for r in results.values():
        if 'previous_report_period' not in r:continue
        p=r['previous_report_period']
        lines.append(f"|{r['name']}|{p['start']}|{pair(p['actual_event_entry'])}|{pair(p['stage_entry'])}|{pair(p['hold'])}|")
    lines+=['', '## 来源与复现', '',
            '规则来源：us_guidance.py、industry_strategy.py、gold_strategy.py；价格来自data_cache中的腾讯前复权缓存，哈希在results.json。美股更长美元价格指数机制研究另见us_etf_guidance_research.md，不混入人民币ETF收益表。', '',
            '方法参考：[CFA Institute回测与敏感性分析](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)。资料不背书本App参数。', '',
            '复现：python -B research_strategy_hold_audit.py。实际资金用途、交易费用和入场时机不同可能改变结论，本轮未修改任何买卖信号。']
    text='\n'.join(lines)+'\n'
    Path('strategy_hold_audit.md').write_text(text,encoding='utf-8')
    Path('results/strategy_hold_audit/report.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
