"""黄金空仓等待回撤，反弹接近买入时参考高点卖出；不改App。"""
import json
from pathlib import Path
import pandas as pd
from research_sector_trend import backtest


def rebound_targets(close,entry=.10,recovery=.02):
    high=close.rolling(250,min_periods=250).max()
    held=False;reference=None;result=[]
    for price,peak in zip(close,high):
        if held and price>=reference*(1-recovery):held=False
        elif not held and pd.notna(peak) and price<=peak*(1-entry):
            held=True;reference=float(peak)
        result.append(held)
    return pd.Series(result,index=close.index,dtype=bool)


def main():
    data=pd.read_csv('data_cache/etf_518850_tencent.csv',index_col='date',parse_dates=True).sort_index().loc[:'2026-09-30']
    output=Path('results/gold_rebound');output.mkdir(parents=True,exist_ok=True)
    results={};lines=['# 黄金：空仓等待回撤研究','',
        '用户用途：寻找买卖点，平时允许空仓。本轮先检查价格回撤，不把回撤等同于低估。',
        '参考高点为买入信号当天近250交易日最高收盘价；回撤5%/10%/15%分别买入，反弹至该高点的98%卖出。',
        '买入后固定参考高点，不让旧高点滚出窗口导致自动降低卖出目标。无止损、不加仓，未回到目标就继续持有。',
        '预先固定三档，非优化；10万元初始现金、100份整数，单边0.1%滑点、佣金万一最低5元；收盘信号下一交易日开盘执行。',
        '共同区间2021-06-17至2026-09-30，一字涨跌停采用10%成交限制近似，现金收益0、末日不强制卖出。','',
        '|方案|收益|最大回撤|持有时间占比|完成交易轮数|','|---|---:|---:|---:|---:|']
    candidates={'长期持有':pd.Series(True,index=data.index)}
    candidates.update({f'回撤{int(p*100)}%买入':rebound_targets(data.close,p) for p in (.05,.10,.15)})
    for label,target in candidates.items():
        stats,curve,trades=backtest(data,target,250,len(data),limit_pct=.10)
        round_days=[];buy_date=None
        for t in trades:
            if t['action']=='买入':buy_date=pd.Timestamp(t['date'])
            elif buy_date is not None:
                round_days.append((pd.Timestamp(t['date'])-buy_date).days);buy_date=None
        stats['longest_closed_calendar_days']=max(round_days,default=None)
        stats['open_holding_calendar_days']=(data.index[-1]-buy_date).days if buy_date is not None else None
        stats['last_signal_held']=bool(target.iloc[-1])
        results[label]=stats
        curve.to_csv(output/f'{label}_curve.csv');pd.DataFrame(trades).to_csv(output/f'{label}_trades.csv',index=False)
        lines.append(f"|{label}|{stats['return_pct']}%|{stats['max_drawdown_pct']}%|{stats['invested_pct']}%|{stats['closed_round_trips']}|")
    lines+=['','这是完整账户按收盘计算的回撤，空仓时间较多可能令回撤看起来较小，不能据此证明入场更准确。',
            '无止损可能长期被套；卖出目标固定可避免滚动高点下降带来的伪反弹。样本只有一只ETF六年左右，涨势阶段较多，不能概括黄金长期规律。',
            '这一候选不适合仅凭收益排名直接采用；需继续研究更长历史、实际持有期风险及退出条件。App不改动。']
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    for label,stats in results.items():print(label,stats)


if __name__=='__main__':main()
