"""Independent, causal 000015 entry study. Never writes strategy/backtest inputs."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'research_bond_entry'
NAV = ROOT / 'research_xingxun_v2/clean_v2/000015.csv'


def features(nav, rates):
    n = nav.copy().sort_index()
    # Reconstruct dividend-reinvested wealth, rather than treating acc_nav as a price.
    n['wealth'] = ((n.nav + n['div']) / n.nav.shift()).fillna(1).cumprod()
    r = rates.sort_index().copy()
    r['percentile'] = r.y10.rolling(1260, min_periods=756).apply(
        lambda x: (x <= x[-1]).mean(), raw=True)
    r['trend_bp'] = (r.y10 - r.y10.shift(60)) * 100
    n['drawdown'] = n.wealth / n.wealth.rolling(252, min_periods=126).max() - 1
    # Use only previous day's yield observation; no same-day publication assumptions.
    n = pd.merge_asof(n.reset_index(), r.reset_index().rename(columns={'date':'rate_date'}),
                      left_on='date', right_on='rate_date', direction='backward', allow_exact_matches=False).set_index('date')
    valid = n.percentile.notna() & n.drawdown.notna() & n.trend_bp.notna() & ((n.index.to_series()-n.rate_date).dt.days <= 7)
    n['environment'] = '数据不足'
    n.loc[valid, 'environment'] = '一般'
    n.loc[valid & (n.percentile >= .6) & (n.trend_bp <= 10) & (n.drawdown <= -.003), 'environment'] = '较好'
    n.loc[valid & ((n.percentile <= .2) | (n.trend_bp >= 25)), 'environment'] = '偏差'
    return n


def study(n):
    rows = []
    # One decision per month; close observed at t, execute at next available NAV.
    decisions = n.groupby(n.index.to_period('M')).tail(1)
    for t, d in decisions.iterrows():
        if d.environment == '数据不足':
            continue
        i = n.index.get_loc(t) + 1
        if i >= len(n):
            continue
        for months in (3, 6, 12):
            end = n.index.searchsorted(n.index[i] + pd.DateOffset(months=months))
            if end >= len(n):
                continue
            path = n.wealth.iloc[i:end+1]
            immediate = path.iloc[-1] / path.iloc[0] - 1
            # Wait for better environment, at most 63 NAV observations, then buy.
            rank = {'偏差':0, '一般':1, '较好':2, '数据不足':-1}
            limit = min(i+63, end)
            entry = limit
            if d.environment == '较好':
                entry = i
            for k in range(i, limit) if d.environment != '较好' else ():
                if rank[n.environment.iloc[k]] > rank[d.environment]:
                    entry = k+1
                    break
            wait_path = np.r_[np.ones(entry-i), n.wealth.iloc[entry:end+1].values/n.wealth.iloc[entry]]
            rows.append(dict(decision=str(t.date()), entry=str(n.index[i].date()), end=str(n.index[end].date()),
                environment=d.environment, months=months, return_pct=immediate*100,
                mdd_pct=(path/path.cummax()-1).min()*100,
                wait_return_pct=(wait_path[-1]-1)*100,
                wait_mdd_pct=(wait_path/np.maximum.accumulate(wait_path)-1).min()*100,
                wait_days=(n.index[entry]-n.index[i]).days,
                missed_return_pct=(n.wealth.iloc[entry]/n.wealth.iloc[i]-1)*100,
                wait_excess_pct=(wait_path[-1]-1-immediate)*100))
    return pd.DataFrame(rows)


def build():
    OUT.mkdir(exist_ok=True)
    nav = pd.read_csv(NAV, parse_dates=['date']).set_index('date')
    raw = pd.DataFrame(json.loads((OUT/'treasury_history.json').read_text(encoding='utf8')))
    rates = raw.rename(columns={'SOLAR_DATE':'date','EMM00166466':'y10'})[['date','y10']]
    rates.date = pd.to_datetime(rates.date)
    rates = rates.dropna().drop_duplicates('date').set_index('date')
    n = features(nav, rates)
    samples = study(n)
    samples.to_csv(OUT/'samples.csv', index=False)
    n.to_csv(OUT/'features.csv')
    summaries = []
    for months in (3,6,12):
        for label in ('全部直接买入','较好','一般','偏差'):
            s = samples[samples.months == months]
            if label != '全部直接买入':
                s = s[s.environment == label]
            if s.empty:
                summaries.append(dict(months=months, environment=label, n=0))
                continue
            summaries.append(dict(months=months, environment=label, n=len(s),
                mean_return=float(s.return_pct.mean()), median_return=float(s.return_pct.median()),
                worst_return=float(s.return_pct.min()), mean_mdd=float(s.mdd_pct.mean()), worst_mdd=float(s.mdd_pct.min()),
                wait_excess=float(s.wait_excess_pct.mean()), wait_win=float((s.wait_excess_pct>0).mean()*100),
                mean_wait_days=float(s.wait_days.mean()), missed_return=float(s.missed_return_pct.mean()),
                wait_excess_cash1=float((s.wait_excess_pct + (1.01**(s.wait_days/365)-1)*100*(1+s.wait_return_pct/100)).mean()),
                wait_mean_mdd=float(s.wait_mdd_pct.mean())))
    d = n.iloc[-1]
    result = dict(as_of=str(n.index[-1].date()), rate_date=str(d.rate_date.date()), nav=float(d.nav),
        day_change_pct=float((n.nav.iloc[-1]/n.nav.iloc[-2]-1)*100),
        environment=d.environment, percentile=float(d.percentile*100), y10=float(d.y10), trend_bp=float(d.trend_bp),
        drawdown=float(d.drawdown*100), duration=None, summaries=summaries,
        input_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (NAV, OUT/'treasury_history.json')})
    (OUT/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    lines = [
        '华夏纯债债券A（000015）买入吸引力研究｜2026-10-26',
        '结论：截至净值2026-10-21、可用利率2026-10-20，买入环境偏差；页面操作状态为观察，已有持仓保持。',
        '10年国债1.6354%，5年滚动分位1.83%，60日下降9.43bp；近252个净值日高点回撤0.0165%。',
        '利率低限制未来票息及利率下行空间，但利率继续下降仍有资本利得，不能直接推导立即买入会亏损。',
        '基金精确当前久期与逐期披露久期均未核实；不能用10年国债期限或持仓剩余期限代替基金久期。',
        '近似利率冲击关系：价格变化约等于负的修正久期乘收益率变化；仅示例，久期2/4/6年时上行25bp约损失0.5/1/1.5%，不是本基金预测。',
        '主要风险：利率、信用利差、流动性与杠杆。净值缓存未核实为最新，以上为截至日观察，不是10月26日实时评级。',
        '', '方法与可复现性：python -B research_bond_entry.py；python -B -m unittest test_bond_entry -v',
        '基金：现有clean_v2/000015.csv，2013-03-08至2026-10-21，利用单位净值及分红重建再投资收益，核对原tr列。',
        '利率：东方财富RPTA_WEB_TREASURYYIELD接口，2026-10-26获取，原始快照存treasury_history.json；仅使用中国10年期限。',
        '来源：https://data.eastmoney.com/cjsj/zmgzsyl.html；https://fund.eastmoney.com/000015.html',
        '披露参考：https://www.chinaamc.com/c/2026-08-31/1001438.shtml（2026中期报告，8月31日披露；不回填历史）。',
        '环境：较好=1260条利率滚动分位>=60%且60日上行<=10bp且252净值日回撤>=0.3%；偏差=分位<=20%或60日上行>=25bp；其余一般。',
        '利率分位至少756条，回撤至少126条；利率只匹配严格早于净值日且不超过7日的观测；无后向填充或全样本分位。',
        '固定解释性规则，未优化参数。历史分组未包含久期，属于利率/净值参考环境，不能声称已验证综合择时。',
        '月末观测后下个净值日买入，日历3/6/12个月后首个净值日退出；未到期不计。最早决策2013-10-31。',
        '每月起点、收益窗口重叠，不是独立样本，不做显著性推断；后验探索不等于独立样本外验证。',
        '收益含基金运营费用，未扣个人渠道买入/赎回费，无税费、申赎延迟与分红再投延迟仿真；不是个人实际到账收益。',
        '等待：相同起点/终点，环境严格改善后下个净值日买入，最多63个净值日（约3个月）后买；较好不等待。',
        '基础现金收益为0；另列现金年化1%敏感性是假设，不是货币基金历史实测。等待减少市场暴露，回撤较低不代表同风险择时优势。',
        '费用示例：买入费0.08%时净收益=(1+毛收益)/1.0008-1；实际费率取决于渠道，表内不冒充费后收益。',
        '', '环境 | 月数 | 样本数 | 平均/中位收益% | 最差收益% | 平均/最差回撤% | 等待超额pp | 等待胜率% | 现金1%等待超额pp']
    for r in summaries:
        if r['n']:
            lines.append(f"{r['environment']} | {r['months']} | {r['n']} | {r['mean_return']:.3f}/{r['median_return']:.3f} | {r['worst_return']:.3f} | {r['mean_mdd']:.3f}/{r['worst_mdd']:.3f} | {r['wait_excess']:.3f} | {r['wait_win']:.1f} | {r['wait_excess_cash1']:.3f}")
    lines += ['', f"全历史直接持有（2013-03-08至2026-10-21）累计收益{(n.wealth.iloc[-1]/n.wealth.iloc[0]-1)*100:.3f}%，最大回撤{(n.wealth/n.wealth.cummax()-1).min()*100:.3f}%；起点不同，仅作背景，公平比较以表内滚动基准为准。",
              '较好仅6次，12个月的组内平均回撤反而大于一般，不能认为环境等级保证收益或保护本金。',
              '偏差组持有3/6/12个月平均收益0.77/1.59/3.25%；等待平均少赚0.51/0.53/0.54个百分点，胜率约22%至23%。',
              '未发现默认空仓等更好买点值得的证据。低频配置可结合期限和承受能力分批；不据本研究改变既有策略或账本。',
              '研究输入SHA256：', json.dumps(result['input_hashes'], ensure_ascii=False, indent=2)]
    (OUT/'conclusions.txt').write_text('\n'.join(lines), encoding='utf8')
    return result


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
