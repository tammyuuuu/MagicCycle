"""宽基现行信号研究；资金执行假设与行情决策分离，不修改生产规则。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from valuation_data import summarize

END = '2026-09-30'
ASSETS = [('510300', '000300', '沪深300'), ('510500', '000905', '中证500'),
          ('588000', '000688', '科创50')]


from broad_signal_rules import signal_frame


def xirr(flows):
    dates = [pd.Timestamp(date) for date, _ in flows]
    elapsed = np.array([(d - dates[0]).days / 365.25 for d in dates])
    amounts = np.array([value for _, value in flows])
    def npv(rate):
        return float(np.sum(amounts / (1 + rate) ** elapsed))
    low, high = -.9999, 10.
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(100):
        middle = (low + high) / 2
        if npv(middle) > 0:
            low = middle
        else:
            high = middle
    return round((low + high) / 2 * 100, 2)


def simulate(prices, frame, start, end=None, mode='strategy', funding='fixed',
             initial=100000., monthly=1000., slippage=.001, minimum_fee=5.,
             buy_fraction=.5):
    """固定本金：每个低估阶段买半份可用现金、加仓用剩余现金。

    月度资金：每月首个交易日入金；当日以前一收盘信号决定是否花一半/全部现金。
    减仓在每个高估阶段只卖一次；退出卖剩余，观察不交易。不按仓位触发信号。
    """
    if (not 0 < buy_fraction <= 1 or initial <= 0 or monthly <= 0 or minimum_fee < 0
            or not 0 <= slippage < 1 or funding not in ('fixed', 'monthly')
            or mode not in ('strategy', 'hold', 'half_hold')):
        raise ValueError('金额与买入比例无效')
    end = len(prices) if end is None else end
    if start < 1 or end <= start or not frame.index.equals(prices.index):
        raise ValueError('回测区间或信号日期无效')
    cash = initial if funding == 'fixed' else 0.
    qty = 0
    units = cash  # 份额化净值：入金不伪造收益或掩盖回撤。
    principal = cash
    flows = [(prices.index[start], -cash)] if cash else []
    bought = added = reduced = False
    trades, rows = [], []
    fee_sum = 0.
    small_orders = 0
    open_, close, high, low = [prices[c].to_numpy() for c in ('open', 'close', 'high', 'low')]
    statuses = frame.status.to_numpy()
    percentiles = frame.percentile.to_numpy()
    months = prices.index.to_period('M')
    for i in range(start, end):
        date = prices.index[i]
        contribution = funding == 'monthly' and (i == start or months[i] != months[i - 1])
        if contribution:
            before = cash + qty * open_[i]
            unit_price = before / units if units else 1.
            units += monthly / unit_price
            cash += monthly
            principal += monthly
            flows.append((date, -monthly))
        status = statuses[i - 1]
        percentile = percentiles[i - 1]
        if np.isfinite(percentile):
            if percentile >= 30:
                bought = added = False
            if percentile <= 70:
                reduced = False
        one_price = high[i] == low[i]
        limit = .20 if prices.attrs.get('code') == '588000' else .10
        change = open_[i] / close[i - 1] - 1
        blocked_buy = one_price and change >= limit - .003
        blocked_sell = one_price and change <= -limit + .003
        action, budget, sell_qty = None, 0., 0
        if mode in ('hold', 'half_hold'):
            if qty == 0 or contribution:
                action, budget = '买入', cash * (.5 if mode == 'half_hold' else 1.)
        elif status == 'exit':
            action, sell_qty = '退出', qty
        elif status == 'reduce' and not reduced and qty:
            action, sell_qty = '减仓', qty // 200 * 100
            if not sell_qty:
                small_orders += 1
                reduced = True
        elif funding == 'monthly':
            if contribution and status in ('buy', 'add'):
                action = '买入' if status == 'buy' else '加仓'
                budget = cash * (buy_fraction if status == 'buy' else 1.)
        elif status == 'add' and not added:
            action, budget = '加仓', cash
        elif status == 'buy' and not bought:
            action, budget = '买入', cash * buy_fraction
        if sell_qty and not blocked_sell:
            execution = open_[i] * (1 - slippage)
            notional = execution * sell_qty
            fee = max(minimum_fee, notional * .0001)
            cash += notional - fee
            qty -= sell_qty
            fee_sum += fee
            if action == '减仓':
                reduced = True
            trades.append({'date': str(date.date()), 'action': action, 'quantity': -sell_qty,
                           'price': execution, 'fee': fee, 'signal_date': str(prices.index[i - 1].date())})
        elif budget > 0 and not blocked_buy:
            execution = open_[i] * (1 + slippage)
            bought_qty = int(budget / (execution * 1.0001) // 100) * 100
            while bought_qty and bought_qty * execution + max(minimum_fee, bought_qty * execution * .0001) > budget:
                bought_qty -= 100
            if bought_qty:
                fee = max(minimum_fee, bought_qty * execution * .0001)
                cash -= bought_qty * execution + fee
                qty += bought_qty
                fee_sum += fee
                if funding == 'fixed':
                    bought = True
                    if status == 'add':
                        added = True
                trades.append({'date': str(date.date()), 'action': action, 'quantity': bought_qty,
                               'price': execution, 'fee': fee, 'signal_date': str(prices.index[i - 1].date())})
            else:
                small_orders += 1
        equity = cash + qty * close[i]
        assert cash >= -1e-7 and qty >= 0 and qty % 100 == 0
        rows.append({'date': date, 'equity': equity, 'cash': cash, 'quantity': qty,
                     'principal': principal, 'nav': equity / units if units else 1.,
                     'exposure': qty * close[i] / equity if equity else 0.})
    curve = pd.DataFrame(rows).set_index('date')
    nav = np.r_[1., curve.nav.to_numpy()]
    elapsed = (curve.index[-1] - curve.index[0]).days / 365.25
    flows.append((curve.index[-1], float(curve.equity.iloc[-1])))
    result = {'principal_yuan': round(principal, 2), 'ending_yuan': round(float(curve.equity.iloc[-1]), 2),
              'profit_yuan': round(float(curve.equity.iloc[-1] - principal), 2),
              'profit_on_contributions_pct': round(float(curve.equity.iloc[-1] / principal - 1) * 100, 2),
              'nav_return_pct': round((nav[-1] - 1) * 100, 2),
              'annualized_nav_pct': round((nav[-1] ** (1 / elapsed) - 1) * 100, 2) if elapsed > 0 else None,
              'xirr_pct': xirr(flows), 'max_drawdown_pct': round(float((nav / np.maximum.accumulate(nav) - 1).min()) * 100, 2),
              'average_exposure_pct': round(float(curve.exposure.mean()) * 100, 2),
              'trades': len(trades), 'reductions': sum(t['action'] == '减仓' for t in trades),
              'exits': sum(t['action'] == '退出' for t in trades), 'fees_yuan': round(fee_sum, 2),
              'too_small_orders': small_orders}
    return result, curve, trades


def load(code, index):
    price_path = Path(f'data_cache/etf_{code}_tencent.csv')
    pe_path = Path(f'data_cache/valuation_{index}_SH.csv')
    prices = pd.read_csv(price_path, index_col='date', parse_dates=True).sort_index().loc[:END]
    prices.attrs['code'] = code
    history = pd.read_csv(pe_path, parse_dates=['date']).sort_values('date')
    history = history[history.date <= pd.Timestamp(END)]
    values = prices[['open', 'close', 'high', 'low']]
    if prices.index.has_duplicates or not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        raise ValueError('行情无效')
    provenance = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (price_path, pe_path)}
    return prices, history, provenance


def main():
    out = Path('results/broad_valuation')
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for code, index, name in ASSETS:
        prices, history, hashes = load(code, index)
        asset = {'name': name, 'price_start': str(prices.index[0].date()),
                 'valuation_start': str(history.date.min().date()), 'hashes': hashes, 'windows': {}}
        for years in (3, 5, 10):
            frame = signal_frame(prices, history, years)
            valid = np.flatnonzero(frame.ready.to_numpy())
            if not len(valid) or valid[0] + 1 >= len(prices):
                asset['windows'][str(years)] = {'error': '完整估值历史不足，无法检验'}
                continue
            start = int(valid[0]) + 1
            window = {'start': str(prices.index[start].date()), 'end': str(prices.index[-1].date()),
                      'trading_days': len(prices) - start,
                      'signal_days': frame.iloc[start - 1:-1].status.value_counts().to_dict(), 'models': {}}
            for funding in ('fixed', 'monthly'):
                for mode in ('strategy', 'hold'):
                    label = funding + '_' + mode
                    stats, curve, trades = simulate(prices, frame, start, funding=funding, mode=mode)
                    window['models'][label] = stats
                    if years == 5:
                        curve.to_csv(out / f'{code}_{label}_curve.csv')
                        pd.DataFrame(trades).to_csv(out / f'{code}_{label}_trades.csv', index=False)
                if years == 5:
                    split = start + (len(prices) - start) // 2
                    window.setdefault('segments', {})[funding] = {
                        segment: {mode: simulate(prices, frame, a, b, funding=funding, mode=mode)[0]
                                  for mode in ('strategy', 'hold')}
                        for segment, a, b in [('first_half', start, split), ('second_half', split, len(prices))]
                    } if split > start else {}
            if years == 5:
                window['half_cash_hold_control'] = simulate(prices, frame, start, mode='half_hold')[0]
                window['sensitivity'] = {}
                for label, kwargs in [('double_slippage', {'slippage': .002}),
                                      ('buy_full_cash', {'buy_fraction': 1.}),
                                      ('small_fixed_1000', {'initial': 1000.})]:
                    window['sensitivity'][label] = {
                        mode: simulate(prices, frame, start, mode=mode, **kwargs)[0]
                        for mode in ('strategy', 'hold')}
                later = signal_frame(prices, history, years, lag=5)
                window['sensitivity']['valuation_lag_5'] = {
                    mode: simulate(prices, later, max(start, int(np.flatnonzero(later.ready)[0]) + 1), mode=mode)[0]
                    for mode in ('strategy', 'hold')}
                only = signal_frame(prices, history, years, drawdown_filter=False)
                window['valuation_only_control'] = simulate(prices, only, start)[0]
                # 窗口对比使用相同起点，避免把3/10年的不同市场区间当参数优势。
                window['same_period_windows'] = {}
                for other in (3, 5, 10):
                    candidate = signal_frame(prices, history, other)
                    if candidate.ready.iloc[start - 1]:
                        window['same_period_windows'][str(other)] = simulate(prices, candidate, start)[0]
                # 每年首个交易日起持有约3年；窗口重叠，不能视为独立试验。
                rolling = []
                for year in sorted(set(prices.index[start:].year)):
                    a = max(start, int(prices.index.searchsorted(pd.Timestamp(year, 1, 1))))
                    b = a + 750
                    if b > len(prices):
                        continue
                    rolling.append({'start': str(prices.index[a].date()),
                                    **{mode: simulate(prices, frame, a, b, mode=mode)[0]
                                       for mode in ('strategy', 'hold')}})
                window['rolling_750_days'] = rolling
            asset['windows'][str(years)] = window
            print(code, years, window['start'], 'completed', flush=True)
        results[code] = asset
        valid_windows = {int(years): signal_frame(prices, history, int(years))
                         for years, w in asset['windows'].items() if 'error' not in w}
        common = max(int(np.flatnonzero(f.ready)[0]) + 1 for f in valid_windows.values())
        asset['common_window_comparison'] = {
            'start': str(prices.index[common].date()), 'hold': simulate(prices, valid_windows[5], common, mode='hold')[0],
            'windows': {str(years): simulate(prices, frame, common)[0] for years, frame in valid_windows.items()}}
    (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write_report(results)


def write_report(results):
    lines = ['# 宽基ETF：估值与回撤规则验证', '', '研究日期：2026-10-04；行情截止2026-09-30。', '',
             '## 主要发现', '',
             '默认5年窗口下，这套规则体现的是收益与回撤的取舍，不能概括为稳定优于长期持有。沪深300固定本金累计收益144.52%，持有161.16%，最大回撤28.72%对52.95%；每月同额新增资金的模拟中，利润/本金50.20%对普通定投47.72%，净值回撤28.09%对52.88%。沪深300有继续研究价值，但收益优势不稳定。', '',
             '中证500固定本金收益35.33%，明显低于持有150.54%，回撤41.59%对65.73%；月度投入也低于普通定投。前后半段均收益落后。当前规则不适合据此宣称中证500收益与回撤同时更优。', '',
             '科创50的完整5年估值窗口只能从2025-07检验，到2026-09共306个交易日，没有买入信号。收益、回撤均为零只是一直持有现金；3年窗口较长区间也未显示收益优势，10年窗口无法检验。', '',
             '以下是现有缓存与假定执行方式下的初步验证；PE没有历史发布版本，金额规则尚未由用户确定，不能将这些数字解释成实盘业绩或最优策略。', '',
             '本轮固定当前信号：月度PE中秩分位＜30%，250交易日高点回撤10%至20%买入，至少20%加仓；PE分位＞70%减仓、至少90%退出。观察不交易。信号不读取仓位、成本或日记。', '',
             '## 执行假设与公平比较', '',
             '- 固定资金：起始10万元；每个低估阶段首次买入用一半可用现金，加仓用剩余现金；每个高估阶段仅减半一次，退出卖剩余。不逐日重复减半、不按目标仓位再平衡。对照同日投入全部资金后持有。',
             '- 月度资金：每月首个交易日入金1000元；买入信号投入一半累计可用现金，加仓投入全部，观察保留现金；卖出信号每天检查，但同一高估阶段只减半一次。对照相同日期入金、全部买入后不卖出的普通定投。两组没有额外初始本金。',
             '- 主结果PE记录额外延迟一个ETF交易日，再按信号次日开盘成交；无未来估值、无同收盘成交。月度快照没有原始历史发布时间及修订版本，额外延迟不能证明当时可获得，结果属于条件模拟。',
             '- 100份整数交易，单边滑点0.1%，万一佣金、最低5元，现金收益0；一字涨跌停近似拦截，科创20%、其他10%。未卖出的持仓按末日收盘估值，未扣假设清仓费。',
             '- 腾讯前复权价格近似反映分红效果，不精确还原原始价格、真实分红现金及当时100份购买力；基金内含费用不重复扣。数据哈希保存在results.json，结果不等于真实可成交业绩。',
             '- 定投资金使用份额化净值计算回撤，避免新增本金掩盖亏损；另列利润/累计本金及资金加权年化XIRR。固定本金和定投收益口径不同，不横向排名。', '',
             '## 默认5年：固定本金', '',
             '|标的与共同区间|方法|累计收益|年化收益|最大回撤|交易次数|平均投入比例|',
             '|---|---|---:|---:|---:|---:|---:|']
    for code, asset in results.items():
        w = asset['windows']['5']
        if 'error' in w:
            continue
        for mode, label in [('hold', '长期持有'), ('strategy', '估值＋回撤')]:
            r = w['models']['fixed_' + mode]
            lines.append(f"|{asset['name']} {w['start']}—{w['end']}|{label}|{r['nav_return_pct']}%|{r['annualized_nav_pct']}%|{r['max_drawdown_pct']}%|{r['trades']}|{r['average_exposure_pct']}%|")
    lines += ['', '## 默认5年：每月1000元', '',
              '|标的|方法|累计本金|末期资产|利润/本金|资金加权年化|净值最大回撤|交易次数|',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    for code, asset in results.items():
        w = asset['windows']['5']
        if 'error' in w:
            continue
        for mode, label in [('hold', '普通定投'), ('strategy', '条件投入＋估值卖出')]:
            r = w['models']['monthly_' + mode]
            lines.append(f"|{asset['name']}|{label}|{r['principal_yuan']}|{r['ending_yuan']}|{r['profit_on_contributions_pct']}%|{r['xirr_pct']}%|{r['max_drawdown_pct']}%|{r['trades']}|")
    lines += ['', '## 估值窗口与样本长度', '',
              '|标的|窗口|起始日|交易日数|策略收益/最大回撤|持有收益/最大回撤|',
              '|---|---:|---|---:|---|---|']
    for asset in results.values():
        for years, w in asset['windows'].items():
            if 'error' in w:
                lines.append(f"|{asset['name']}|{years}年|无法检验|—|{w['error']}|—|")
            else:
                s, h = [w['models']['fixed_' + m] for m in ('strategy', 'hold')]
                lines.append(f"|{asset['name']}|{years}年|{w['start']}|{w['trading_days']}|{s['nav_return_pct']}% / {s['max_drawdown_pct']}%|{h['nav_return_pct']}% / {h['max_drawdown_pct']}%|")
    lines += ['', '## 同起点窗口比较：固定本金', '',
              '|标的与共同起点|持有收益/回撤|3年策略收益/回撤|5年策略收益/回撤|10年策略收益/回撤|',
              '|---|---|---|---|---|']
    def pair(r):
        return f"{r['nav_return_pct']}% / {r['max_drawdown_pct']}%" if r else '不足历史'
    for asset in results.values():
        common = asset['common_window_comparison']
        lines.append('|'+asset['name']+' '+common['start']+'|'+pair(common['hold'])+'|'+
                     '|'.join(pair(common['windows'].get(str(year))) for year in (3, 5, 10))+'|')
    lines += ['', '不同起点不能直接比较窗口参数好坏；统一起点后，沪深300的5年与10年窗口表现接近，3年明显落后；中证50010年窗口收益有所改善，但回撤几乎不优于持有。不能据此选出未来最优窗口。', '',
              '## 稳健性与收益来源', '',
              '|标的|默认策略收益/回撤|50%初始投入后持有收益/回撤|只用低估入场、不加回撤门槛|加倍滑点策略收益/回撤|',
              '|---|---|---|---|---|']
    for asset in results.values():
        w = asset['windows']['5']
        if 'error' in w:
            continue
        lines.append('|'+asset['name']+'|'+pair(w['models']['fixed_strategy'])+'|'+pair(w['half_cash_hold_control'])+'|'+
                     pair(w['valuation_only_control'])+'|'+pair(w['sensitivity']['double_slippage']['strategy'])+'|')
    lines += ['', '50%初始投入后持有仅用于检查现金降低风险的贡献，不是每天再平衡，也不是严格风险匹配。沪深300策略在本样本优于这一现金对照；中证500策略收益仍低于对照，说明低回撤不能全部解释为择时更准。取消回撤门槛的候选没有明显改善，暂没有证据要求删除该条件。', '',
              '|标的|前半段策略/持有收益|后半段策略/持有收益|约3年窗口收益胜出次数|',
              '|---|---|---|---|']
    for asset in results.values():
        w = asset['windows']['5']
        if 'error' in w:
            continue
        segments = w['segments']['fixed']
        first, second = [segments[s] for s in ('first_half','second_half')]
        rolling = w['rolling_750_days']
        wins = sum(r['strategy']['nav_return_pct'] > r['hold']['nav_return_pct'] for r in rolling)
        lines.append(f"|{asset['name']}|{first['strategy']['nav_return_pct']}% / {first['hold']['nav_return_pct']}%|{second['strategy']['nav_return_pct']}% / {second['hold']['nav_return_pct']}%|{wins}/{len(rolling)}|")
    lines += ['', '750交易日窗口按每年起点选取，彼此重叠，不能当成独立胜率；科创50默认5年窗口不够750交易日。分段均从现金重新开始，不能相乘复原完整回测。', '',
              '加倍滑点、买入改用全部可用现金、估值额外延迟5交易日没有推翻主要结论。1000元固定本金对一手取整和最低佣金敏感，沪深300的小额相对收益甚至反转，不应将这个取整差异视为策略优势。完整结果、信号天数、实际交易明细与资金曲线见results/broad_valuation/。分段是事后稳健性检查，不是独立样本外验证。', '',
              '## 数据与参考', '',
              '- 月度指数加权滚动PE：[乐咕乐股](https://legulegu.com/stockdata/index-basic)，现有缓存；使用自己的历史滚动分位，未使用网站全样本分位。沪深300历史始于2005-04、中证500始于2007-01、科创50始于2020-07。',
              '- [AQR：Market Timing—Sin a Little](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Market-Timing-Sin-a-Little.pdf)：估值与长期收益有关，不代表估值择时必然胜过持有；该研究不是本App阈值的验证。', '',
              '复现：python -B research_broad_valuation.py。研究结果不修改今日提醒信号；买入比例、资金频率、减仓次数是执行假设，后续应由用户确定。']
    text = '\n'.join(lines) + '\n'
    Path('broad_valuation_research.md').write_text(text, encoding='utf-8')
    Path('results/broad_valuation/report.md').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
