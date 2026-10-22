"""分标的研究：固定少量候选，前60%筛选，后40%只做留出检验。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_broad_valuation import ASSETS, load, signal_frame, xirr
from broad_signal_rules import valuation_positions, low_value_or_trend
from research_us_etf_extended import monthly_state





def buffered_trend(close, window, buffer=.02):
    average = close.rolling(window, min_periods=window).mean()
    held = False
    values = []
    for price, ma in zip(close, average):
        if not np.isfinite(ma):
            held = False
        elif price > ma * (1 + buffer):
            held = True
        elif price <= ma * (1 - buffer):
            held = False
        values.append(float(held))
    return pd.Series(values, index=close.index)





def secondary_sector_rules(prices, history):
    """中证500追加探索：低估底部保护与趋势重新入场、经典通道突破。

    第一轮后段已看过；此组结果一律标为探索，不冒充新的留出验证。
    """
    pct = signal_frame(prices, history, 5).percentile
    close = prices.close
    rules, descriptions = {}, {}
    for n in (60, 120, 200):
        key = f'low_value_or_trend{n}'
        rules[key] = low_value_or_trend(close, pct, n)
        descriptions[key] = f'5年PE低于30%直接买入，或PE低于90%且价格高于{n}日均价买入；离开低估区且回到均价或下方退出。'
    for buy_window, sell_window in ((20, 10), (60, 20), (120, 60)):
        upper = close.rolling(buy_window).max().shift(1)
        lower = close.rolling(sell_window).min().shift(1)
        held = False
        states = []
        for price, top, bottom in zip(close, upper, lower):
            if held and np.isfinite(bottom) and price < bottom:
                held = False
            elif not held and np.isfinite(top) and price > top:
                held = True
            states.append(float(held))
        key = f'channel{buy_window}_{sell_window}'
        rules[key] = pd.Series(states, index=close.index)
        descriptions[key] = f'收盘突破此前{buy_window}日最高收盘价买入，跌破此前{sell_window}日最低收盘价退出。'
    return rules, descriptions


def candidate_rules(prices, history, code):
    close = prices.close
    rules, descriptions = {}, {}
    def add(key, values, text):
        rules[key] = values.astype(float)
        descriptions[key] = text
    for n in (20, 60, 120, 200):
        add(f'ma{n}', close > close.rolling(n, min_periods=n).mean(),
            f'收盘高于{n}日均价可以买入，收盘不高于均价退出。')
    for n in (60, 120):
        add(f'buffer_ma{n}', buffered_trend(close, n),
            f'收盘高于{n}日均价2%买入，低于或等于均价的98%退出，中间保持。')
    add('cross20_60', close.rolling(20).mean() > close.rolling(60).mean(),
        '20日均价高于60日均价买入，否则退出。')
    add('cross60_120', close.rolling(60).mean() > close.rolling(120).mean(),
        '60日均价高于120日均价买入，否则退出。')
    add('monthly10', monthly_state(close, 10), '最近完整月份收盘高于10个月均价买入，否则退出。')
    monthly = close.resample('ME').last()
    monthly = monthly.loc[monthly.index <= close.index[-1]]
    momentum = monthly.pct_change(12, fill_method=None)
    add('momentum12', (momentum > 0).astype(float).reindex(close.index, method='ffill').fillna(0),
        '最近完整月份过去12个月涨幅为正买入，否则退出。')
    for years in ((3,) if code == '588000' else (3, 5)):
        pct = signal_frame(prices, history, years, lag=1).percentile
        for entry in (30, 50):
            add(f'pe{years}_{entry}_90', valuation_positions(pct, close, entry=entry),
                f'近{years}年月度PE分位低于{entry}%买入，达到90%退出。')
        add(f'pe{years}_confirmed_exit', valuation_positions(pct, close, confirm_exit=True),
            f'近{years}年PE分位低于30%买入；分位至少90%且价格不高于60日均价退出。')
        add(f'pe{years}_protected', valuation_positions(pct, close, confirm_exit=True, protect=True),
            f'近{years}年PE分位低于30%买入；高估转弱退出，或离开低估区且不高于120日均价退出。')
        ma = close.rolling(60).mean()
        held = False
        values = []
        for value, price, average in zip(pct, close, ma):
            if held and price <= average:
                held = False
            elif not held and np.isfinite(value) and value < 70 and price > average:
                held = True
            values.append(float(held))
        add(f'pe{years}_trend60', pd.Series(values, index=close.index),
            f'近{years}年PE分位低于70%且价格高于60日均价买入，回到均价或下方退出。')
    return rules, descriptions


def execute(prices, target, start, end=None, initial=100000., monthly=None,
            slippage=.001, minimum_fee=5.):
    """行情给出持有许可，次日开盘执行；整数一手、费用、每日最多一笔。

    一开始有固定资金，或者每月同额入金；净值份额化，入金不影响回撤。
    target仅0/1，无杠杆、不卖空。恢复为1时可投入可用现金，非每日再平衡。
    """
    end = len(prices) if end is None else end
    if (not target.index.equals(prices.index) or target.isna().any()
            or not target.isin([0., 1.]).all() or not 1 <= start < end <= len(prices)
            or initial <= 0 or minimum_fee < 0 or not 0 <= slippage < 1
            or monthly is not None and monthly <= 0):
        raise ValueError('无效执行参数')
    cash = float(initial) if monthly is None else 0.
    qty = 0
    units = principal = cash
    flows = [(prices.index[start], -cash)] if cash else []
    opening, closing, high, low = [prices[c].to_numpy() for c in ('open', 'close', 'high', 'low')]
    desired = target.to_numpy()
    months = prices.index.to_period('M')
    records, trades = [], []
    fees = 0.
    last_desired = 0.
    for i in range(start, end):
        date = prices.index[i]
        deposit = monthly is not None and (i == start or months[i] != months[i - 1])
        if deposit:
            before = cash + qty * opening[i]
            nav_before = before / units if units else 1.
            units += monthly / nav_before
            cash += monthly
            principal += monthly
            flows.append((date, -monthly))
        held = desired[i - 1] == 1.
        one_price = high[i] == low[i]
        limit = .20 if prices.attrs.get('code') == '588000' else .10
        change = opening[i] / closing[i - 1] - 1
        if held and (qty == 0 or deposit or last_desired == 0.) and not (one_price and change >= limit - .003):
            price = opening[i] * (1 + slippage)
            quantity = int(cash / (price * 1.0001) // 100) * 100
            while quantity and quantity * price + max(minimum_fee, quantity * price * .0001) > cash:
                quantity -= 100
            if quantity:
                fee = max(minimum_fee, quantity * price * .0001)
                cash -= quantity * price + fee
                qty += quantity
                fees += fee
                trades.append({'date': str(date.date()), 'action': '买入', 'quantity': quantity,
                               'price': price, 'fee': fee, 'signal_date': str(prices.index[i - 1].date())})
        elif not held and qty and not (one_price and change <= -limit + .003):
            price = opening[i] * (1 - slippage)
            fee = max(minimum_fee, qty * price * .0001)
            cash += qty * price - fee
            fees += fee
            trades.append({'date': str(date.date()), 'action': '退出', 'quantity': -qty,
                           'price': price, 'fee': fee, 'signal_date': str(prices.index[i - 1].date())})
            qty = 0
        last_desired = desired[i - 1]
        equity = cash + qty * closing[i]
        assert cash >= -1e-7 and qty % 100 == 0 and qty >= 0
        records.append({'date': date, 'equity': equity, 'nav': equity / units if units else 1.,
                        'cash': cash, 'quantity': qty, 'principal': principal,
                        'exposure': qty * closing[i] / equity if equity else 0.})
    curve = pd.DataFrame(records).set_index('date')
    nav = np.r_[1., curve.nav.to_numpy()]
    elapsed = (curve.index[-1] - curve.index[0]).days / 365.25
    dd = float((nav / np.maximum.accumulate(nav) - 1).min()) * 100
    annual = float((nav[-1] ** (1 / elapsed) - 1) * 100) if elapsed else 0.
    flows.append((curve.index[-1], float(curve.equity.iloc[-1])))
    stats = {'return_pct': round(float(nav[-1] - 1) * 100, 2),
             'annualized_pct': round(annual, 2), 'max_drawdown_pct': round(dd, 2),
             'calmar': round(annual / abs(dd), 4) if dd < 0 else None,
             'trades': len(trades), 'fees_yuan': round(fees, 2),
             'average_exposure_pct': round(float(curve.exposure.mean()) * 100, 2),
             'principal_yuan': round(principal, 2), 'ending_yuan': round(float(curve.equity.iloc[-1]), 2),
             'profit_on_contributions_pct': round(float(curve.equity.iloc[-1] / principal - 1) * 100, 2),
             'xirr_pct': xirr(flows)}
    return stats, curve, trades


def dominates(candidate, baseline):
    # 两项严格改善；四舍五入后平局不算达标。
    return (candidate['return_pct'] > baseline['return_pct'] and
            candidate['max_drawdown_pct'] > baseline['max_drawdown_pct'])


def choose_training(training, baseline):
    eligible = [key for key, stats in training.items() if dominates(stats, baseline)]
    if not eligible:
        return None
    # 只读取训练指标；先卡玛比率、再收益、最后固定名称打破平局。
    return max(eligible, key=lambda key: (training[key]['calmar'] or 0,
                                         training[key]['return_pct'], key))


def main():
    out = Path('results/broad_individual')
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for code, index, name in ASSETS:
        prices, history, hashes = load(code, index)
        base = signal_frame(prices, history, 3 if code == '588000' else 5)
        start = int(np.flatnonzero(base.ready)[0]) + 1
        split = start + int((len(prices) - start) * .6)
        rules, descriptions = candidate_rules(prices, history, code)
        hold = pd.Series(1., index=prices.index)
        periods = {'train': (start, split), 'holdout': (split, len(prices)), 'full': (start, len(prices))}
        baseline = {period: execute(prices, hold, a, b)[0] for period, (a, b) in periods.items()}
        training = {key: execute(prices, target, start, split)[0] for key, target in rules.items()}
        selected = choose_training(training, baseline['train'])
        # 后段只在选定候选后计算，所有候选均公开，未通过时不改选。
        evaluated = {key: {'description': descriptions[key], 'train': training[key],
                           **{period: execute(prices, target, a, b)[0]
                              for period, (a, b) in periods.items() if period != 'train'}}
                     for key, target in rules.items()}
        result = {'name': name, 'hashes': hashes, 'start': str(prices.index[start].date()),
                  'split': str(prices.index[split].date()), 'end': str(prices.index[-1].date()),
                  'candidate_count': len(rules), 'train_days': split-start,
                  'holdout_days': len(prices)-split, 'selected_by_training': selected,
                  'baseline': baseline, 'rules': evaluated,
                  'training_eligible': [key for key, stats in training.items() if dominates(stats, baseline['train'])],
                  'exploratory_full_pass': [key for key, value in evaluated.items() if dominates(value['full'], baseline['full'])]}
        if selected:
            target = rules[selected]
            result['holdout_pass'] = dominates(evaluated[selected]['holdout'], baseline['holdout'])
            result['full_pass'] = dominates(evaluated[selected]['full'], baseline['full'])
            result['sensitivity'] = {
                label: {mode: execute(prices, t, start, **kwargs)[0] for mode, t in [('candidate', target), ('hold', hold)]}
                for label, kwargs in [('double_slippage', {'slippage': .002}),
                                      ('small_1000', {'initial': 1000.}),
                                      ('monthly_1000', {'monthly': 1000.})]}
            rolling = []
            for year in sorted(set(prices.index[start:].year)):
                a = max(start, int(prices.index.searchsorted(pd.Timestamp(year, 1, 1))))
                b = a + 750
                if b <= len(prices):
                    strategy = execute(prices, target, a, b)[0]
                    reference = execute(prices, hold, a, b)[0]
                    rolling.append({'start': str(prices.index[a].date()), 'candidate': strategy,
                                    'hold': reference, 'both_pass': dominates(strategy, reference)})
            result['rolling_750_days'] = rolling
            stats, curve, trades = execute(prices, target, start)
            curve.to_csv(out / f'{code}_selected_curve.csv')
            pd.DataFrame(trades).to_csv(out / f'{code}_selected_trades.csv', index=False)
            execute(prices, hold, start)[1].to_csv(out / f'{code}_hold_curve.csv')
        # 不覆盖训练选择；科创20日候选是在公开后段结果后关注的探索项。
        focus = 'ma20' if code == '588000' else selected
        if focus:
            result['focus'] = {'key': focus, 'post_hoc': focus != selected,
                               'full': evaluated[focus]['full'], 'holdout': evaluated[focus]['holdout']}
            variants = {}
            if focus == 'ma20':
                variants = {f'ma{n}': (prices.close > prices.close.rolling(n).mean()).astype(float)
                            for n in (16, 20, 24)}
            elif focus == 'pe5_confirmed_exit':
                pct = signal_frame(prices, history, 5).percentile
                variants = {f'exit_ma{n}': valuation_positions(pct, prices.close, confirm_exit=True, exit_ma=n)
                            for n in (40, 60, 80)}
                for entry in (20, 40):
                    variants[f'entry{entry}'] = valuation_positions(pct, prices.close, entry=entry, confirm_exit=True)
                pct_late = signal_frame(prices, history, 5, lag=5).percentile
                variants['valuation_lag5'] = valuation_positions(pct_late, prices.close, confirm_exit=True)
            result['focus']['neighbor_checks'] = {
                key: {period: execute(prices, target, a, b)[0] for period, (a, b) in periods.items()}
                for key, target in variants.items()}
            result['focus']['execution_checks'] = {
                label: {mode: execute(prices, t, start, **kwargs)[0]
                        for mode, t in [('candidate', rules[focus]), ('hold', hold)]}
                for label, kwargs in [('double_slippage', {'slippage': .002}),
                                      ('small_1000', {'initial': 1000.}),
                                      ('monthly_1000', {'monthly': 1000.})]}
            if code == '588000':
                result['focus']['price_only_extension'] = {
                    'start': str(prices.index[250].date()),
                    'candidate': execute(prices, rules[focus], 250)[0],
                    'hold': execute(prices, hold, 250)[0]}
            focus_curve, focus_trades = execute(prices, rules[focus], start)[1:]
            focus_curve.to_csv(out / f'{code}_focus_curve.csv')
            pd.DataFrame(focus_trades).to_csv(out / f'{code}_focus_trades.csv', index=False)
        results[code] = result
        if code == '510500':
            extra, extra_descriptions = secondary_sector_rules(prices, history)
            result['secondary_exploration'] = {
                key: {'description': extra_descriptions[key],
                      **{period: execute(prices, target, a, b)[0] for period, (a, b) in periods.items()}}
                for key, target in extra.items()}
            target = extra['low_value_or_trend120']
            pct = signal_frame(prices, history, 5).percentile
            result['secondary_focus'] = {
                'key': 'low_value_or_trend120', 'post_hoc': True,
                'execution_checks': {label: {
                    mode: execute(prices, t, start, **kwargs)[0]
                    for mode, t in [('candidate', target), ('hold', hold)]}
                    for label, kwargs in [('double_slippage', {'slippage': .002}),
                                          ('small_1000', {'initial': 1000.}),
                                          ('monthly_1000', {'monthly': 1000.})]},
                'neighbor_checks': {f'ma{n}': {
                    period: execute(prices, low_value_or_trend(prices.close, pct, n), a, b)[0]
                    for period, (a, b) in periods.items()} for n in (100, 120, 140)}}
            execute(prices, target, start)[1].to_csv(out / f'{code}_secondary_focus_curve.csv')
            pd.DataFrame(execute(prices, target, start)[2]).to_csv(out / f'{code}_secondary_focus_trades.csv', index=False)
        print(code, selected, 'holdout_pass', result.get('holdout_pass'), 'full_pass', result.get('full_pass'), flush=True)
    (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write_report(results)


def write_report(results):
    lines = ['# 三只宽基ETF分别研究：收益与回撤同时改善', '',
             '研究日期2026-10-04，行情截止2026-09-30。目标是相同本金、相同日期、相同成本下，收益严格高于持有且最大回撤绝对值更小。相同或只有一项改善不达标。', '']
    def pair(stats):
        return f"{stats['return_pct']}% / {abs(stats['max_drawdown_pct'])}%"
    lines += ['## 结论先看', '',
              '三只都找到全区间两项改善的候选，但证据等级不同。沪深300前段选中的候选通过后段，邻近参数也支持继续试行研究；中证500和科创50的关注候选包含看过后段后的选择，不能与沪深300视为同等验证。', '',
              '|标的|候选|全区间策略收益/回撤|持有收益/回撤|证据与限制|',
              '|---|---|---|---|---|']
    labels = {'510300':('pe5_confirmed_exit','低估买入，高估转弱退出','训练选择通过后段；邻近参数检查较稳健'),
              '510500':('low_value_or_trend120','低估优先＋120日趋势','追加探索；回撤仍大，140日邻近规则全区间失败'),
              '588000':('ma20','20日均线趋势','事后关注；24日邻近规则失败，1000元固定本金未达标')}
    for code,result in results.items():
        key,label,caveat = labels[code]
        rule = result['secondary_exploration'][key] if code=='510500' else result['rules'][key]
        lines.append(f"|{result['name']}|{label}|{pair(rule['full'])}|{pair(result['baseline']['full'])}|{caveat}|")
    lines += ['', '即使历史两项都改善，也不等于未来每年都优于持有；低回撤不等于低风险，中证500候选仍有约59%回撤。未直接改动App信号，避免把探索结果包装成已验证策略。', '',
             '## 方法', '',
             '固定候选包括估值、均线、月度动量和估值与趋势结合，每支15至20种；在计算候选结果前写定，没有遍历大量阈值。沪深300和中证500使用3/5年月度PE，科创50仅使用3年，因为5年有效样本太短。各候选使用同一起点；不足250交易日或估值预热期不参与比较。', '',
             '每支前60%交易日用于筛选；训练中同时改善收益与回撤的候选按卡玛比率选择一个。其后40%只检验，不因后段结果换候选。全区间排名仅标为探索，不替代训练选择。此前已分析过这份历史，属于回顾性留出检验，不是真正未见的独立样本外证据。', '',
             '固定10万元，买入许可投入可用现金、退出卖全部，无杠杆卖空；行情信号不读取仓位或成本。收盘产生信号、次日开盘成交；100份整数、单边0.1%滑点、万一佣金且最低5元，现金收益0，末日不强制清仓。一字涨跌停近似拦截。', '',
             '前复权价格不能精确还原原始成交及分红现金；PE多延迟一ETF交易日，但缓存没有历史发布时间或修订版本，估值策略结果仍为条件模拟。数据哈希保存在JSON。', '',
             '## 前段选定候选，后段与全区间检验', '',
             '|标的|前段选定策略|期间|策略收益 / 最大回撤|持有收益 / 最大回撤|两项是否达标|',
             '|---|---|---|---|---|---|']
    notes = []
    for code, result in results.items():
        selected = result['selected_by_training']
        if selected is None:
            lines.append(f"|{result['name']}|训练中没有合格候选|—|—|—|否|")
            continue
        rule = result['rules'][selected]
        for period, label in [('train','前段筛选'),('holdout','后段留出'),('full','全区间')]:
            lines.append(f"|{result['name']}|{selected}|{label}|{pair(rule[period])}|{pair(result['baseline'][period])}|{'是' if dominates(rule[period],result['baseline'][period]) else '否'}|")
        notes += ['', f"**{result['name']}**：{rule['description']} 比较区间{result['start']}—{result['end']}；留出开始{result['split']}，前段{result['train_days']}日，后段{result['holdout_days']}日。", '']
    lines += notes
    lines += ['', '## 分标的结论与重点候选', '',
              '沪深300：前段筛选选中的5年低估入场、高估转弱退出候选，在后段和全区间均达标。它不要求低估与10%回撤同时出现，并把卖出改为PE分位至少90%且价格不高于60日均价。属于较有希望的试行候选，不是未来保证。', '',
              '中证500：前段首选同样是低估入场、高估转弱退出；全区间达标，但后段收益低于持有、回撤也没有改善。追加探索中，“低估直接入场、非高估时跟随120日趋势”在前段、后段和全区间都达标；但这组候选是在看过第一轮后段后追加，不能当成新的独立验证。', '',
              '科创50：前段首选200日均线，在后段失败。20日均线在前段、后段及全区间均达标，但它是在看到后段后才重点关注，仍属探索候选。下面追加邻近周期和更长价格样本检查，不把这当成新的独立验证，也不据此重写训练选择。', '',
              '|重点候选|全区间收益/回撤|后段收益/回撤|后段是否同时优于持有|',
              '|---|---|---|---|']
    for result in results.values():
        if not result.get('focus'):
            continue
        focus = result['focus']
        lines.append(f"|{result['name']} {focus['key']}|{pair(focus['full'])}|{pair(focus['holdout'])}|{'是' if dominates(focus['holdout'],result['baseline']['holdout']) else '否'}|")
    lines += ['', '## 邻近参数检查（不用于重新选择）', '',
              '|标的|参数|全区间收益/回撤|后段收益/回撤|后段同时达标|',
              '|---|---|---|---|---|']
    for result in results.values():
        for key, values in result.get('focus', {}).get('neighbor_checks', {}).items():
            lines.append(f"|{result['name']}|{key}|{pair(values['full'])}|{pair(values['holdout'])}|{'是' if dominates(values['holdout'],result['baseline']['holdout']) else '否'}|")
    for result in results.values():
        extension = result.get('focus', {}).get('price_only_extension')
        if extension:
            lines += ['', f"科创50纯价格候选延伸至{extension['start']}（250日价格预热，无需等待PE历史），20日均线为{pair(extension['candidate'])}，同日持有为{pair(extension['hold'])}。延伸同一份历史属于事后检查，不能冒充独立证据。", '']
    lines += ['', '## 全部候选（公开失败结果）', '',
              '|标的|候选|前段收益/回撤|后段收益/回撤|全区间收益/回撤|全区间达标|',
              '|---|---|---|---|---|---|']
    for result in results.values():
        for key, rule in result['rules'].items():
            lines.append(f"|{result['name']}|{key}|{pair(rule['train'])}|{pair(rule['holdout'])}|{pair(rule['full'])}|{'是' if dominates(rule['full'],result['baseline']['full']) else '否'}|")
    lines += ['', '## 中证500追加探索', '',
              '第一轮后段已看过，因此追加低估底部保护与趋势重新入场、经典价格通道突破6种候选，只作探索，不视为独立验证。', '',
              '|候选|前段收益/回撤|后段收益/回撤|全区间收益/回撤|全区间及后段均达标|',
              '|---|---|---|---|---|']
    for result in results.values():
        for key, values in result.get('secondary_exploration', {}).items():
            passed = all(dominates(values[p], result['baseline'][p]) for p in ('full','holdout'))
            lines.append(f"|{key}|{pair(values['train'])}|{pair(values['holdout'])}|{pair(values['full'])}|{'是' if passed else '否'}|")
    lines += ['', '中证500120日追加候选：只要PE分位低于30%，允许低估买入；否则必须PE低于90%且收盘高于120日均价才能买入。退出要求同时离开低估区且价格回到120日均价或下方。低估时价格仍弱也可能继续持有，这是大回撤来源之一。', '',
              '## 重点候选的执行成本与月度资金', '',
              '|标的|检查|候选收益/回撤|持有收益/回撤|', '|---|---|---|---|']
    for result in results.values():
        focused = result.get('secondary_focus') or result.get('focus', {})
        for label, values in focused.get('execution_checks', {}).items():
            lines.append(f"|{result['name']}|{label}|{pair(values['candidate'])}|{pair(values['hold'])}|")
    lines += ['', '科创50默认10万元时20日均线全区间收益76.73%、回撤24.91%；滑点加倍为60.57%、25.72%，仍达标。但1000元固定本金为-3.29%、33.93%，持有50.08%、34.79%，收益明显落后。频繁交易与最低佣金会改变可用性。', '',
              '中证500追加候选100/120日邻近规则在全区间与后段均达标，140日全区间失败；科创16日全区间达标但后段收益略低于持有，24日全区间及后段均失败。不能宣称对参数稳定。完整邻近检查保存在JSON。', '',
              'monthly_1000为每月相同日期各入金1000元的对照，收益和回撤使用份额化净值；不是累计利润/本金。利润、XIRR、交易明细、滚动750日比较保存在results/broad_individual/。滚动区间重叠，不能作为独立试验或真实胜率。训练选定后不按这些结果重新选策略。', '',
              '## 来源与边界', '',
              '[AQR估值择时研究](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Market-Timing-Sin-a-Little.pdf)与[CFA回测方法](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation)用于研究方法参考，不背书具体参数。价格来自现有腾讯前复权缓存，月度PE来自[乐咕乐股](https://legulegu.com/stockdata/index-basic)。', '',
              '没有任何候选能因此保证未来同时提高收益、降低回撤；科创50可检验历史尤其短。2026-10-04用户授权将沪深300低估＋转弱退出、中证500低估＋120日趋势、科创50的20日趋势采纳为试行策略；中证500与科创50仍保留探索标注。', '',
              '复现：python -B research_broad_individual.py。']
    text = '\n'.join(lines) + '\n'
    Path('broad_individual_research.md').write_text(text, encoding='utf-8')
    Path('results/broad_individual/report.md').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
