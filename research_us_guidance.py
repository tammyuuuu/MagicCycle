"""可操作美股规则研究：长期方向、短期过热；不按收益排名自动挑参数。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_us_etf_extended import load, monthly_state, stats
from research_sector_partial_exit import backtest_partial
from us_guidance import guidance_frame


def momentum(close, window=12):
    monthly = close.resample('ME').last()
    monthly = monthly.loc[monthly.index <= close.index[-1]]
    change = monthly.pct_change(window, fill_method=None)
    return change.reindex(close.index, method='ffill')


def heat_stages(close, threshold=.15, cooling=.05, window=60, recovery=False):
    deviation = close / close.rolling(window, min_periods=window).mean() - 1
    heated = False
    stages = []
    ma20 = close.rolling(20, min_periods=20).mean()
    for i, value in enumerate(deviation):
        if np.isfinite(value):
            if value <= cooling and (not recovery or close.iloc[i] > ma20.iloc[i]):
                heated = False
            if value >= threshold:
                heated = True
        stages.append(heated)
    return pd.DataFrame({'heated': stages, 'deviation': deviation}, index=close.index)


def candidates(close):
    direction = momentum(close) > 0
    rules = {'长期持有': pd.Series(1., index=close.index),
             '10个月均线': monthly_state(close),
             '12个月涨幅方向': direction.astype(float)}
    for threshold in (.10, .15, .20):
        heated = heat_stages(close, threshold).heated
        rules[f'12个月方向+{int(threshold*100)}%过热减半'] = direction.astype(float) * np.where(heated, .5, 1.)
    heated = heat_stages(close).heated
    rules['长期持有+15%过热减半'] = pd.Series(np.where(heated, .5, 1.), index=close.index)
    rules['10个月均线+15%过热减半'] = monthly_state(close) * np.where(heated, .5, 1.)
    rules['12个月方向+15%过热减四分之一'] = direction.astype(float) * np.where(heated, .75, 1.)
    for threshold in (.10, .15, .20):
        frame = guidance_frame(close, heat_threshold=threshold)
        rules[f'12个月方向+{int(threshold*100)}%过热+短期确认'] = frame.target
    return rules


def index_backtest(close, target, start, end, slippage=.001, entry_allowed=None):
    """指数机制检验：前日信号，次日收盘交易，连续份额、单边万一佣金。"""
    cash, qty, stage = 100000., 0., 0.
    prices, desired = close.to_numpy(), target.to_numpy()
    eligible = np.ones(len(close), dtype=bool) if entry_allowed is None else entry_allowed.to_numpy(dtype=bool)
    equity, exposures, orders = [], [], 0
    for i in range(start, end):
        weight = float(desired[i - 1])
        price = float(prices[i])
        nav = cash + qty * price
        if weight == 1 and stage != 1 and eligible[i - 1]:
            execution = price * (1 + slippage)
            bought = cash / (execution * 1.0001)
            cash -= bought * execution * 1.0001
            qty += bought
            orders += bool(bought > 0)
            stage = 1. if qty else 0.
        elif weight == 0 and qty:
            sold = qty
            execution = price * (1 - slippage)
            cash += sold * execution * .9999
            qty -= sold
            orders += bool(sold > 0)
            stage = 0.
        elif 0 < weight < 1 and qty and stage == 1:
            sold = qty * (1 - weight)
            execution = price * (1 - slippage)
            cash += sold * execution * .9999
            qty -= sold
            orders += bool(sold > 0)
            stage = weight
        nav = cash + qty * price
        equity.append(nav)
        exposures.append(qty * price / nav)
    return stats(np.array(equity), 100000., close.index[start:end], int(orders), exposures)


def write_report(results):
    chosen = '12个月方向+15%过热+短期确认'
    lines = ['# 美股ETF：可操作的风险管理指导规则', '',
             '2026-10-04研究，所有行情截到2026-09-30。生产版本us_momentum_heat_v2。', '',
             '## 本轮落地规则', '',
             '|动作|条件与执行|', '|---|---|',
             '|买入|最近完整月份的过去12个月涨幅＞0，未处于过热阶段，价格高于20日均价。本期新资金可买；已有持仓不重复买。|',
             '|加仓|长期方向向上；过热后偏离降至5%以内，且价格高于20日均价，解除当日可加大本期投入。未持有也可买。|',
             '|观察|过热尚未解除、短期价格未恢复、数据不足或行情更新受限；先不新增资金。20日均价仅是买入确认，不单独触发已有持仓退出。|',
             '|减仓|长期方向向上时，首次达到高于60日均价15%，卖出已有份数的一半，仅一次；未持有不买。|',
             '|退出|最近完整月份的过去12个月涨幅≤0，退出已有持仓；数据不足不当作转弱。|', '',
             '月度方向需要13个连续完整月份；缺一个月先观察。月末非交易日时采用现有App的保守确认时点，不提前读取未来月收盘。',
             '过热状态不会在偏离刚跌回15%以下就消失；需偏离≤5%且价格高于20日均价。单纯下跌导致偏离缩小不算加仓，防止机械接下跌。',
             '月度方向转弱优先退出；同期溢价公告阻止新资金买入，但不掩盖减仓、退出。公告只用于同日期行情，不伪造历史或实时溢价率。',
             '每日收盘判断，下一交易日执行。信号不读取持仓比例、成本、收益或日记；实际买卖份数由用户决定。', '',
             '## 为什么采用这个版本', '',
             '原10个月均线只有重新上穿当天提示买入，持续在线上的新资金长期等待；现在把新资金入场许可与持仓卖出规则分开。',
             '较长指数样本显示，持续下跌需要防守；近十多年人民币ETF样本又显示，频繁均线进出容易错过上涨。12个月方向减少切换，过热阶段控制追涨，再用短期价格确认恢复。',
             '这是一套能一致执行的风险管理型试行，不是收益最高策略，也未证明优于所有替代方案。15%与5%是解释清晰的研究假设；同时比较10%/20%敏感性，未宣称最优参数。', '',
             '## 与旧策略和持有基准对比', '',
             '|数据与区间|规则|年化收益|最大回撤|买卖次数|', '|---|---|---:|---:|---:|']
    for code, result in results.items():
        for name in ('长期持有', '10个月均线', chosen):
            row = result['rules'][name]['full']
            lines.append(f"|{code} · {result['start']}—{result['end']}|{name}|{row['annualized_pct']}%|{row['max_drawdown_pct']}%|{row['trades']}|")
    lines += ['', '不能只展示支持新规则的部分：标普较长指数样本中，新规则年化收益及最大回撤都不优于旧月均线；纳指长期样本中有所改善。',
              '与长期持有相比，新规则在长样本降低大回撤，但付出收益损失；国内标普ETF全样本回撤几乎未改善。它不是稳赚、更不是每个阶段都占优。', '',
              '## 每月换一个起点，观察约三年', '',
              '750交易日观察窗，逐月滚动；各窗独立从同额现金开始，窗口重叠，不是独立样本或未来胜率。',
              '|数据|规则|窗口数|收益中位数|最差收益|回撤中位数|最差回撤|', '|---|---|---:|---:|---:|---:|---:|']
    for code, result in results.items():
        for name, row in result['rolling_750'].items():
            lines.append(f"|{code}|{name}|{row['windows']}|{row['median_return_pct']}%|{row['worst_return_pct']}%|{row['median_drawdown_pct']}%|{row['worst_drawdown_pct']}%|")
    lines += ['', '## 分段检查', '',
              '每段独立从现金开始；所有规则已看过同一历史，不能称独立样本外。',
              '|数据|实际区间|规则|累计收益|最大回撤|', '|---|---|---|---:|---:|']
    for code, result in results.items():
        for name in ('长期持有', '10个月均线', chosen):
            for period, row in result['rules'][name]['periods'].items():
                lines.append(f"|{code}|{period}|{name}|{row['return_pct']}%|{row['max_drawdown_pct']}%|")
    lines += ['', '## 参数和费用敏感性', '',
              '|数据|规则|年化收益|最大回撤|单边滑点加倍累计收益|1000元起投累计收益|', '|---|---|---:|---:|---:|---:|']
    for code, result in results.items():
        for name in ('12个月方向+10%过热+短期确认', chosen, '12个月方向+20%过热+短期确认'):
            row = result['rules'][name]
            small = str(row['small_capital']['return_pct']) + '%' if 'small_capital' in row else '指数机制检验不模拟小额份数'
            lines.append(f"|{code}|{name}|{row['full']['annualized_pct']}%|{row['full']['max_drawdown_pct']}%|{row['double_cost']['return_pct']}%|{small}|")
    lines += ['', '详细结果还包含单独动量、单独过热减仓、取消恢复确认及减四分之一等对照。没有只保存排名第一的结果。', '',
              '## 研究执行口径与边界', '',
              '- 国内ETF：513500与513100腾讯前复权人民币场内价格，2015-03-02起；10万元，100份整数，万一佣金最低5元，单边0.1%滑点，前日信号次日开盘，近似一字10%涨跌停限制，末日不强制平仓。',
              '- 减仓严格按已有份数减一次，而非每天维持半仓；同一阶段不重复卖，冷却确认后只投入可用现金。空仓处于过热阶段不买所谓半仓。不同资金规模会受最低佣金和一手限制影响。',
              '- 指数机制：纳指FRED/Nasdaq从1987-03-02评价，覆盖科技泡沫；标普新浪指数从2005-03-01评价，覆盖金融危机、未覆盖科技泡沫。不是两指数共同起点，不可直接比较累计收益。',
              '- 纳指只有每日收盘价，所有指数统一前日信号次日收盘执行；连续份额，万一佣金、单边0.1%滑点，没有ETF一手限制。指数不可直接交易；不含股息、汇率、基金费和溢价，数字不是可获得的基金收益。',
              '- 现金利息为0。ETF价格已反映管理费影响，不重复扣费；前复权无法精确重建历史分红现金。未模拟临时停牌、盘中排队或交易时真实价差。',
              '- 纳指FRED与新浪重合3173日收盘价相对差异中位数约0.0000043%，最大约0.73%；长期纳指采用官方FRED来源，未拼接两源或修改异常日期。',
              '- 研究含过去历史回顾和候选比较，不是预先注册或独立样本外验证。新策略仍可能承受超过30%—40%的回撤，不能视为止损保证。',
              '- 建议配比的半份/一份是本期新预算分配规则，不是上述单只基金持仓回测的仓位，也没有证明是最优组合配比。',
              '- 当前生产信号使用国内ETF价格，因此包含溢价、汇率影响。没有全历史同步净值，尚不能回测可靠的数值溢价过滤；现有公告是定日快照。', '',
              '## 来源与复现', '',
              '- [FRED / Nasdaq：NASDAQ-100每日收盘价](https://fred.stlouisfed.org/series/NASDAQ100)，长期表从1986年开始，预热后评价。',
              '- [新浪标普500指数行情](https://stock.finance.sina.com.cn/usstock/quotes/.INX.html)，缓存从2004年开始。',
              '- [AQR：A Century of Evidence on Trend-Following Investing](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf)：跨市场趋势研究，支持研究框架，不背书本App单只ETF或15%/5%参数。',
              '- [Meb Faber趋势模型FAQ](https://mebfaber.com/timing-model/)：旧月均线基准和收益/风险取舍。', '',
              '复现：python -B research_us_guidance.py；生产与候选共用us_guidance.guidance_frame，原始/完整结果保存在results/us_guidance/results.json。']
    report = '\n'.join(lines) + '\n'
    Path('us_etf_guidance_research.md').write_text(report, encoding='utf-8')
    Path('results/us_guidance/report.md').write_text(report, encoding='utf-8')


def main():
    results = {}
    sources = [
        ('513500', load('513500'), '2015-03-01', 'ETF'),
        ('513100', load('513100'), '2015-03-01', 'ETF'),
    ]
    for code, filename, start in (
        ('SP500指数', 'data_cache/us_inx_sina.csv', '2005-03-01'),
        ('NASDAQ100指数', 'data_cache/us_nasdaq100_fred.csv', '1987-03-01'),
    ):
        data = pd.read_csv(filename, index_col='date', parse_dates=True)
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index().loc[:'2026-09-30']
        if data.index.has_duplicates or not np.isfinite(data.close).all() or (data.close <= 0).any():
            raise ValueError('指数价格无效 ' + code)
        sources.append((code, data, start, 'index'))
    for code, data, beginning, kind in sources:
        start = int(data.index.searchsorted(beginning))
        rules = candidates(data.close)
        results[code] = {'start': str(data.index[start].date()), 'end': str(data.index[-1].date()), 'kind': kind, 'rules': {}}
        for name, target in rules.items():
            entry_allowed = None
            if name.endswith('过热+短期确认'):
                threshold = int(name.split('+')[1].split('%')[0]) / 100
                entry_allowed = guidance_frame(data.close, heat_threshold=threshold).entry_allowed
            def run(a, b, **kw):
                if kind == 'ETF':
                    if 'initial' in kw:
                        kw['initial_cash'] = kw.pop('initial')
                    result, curve, _ = backtest_partial(data, target, a, b, entry_allowed=entry_allowed, limit_pct=.10, **kw)
                    result.update(stats(curve.equity.to_numpy(), kw.get('initial_cash', 100000.), curve.index, result['trades']))
                    return result
                return index_backtest(data.close, target, a, b, entry_allowed=entry_allowed, **kw)
            row = {'full': run(start, len(data)), 'double_cost': run(start, len(data), slippage=.002), 'periods': {}}
            for a, b in (('1987-03-01', '1999-12-31'), ('2000-01-01', '2009-12-31'), ('2010-01-01', '2019-12-31'), ('2020-01-01', '2026-09-30')):
                first = max(start, int(data.index.searchsorted(a)))
                last = int(data.index.searchsorted(b, side='right'))
                if last - first >= 250:
                    row['periods'][f'{data.index[first].date()}—{data.index[last-1].date()}'] = run(first, last)
            if kind == 'ETF':
                row['small_capital'] = run(start, len(data), initial=1000.)
            results[code]['rules'][name] = row
        result = results[code]
        result['rolling_750'] = {}
        monthly_positions = np.arange(start, len(data))[~data.index[start:].to_period('M').duplicated()]
        positions = monthly_positions[monthly_positions + 750 <= len(data)]
        for name in ('长期持有', '10个月均线', '12个月方向+15%过热+短期确认'):
            target = rules[name]
            eligible = guidance_frame(data.close).entry_allowed if name.endswith('短期确认') else None
            rows = []
            for pos in positions:
                if kind == 'ETF':
                    metrics = backtest_partial(data, target, pos, pos+750, entry_allowed=eligible, limit_pct=.10)[0]
                else:
                    metrics = index_backtest(data.close, target, pos, pos+750, entry_allowed=eligible)
                rows.append({'start': str(data.index[pos].date()), **metrics})
            result['rolling_750'][name] = {'windows': len(rows),
                'median_return_pct': round(float(np.median([r['return_pct'] for r in rows])), 2),
                'worst_return_pct': min(r['return_pct'] for r in rows),
                'median_drawdown_pct': round(float(np.median([r['max_drawdown_pct'] for r in rows])), 2),
                'worst_drawdown_pct': min(r['max_drawdown_pct'] for r in rows)}
        print(code, {n: x['full'] for n, x in results[code]['rules'].items()}, flush=True)
    output = Path('results/us_guidance')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write_report(results)


if __name__ == '__main__':
    main()
