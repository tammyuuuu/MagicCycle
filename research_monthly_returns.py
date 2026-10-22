"""描述性研究：月跌幅出现后，以下一交易日开盘价观察后续收益。"""
import json
from pathlib import Path
import pandas as pd

AS_OF = '2026-10-03'
TARGETS = {'510300':'沪深300', '510500':'中证500', '588000':'科创50'}


def observations(code):
    data = pd.read_csv(f'data_cache/etf_{code}_tencent.csv', parse_dates=['date']).set_index('date').sort_index()
    data = data[data.index < pd.Timestamp(AS_OF).replace(day=1)]
    monthly = data.groupby(data.index.to_period('M')).agg(close=('close','last'))
    monthly['date'] = data.index.to_series().groupby(data.index.to_period('M')).last()
    monthly['return'] = monthly.close.pct_change()
    rows=[]
    for period, row in monthly.iterrows():
        if pd.isna(row['return']):continue
        next_days = data[data.index > row.date]
        if next_days.empty:continue
        entry_date=next_days.index[0];entry=float(next_days.iloc[0].open)
        event={'month':str(period),'monthly_return':float(row['return']),'entry_date':str(entry_date.date())}
        for horizon in (1,3,6,12):
            target=period+horizon
            if target not in monthly.index:continue
            exit_date=monthly.loc[target,'date']
            event[f'return_{horizon}m']=float(monthly.loc[target,'close']/entry-1)
            path=data.loc[entry_date:exit_date,'close']
            event[f'worst_{horizon}m']=float(min(0,path.min()/entry-1))
        rows.append(event)
    return data, pd.DataFrame(rows)


def stats(events, threshold, horizon):
    selected=events if threshold is None else events[events.monthly_return <= -threshold]
    selected=selected.dropna(subset=[f'return_{horizon}m'])
    if selected.empty:return {'count':0}
    future=selected[f'return_{horizon}m']*100
    return {'count':len(selected),'mean_pct':round(float(future.mean()),2),
            'median_pct':round(float(future.median()),2),
            'positive_pct':round(float((future>0).mean()*100),1),
            'worst_forward_pct':round(float(future.min()),2),
            'median_further_drop_pct':round(float(selected[f'worst_{horizon}m'].median()*100),2)}


def first_touch(data, threshold=.05):
    """每日收盘首次达到当月跌幅；次日开盘执行，避免月末信息泄露。"""
    monthly=data.groupby(data.index.to_period('M')).agg(close=('close','last'))
    monthly['date']=data.index.to_series().groupby(data.index.to_period('M')).last()
    rows=[]
    for period in monthly.index[1:]:
        previous=monthly.loc[period-1,'close'] if period-1 in monthly.index else None
        if previous is None:continue
        days=data[data.index.to_period('M')==period]
        signals=days[days.close/previous-1 <= -threshold]
        if signals.empty:continue
        signal_date=signals.index[0];following=data[data.index>signal_date]
        if following.empty:continue
        entry_date=following.index[0];entry=float(following.iloc[0].open)
        event={'month':str(period),'signal_date':str(signal_date.date()),'entry_date':str(entry_date.date()),
               'monthly_return':float(signals.iloc[0].close/previous-1)}
        for horizon in (1,3,6,12):
            target=period+horizon
            if target not in monthly.index:continue
            exit_date=monthly.loc[target,'date']
            event[f'return_{horizon}m']=float(monthly.loc[target,'close']/entry-1)
            path=data.loc[entry_date:exit_date,'close']
            event[f'worst_{horizon}m']=float(min(0,path.min()/entry-1))
        rows.append(event)
    return pd.DataFrame(rows)


def main():
    output=Path('results/monthly_drop_research');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 宽基月跌幅研究','',f'研究日期：{AS_OF}。仅使用截至2026年9月的完整月份。',
      '','使用本地腾讯前复权ETF行情；信号月结束后，以下一交易日开盘价买入，观察1／3／6／12个月后的月末价格。',
      '不含手续费、滑点和现金收益；不是完整策略回测。样本可能重叠，胜率不代表独立试验；不据此选出最优阈值。',
      '另检验每日收盘首次触及当月跌5%的情况，每月只取一次，仍以下一交易日开盘价执行。','']
    for code,name in TARGETS.items():
        data,events=observations(code)
        distribution=events.monthly_return.mul(100).quantile([.1,.25,.5,.75,.9]).round(2).to_dict()
        result={'start':str(data.index[0].date()),'end':str(data.index[-1].date()),
                'months':len(events),'distribution':distribution,'groups':{}}
        lines += [f'## {name}', '',f"行情覆盖{result['start']}至{result['end']}；有下一交易日的完整月收益样本{len(events)}个。",'']
        lines += ['| 月跌幅条件 | 6个月样本 | 6个月平均收益 | 6个月中位收益 | 6个月上涨比例 | 期间继续下跌中位数 |','|---|---:|---:|---:|---:|---:|']
        for threshold in (None,.03,.05,.08,.10):
            label='全部月份' if threshold is None else f'下跌至少{threshold*100:g}%'
            group={str(h):stats(events,threshold,h) for h in (1,3,6,12)}
            group['before_2021_6m']=stats(events[events.month<'2021-01'],threshold,6)
            group['since_2021_6m']=stats(events[events.month>='2021-01'],threshold,6)
            result['groups'][label]=group
            x=group['6']
            if x['count']:lines.append(f"| {label} | {x['count']} | {x['mean_pct']}% | {x['median_pct']}% | {x['positive_pct']}% | {x['median_further_drop_pct']}% |")
            else:lines.append(f'| {label} | 0 | — | — | — | — |')
        events.to_csv(output/f'{code}_events.csv',index=False)
        touches=first_touch(data)
        result['first_touch_5pct']={str(h):stats(touches,None,h) for h in (1,3,6,12)}
        touches.to_csv(output/f'{code}_first_touch_5pct.csv',index=False)
        touch=result['first_touch_5pct']['6']
        lines+=['',f"每日收盘首次触及当月跌5%：6个月完整样本{touch['count']}次，平均收益{touch['mean_pct']}%，中位收益{touch['median_pct']}%，上涨比例{touch['positive_pct']}%。"]
        results[code]=result
        lines+=['']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Research saved: '+str(output/'report.md'))


if __name__=='__main__':main()
