"""沪深300逐月起点比较；预先固定规则，不按窗口结果调参。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_broad_valuation import load, signal_frame, simulate
from research_broad_individual import execute
from broad_signal_rules import valuation_positions


def windows(prices, ready, years):
    """月内首个可比较交易日开始；只保留完整日历期限。"""
    eligible = prices.index[ready.shift(1, fill_value=False)]
    starts = pd.Series(eligible, index=eligible).groupby(eligible.to_period('M')).first()
    result = []
    for date in starts:
        anniversary = date + pd.DateOffset(years=years)
        if anniversary > prices.index[-1]:
            continue
        start = int(prices.index.get_loc(date))
        end = int(prices.index.searchsorted(anniversary, side='right'))
        result.append((start, end))
    return result


def aggregate(rows, model, baseline):
    pairs = [(r['models'][model], r['models'][baseline]) for r in rows]
    profit = np.array([a['profit_on_contributions_pct'] for a, _ in pairs])
    excess = np.array([a['profit_on_contributions_pct']-b['profit_on_contributions_pct'] for a,b in pairs])
    dd = np.array([a['max_drawdown_pct'] for a, _ in pairs])
    better_dd = np.array([a['max_drawdown_pct'] > b['max_drawdown_pct'] for a,b in pairs])
    return {'windows': len(rows), 'median_profit_pct': round(float(np.median(profit)), 2),
            'median_excess_profit_pp': round(float(np.median(excess)), 2),
            'worst_profit_pct': round(float(profit.min()), 2),
            'median_drawdown_pct': round(float(np.median(dd)), 2),
            'worst_drawdown_pct': round(float(dd.min()), 2),
            'return_win_pct': round(float((excess>0).mean()*100), 1),
            'joint_win_pct': round(float(((excess>0)&better_dd).mean()*100), 1)}


def main():
    prices, history, hashes = load('510300', '000300')
    frame = signal_frame(prices, history, 5)
    targets = {
        'simple_value': valuation_positions(frame.percentile, prices.close),
        'current': valuation_positions(frame.percentile, prices.close, confirm_exit=True),
        'hold': pd.Series(1., index=prices.index)}
    output = {'hashes': hashes, 'cutoff': str(prices.index[-1].date()), 'periods': {}}
    for years in (1, 3, 5):
        rows = []
        for start, end in windows(prices, frame.ready, years):
            models = {}
            for funding in ('fixed', 'monthly'):
                for name, target in targets.items():
                    stats, _, _ = execute(prices, target, start, end, monthly=1000. if funding=='monthly' else None)
                    models[f'{funding}_{name}'] = stats
                stats, _, _ = simulate(prices, frame, start, end, funding=funding)
                models[f'{funding}_original'] = stats
            rows.append({'start': str(prices.index[start].date()), 'end': str(prices.index[end-1].date()), 'models': models})
        summaries = {f'{funding}_{name}': aggregate(rows, f'{funding}_{name}', f'{funding}_hold')
                     for funding in ('fixed', 'monthly') for name in targets.keys() | {'original'}}
        output['periods'][str(years)] = {'rows': rows, 'summary': summaries}
        print(years, len(rows), summaries, flush=True)
    out = Path('results/csi300_entry_windows')
    out.mkdir(parents=True, exist_ok=True)
    (out/'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    report = ['# 沪深300：不同入场时间的比较', '',
              '行情截至2026-09-30；逐月起点，固定1/3/5年期限，仅保留完整窗口。每个窗口账户从现金开始。', '',
              '固定资金10万元，或每月首个交易日入金1000元，分开比较。固定资金基准为立即买入持有，月度资金基准为普通定投。', '',
              '原版：5年PE与250日高点回撤结合，买入半份、加仓余款、高估减仓/退出。简化估值：PE分位低于30%允许买入、至少90%退出。当前：低于30%允许买入，至少90%且跌到60日均价或下方退出。后两者买入许可使用全部可用现金；许可状态可由起点前已发生的信号延续，不读取实际仓位。', '',
              '比较收益使用累计利润/累计入金，回撤使用排除入金影响的份额化净值。表中同时胜出必须收益严格更高、回撤严格更小；平局不算。', '',
              '沿用次日开盘、100份整数、万一佣金最低5元、单边0.1%滑点，现金收益0。前复权近似，PE无历史发布/修订版本；规则与历史此前已看过，属于回顾性检验。重叠窗口不独立，比例不是未来胜率。无参数搜索、无生产规则修改。', '']
    labels = {'hold':'持有/普通定投', 'original':'原版价格＋估值', 'simple_value':'单纯估值', 'current':'当前估值＋退出确认'}
    for years, period in output['periods'].items():
        report += [f'## {years}年期限（{len(period["rows"])}个起点）', '',
                   '|资金方式|策略|利润率中位数|相对基准利润差中位数|回撤中位数|最差回撤|收益胜出起点|两项同时胜出|',
                   '|---|---|---:|---:|---:|---:|---:|---:|']
        for funding in ('fixed', 'monthly'):
            for name in labels:
                s = period['summary'][f'{funding}_{name}']
                report.append(f'|{"固定资金" if funding=="fixed" else "每月1000元"}|{labels[name]}|{s["median_profit_pct"]}%|{s["median_excess_profit_pp"]}个百分点|{abs(s["median_drawdown_pct"])}%|{abs(s["worst_drawdown_pct"])}%|{s["return_win_pct"]}%|{s["joint_win_pct"]}%|')
        report.append('')
    report += ['逐月完整明细、资金收益率XIRR、最差利润率与数据哈希见 results/csi300_entry_windows/results.json。', '', '复现：python -B research_csi300_entry_windows.py。']
    Path('csi300_entry_windows_research.md').write_text('\n'.join(report)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
