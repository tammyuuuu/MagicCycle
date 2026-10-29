# -*- coding: utf-8 -*-
"""
策略模块
========
【重要】这是你日后填写“自己的买卖规则”的地方：只需改写下方 my_strategy 函数。

每个策略都是一个函数：
    def strategy(df, params) -> pd.Series
      - df    : 按日期升序的日线 DataFrame（含 open/high/low/close/volume 列）
      - params: 参数字典（DEFAULT_PARAMS 里定义，命令行可 --params 覆盖）
      - 返回 与 df 等长的信号序列，取值含义：
            +1  -> 买入信号（空仓时次日开盘全仓买入）
            -1  -> 卖出信号（持仓时次日开盘清仓）
             0  -> 无操作

时间约定：信号在第 t 天【收盘后】产生，实际在第 t+1 天【开盘价】成交，
不包含未来数据，可直接用于回测。

内置了 3 个可直接运行的示例策略作对照：ma_cross / rsi_reversal / macd_cross。
"""

import pandas as pd

import indicators as ta
from strategy_config import SECTOR_PROFILE

# 各策略默认参数（命令行可用 --params k=v,k=v 覆盖）
DEFAULT_PARAMS = {
    "ma_cross":     {"fast": 20, "slow": 60},
    "rsi_reversal": {"rsi_n": 14, "oversold": 30, "overbought": 70},
    "macd_cross":   {"fast": 12, "slow": 26, "signal": 9},
    "my_strategy":  {"ma_n": 60},
    "sector_ma20":  {"ma_n": SECTOR_PROFILE['ma_fast']},
}


# ---------------------------------------------------------------
# 示例策略 1：双均线 —— MA(fast) 上穿 MA(slow) 买入，下穿卖出（趋势跟随）
# ---------------------------------------------------------------
def ma_cross(df, params):
    fast_n = int(params.get("fast", 20))
    slow_n = int(params.get("slow", 60))
    fast = ta.ma(df["close"], fast_n)
    slow = ta.ma(df["close"], slow_n)
    buy = ta.cross_up(fast, slow)
    sell = ta.cross_down(fast, slow)
    return buy.astype(int) - sell.astype(int)


# ---------------------------------------------------------------
# 示例策略 2：RSI 均值回归 —— 从超卖区回升买入，从超买区回落卖出
# ---------------------------------------------------------------
def rsi_reversal(df, params):
    n = int(params.get("rsi_n", 14))
    buy_th = float(params.get("oversold", 30))
    sell_th = float(params.get("overbought", 70))
    r = ta.rsi(df["close"], n)
    buy = (r > buy_th) & (r.shift(1) <= buy_th)
    sell = (r < sell_th) & (r.shift(1) >= sell_th)
    return buy.astype(int) - sell.astype(int)


# ---------------------------------------------------------------
# 示例策略 3：MACD —— DIF 上穿 DEA 买入，下穿卖出（趋势跟随）
# ---------------------------------------------------------------
def macd_cross(df, params):
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    sig_n = int(params.get("signal", 9))
    dif, dea, _ = ta.macd(df["close"], fast, slow, sig_n)
    buy = ta.cross_up(dif, dea)
    sell = ta.cross_down(dif, dea)
    return buy.astype(int) - sell.astype(int)


# ===============================================================
# 【你的策略】my_strategy
# ---------------------------------------------------------------
# 目前先放一个能跑的示例（收盘价上穿 MA60 买入 / 下穿 MA60 卖出）。
# 等把你的具体买卖规则告诉我，我帮你在这里替换成真正的规则即可。
#
# 编写时可自由使用：
#   - df 里的列：open/high/low/close/volume/pct_chg
#   - indicators 里的现成函数：ma/ema/rsi/macd/bollinger/atr/highest/lowest
#     cross_up/cross_down
#   - params 字典里自定义参数，并同步加到上方 DEFAULT_PARAMS
# ===============================================================
def my_strategy(df, params):
    ma_n = int(params.get("ma_n", 60))
    ma_line = ta.ma(df["close"], ma_n)

    # TODO: 在这里实现你自己的买卖规则 ------------------------------
    #   buy  = <你的买入条件>（布尔 Series，True 处发买入信号）
    #   sell = <你的卖出条件>（布尔 Series，True 处发卖出信号）
    # -----------------------------------------------------------------
    buy = (df["close"] > ma_line) & (df["close"].shift(1) <= ma_line.shift(1))
    sell = (df["close"] < ma_line) & (df["close"].shift(1) >= ma_line.shift(1))

    return buy.astype(int) - sell.astype(int)


def sector_ma20(df, params):
    """行业单均线：目标状态变化时下单，同方向不重复买卖。"""
    from industry_strategy import trend_positions
    positions = trend_positions(df['close'], params.get('ma_n', SECTOR_PROFILE['ma_fast'])).astype(int)
    return positions.diff().fillna(0).astype(int)


# ------------------------- 策略注册表 -------------------------
STRATEGIES = {
    "ma_cross":     ma_cross,
    "rsi_reversal": rsi_reversal,
    "macd_cross":   macd_cross,
    "my_strategy":  my_strategy,
    "sector_ma20":  sector_ma20,
}


def list_strategies():
    """列出所有策略及其默认参数（用于命令行展示）。"""
    return {name: dict(DEFAULT_PARAMS.get(name, {})) for name in STRATEGIES}


def generate_signals(df: pd.DataFrame, name: str, params: dict = None) -> pd.Series:
    """
    统一的信号生成入口。
    params 为空时使用该策略的默认参数；返回 +1/-1/0 的整型 Series，
    指标未就绪的前段一律填 0（视为不操作）。
    """
    if name not in STRATEGIES:
        raise KeyError(f"未知策略：{name}，可用：{list(STRATEGIES)}")
    p = dict(DEFAULT_PARAMS.get(name, {}))
    if params:
        p.update(params)
    sig = STRATEGIES[name](df, p)
    return sig.fillna(0).astype(int)

# 四类资产提醒入口。原有信号序列策略与回测接口保持不变。
def analyze_asset(df, item, holding=None, overrides=None, sell_rules=None):
    """纯计算，无网络。收益率/仓位为小数；current_return 为百分数兼容旧接口。

    输出百分比指标采用百分点，缺失值为 None，严格 JSON 可序列化。
    """
    import math
    from copy import deepcopy
    from strategy_config import STRATEGY_CONFIG
    import alerts
    import industry_strategy

    asset = item.get('asset_type') or ('sector_etf' if item.get('strategy_type') == 'industry' else 'broad_etf')
    subtype = item.get('subtype')
    if asset not in STRATEGY_CONFIG:
        raise ValueError('未知资产类型：' + asset)
    if asset == 'macro_asset':
        subtype = subtype or 'gold'
        if subtype not in STRATEGY_CONFIG[asset]:
            raise ValueError('暂未实现大类资产子类型：' + subtype)
        p = deepcopy(STRATEGY_CONFIG[asset][subtype])
    else:
        p = deepcopy(STRATEGY_CONFIG[asset])
    p.update(item.get('industry_profile') or {})
    p.update(overrides or {})
    h = holding or {}
    held = bool(h.get('holding', False))
    def finite(v):
        try:
            value = float(v)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None
    rr = finite(h.get('return_rate'))
    if rr is None and h.get('current_return') is not None:
        value = finite(h['current_return'])
        rr = value / 100 if value is not None else None
    d = df.copy().sort_index()
    d = d[~d.index.duplicated(keep='last')]
    d['close'] = pd.to_numeric(d['close'], errors='coerce')
    d = d[d['close'].map(lambda value: finite(value) is not None and value > 0)]
    if d.empty:
        raise ValueError('缺少有效收盘行情')
    c = d['close'].astype(float)
    price = float(c.iloc[-1])
    cost = finite(h.get('avg_cost'))
    if rr is None and cost is not None and cost > 0:
        rr = price / cost - 1
    mas = {n: ta.ma(c, n) for n in (5, 10, 20, 60, 120)}
    m = {n: finite(s.iloc[-1]) for n, s in mas.items()}
    r = ta.rsi(c, 14)
    rsi = finite(r.iloc[-1])
    prev_rsi = finite(r.iloc[-2]) if len(r) > 1 else None
    slope = finite(mas[20].iloc[-1] - mas[20].iloc[-6]) if len(c) >= 25 else None
    returns = c.pct_change()
    vol = finite(returns.tail(60).std())
    high = float(c.tail(int(p.get('high_window', 250))).max())
    dd = price / high - 1
    change = finite(returns.iloc[-1])
    volume_ratio = None
    if 'volume' in d and len(d) >= 21:
        volume = pd.to_numeric(d['volume'], errors='coerce')
        base = finite(volume.iloc[-21:-1].mean())
        latest = finite(volume.iloc[-1])
        if base and latest is not None:
            volume_ratio = latest / base
    atr_value = finite(ta.atr(d, 14).iloc[-1]) if {'high','low'}.issubset(d.columns) and len(d) > 14 else None
    insufficient = len(c) < int(p['min_history'])
    weak = m[20] is not None and m[60] is not None and m[20] < m[60] and (slope or 0) < 0
    trend = 'unknown' if m[60] is None else 'weak' if weak else 'strong' if price > m[60] else 'neutral'
    details = {'trend': trend, 'position': None, 'overheated': False,
               'insufficient_history': insufficient, 'history_days': len(c),
               'holding': held, 'holding_return': rr, 'parameters': p,
               'data_warning': d.attrs.get('stale_note'),
               'fundamental_data_available': None}
    metrics = {'price': round(price, 4), 'day_change_pct': round(change*100, 2) if change is not None else None,
               'historical_percentile': None, 'drawdown': round(dd*100, 2),
               'rsi14': round(rsi, 2) if rsi is not None else None,
               **{'ma'+str(n): round(v, 4) if v is not None else None for n,v in m.items()},
               'ma20_slope': slope, 'volatility': vol, 'atr': atr_value,
               'volume_ratio': volume_ratio}
    if asset == 'broad_etf' and item.get('strategy_mode') == 'us_monthly_trend':
        from us_etf_strategy import analyze
        return analyze(d, item, metrics, details)
    if asset == 'broad_etf' and item.get('strategy_mode') == 'broad_individual':
        from broad_individual_strategy import analyze
        return analyze(d, item, metrics, details)
    status, action, reason, risk = 'watch', '暂时观察', '等待足够行情后再判断。', 'normal'
    legacy = None
    if asset == 'broad_etf':
        legacy = alerts.analyze_latest(d, p, sell_rules=sell_rules)
        percentile = legacy['pct']
        metrics['historical_percentile'] = percentile
        metrics['drawdown'] = round((price / legacy['hist_high'] - 1)*100, 2) if legacy['hist_high'] else None
        high_position = percentile is not None and percentile > p['p_high']
        low = percentile is not None and percentile < p['p_low']
        details.update(position='high' if high_position else 'low' if low else 'neutral', overheated=high_position)
        valuation = item.get('valuation') or {}
        valuation_pct = finite(valuation.get('percentile'))
        valuation_date = pd.to_datetime(valuation.get('date'), errors='coerce')
        valid_valuation = (valuation_pct is not None and 0 <= valuation_pct <= 100
                           and pd.notna(valuation_date)
                           and 0 <= (d.index[-1].normalize() - valuation_date).days <= (35 if valuation.get('frequency') == 'monthly' else 0)
                           and valuation.get('metric') in ('PE', 'PB')
                           and bool(valuation.get('source')))
        def band(value):
            return '低位' if value < p['p_low'] else '高位' if value > p['p_high'] else '中位'
        high_1y = float(c.tail(p['price_high_window']).max())
        drawdown_1y = max(0., (high_1y-price)/high_1y)
        metrics.update(drawdown_1y_pct=round(drawdown_1y*100,2), high_1y=round(high_1y,4))
        price_band = ('回撤较大' if drawdown_1y >= p['drawdown_large'] else '回撤中等' if drawdown_1y >= p['drawdown_medium'] else '回撤较小') if not insufficient else '无法判断'
        valuation_band = band(valuation_pct) if valid_valuation else '无法判断'
        details.update(price_band=price_band, valuation_band=valuation_band,
                       drawdown_1y=drawdown_1y,
                       valuation_options=valuation.get('windows', {}),
                       valuation=valuation if valid_valuation else None,
                       strategy_version='broad_drawdown_valuation_v2')
        metrics['valuation_percentile'] = valuation_pct if valid_valuation else None
        if '无法判断' in (price_band, valuation_band):
            status, action, reason = 'watch', '观察', '价格区间或估值数据不足，暂不作买卖判断。'
        else:
            status = 'exit' if valuation_pct >= p['valuation_exit_percentile'] else 'reduce' if valuation_band=='高位' else 'buy_more' if valuation_band=='低位' and price_band=='回撤较大' else 'buy' if valuation_band=='低位' and price_band=='回撤中等' else 'watch'
            action = {'buy_more':'加仓','buy':'买入','watch':'观察','reduce':'减仓','exit':'退出'}[status]
            reason = f'距近一年高点回撤{drawdown_1y*100:.1f}%，估值处于{valuation_band}，对应{action}信号。'
    elif asset == 'sector_etf':
        legacy = industry_strategy.analyze_latest(d, p)
        p.update(legacy['profile'])
        status, action, reason = legacy['status'], legacy['action'], legacy['reason']
        insufficient = legacy['insufficient_history']
        risk = 'elevated' if insufficient else 'high' if status == 'exit' else 'normal'
        details.update(strategy_version=legacy['strategy_version'],
                       trend='unknown' if insufficient else 'strong' if legacy['above_ma'] else 'weak',
                       ma_window=p['ma_fast'], above_ma=legacy['above_ma'],
                       fresh_entry=legacy['fresh_entry'], crossed_down=legacy['crossed_down'],
                       target_exposure=legacy['target_exposure'],
                       below_days=legacy['below_days'],
                       insufficient_history=insufficient, enabled_decisions=['buy','watch','reduce','exit'])
        metrics['ma20'] = legacy['ma20']
    elif asset == 'macro_asset':
        import gold_strategy
        gold = gold_strategy.analyze_latest(d, p)
        status, action, reason = gold['status'], gold['action'], gold['reason']
        insufficient = gold['insufficient_history']
        details.update({k:v for k,v in gold.items() if k not in ('status','action','reason','profile')})
        details['enabled_decisions'] = ['add','buy','watch','reduce']
        details['overheated'] = bool(gold['heat_phase'])
        metrics['return_20d_pct'] = round(gold['return_20d_pct'],2) if gold['return_20d_pct'] is not None else None
        metrics['deviation60_pct'] = round(gold['deviation60_pct'],2) if gold['deviation60_pct'] is not None else None
        risk = 'elevated' if insufficient or gold['heat_phase'] else 'normal'
    details['legacy'] = legacy
    result = {'symbol': item['code'], 'name': item['name'], 'asset_type': asset,
              'subtype': subtype, 'date': d.index[-1].date().isoformat(),
              'status': status, 'action': action, 'reason': reason, 'risk_level': risk,
              'metrics': metrics, 'details': details}
    # 判断依据来自本次策略实际使用的条件与未四舍五入的数据。
    checks=[]
    def record(condition, met):
        checks.append({"condition":condition,"met":None if met is None else bool(met),
                       "result":"无法判断（数据或持仓信息不足）" if met is None else "满足" if met else "未满足"})
    record(f"历史样本不少于 {p['min_history']} 个交易日",len(c)>=p['min_history'])
    if asset=='broad_etf':
        checks=[]
        record('价格回撤：'+price_band+f'（距近一年高点下跌{drawdown_1y*100:.1f}%）', None if price_band=='无法判断' else True)
        record('估值区间：'+valuation_band + (f"（PE {valuation['value']:g}，近{valuation.get('window_years',5)}年分位{valuation_pct:g}%，{valuation['date']}，月度）" if valid_valuation and valuation.get('value') is not None else '（'+valuation.get('error','数据不足')+'）'), None if valuation_band=='无法判断' else True)
    elif asset=='sector_etf':
        checks=[]
        line=f"{p['ma_fast']}日均线"
        if insufficient:
            record(f"判断前提：至少{p['min_history']}个有效交易日，当前{len(c)}个",None)
        elif status=='buy':
            record(f"买入条件：收盘价转到{line}上方；减半后恢复时只买回减掉的部分",True)
        elif status=='reduce':
            record(f"减仓条件：收盘价首次回到{line}或下方，下一交易日减半一次",True)
        elif status=='exit':
            record(f"退出条件：连续两个交易日收盘不高于{line}，卖出剩余持仓",legacy['below_days']>=2)
        elif not legacy['above_ma']:
            record("观察条件：均线刚就绪，尚未出现进入信号",True)
        else:
            record(f"趋势条件：收盘价保持在{line}上方",True)
            record("操作条件：未出现新的进入信号，不重复买入",True)
    elif asset=='macro_asset':
        checks=[]
        if insufficient:
            record(f"判断前提：至少{p['min_history']}个有效交易日",None)
        elif status=='reduce':
            record(f"减仓条件：近{p['return_window']}个交易日涨幅至少{p['heat_threshold']*100:g}%",True)
            record(f"减仓条件：高于{p['ma_window']}日均价至少{p['heat_threshold']*100:g}%；同一过热阶段减半一次",True)
        elif gold['fresh_add']:
            record(f"买回条件：过热阶段结束，短期涨幅与均线偏离均不高于{p['cooling_threshold']*100:g}%；可买回并恢复仓位",True)
        elif gold['heat_phase']:
            record(f"观察条件：过热阶段尚未冷却，等待两个指标均不高于{p['cooling_threshold']*100:g}%；不重复减仓",True)
        else:
            record("买入／持有：允许长期持有，普通回调不单独触发买入；双15%过热减半，双5%冷却买回",True)
    # 仅调整解释顺序，不改变买卖逻辑。风险/暂停条件先于机会确认。
    basis_order = {
        'broad_etf': [0, 1],
        'sector_etf': list(range(len(checks))),
        'macro_asset': list(range(len(checks))),
    }[asset]
    # 样本不够时先说明无法可靠判断的根本原因。
    if insufficient and asset != 'broad_etf':
        leading = [0]
        basis_order = leading + [i for i in basis_order if i not in leading]
    ranked = [checks[i] for i in basis_order]
    # 缺少持仓等输入的条件放到最后，避免挡住当前能确定的关键判断。
    checks = [row for row in ranked if row['met'] is not None] + [row for row in ranked if row['met'] is None]
    result['decision_conditions']=checks
    result['decision_basis']=[(row['condition'],row['result']) for row in checks]
    return result
