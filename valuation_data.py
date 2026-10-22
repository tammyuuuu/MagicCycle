"""指数估值获取与缓存；纯策略计算只接收整理后的数据。"""
from pathlib import Path
from datetime import datetime
import json
import pandas as pd
import requests
from config import CACHE_DIR

INDEX_CODES = {'中证500': '000905.SH', '科创50': '000688.SH',
               '沪深300': '000300.SH', '上证50': '000016.SH',
               '中证1000': '000852.SH'}
SOURCE = '乐咕乐股 · 指数加权滚动市盈率（月度）'
SOURCE_URL = 'https://legulegu.com/stockdata/index-basic'


def normalize_history(rows):
    """仅接受有日期且为正数的同口径PE；不将亏损PE当低估。"""
    data = pd.DataFrame(rows)
    if data.empty or not {'date', 'ttmPe'}.issubset(data.columns):
        raise ValueError('接口未返回指数滚动市盈率历史')
    data = data[['date', 'ttmPe']].copy()
    # 当前接口返回日期字符串；兼容旧接口的毫秒时间戳。
    if pd.api.types.is_numeric_dtype(data['date']):
        data['date'] = pd.to_datetime(data['date'], unit='ms', utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    else:
        data['date'] = pd.to_datetime(data['date'], errors='coerce')
    data['pe'] = pd.to_numeric(data['ttmPe'], errors='coerce')
    data = data.dropna(subset=['date', 'pe'])
    data = data[(data.pe > 0) & (data.pe < float('inf'))]
    return data[['date', 'pe']].drop_duplicates('date', keep='last').sort_values('date')


def summarize(history, as_of, years=5):
    """按所选年限比较月度样本，禁止未来数据或冒充完整区间。"""
    if years not in (3, 5, 10):
        raise ValueError('估值参考年限只能选择3、5、10年')
    end = pd.Timestamp(as_of).normalize()
    # 先截断到当时可见日期，再每月保留最新快照；不能先按月去重，
    # 否则后来的更新会抹掉月内早期可见的数据，产生前视偏差。
    past = history[history.date <= end].sort_values('date')
    past = past.drop_duplicates('date', keep='last')
    past = past.loc[~past.date.dt.to_period('M').duplicated(keep='last')]
    if past.empty:
        return {'error': '该行情日期之前没有估值记录'}
    latest = past.iloc[-1]
    window = past[past.date >= latest.date - pd.DateOffset(years=years)]
    result = {'metric': 'PE', 'value': float(latest.pe),
              'date': latest.date.date().isoformat(), 'source': SOURCE,
              'source_url': SOURCE_URL, 'frequency': 'monthly',
              'window_years': years, 'samples': len(window),
              'history_start': window.iloc[0].date.date().isoformat(),
              'percentile': None}
    if (end - latest.date).days > 35:
        result['error'] = '估值超过正常月度更新间隔，暂不判断区间'
    elif len(window) < years * 12 or (latest.date - window.iloc[0].date).days < years * 365 - 35:
        result['error'] = f'估值历史不足{years}年，暂不判断区间'
    else:
        # 中秩分位：重复值取中间位置，完全相同的样本为50%。
        result['percentile'] = round(float(((window.pe < latest.pe).sum()
                                           + .5 * (window.pe == latest.pe).sum()) / len(window) * 100), 2)
    return result


def get_valuation(item, as_of, force=False):
    if item.get('valuation') is not None:
        return item['valuation']
    code = item.get('valuation_index') or INDEX_CODES.get(item.get('index'))
    if not code:
        return {'error': '尚未配置对应指数的估值来源'}
    directory = Path(CACHE_DIR)
    directory.mkdir(exist_ok=True)
    path = directory / ('valuation_' + code.replace('.', '_') + '.csv')
    meta_path = path.with_suffix('.json')
    history = pd.DataFrame(columns=['date', 'pe'])
    if path.exists():
        history = pd.read_csv(path, parse_dates=['date'])
    try:
        metadata = json.loads(meta_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        metadata = {}
    # 同一行情日期不重复拉取；月度资料休市期间保持有效。
    refresh = force or history.empty or metadata.get('checked_as_of') != str(as_of)
    warning = None
    if refresh:
        try:
            import akshare.stock_feature.stock_a_pe_and_pb as upstream
            js = upstream.py_mini_racer.MiniRacer()
            js.eval(upstream.hash_code)
            token = js.call('hex', datetime.now().date().isoformat()).lower()
            cookies = upstream.get_cookie_csrf(url='https://legulegu.com/stockdata/sz50-ttm-lyr')
            response = requests.get('https://legulegu.com/api/stockdata/index-basic-pe',
                                    params={'token': token, 'indexCode': code}, timeout=20, **cookies)
            response.raise_for_status()
            fresh = normalize_history(response.json().get('data', []))
            if fresh.empty:
                raise ValueError('估值历史为空')
            history = (fresh if history.empty else pd.concat([history, fresh], ignore_index=True)).drop_duplicates('date', keep='last').sort_values('date')
            history.to_csv(path, index=False)
            meta_path.write_text(json.dumps({'checked_as_of': str(as_of), 'source': SOURCE}, ensure_ascii=False), encoding='utf-8')
        except Exception as exc:
            warning = '估值接口暂不可用：' + type(exc).__name__
    if history.empty:
        return {'error': warning or '没有可用估值历史'}
    result = summarize(history, as_of)
    result['windows'] = {str(years): summarize(history, as_of, years) for years in (3, 5, 10)}
    result['index_code'] = code
    if warning:
        result['warning'] = warning + '；使用已缓存记录'
    return result


def attach_valuation(item, as_of):
    if item.get('asset_type', 'broad_etf') != 'broad_etf' or item.get('strategy_mode') == 'us_monthly_trend':
        return item
    if item.get('broad_strategy') in ('trend20','trend16_buffer2'):
        return item
    result = {**item, 'valuation': get_valuation(item, as_of)}
    if item.get('strategy_mode') == 'broad_individual' and not item.get('valuation_history'):
        code = item.get('valuation_index') or INDEX_CODES.get(item.get('index'))
        path = Path(CACHE_DIR) / ('valuation_' + code.replace('.', '_') + '.csv') if code else None
        if path and path.exists():
            history = pd.read_csv(path, parse_dates=['date'])
            history = history[history.date <= pd.Timestamp(as_of)].copy()
            history.date = history.date.dt.strftime('%Y-%m-%d')
            result['valuation_history'] = history.to_dict('records')
    return result


if __name__ == '__main__':
    import config
    import data_fetcher
    for target in config.TARGET_ETFS:
        if target.get('asset_type') == 'broad_etf':
            prices = data_fetcher.fetch_etf_daily(target['code'], start='20100101', end='20500101')
            print(target['name'], json.dumps(get_valuation(target, prices.index[-1].date().isoformat(), force=True), ensure_ascii=False))
