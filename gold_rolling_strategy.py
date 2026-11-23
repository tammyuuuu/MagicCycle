"""Au99.99 rolling policy from CycleTest heat_repurchase and early_extension."""
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).with_name("gold_au9999")
STRATEGY_VERSION = "au9999_trim5_v1"
FEE = .001
HEAT=[(3,.03),(5,.03),(5,.04),(5,.06),(10,.05),(20,.08)]
SIGNALS=list(product(HEAT,("down","pullback1")))
RULES=[(None,"hold",0.)]+list(product(range(len(SIGNALS)),("recover5","discount10","bounce15"),(.5,1.)))


def confirmations(c):
    signals=[]
    for (days,threshold),method in SIGNALS:
        heat=(c/c.shift(days)-1).ge(threshold) & c.rolling(days+1).count().eq(days+1)
        if method=="down":
            flag=heat.shift(1,fill_value=False) & c.diff().lt(0)
        else:
            # Only reference actual heat-day closes from the preceding three sessions.
            peak=pd.concat([c.where(heat).shift(j) for j in (1,2,3)],axis=1).max(axis=1)
            flag=c.le(.99*peak) & c.rolling(4).count().eq(4)
        signals.append(flag & ~flag.shift(1,fill_value=False))
    return np.column_stack([np.zeros(len(c),bool),*signals])


class Market:
    def __init__(self,c):
        self.c=c
        self.price=c.to_numpy()
        self.year=c.index.year
        self.valid=c.notna().to_numpy()
        self.confirmed=confirmations(c)
        self.flags=np.roll(self.confirmed,1,axis=0)
        self.flags[0]=False
        self.feature=np.array([0 if i is None else i+1 for i,_,_ in RULES])
        self.fraction=np.array([f for _,_,f in RULES])
        self.method=np.array([m for _,m,_ in RULES])
        self.limit=np.array([{"hold":0,"recover5":5,"discount10":10,"bounce15":15}[m] for m in self.method])

    def select(self,year):
        start, end, fee = year-5, year-1, FEE
        # Vector accounts for training; single continuous account for a frozen year-by-year policy.
        keys=np.arange(len(RULES))
        n=len(keys)
        rows=np.flatnonzero((self.year>=start)&(self.year<=end)&self.valid)
        initial=1/(self.price[rows[0]]*(1+fee))
        qty=np.full(n,initial)
        cash=np.zeros(n)
        origin=np.zeros(n,dtype=int)
        sale=np.zeros(n)
        trough=np.full(n,np.inf)
        at=np.zeros(n,dtype=int)
        before=qty.copy()
        best=np.ones(n)
        for j,i in enumerate(rows):
            p=self.price[i]
            active=origin!=0
            available=self.valid[i-1]
            prev=self.price[i-1]
            # Decision only uses the previous close or the previously scheduled expiry.
            if available: trough=np.minimum(trough,prev)
            recover=(prev>sale) | ((self.method[origin]=="discount10") & (prev<=.98*sale))
            bounce=(self.method[origin]=="bounce15") & (prev>=1.01*trough)
            due=j-at>=self.limit[origin]
            buy=active & available & (recover|bounce|due)
            sell=~active & self.flags[i,self.feature[keys]] & (j>0)
            deal=np.zeros(n)
            if np.any(buy):
                deal[buy]=cash[buy]/(1+fee)
                qty[buy]+=deal[buy]/p
                cash[buy]=0.
                ratio=qty[buy]/before[buy]
                best[buy]=np.maximum(best[buy],ratio)
                origin[buy]=0
            if np.any(sell):
                before[sell]=qty[sell]
                deal[sell]=-qty[sell]*self.fraction[keys[sell]]*p
                qty[sell]+=deal[sell]/p
                cash[sell]=-deal[sell]*(1-fee)
                origin[sell]=keys[sell]
                sale[sell]=p
                trough[sell]=p
                at[sell]=j
            wealth=qty*p+cash
        marked=np.where(origin!=0,wealth/(before*p),1.)
        score=wealth/np.maximum(best,marked)
        return int(np.round(score,12).argmax())

def rule_text(key):
    signal, method, fraction = RULES[key]
    if signal is None:
        return "全年持金。"
    (days, rise), confirm = SIGNALS[signal]
    trigger = "次日收跌" if confirm == "down" else "其后三日内收盘较急涨日最高收盘回落至少1%"
    restore = {"recover5":"高于卖价，最迟第5个交易日",
               "discount10":"高于卖价或不高于卖价的98%，最迟第10个交易日",
               "bounce15":"高于卖价或较离场以来最低收盘反弹至少1%，最迟第15个交易日"}[method]
    return (f"{days}日涨幅达到{rise:.0%}，{trigger}首次确认，下一交易日收盘卖出{fraction:.0%}。"
            f"收盘{restore}回补。价格触发均在下一交易日收盘执行。")


def replay(close):
    """Decide after each close and carry both pending orders and exit terms across years."""
    market = Market(close)
    policy = pd.read_csv(ROOT / "schedule.csv",index_col="year").rule.to_dict()
    def rule(year):
        if year not in policy:
            policy[year] = market.select(year)
        return policy[year]

    dates = close.index
    start = dates.searchsorted(pd.Timestamp("2012-01-01"))
    cash, grams, origin, pending = 1., 0., 0, "initial"
    sale = trough = 0.
    sold_at = None
    records = []
    for i in range(start, len(close)):
        day, price = dates[i], market.price[i]
        key = rule(day.year)
        trade = 0.
        if pending in ("initial","above_sale","discount","bounce","timeout"):
            trade = cash / (1 + FEE)
            grams += trade / price
            cash, origin = 0., 0
        elif pending == "sell":
            trade = -grams * market.fraction[key] * price
            grams += trade / price
            cash = -trade * (1 - FEE)
            sale = trough = price
            origin, sold_at = key, i
        executed, pending = pending, ""
        # During replay the actual next session is known. On the live edge the
        # next weekday suffices for the December/January execution-year boundary.
        next_day = dates[i+1] if i+1 < len(close) else day + pd.offsets.BDay()
        next_key = rule(next_day.year)
        if origin:
            trough = min(trough,price)
            method = market.method[origin]
            if price > sale:
                pending = "above_sale"
            elif method == "discount10" and price <= .98*sale:
                pending = "discount"
            elif method == "bounce15" and price >= 1.01*trough:
                pending = "bounce"
            elif i+1-sold_at >= market.limit[origin]:
                pending = "timeout"
        elif market.confirmed[i,market.feature[next_key]]:
            pending = "sell"
        nav = cash + grams*price
        records.append((day,key,price,nav,grams,cash,grams*price/nav,trade,
                        executed,pending,next_key,origin,sale if origin else None))
    return pd.DataFrame(records,columns=["date","rule","close","nav","grams","cash","weight","signed_trade",
                                          "executed","pending","next_rule","origin","sell_price"]).set_index("date")


def analyze(close, as_of):
    close = close.loc[:as_of]
    details = dict(strategy_version=STRATEGY_VERSION,signal_source="上金所 Au99.99",
                   signal_date=str(close.index[-1].date()) if len(close) else None,
                   signal_price=float(close.iloc[-1]) if len(close) else None)
    if close.empty or close.index[-1] != as_of or as_of.year < 2012:
        return "watch","等待金价","缺少对应交易日的 Au99.99 收盘价或五年训练历史。",dict(details,insufficient_history=True)
    row = replay(close).iloc[-1]
    weight = float(np.clip(row.weight,0,1))
    position = "持金" if weight > .999999 else "空仓" if weight < .000001 else f"部分持金（{weight:.1%}）"
    status, action = "watch",position
    next_action = "下一交易日无买卖提醒。"
    if row.pending == "sell":
        fraction = RULES[row.next_rule][2]
        status, action = ("exit","卖出") if fraction == 1 else ("reduce","减仓")
        next_action = f"下一交易日收盘卖出 ETF 持仓的{fraction:.0%}。"
    elif row.pending:
        status, action = "buy","回补"
        why = {"above_sale":"金价高于卖价","discount":"金价跌至折价线","bounce":"金价自低点反弹","timeout":"达到离场期限"}
        next_action = f"{why[row.pending]}，下一交易日收盘回补此前卖出的 ETF 仓位。"
    reason = f"Au99.99 收盘 {row.close:g} 元/克，策略当前{position}。{next_action}"
    return status, action, reason, dict(details,insufficient_history=False,target_exposure=weight,
            model_position=position,rule_year=as_of.year,annual_rule=int(row.rule),next_rule=int(row.next_rule),
            rule_text=rule_text(row.rule),pending=row.pending,executed=row.executed,origin_rule=int(row.origin),
            sell_price=float(row.sell_price) if row.origin else None)

def backtest_summary():
    stats = pd.read_csv(ROOT / "summary.csv").iloc[0]
    return dict(start=stats.start,end=stats.end,annual_pct=100*stats.cagr,annual_method="CAGR",
                max_drawdown_pct=100*stats.mdd,total_pct=100*stats.strategy,orders=int(stats.trades),
                period_label=f"Au99.99 现货回测 {stats.start} — {stats.end}",
                note="按上金所收盘价模拟，单边费率0.10%，现金无息。")
