"""半导体估值与趋势比较；固定候选、日期匹配、仅使用当时及此前数据。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_sector_trend import backtest
from research_sector_confirmation import confirmed_signal


def historical_percentile(series, years):
    """滚动日估值中位秩；要求完整年跨度，禁止用未来数据补历史。"""
    series=series.astype(float).where(lambda x:np.isfinite(x)&(x>0)).dropna().sort_index()
    result=pd.Series(np.nan,index=series.index,dtype=float)
    if series.empty:return result
    for i,(date,value) in enumerate(series.items()):
        cutoff=date-pd.DateOffset(years=years)
        if series.index[0]>cutoff:continue
        sample=series.loc[cutoff:date]
        if len(sample)<years*200 or sample.index[0]>cutoff+pd.Timedelta(days=14):continue
        result.iloc[i]=((sample<value).sum()+.5*(sample==value).sum())/len(sample)*100
    return result


def align_percentile(series, dates, lag=1):
    # 禁止把尚未发布的当日估值当成已知；主结果额外延迟一个ETF交易日。
    left=pd.DataFrame({'date':dates})
    right=series.rename('percentile').rename_axis('valuation_date').reset_index()
    merged=pd.merge_asof(left,right,left_on='date',right_on='valuation_date',
                         direction='backward',tolerance=pd.Timedelta(days=10))
    return pd.Series(merged.percentile.to_numpy(),index=dates).shift(lag)


def valuation_signal(percentile, trend=None, entry=30, exit=70):
    held=False;states=[]
    for i,value in enumerate(percentile):
        above=True if trend is None else bool(trend.iloc[i])
        if pd.isna(value):held=False
        elif held and (value>exit or not above):held=False
        elif not held and value<entry and above:held=True
        states.append(held)
    return pd.Series(states,index=percentile.index)


def weekly_signal(daily_signal):
    """周五完成判断后保持到下周；周内不读取尚未结束一周的信号。"""
    return daily_signal.resample('W-FRI').last().reindex(daily_signal.index,method='ffill').eq(True)


def make_rules(data, pe, pb):
    trend=confirmed_signal(data.close,20)
    return {
        '持有不择时':pd.Series(True,index=data.index),
        '20日均线':trend,
        '30日均线':confirmed_signal(data.close,30),
        '20日均线±2%':confirmed_signal(data.close,20,buffer=.02),
        '20日均线每周判断':weekly_signal(trend),
        '30日均线每周判断':weekly_signal(confirmed_signal(data.close,30)),
        'PE估值30/70':valuation_signal(pe),
        'PB估值30/70':valuation_signal(pb),
        '低PE+20日均线':valuation_signal(pe,trend),
        '低PB+20日均线':valuation_signal(pb,trend),
        '20日均线+PE不超90':valuation_signal(pe,trend,entry=90,exit=90),
        '20日均线+PB不超90':valuation_signal(pb,trend,entry=90,exit=90),
    }


def enriched(stats, curve, initial_cash):
    stats=dict(stats)
    years=(curve.index[-1]-curve.index[0]).days/365.25
    stats['annualized_return_pct']=round(((curve.equity.iloc[-1]/initial_cash)**(1/years)-1)*100,2) if years>0 else None
    stats['trades_per_year']=round(stats['trades']/years,1) if years>0 else None
    stats['calmar']=round(stats['annualized_return_pct']/abs(stats['max_drawdown_pct']),2) if stats['max_drawdown_pct']<0 else None
    return stats


def main():
    output=Path('results/sector_valuation_comparison');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 半导体ETF估值与趋势策略比较','',
        '本报告按控制回撤、合理收益、交易频率比较固定候选。不是从大量参数中搜索最高收益。',
        '公开页面取得对应指数等权PE/PB日序列；它与官方PE1/PE2口径不同，未拼接。',
        '估值分位自行按历史滚动计算，不使用网站已经计算好的分位。主结果额外滞后一个ETF交易日，再于信号次日开盘执行。',
        '每周判断为后续探索：周五完成判断、下一交易日开盘执行，周内保持；假日周周五不交易时等下周交易日确认。它不是事前留出验证。',
        '初始10万元、100份整数交易、佣金万一且最低5元，单边滑点0.1%，现金收益0。另检查滑点加倍及1000元本金。',
        '买卖为全进全出，用于比较信号；不等于建议个人资金全进全出。前复权行情不能精确还原分红现金。','']
    for code,index_code,years,limit in [('512760','990001',3,.10),('588170','950125',1,.20)]:
        data=pd.read_csv(f'data_cache/etf_{code}_tencent.csv',parse_dates=['date']).set_index('date').sort_index()
        history=pd.read_csv(f'data_cache/research_etfrun_valuation_{index_code}.csv',parse_dates=['date']).set_index('date').sort_index()
        if data.index.has_duplicates or history.index.has_duplicates:raise ValueError('重复日期')
        if data[['open','close']].isna().any().any() or (data[['open','close']]<=0).any().any():raise ValueError('无效行情')
        pe_raw=historical_percentile(history.equalWeightedPeTtm,years)
        pb_raw=historical_percentile(history.equalWeightedPbTtm,years)
        data=data.loc[:min(history.index[-1],pd.Timestamp('2026-09-30'))]
        pe=align_percentile(pe_raw,data.index);pb=align_percentile(pb_raw,data.index)
        starts=np.flatnonzero((pe.notna()&pb.notna()).to_numpy())
        start=max(120,int(starts[0])+1)
        # 本段前一日必须有估值；所有规则使用同样比较期间。
        while pd.isna(pe.iloc[start-1]) or pd.isna(pb.iloc[start-1]):start+=1
        rules=make_rules(data,pe,pb)
        result={'index_code':index_code,'valuation_window_years':years,
                'comparison_start':str(data.index[start].date()),'comparison_end':str(data.index[-1].date()),
                'valuation_valid_start':str(history[history.equalWeightedPeTtm.notna()].index[0].date()),
                'valuation_end':str(history.index[-1].date()),'valuation_missing_days':int((pe.iloc[start:].isna()|pb.iloc[start:].isna()).sum()),
                'rules':{}}
        split_date=pd.Timestamp('2023-01-01' if code=='512760' else '2026-04-07')
        split=max(start,int(data.index.searchsorted(split_date)))
        lines += [f'## {code}','',f"公平比较：{result['comparison_start']}至{result['comparison_end']}。估值窗口{years}年。",
                  '588170估值不足3年，只能做1年窗口的短期探索；不能把两只ETF或不同估值窗口的结果当作相同样本。' if code=='588170' else '512760历史估值截至2026-07-06，因此各规则都在该日停止。','',
                  '| 规则 | 累计收益 | 最大回撤 | 买卖次数 | 年化收益 |','|---|---:|---:|---:|---:|']
        for label,signal in rules.items():
            full,curve,trades=backtest(data,signal,start,len(data),limit_pct=limit)
            full=enriched(full,curve,100000.)
            check={'full':full,'later_period':backtest(data,signal,split,len(data),limit_pct=limit)[0],
                   'double_slippage':backtest(data,signal,start,len(data),slippage=.002,limit_pct=limit)[0],
                   'small_capital_min5':backtest(data,signal,start,len(data),limit_pct=limit,initial_cash=1000)[0],
                   'small_capital_no_minimum':backtest(data,signal,start,len(data),limit_pct=limit,initial_cash=1000,minimum_fee=0)[0]}
            annual={}
            for year in sorted(set(data.index[start:].year)):
                indices=np.flatnonzero((data.index.year==year)&(np.arange(len(data))>=start))
                annual[str(year)]=backtest(data,signal,int(indices[0]),int(indices[-1])+1,limit_pct=limit)[0]
            check['annual']=annual
            windows=[]
            for begin in pd.date_range(data.index[start].normalize(),data.index[-1],freq='QS'):
                end=begin+pd.DateOffset(years=1)
                if end>data.index[-1]:continue
                a=max(start,int(data.index.searchsorted(begin)));b=int(data.index.searchsorted(end))
                if b-a<200:continue
                stat=backtest(data,signal,a,b,limit_pct=limit)[0]
                windows.append({'start':str(data.index[a].date()),'end':str(data.index[b-1].date()),**stat})
            check['rolling_years']=windows
            if windows:
                check['rolling_summary']={'windows':len(windows),'positive_windows':sum(x['return_pct']>0 for x in windows),
                    'median_return_pct':round(float(np.median([x['return_pct'] for x in windows])),2),
                    'worst_return_pct':min(x['return_pct'] for x in windows),
                    'worst_drawdown_pct':min(x['max_drawdown_pct'] for x in windows)}
            result['rules'][label]=check
            safe=label.replace('/','_').replace('+','_').replace('±','_')
            curve.to_csv(output/f'{code}_{safe}_curve.csv')
            pd.DataFrame(trades).to_csv(output/f'{code}_{safe}_trades.csv',index=False)
            lines.append(f"| {label} | {full['return_pct']}% | {full['max_drawdown_pct']}% | {full['trades']} | {full['annualized_return_pct']}% |")
        # 保守估值延迟以外，再检查不额外延迟及额外延迟2日；所有规则区间保持一致。
        for lag in (0,2):
            alternatives=make_rules(data,align_percentile(pe_raw,data.index,lag),align_percentile(pb_raw,data.index,lag))
            for label in rules:
                result['rules'][label][f'valuation_lag_{lag}']=backtest(data,alternatives[label],start,len(data),limit_pct=limit)[0]
        if code=='512760':
            pe5=align_percentile(historical_percentile(history.equalWeightedPeTtm,5),data.index)
            pb5=align_percentile(historical_percentile(history.equalWeightedPbTtm,5),data.index)
            indices=np.flatnonzero((pe5.notna()&pb5.notna()).to_numpy())
            check_start=max(start,int(indices[0])+1)
            alternatives=make_rules(data,pe5,pb5)
            result['window_sensitivity']={'start':str(data.index[check_start].date()),'rules':{}}
            for label in rules:
                result['window_sensitivity']['rules'][label]={
                    'years3':backtest(data,rules[label],check_start,len(data),limit_pct=limit)[0],
                    'years5':backtest(data,alternatives[label],check_start,len(data),limit_pct=limit)[0]}
            lines+=['','### 3年与5年估值窗口检查','',f'两种窗口都从{data.index[check_start].date()}比较，避免起止日期不同。','',
                    '| 规则 | 3年窗口收益/回撤 | 5年窗口收益/回撤 |','|---|---:|---:|']
            for label,check in result['window_sensitivity']['rules'].items():
                a=check['years3'];b=check['years5']
                lines.append(f"| {label} | {a['return_pct']}% / {a['max_drawdown_pct']}% | {b['return_pct']}% / {b['max_drawdown_pct']}% |")
        lines+=['','| 规则 | 后段收益/回撤 | 滑点加倍收益 | 1000元最低佣金5元收益 | 1000元无最低佣金收益 |','|---|---:|---:|---:|---:|']
        for label,check in result['rules'].items():
            later=check['later_period']
            lines.append(f"| {label} | {later['return_pct']}% / {later['max_drawdown_pct']}% | {check['double_slippage']['return_pct']}% | {check['small_capital_min5']['return_pct']}% | {check['small_capital_no_minimum']['return_pct']}% |")
        lines += ['',f'后段比较从{data.index[split].date()}开始，独立从现金开始。这是历史分段检查，不是未被看过的真正样本外。','']
        results[code]=result
    lines+=['## 可复现性与限制','',
        '运行python -B research_sector_valuation_comparison.py；原始公开页面和解码后的日估值保存在data_cache/research_etfrun_*。',
        '网站未提供每条历史记录最初发布时间或修订版本，因此无法排除历史财务数据修订。额外延迟检查仅处理时间敏感性，不能消除历史修订偏差。',
        '等权估值与ETF指数权重不同，需明确区分；估值样本少、缺乏原始发布时间记录限制结论强度。',
        '只比较现存两只ETF存在标的选择偏差；季度起点的一年窗口互相重叠，不能作为独立显著性样本。',
        '阈值30/70、90以及均线20/30日是研究候选，前序研究已经查看过部分历史；不存在严格未被触及的留出样本。',
        '盈亏以日收盘衡量，最大回撤不是盘中最大跌幅。一字涨停不买、一字跌停不卖，未模拟部分成交与排队。',
        '本金敏感性检查假设单次全部操作1000元，并非每月定投1000元；佣金最低收费取决于个人账户，不能视为统一市场规定。',
        '本研究不修改App当前决策。', '',
        '公开估值来源：[990001](https://www.etf.run/index/CSI/990001)、[950125](https://www.etf.run/index/CSI/950125)。']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    for code,result in results.items():
        print(code,result['comparison_start'],result['comparison_end'],'missing',result['valuation_missing_days'])
        for name,check in result['rules'].items():print(name,check['full'])
    print('Saved',output/'report.md')


if __name__=='__main__':main()
