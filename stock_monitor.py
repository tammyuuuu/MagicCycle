"""Long-horizon stock research display; no automated trade signals."""
import datetime as dt
import json
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import importlib.util
import pandas as pd

ROOT = Path(__file__).resolve().parent / 'stock_monitor_data'
CIK = {'NVDA':'0001045810','MSFT':'0000789019','GOOGL':'0001652044','BWXT':'0001486957'}
INFO = {
    'NVDA': ('NVIDIA', '中性 DCF $158.38；观察区间 $110–130', '2026-11-06'),
    'MSFT': ('Microsoft', '研究区间 $300–325；现金流需重新核对', '2026-11-06'),
    'GOOGL': ('Alphabet', '研究区间 $210–240；并非独立 DCF', '2026-11-06'),
    'BWXT': ('BWX Technologies', '研究区间 $75–95；须重估业务剥离与净债', '2026-11-06'),
}

def refresh():
    ROOT.mkdir(exist_ok=True)
    for symbol in INFO:
        try:
            response = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',
                params={'period1': 1262304000, 'period2': int(dt.datetime.now(dt.timezone.utc).timestamp()) + 86400, 'interval': '1d', 'events': 'div,splits'},
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
            response.raise_for_status()
            data = response.json()
            result = data['chart']['result'][0]
            if result['meta']['symbol'] != symbol or not result.get('timestamp'):
                raise ValueError('行情校验失败')
            (ROOT / f'{symbol}.json').write_text(json.dumps(data), encoding='utf8')
            raw = ROOT / 'raw'; raw.mkdir(exist_ok=True)
            (raw / f'{symbol}_chart.json').write_text(json.dumps(data), encoding='utf8')
            facts = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK[symbol]}.json', headers={'User-Agent':'Xingxun research research@example.org'}, timeout=20)
            facts.raise_for_status(); facts.json()
            (raw / f'{symbol}_facts.json').write_bytes(facts.content)
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            pass

def reference_price(symbol):
    try:
        spec=importlib.util.spec_from_file_location('stock_reference_engine',Path(__file__).parent/'research_msft_strategy/engine/backtest.py')
        engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine);engine.ROOT=ROOT
        prices,splits,_=engine.load_chart(symbol)
        if symbol=='BWXT': prices=prices.loc['2015-07-01':]
        fundamentals=engine.pit_fundamentals(symbol,splits)
        x=pd.merge_asof(prices.reset_index(names='date'),fundamentals,left_on='date',right_on='effective',direction='backward').set_index('date')
        pe=x.close*x.diluted_shares/x.ttm_net_income
        pe=pe.mask(((x.index-x.period_end).dt.days>190)|((x.index-x.share_end).dt.days>190)|(x.ttm_net_income<=0))
        ref=pe.shift(1).rolling(1260,min_periods=504).median()*x.ttm_net_income/x.diluted_shares
        row=x.iloc[-1]; value=ref.iloc[-1]
        if not pd.notna(pe.iloc[-1]) or not pd.notna(value) or value<=0: return '数据不足'
        return f'${value:.2f}（{x.index[-1].date()}；历史 PE 中位数模型，仅供研究）'
    except (OSError, ValueError, KeyError, IndexError, TypeError, AssertionError):
        return '数据不足'

def render():
    from asset_states import render_rail, render_basis
    cards = []
    for symbol, (name, valuation, valuation_date) in INFO.items():
        try:
            result = json.loads((ROOT / f'{symbol}.json').read_text(encoding='utf8'))['chart']['result'][0]
            timestamps = result['timestamp']
            close = result['indicators']['quote'][0]['close']
            adjusted = result['indicators']['adjclose'][0]['adjclose']
            rows = [(dt.datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date(), c, a)
                    for t, c, a in zip(timestamps, close, adjusted) if c is not None and a is not None and c > 0 and a > 0]
            if symbol == 'BWXT':
                rows = [row for row in rows if row[0] >= dt.date(2015, 7, 1)]
            end, price, _ = rows[-1]
            price_text = f'行情日 {end} · 收盘 ${price:.2f}（缓存行情，是否最新须核对）'
            historical = ''
            backtest = None
            for years in (1, 3, 5):
                try:
                    target = end.replace(year=end.year-years)
                except ValueError:
                    target = end.replace(year=end.year-years, day=28)
                selected = [row for row in rows if row[0] >= target]
                if not selected or (selected[0][0]-target).days > 7:
                    historical += f'<tr><td>{years}年</td><td>数据不足</td><td>数据不足</td><td>数据不足</td></tr>'
                    continue
                values = [row[2] for row in selected]
                peak = values[0]; drawdown = 0.0
                for value in values:
                    peak = max(peak, value); drawdown = min(drawdown, value / peak - 1)
                elapsed = (selected[-1][0] - selected[0][0]).days / 365.2425
                total = values[-1] / values[0] - 1
                annual = ((1 + total) ** (1 / elapsed) - 1) if elapsed > 0 else 0
                historical += f'<tr><td>{years}年</td><td>{annual*100:+.2f}%</td><td>{drawdown*100:.2f}%</td><td>{total*100:+.2f}%</td></tr>'
                if years == 5:
                    backtest = {'annual_pct':annual*100, 'max_drawdown_pct':abs(drawdown)*100,
                                'start':str(selected[0][0]), 'end':str(selected[-1][0]),
                                'period_label':f'长期持有 · {selected[0][0]} — {selected[-1][0]}'}
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            price_text = '行情数据不可用'; backtest = None; historical = ''.join(f'<tr><td>{y}年</td><td>数据不足</td><td>数据不足</td><td>数据不足</td></tr>' for y in (1, 3, 5))
        extra = ('BWXT 回撤25%–30%仅为初步研究参考，不自动触发买入。' if symbol == 'BWXT' else
                 '原 PE 择时策略保留为历史研究，不作为正式买卖信号。' if symbol == 'MSFT' else '')
        available = price_text != '行情数据不可用'
        reference = reference_price(symbol)
        summary = {'asset_type':'stock_long_term', 'status':'buy' if available else 'wait', 'action':'买入/持有' if available else '等待',
                   'reason':'长期持有基准；参考价规则未显示稳定优势，不限制建仓。' if available else '行情数据不足，等待更新。',
                   'decision_basis':[('首次建仓','立即买入并长期持有为研究基准；策略状态独立于个人实际持仓'),
                       ('动态参考价',reference),
                       ('研究估值',f'{valuation_date} · {valuation}；仅供参考，不触发交易'),
                       ('策略规则','立即买入长期持有；参考价不触发交易，持有后不因上涨自动卖出'),
                       ('研究限制',extra or '公司行动和历史价格尚未完成完整交叉核验。')],
                   'details':{'strategy_presentation':{'title':'长期持有 · 近五年','backtest':backtest}}}
        cards.append(f'''<div class="card" data-asset-symbol="{symbol}"><h2>{escape(name)} <span class="muted">{symbol}</span></h2>
        <p>{escape(price_text)}</p><p>参考价 {escape(reference)}</p>{render_rail(summary)}
        <details><summary>查看判断依据</summary>{render_basis(summary)}
        <details><summary>查看各区间回测</summary><div style="overflow-x:auto"><table><thead><tr><th>区间</th><th>年化收益</th><th>最大回撤</th><th>累计收益</th></tr></thead><tbody>{historical}</tbody></table></div>
        <p class="strategy-note">区间以行情最后日期向前计算，采用供应商复权收盘价，股息再投近似；年化按实际天数计算。不含交易成本、税和汇率。历史不足完整区间时显示数据不足；公司行动尚未逐笔交叉验证，历史表现不代表未来。</p></details></details></div>''')
    return ''.join(cards)
