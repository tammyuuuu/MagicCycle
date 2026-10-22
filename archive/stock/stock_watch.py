"""宇树研究观察模式：财报快照与价格描述，不生成交易信号。"""
SOURCE = 'https://file.finance.sina.com.cn/211.154.219.97:9494/MRGG/CNSESH_STOCK/2026/2026-8/2026-08-18/12500216.PDF'
SNAPSHOT = {'period': '2026年上半年', 'published': '2026-08-18',
            'revenue_yoy_pct': 48.54, 'adjusted_profit_yoy_pct': -19.34,
            'audited': False, 'source': SOURCE}


def analyze(item, date, metrics, details):
    available = item['code'] == '688836' and date >= SNAPSHOT['published']
    rows = [('营收增长', '上半年营收同比增长48.54%' if available else '尚无已公布的财报快照'),
            ('扣非利润', '上半年扣非利润同比下降19.34%，盈利仍承压' if available else '尚无已公布的财报快照')]
    ma = metrics.get('ma20')
    trend = '不足20个交易日，暂不能比较' if ma is None else ('收盘价高于20日均价' if metrics['price'] > ma else '收盘价不高于20日均价，趋势尚未改善')
    rows.append(('价格趋势', trend + '；仅作观察，不触发买卖'))
    details.update(strategy_mode='research_watch', strategy_version='stock_watch_v1',
                   enabled_decisions=['watch'], legacy=None, parameters={},
                   insufficient_history=ma is None, fundamental_data_available=available,
                   financial_snapshot=dict(SNAPSHOT) if available else None)
    return {'symbol': item['code'], 'name': item['name'], 'asset_type': 'stock',
            'subtype': None, 'date': date, 'status': 'watch', 'action': '研究观察',
            'reason': '先观察营收、扣非利润和价格趋势；买卖条件尚未确定，不自动给出交易信号。',
            'risk_level': 'normal', 'metrics': metrics, 'details': details,
            'decision_basis': rows,
            'decision_conditions': [{'condition': title, 'result': text, 'met': None} for title, text in rows]}
