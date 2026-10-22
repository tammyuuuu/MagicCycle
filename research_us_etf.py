"""缓存行情比较：持有、日均线与经典月度趋势；不调参寻优。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_sector_trend import backtest
from us_etf_strategy import targets


def main():
    results = {}
    lines = ['# 标普500与纳指100：买卖条件初步研究', '',
             '腾讯前复权国内ETF行情，人民币场内价格；包含汇率、溢价及跟踪误差，不等同美国指数。',
             '共同评价起点2015-01-01，此前行情仅预热。10万元，100份整数，万一佣金最低5元，单边0.1%滑点，信号后次日开盘；现金收益为0，末日不强制平仓。',
             '一字涨跌停使用10%近似，不模拟临时停牌与盘口排队；前复权不能精确重现历史分红现金/份数。分段从现金重启，不是样本外验证。', '',
             '|ETF|规则|收益|最大回撤|交易次数|前段收益|后段收益|滑点加倍收益|',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for code in ('513500', '513100'):
        data = pd.read_csv(f'data_cache/etf_{code}_tencent.csv', index_col='date', parse_dates=True).sort_index().loc[:'2026-09-30']
        values = data[['open', 'close', 'high', 'low']]
        if data.index.has_duplicates or not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
            raise ValueError('无效行情 ' + code)
        start = int(data.index.searchsorted(pd.Timestamp('2015-01-01')))
        split = start + (len(data) - start) // 2
        rules = {'长期持有': pd.Series(True, index=data.index), '10个月均线': targets(data.close)}
        for days in (60, 120, 200):
            rules[f'{days}日均线'] = data.close > data.close.rolling(days).mean()
        result = {'history_start': str(data.index[0].date()), 'history_end': str(data.index[-1].date()),
                  'days': len(data), 'evaluation_start': str(data.index[start].date()),
                  'split': str(data.index[split].date()), 'rules': {}}
        for label, signal in rules.items():
            def run(a, b, **kwargs):
                return backtest(data, signal, a, b, limit_pct=.10, **kwargs)[0]
            row = {'full': run(start, len(data)), 'first_half': run(start, split),
                   'second_half': run(split, len(data)),
                   'double_slippage': run(start, len(data), slippage=.002)}
            result['rules'][label] = row
            full = row['full']
            lines.append(f"|{code}|{label}|{full['return_pct']}%|{full['max_drawdown_pct']}%|{full['trades']}|{row['first_half']['return_pct']}%|{row['second_half']['return_pct']}%|{row['double_slippage']['return_pct']}%|")
        results[code] = result
    lines += ['', '## 当前选择', '',
              '月度规则交易次数较少，但未稳定优于长期持有。仅作为经典、易解释的试行策略，不称最优。',
              '月收盘重新站上10个月平均月收盘价时提示买入；持续在线上观察；线下提示退出剩余持仓。暂不单独设置加仓/减仓。',
              '使用已结束月份。月末非交易日时，保守等待新月份行情确认，避免从未结束月份读取月收盘；因此可能延迟提示。',
              '实时接口与页面只展示最新状态；历史回测为风险敞口规则，不代表每天重复买卖。当前9月30日溢价公告快照只适用于同日期行情，不假定今后持续，也不构造溢价百分比。', '',
              '[策略来源：Meb Faber月度趋势模型](https://mebfaber.com/timing-model/)',
              '[标普500基金及溢价公告](https://www.bosera.com/column/infoDetail.do?classid=00020002000200020002&infoid=2976810)',
              '[国泰纳指100产品页](https://www.gtfund.com/product/productlist/haiwai/513100/index.html)',
              '[国泰9月30日溢价及停牌公告](https://epaper.cs.com.cn/zgzqb/html/2026-09/30/nw.D110000zgzqb_20260930_1-B044.htm)']
    output = Path('results/us_etf')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    report = '\n'.join(lines) + '\n'
    (output / 'report.md').write_text(report, encoding='utf-8')
    Path('us_etf_strategy_research.md').write_text(report, encoding='utf-8')
    for code, result in results.items():
        print(code, result['days'], result['rules']['10个月均线']['full'])


if __name__ == '__main__':
    main()
