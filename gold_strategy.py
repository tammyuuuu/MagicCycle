"""黄金：过热减仓、冷却加仓，行情条件不设固定目标仓位。"""
import math
import pandas as pd
from strategy_config import STRATEGY_CONFIG

STRATEGY_VERSION='gold_heat_actions_v2'


def stages(close, threshold=.15, cooling=.05, return_window=20, ma_window=60, min_history=120):
    if not 0<=cooling<threshold:raise ValueError('冷却阈值须小于过热阈值')
    for n in (return_window,ma_window,min_history):
        if int(n)!=n or n<2:raise ValueError('周期须为至少2的整数')
    minimum=max(min_history,ma_window,return_window+1)
    rise=close.pct_change(return_window,fill_method=None)
    deviation=close/close.rolling(ma_window,min_periods=ma_window).mean()-1
    hot=(rise>=threshold)&(deviation>=threshold)
    cold=(rise<=cooling)&(deviation<=cooling)
    heated=False;targets=[]
    for i in range(len(close)):
        if cold.iloc[i]:heated=False
        if hot.iloc[i]:heated=True
        targets.append(0. if i+1<minimum else .5 if heated else 1.)
    return pd.DataFrame({'target':targets,'rise':rise,'deviation':deviation,'hot':hot,'cold':cold},index=close.index)


def analyze_latest(df,profile=None):
    p={**STRATEGY_CONFIG['macro_asset']['gold'],**(profile or {})}
    d=df.sort_index().copy();d=d[~d.index.duplicated(keep='last')]
    d['close']=pd.to_numeric(d.close,errors='coerce')
    d=d[d.close.map(lambda v:pd.notna(v) and math.isfinite(v) and v>0)]
    if d.empty:raise ValueError('缺少有效收盘行情')
    s=stages(d.close,p['heat_threshold'],p['cooling_threshold'],p['return_window'],p['ma_window'],p['min_history'])
    current=s.iloc[-1];previous=float(s.target.iloc[-2]) if len(s)>1 else 0.
    ready=len(s)>=max(p['min_history'],p['ma_window'],p['return_window']+1)
    target=float(current.target)
    fresh_add=ready and target==1 and previous==.5
    if not ready:status,reason='watch','历史数据不足，先观察。'
    elif target==.5 and previous==1:
        status,reason='reduce','短期涨幅和均线偏离均达到过热线，下一交易日减半一次；未持有无需卖出。'
    elif target==1 and previous!=1:
        status='add' if fresh_add else 'buy'
        reason='短期涨幅与均线偏离均已冷却，可按本期预算加仓；未持有可买入，不要求之前卖出过。' if fresh_add else '指标已就绪，未进入过热阶段，可按计划开始配置；已有持仓不重复买入。'
    elif target==.5:
        status,reason='watch','仍处于过热后的减仓阶段，不重复减半，等待两个指标都冷却；未持有先不追买。'
    else:status,reason='watch','未出现新的买卖信号，已有持仓保持；本策略允许普通波动中长期持有。'
    def number(value):return float(value) if pd.notna(value) else None
    return {'status':status,'action':{'add':'加仓','buy':'买入','reduce':'减仓','watch':'观察'}[status],
            'reason':reason,'strategy_version':STRATEGY_VERSION,
            'return_20d_pct':number(current.rise*100),'deviation60_pct':number(current.deviation*100),
            'heat_phase':target==.5 if ready else None,'hot_now':bool(current.hot),'cold_now':bool(current.cold),
            'fresh_add':fresh_add,'insufficient_history':not ready,'profile':p}
