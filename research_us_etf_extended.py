"""美股ETF追加研究：持仓风控与新资金入场分开评价，不修改生产策略。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from us_etf_strategy import targets as original_targets

END = '2026-09-30'
START = '2015-03-01'
CAPITAL = 100000.


def load(code):
    data = pd.read_csv(f'data_cache/etf_{code}_tencent.csv', index_col='date', parse_dates=True).sort_index().loc[:END]
    values = data[['open', 'high', 'low', 'close']]
    if data.index.has_duplicates or not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        raise ValueError('行情无效 ' + code)
    if (data.high < data[['open', 'close', 'low']].max(axis=1)).any() or (data.low > data[['open', 'close', 'high']].min(axis=1)).any():
        raise ValueError('OHLC不一致 ' + code)
    return data


def monthly_state(close, months=10, band=0., confirmations=1):
    """月末标签未到达时不可见；非交易日月末采用现有App的保守延迟。"""
    monthly = close.resample('ME').last()
    monthly = monthly.loc[monthly.index <= close.index[-1]]
    ma = monthly.rolling(months, min_periods=months).mean()
    state = False
    below = 0
    states = []
    for price, average in zip(monthly, ma):
        if not np.isfinite(average):
            state, below = False, 0
        elif price > average * (1 + band):
            state, below = True, 0
        elif price <= average * (1 - band):
            below += 1
            if below >= confirmations:
                state = False
        else:
            below = 0
        states.append(float(state))
    return pd.Series(states, index=monthly.index).reindex(close.index, method='ffill').fillna(0.)


def candidates(close):
    monthly = close.resample('ME').last()
    monthly = monthly.loc[monthly.index <= close.index[-1]]
    momentum = (monthly.pct_change(12, fill_method=None) > 0).astype(float).reindex(close.index, method='ffill').fillna(0.)
    trend = monthly_state(close)
    return {
        '长期持有': pd.Series(1., index=close.index),
        '初始50%投入后持有': pd.Series(.5, index=close.index),
        '10个月均线全进全出': trend,
        '10个月均线±2%缓冲': monthly_state(close, band=.02),
        '连续两月线下才退出': monthly_state(close, confirmations=2),
        '10个月均线线下减半': .5 + .5 * trend,
        '12个月涨幅为正才持有': momentum,
        '8个月均线全进全出': monthly_state(close, months=8),
        '12个月均线全进全出': monthly_state(close, months=12),
    }


def stats(equity, initial, dates, trades=0, exposure=None):
    values = np.r_[initial, equity]
    years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)
    return {
        'return_pct': round((values[-1] / initial - 1) * 100, 2),
        'annualized_pct': round(((values[-1] / initial) ** (1 / years) - 1) * 100, 2),
        'max_drawdown_pct': round(float((values / np.maximum.accumulate(values) - 1).min() * 100), 2),
        'trades': trades,
        'average_exposure_pct': round(float(np.mean(exposure)) * 100, 1) if exposure is not None else None,
    }


def exposure_backtest(data, target, start, end, slippage=.001, initial=CAPITAL, entry_allowed=None):
    """只在信号敞口改变时再配置；不每日再平衡，信号使用前日收盘。"""
    opening = data.open.to_numpy()
    close = data.close.to_numpy()
    high = data.high.to_numpy()
    low = data.low.to_numpy()
    desired = target.to_numpy()
    eligible = np.ones(len(data), dtype=bool) if entry_allowed is None else entry_allowed.to_numpy(dtype=bool)
    cash, qty, old = initial, 0, None
    curve, exposure, trades = [], [], []
    for i in range(start, end):
        weight = float(desired[i - 1])
        if (old is None or weight != old) and not (qty == 0 and weight > 0 and not eligible[i - 1]):
            account = cash + qty * opening[i]
            execution = opening[i] * (1 + slippage)
            wanted = int(weight * account / execution // 100) * 100
            if weight == 0:
                wanted = 0
            one_price = high[i] == low[i]
            change = opening[i] / close[i - 1] - 1
            if wanted > qty and not (one_price and change >= .097):
                units = wanted - qty
                while units and units * execution + max(5., units * execution * .0001) > cash:
                    units -= 100
                if units:
                    cash -= units * execution + max(5., units * execution * .0001)
                    qty += units
                    trades.append({'date': str(data.index[i].date()), 'action': '买入', 'quantity': units})
                old = weight
            elif wanted < qty and not (one_price and change <= -.097):
                units = qty - wanted
                execution = opening[i] * (1 - slippage)
                cash += units * execution - max(5., units * execution * .0001)
                qty -= units
                trades.append({'date': str(data.index[i].date()), 'action': '卖出', 'quantity': units})
                old = weight
            elif wanted == qty:
                old = weight
            # 被近似涨跌停拦住时，下个交易日重试，不提前假定成交。
        value = cash + qty * close[i]
        curve.append(value)
        exposure.append(qty * close[i] / value)
    result = stats(np.array(curve), initial, data.index[start:end], len(trades), exposure)
    return result, pd.DataFrame({'equity': curve, 'exposure': exposure}, index=data.index[start:end]), trades


def entry_signals(close):
    drawdown = 1 - close / close.rolling(250, min_periods=250).max()
    trend = monthly_state(close).astype(bool)
    cross = trend & ~trend.shift(1, fill_value=False)
    return {
        '立即买入': (pd.Series(True, index=close.index), None),
        '等回撤5%': (drawdown >= .05, None),
        '等回撤10%': (drawdown >= .10, None),
        '等回撤20%': (drawdown >= .20, None),
        '等回撤5%最多三个月': (drawdown >= .05, 63),
        '等回撤10%最多三个月': (drawdown >= .10, 63),
        '月度趋势在线上即可买': (trend, None),
        '只等月度重新上穿': (cross, None),
        '趋势向上且回撤5%最多三个月': (trend & (drawdown >= .05), 63),
    }


def entry_backtest(data, signal, start, end, deadline=None, installments=False, slippage=.001):
    """同笔资金、同起点和终点；买入后不卖，隔离入场择时效果。"""
    if installments:
        months = data.index[start:end].to_period('M')
        entries = (np.flatnonzero(~months.duplicated())[:3] + start).tolist()
    else:
        eligible = np.flatnonzero(signal.to_numpy()[start - 1:end - 1])
        entry = start + int(eligible[0]) if len(eligible) else None
        if deadline is not None and (entry is None or entry > start + deadline):
            entry = min(start + deadline, end - 1)
        entries = [] if entry is None else [entry]
    cash, qty = CAPITAL, 0
    equity = []
    first = None
    order_count = 0
    for i in range(start, end):
        if i in entries:
            one_price = data.high.iloc[i] == data.low.iloc[i]
            blocked = one_price and data.open.iloc[i] / data.close.iloc[i - 1] - 1 >= .097
            if blocked:
                if i + 1 < end:
                    entries.append(i + 1)
            else:
                execution = float(data.open.iloc[i]) * (1 + slippage)
                budget = min(cash, CAPITAL / 3) if installments else cash
                units = int(budget / execution // 100) * 100
                while units and units * execution + max(5., units * execution * .0001) > budget:
                    units -= 100
                if units:
                    cash -= units * execution + max(5., units * execution * .0001)
                    qty += units
                    first = i if first is None else first
                    order_count += 1
        equity.append(cash + qty * float(data.close.iloc[i]))
    result = stats(np.array(equity), CAPITAL, data.index[start:end], order_count)
    result['wait_days'] = (data.index[first] - data.index[start]).days if first is not None else None
    result['never_entered'] = first is None
    return result


def rolling_entries(data, start, horizon):
    positions = np.arange(start, len(data))
    positions = positions[~data.index[start:].to_period('M').duplicated()]
    positions = positions[positions + horizon <= len(data)]
    rules = entry_signals(data.close)
    rules['分三个月等额买入'] = (pd.Series(True, index=data.index), None)
    observations = []
    for pos in positions:
        baseline = entry_backtest(data, rules['立即买入'][0], pos, pos + horizon)
        for name, (signal, deadline) in rules.items():
            row = entry_backtest(data, signal, pos, pos + horizon, deadline, name == '分三个月等额买入')
            observations.append({'start': str(data.index[pos].date()), 'rule': name, **row,
                                 'excess_pct': round(row['return_pct'] - baseline['return_pct'], 2)})
    result = {}
    for name in rules:
        rows = [r for r in observations if r['rule'] == name]
        waits = [r['wait_days'] for r in rows if r['wait_days'] is not None]
        result[name] = {
            'windows': len(rows),
            'median_return_pct': round(float(np.median([r['return_pct'] for r in rows])), 2),
            'worst_return_pct': min(r['return_pct'] for r in rows),
            'median_drawdown_pct': round(float(np.median([r['max_drawdown_pct'] for r in rows])), 2),
            'median_excess_pct': round(float(np.median([r['excess_pct'] for r in rows])), 2),
            'beat_immediate_pct': round(sum(r['excess_pct'] > 0 for r in rows) / len(rows) * 100, 1),
            'never_entered_pct': round(sum(r['never_entered'] for r in rows) / len(rows) * 100, 1),
            'median_wait_days_if_entered': round(float(np.median(waits)), 1) if waits else None,
        }
    return result, observations


def write_report(results):
    lines = ['# 美股ETF继续研究：持仓规则与新资金买点', '',
             '研究数据截至2026-09-30。标普500使用博时513500，纳指100使用国泰513100；均为腾讯前复权人民币场内价格。',
             '共同比较从2015-03-02开始，所有候选都有足够预热数据。此前初步报告从2015年1月开始，数字不能直接混用。',
             '主候选在运行前固定：持有、10个月均线、±2%缓冲、连续两月确认、线下减半、12个月动量；8/12个月均线仅做参数敏感性检查。没有从大网格挑最佳参数。', '',
             '## 固定评价方法', '',
             '初始10万元，无新增资金；100份整数，万一佣金最低5元，买卖单边0.1%滑点。现金收益为0，末日不强制清仓。',
             '前一日收盘信号，下一交易日开盘执行；涨跌停只按一字10%限制近似，拦住的交易次日重试。未模拟临时停牌、盘中波动或排队。',
             '只在目标风险敞口改变时交易，不每天再平衡。“初始50%投入后持有”仅在起点买半份本金，之后比例自然漂移，用来识别少投入资金带来的风险降低，不是固定仓位建议。',
             '月均线使用已结束月份；沿用App的保守时点：月末不是交易日时，等待新月份第一根行情确认，再在下一交易日执行。',
             '年化收益为日历时间复合收益；最大回撤为收盘账户净值，含初始本金。月度状态决定持仓敞口，绝不代表每日重复买卖。', '',
             '## 持仓风控比较', '',
             '|ETF|规则|累计收益|年化收益|最大回撤|买卖次数|',
             '|---|---|---:|---:|---:|---:|']
    for code, result in results.items():
        for name, rule in result['rules'].items():
            row = rule['full']
            lines.append(f"|{code}|{name}|{row['return_pct']}%|{row['annualized_pct']}%|{row['max_drawdown_pct']}%|{row['trades']}|")
    lines += ['', '## 不同阶段与交易成本', '',
              '两段均从现金重启；规则未根据前段结果调整，但已经看过同一历史，后段不能声称独立样本外。',
              '|ETF|规则|2015—2020收益/回撤|2021—2026收益/回撤|滑点加倍收益|1000元起投收益|',
              '|---|---|---:|---:|---:|---:|']
    for code, result in results.items():
        for name, rule in result['rules'].items():
            a, b = rule['2015_2020'], rule['2021_2026']
            lines.append(f"|{code}|{name}|{a['return_pct']}% / {a['max_drawdown_pct']}%|{b['return_pct']}% / {b['max_drawdown_pct']}%|{rule['double_cost']['return_pct']}%|{rule['small_capital']['return_pct']}%|")
    lines += ['', '## 新资金入场比较', '',
              '每个观察窗都只有同一笔10万元，起止时间相同；入场后持有至窗口末尾，隔离“买点”效果，不和持仓退出规则混测。',
              '从每月第一个交易日起算，分别观察250和750交易日，约一年和三年。观察窗大量重叠，不是独立样本，优胜比例不是未来胜率。',
              '“回撤”指价格低于过去250交易日最高收盘价的幅度，不是从投入日再跌多少。“最多三个月”近似为最多63交易日，期限到了即买，不无限等待。',
              '三个月分批用同笔本金分三份，在起点及下两个月首个交易日买入，不是持续追加本金的定投。',
              '中位相对收益为每个窗口“该方案累计收益减立即买入累计收益”的中位数；不是两个中位数直接相减。空仓窗口收益为0，也纳入统计。', '']
    for horizon in ('250', '750'):
        lines += [f'### {horizon}交易日观察窗', '',
                  '|ETF|入场规则|窗口数|收益中位数|最差收益|相对立即买入中位差|优于立即买入的窗口占比|一直未买入占比|已入场窗口等待天数中位数|',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for code, result in results.items():
            for name, row in result['entry'][horizon].items():
                lines.append(f"|{code}|{name}|{row['windows']}|{row['median_return_pct']}%|{row['worst_return_pct']}%|{row['median_excess_pct']}个百分点|{row['beat_immediate_pct']}%|{row['never_entered_pct']}%|{row['median_wait_days_if_entered']}|")
    lines += ['', '## 结论与下一步', '',
              '1. 本样本没有证明简单均线退出优于长期持有。缓冲、两月确认与减半只是不同的风险/收益取舍，不能称最佳买卖点。',
              '2. 等待重新上穿是持仓切换信号，不应机械地成为所有新资金唯一买入日。长期在线上的市场会让新资金错过上涨。',
              '3. 等大回撤存在明显机会成本；5%/10%等待与有限期分批也没有稳定胜出，不能照搬A股宽基的低位等待策略。',
              '4. 当前数据不足以验证五个决策或最优配比。先把新资金的入场许可与已有持仓的卖出判断分开研究；不凭这次结果自动替换App策略或设定加仓/减仓阈值。', '',
              '## 数据与推论边界', '',
              '这是国内ETF的人民币交易价研究，包含汇率、溢价、跟踪偏差。不是标普500/纳指100美元指数的纯策略回测，也不是华夏159655的直接测试。',
              '管理/托管费用已经影响实际ETF价格和净值，不再重复扣减；前复权不能精确重现实际分红现金与历史份数。',
              '没有完整历史同步净值，不能把场内溢价的涨跌当成指数涨跌，也不能回测“溢价低于某值才买”。当前溢价公告未倒灌到历史信号。',
              '本轮尝试获取更早美股ETF与FRED指数数据未获得可用文件；现有样本不含2000年科技泡沫和2008年金融危机。不能推断长期持有在所有周期风险都小。',
              '没有点时可见、覆盖同周期的美国估值历史，不构造PE/CAPE择时结论。没有轮动组合收益回测，单只结果不能证明配比最优。', '',
              '## 参考来源', '',
              '- [Meb Faber原作者月度趋势模型与FAQ](https://mebfaber.com/timing-model/)：趋势状态与持仓敞口，月度更新；并非新资金只能在重新上穿时进入。',
              '- [Vanguard 2023：一次投入与分批投入](https://corporate.vanguard.com/content/dam/corp/research/pdf/cost_averaging_invest_now_or_temporarily_hold_your_cash.pdf)：同笔资金分批与等待现金的机会成本，不证明某ETF当前适合买。',
              '- [AQR：A Century of Evidence on Trend-Following Investing](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf)：跨市场、跨资产研究，不能直接当作单只国内美股ETF均线有效的证据。', '',
              '复现：python -B research_us_etf_extended.py；详细结果、逐笔交易与曲线保存在results/us_etf_extended/。生产买卖策略及配比规则未改。']
    report = '\n'.join(lines) + '\n'
    Path('us_etf_strategy_extended_research.md').write_text(report, encoding='utf-8')
    Path('results/us_etf_extended/report.md').write_text(report, encoding='utf-8')


def main():
    output = Path('results/us_etf_extended')
    output.mkdir(parents=True, exist_ok=True)
    all_results = {}
    for code in ('513500', '513100'):
        data = load(code)
        start = int(data.index.searchsorted(START))
        split = int(data.index.searchsorted('2021-01-01'))
        rules = candidates(data.close)
        if not np.array_equal(rules['10个月均线全进全出'].to_numpy().astype(bool), original_targets(data.close).to_numpy()):
            raise AssertionError('与原策略不一致')
        result = {'history_start': str(data.index[0].date()), 'start': str(data.index[start].date()),
                  'end': str(data.index[-1].date()), 'split': str(data.index[split].date()), 'rules': {}, 'entry': {}}
        for name, target in rules.items():
            full, curve, trades = exposure_backtest(data, target, start, len(data))
            curve.to_csv(output / f'{code}_{name}_curve.csv')
            result['rules'][name] = {
                'full': full,
                '2015_2020': exposure_backtest(data, target, start, split)[0],
                '2021_2026': exposure_backtest(data, target, split, len(data))[0],
                'double_cost': exposure_backtest(data, target, start, len(data), slippage=.002)[0],
                'small_capital': exposure_backtest(data, target, start, len(data), initial=1000.)[0],
                'trades': trades,
            }
        for horizon in (250, 750):
            # 回撤观察窗需要250日预热，避免首个窗口缺指标。
            summary, observations = rolling_entries(data, max(start, 250), horizon)
            result['entry'][str(horizon)] = summary
            pd.DataFrame(observations).to_csv(output / f'{code}_entry_{horizon}.csv', index=False)
        all_results[code] = result
        print(code, 'rules', {k: v['full'] for k, v in result['rules'].items()})
        print(code, 'entry_750', result['entry']['750'])
    (output / 'results.json').write_text(json.dumps(all_results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write_report(all_results)


if __name__ == '__main__':
    main()
