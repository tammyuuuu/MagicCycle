"""三只宽基的分标的策略；只读历史行情与估值，不用持仓决定信号。"""
import numpy as np
import pandas as pd

from broad_signal_rules import signal_frame, valuation_positions, low_value_or_trend, price_band_positions
from valuation_data import SOURCE, SOURCE_URL, summarize

VERSION = 'broad_individual_v1'


def individual_frame(data, history, strategy_id, years=5):
    close = data.close
    window = {'value_confirmed_exit': 80, 'value_or_trend120': 120, 'trend20': 20, 'trend16_buffer2': 16}[strategy_id]
    average = close.rolling(window, min_periods=window).mean()
    if strategy_id.startswith('trend'):
        position = price_band_positions(close,16,.02) if strategy_id=='trend16_buffer2' else (close>average).astype(float)
        return pd.DataFrame({'ready': average.notna(), 'position': position,
                             'percentile': np.nan, 'average': average}, index=data.index)
    if history.empty:
        return pd.DataFrame({'ready': False, 'position': 0., 'percentile': np.nan,
                             'average': average}, index=data.index)
    frame = signal_frame(data, history, years, lag=1)
    position = (valuation_positions(frame.percentile, close, confirm_exit=True, entry_ma=60, exit_ma=80)
                if strategy_id == 'value_confirmed_exit' else low_value_or_trend(close, frame.percentile, 120, ceiling=60))
    return pd.DataFrame({'ready': frame.ready & average.notna(), 'position': position,
                         'percentile': frame.percentile, 'average': average}, index=data.index)


def snapshot(data, history, strategy_id, years):
    frame = individual_frame(data, history, strategy_id, years)
    row = frame.iloc[-1]
    ready = bool(row.ready)
    price = float(data.close.iloc[-1])
    above = bool(pd.notna(row.average) and price > row.average)
    percentile = float(row.percentile) if pd.notna(row.percentile) else None
    valuation = None
    if not strategy_id.startswith('trend') and not history.empty and len(data) > 1:
        # 一个ETF交易日额外延迟，与研究使用同一估值可见时点。
        valuation = summarize(history, data.index[-2], years)
        valuation.update(source=SOURCE, source_url=SOURCE_URL)
    status = 'watch'
    if not ready:
        reason = '价格或所选年限的估值历史不足、过旧，先观察。' if not strategy_id.startswith('trend') else ('不足16个交易日，先观察。' if strategy_id=='trend16_buffer2' else '不足20个交易日，先观察。')
        checks = [('判断前提', '至少250个交易日价格及完整估值历史' if not strategy_id.startswith('trend') else ('至少16个交易日价格' if strategy_id=='trend16_buffer2' else '至少20个交易日价格'))]
    else:
        allowed = bool(row.position)
        exit_condition = (price <= row.average*.98 if strategy_id=='trend16_buffer2' else not above if strategy_id == 'trend20' else
                          percentile >= 90 and not above if strategy_id == 'value_confirmed_exit' else
                          percentile >= 30 and not above)
        status = 'buy' if allowed else 'exit' if exit_condition else 'watch'
        if strategy_id == 'value_confirmed_exit':
            reason = ('低估且价格恢复后进入买入阶段，尚未触发“高估且转弱”退出；本期新资金可买入，已有持仓不必重复交易。' if allowed else
                      '估值分位至少90%，且价格不高于80日均价；已有持仓考虑退出。' if exit_condition else
                      '等待低估与价格恢复同时出现：PE分位低于30%，且收盘高于60日均价才开始买入。')
            entry_above = price > float(data.close.rolling(60).mean().iloc[-1])
            checks = [('当前分位', f'近{years}年PE分位{percentile:g}%（估值日期：{valuation["date"]}）'),
                      ('入场条件', 'PE分位低于30%且收盘高于60日均价才进入买入阶段'),
                      ('买入确认', '价格'+('高于' if entry_above else '不高于')+'60日均价；用于初次进入，入场后不因跌回线下自动退出'),
                      ('退出确认', '价格'+('高于' if above else '不高于')+'80日均价；PE分位至少90%且转弱才退出'),
                      ('策略阶段', '允许持有与本期新资金买入' if allowed else '等待低估入场或保持退出')]
        elif strategy_id == 'value_or_trend120':
            reason = ('已由低估或估值分位低于60%且趋势恢复进入买入阶段，尚未触发退出；本期新资金可买入。' if allowed else
                      '估值已离开低估区，且价格不高于120日均价；已有持仓考虑退出。' if exit_condition else
                      '估值与趋势尚未满足入场条件，先观察。')
            checks = [('当前分位', f'近{years}年PE分位{percentile:g}%（估值日期：{valuation["date"]}）'),
                      ('入场条件', 'PE分位低于30%允许买入，否则须低于60%且高于120日均价'),
                      ('退出条件', '价格'+('高于' if above else '不高于')+'120日均价；PE分位至少30%且价格转弱才退出'),
                      ('策略阶段', '退出前保持买入许可；分位升到60%以上不单独卖出' if allowed else '等待入场条件或保持退出')]
        elif strategy_id == 'trend16_buffer2':
            reason = ('价格已突破16日均线的上方2%进入买入阶段，尚未跌到下方2%；本期新资金可买入。' if allowed else
                      '收盘跌到16日均价下方2%或更低；已有持仓考虑退出。' if exit_condition else
                      '等待收盘高于16日均价的上方2%，先观察。')
            checks = [('入场条件','收盘高于16日均价的102%才进入买入阶段'),
                      ('退出条件','收盘不高于16日均价的98%才退出'),
                      ('缓冲区','上下2%之间保持原有行情许可，避免围绕均线反复交易'),
                      ('策略阶段','允许本期新资金买入，已有持仓不必重复交易' if allowed else '等待上沿突破或保持退出')]
        else:
            reason = ('收盘高于20日均价，本期新资金可买入；已有持仓不必重复交易。' if above else
                      '收盘不高于20日均价，趋势转弱；已有持仓考虑退出。')
            checks = [('趋势条件', '收盘'+('高于' if above else '不高于')+'20日均价；线上允许买入，回到线下退出')]
    return {'status': status, 'action': {'buy':'买入','watch':'观察','exit':'退出'}[status],
            'reason': reason, 'decision_basis': checks,
            'decision_conditions': [{'condition':title,'result':text,'met':None} for title,text in checks],
            'valuation': valuation, 'valuation_percentile': percentile,
            'insufficient_history': not ready, 'average': float(row.average) if pd.notna(row.average) else None}


def analyze(data, item, metrics, details):
    strategy_id = item['broad_strategy']
    history = pd.DataFrame(item.get('valuation_history') or [], columns=['date','pe'])
    if not history.empty:
        history.date = pd.to_datetime(history.date)
        history = history[history.date <= data.index[-1]]
    options = {str(years): snapshot(data, history, strategy_id, years) for years in (3,5,10)} if not strategy_id.startswith('trend') else {}
    current = options['5'] if options else snapshot(data, history, strategy_id, 5)
    metrics.update(valuation_percentile=current['valuation_percentile'],
                   **{f"ma{16 if strategy_id=='trend16_buffer2' else 20 if strategy_id=='trend20' else 80 if strategy_id=='value_confirmed_exit' else 120}":current['average']})
    if strategy_id == 'value_confirmed_exit':
        metrics['ma60'] = float(data.close.rolling(60).mean().iloc[-1]) if len(data)>=60 else None
    warning = details.get('data_warning')
    if warning:
        for option in list(options.values()) or [current]:
            option.update(status='watch', action='观察', reason='行情更新受限，待数据更新后再判断。')
            option['decision_basis'].insert(0, ('行情前提','更新受限，先观察'))
            option['decision_conditions'] = [{'condition':title,'result':text,'met':None} for title,text in option['decision_basis']]
    details.update(strategy_mode='broad_individual', strategy_id=strategy_id,
                   strategy_version='csi300_value_confirm_v2' if strategy_id=='value_confirmed_exit' else 'csi500_value_trend_v2' if strategy_id=='value_or_trend120' else 'star50_buffer_v2' if strategy_id=='trend16_buffer2' else VERSION,
                   legacy=None, enabled_decisions=['buy','watch','exit'],
                   insufficient_history=current['insufficient_history'], strategy_options=options,
                   valuation=current['valuation'],
                   valuation_options={key:value['valuation'] for key,value in options.items()},
                   parameters={'valuation_years':5,'entry_percentile':30,'exit_percentile':30 if strategy_id=='value_or_trend120' else 90,
                               'ma_window':16 if strategy_id=='trend16_buffer2' else 20 if strategy_id=='trend20' else 80 if strategy_id=='value_confirmed_exit' else 120,
                               **({'entry_ma_window':60} if strategy_id=='value_confirmed_exit' else {}),
                               **({'trend_entry_ceiling':60} if strategy_id=='value_or_trend120' else {}),
                               **({'price_buffer':.02} if strategy_id=='trend16_buffer2' else {}), 'valuation_lag':1}, new_money_fraction=.5 if current['status']=='buy' else 0.)
    return {'symbol':item['code'],'name':item['name'],'asset_type':'broad_etf','subtype':item.get('index'),
            'date':data.index[-1].date().isoformat(),'status':current['status'],'action':current['action'],
            'reason':current['reason'],'risk_level':'normal','metrics':metrics,'details':details,
            'decision_basis':current['decision_basis'],'decision_conditions':current['decision_conditions']}
