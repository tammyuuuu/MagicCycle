# -*- coding: utf-8 -*-
"""第一轮：资产相关性与互补性研究。

数据只用 clean/ 下的场外基金净值（含分红再投资的总收益指数）。
不使用 ETF 价格，也不把指数历史冒充基金历史。

四个面板：
    A. 长期股票+黄金（2013-08-22 起，4 只）
    B. 全资产（2019-03-08 起，含债券与货币基金 8 只）

输出目录 research_xingxun_v1/out_corr/
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "out_corr"
OUT.mkdir(exist_ok=True)

LABEL = {
    "000216": "Gold", "160706": "CSI300", "160119": "CSI500", "090010": "Dividend",
    "006484": "Bond1-3Y", "003358": "Bond7-10Y", "006989": "ShortBond", "000198": "MoneyFund",
}
LONG = ["000216", "160706", "160119", "090010"]
FULL = ["160706", "160119", "090010", "000216", "006484", "003358", "006989", "000198"]
START = {"long": "2013-08-22", "full": "2019-03-08"}
END = "2026-10-21"


def load_tr(code):
    d = pd.read_csv(CLEAN / f"{code}.csv", parse_dates=["date"]).set_index("date")
    return d["tr"].astype(float)


def load_ret(code):
    d = pd.read_csv(CLEAN / f"{code}.csv", parse_dates=["date"]).set_index("date")
    return d["ret"].astype(float)


def panel(codes, start=START["long"], end=END):
    """按共同可得日期对齐，收益用总收益指数计算。"""
    tr = pd.DataFrame({c: load_tr(c) for c in codes})
    tr = tr[(tr.index >= pd.Timestamp(start)) & (tr.index <= pd.Timestamp(end))]
    tr = tr.dropna(how="any")
    return tr


def resample_ret(tr, rule):
    last = tr.resample(rule).last()
    return last.pct_change(fill_method=None).dropna(how="all")


def corr_table(tr, name):
    out = {}
    for rule, tag in (("B", "daily"), ("W-FRI", "weekly"), ("ME", "monthly")):
        r = resample_ret(tr, rule) if rule != "B" else tr.pct_change(fill_method=None).dropna(how="all")
        c = r.corr()
        c.round(4).to_csv(OUT / f"corr_{tag}_{name}.csv", encoding="utf-8-sig")
        out[tag] = c
        print(f"[{name}] {tag} corr ({len(r)} obs)")
        print(c.round(3).to_string())
    return out


def heatmap(c, title, path):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    im = ax.imshow(c.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(c)), c.columns, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(c)), c.index, fontsize=9)
    for i in range(len(c)):
        for j in range(len(c)):
            ax.text(j, i, f"{c.values[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="black" if abs(c.values[i, j]) < 0.6 else "white")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def rolling_corr(tr, pairs, windows=(60, 120, 250), name="long"):
    ret = tr.pct_change(fill_method=None).dropna(how="all")
    fig, axes = plt.subplots(len(windows), 1, figsize=(11, 3.0 * len(windows)), sharex=True)
    rows = []
    for ax, w in zip(axes, windows):
        for a, b in pairs:
            rc = ret[a].rolling(w).corr(ret[b])
            ax.plot(rc.index, rc, lw=1.1, label=f"{LABEL[a]}-{LABEL[b]}")
            rows.append(pd.DataFrame({"window": w, "pair": f"{LABEL[a]}-{LABEL[b]}",
                                      "date": rc.index, "corr": rc.values}))
        ax.axhline(0, color="grey", lw=.8)
        ax.axhline(0.8, color="red", lw=.6, ls="--")
        ax.set_ylim(-1, 1)
        ax.set_ylabel(f"{w}d corr")
        ax.legend(fontsize=7, ncol=3, loc="lower left")
        ax.grid(alpha=.25)
    fig.suptitle(f"Rolling return correlation ({name} panel)")
    fig.tight_layout()
    fig.savefig(OUT / f"rolling_corr_{name}.png", dpi=150)
    plt.close(fig)
    pd.concat(rows).to_csv(OUT / f"rolling_corr_{name}.csv", index=False, encoding="utf-8-sig")
    last = {f"{LABEL[a]}-{LABEL[b]}": {
        f"last_{w}d": float(ret[a].rolling(w).corr(ret[b]).iloc[-1]) for w in windows}
        for a, b in pairs}
    return last


def rolling_stability(tr, pairs, windows=(60, 250), name="long"):
    """滚动相关性的分布：均值、中位数、极值、>0.5 的时间占比。"""
    ret = tr.pct_change(fill_method=None).dropna(how="all")
    rows = []
    for a, b in pairs:
        for w in windows:
            rc = ret[a].rolling(w).corr(ret[b]).dropna()
            if rc.empty:
                continue
            rows.append(dict(pair=f"{LABEL[a]}-{LABEL[b]}", window=w, obs=len(rc),
                             mean=round(rc.mean(), 3), median=round(rc.median(), 3),
                             p10=round(rc.quantile(.1), 3), p90=round(rc.quantile(.9), 3),
                             min=round(rc.min(), 3), max=round(rc.max(), 3),
                             share_above_0_5=round((rc > .5).mean() * 100, 1),
                             share_below_0=round((rc < 0).mean() * 100, 1)))
    return pd.DataFrame(rows)


def drawdown_episodes(tr300, threshold=-0.10):
    """从沪深300总收益指数识别回撤>10%的非重叠下跌段（峰→谷→收复）。"""
    eq = tr300.dropna()
    peak_value, peak_date = -np.inf, eq.index[0]
    episodes, ep = [], None
    for date, value in eq.items():
        if value >= peak_value:
            peak_value, peak_date = value, date
            if ep is not None:            # 收复前高，结束本段
                ep["end"] = date
                episodes.append(ep)
                ep = None
            continue
        dd = value / peak_value - 1
        if ep is None and dd <= threshold:
            ep = dict(start=peak_date, trough=date, low_dd=dd, peak=peak_value)
        elif ep is not None and dd < ep["low_dd"]:
            ep["trough"], ep["low_dd"] = date, dd
    if ep is not None:
        ep["end"] = eq.index[-1]
        episodes.append(ep)
    for e in episodes:
        e["depth"] = float(eq.loc[e["trough"]] / e["peak"] - 1)
        e["days"] = int((e["trough"] - e["start"]).days)
    episodes = sorted(episodes, key=lambda x: x["depth"])[:6]
    return episodes


def crisis_stats(tr, code300="160706"):
    """峰→谷下跌段内各资产表现与相关性；以及沪深300最差5%交易日的表现。"""
    ret = tr.pct_change(fill_method=None).dropna(how="all")
    eps = drawdown_episodes(tr[code300])
    rows = []
    for e in eps:
        # 只统计下跌段（峰→谷），不把收复阶段混进来
        seg = ret.loc[(ret.index >= e["start"]) & (ret.index <= e["trough"])]
        row = dict(start=str(e["start"].date()), trough=str(e["trough"].date()),
                   end=str(e["end"].date()), depth=round(e["depth"] * 100, 2),
                   decline_days=e["days"], obs=len(seg))
        for c in tr.columns:
            row[f"{LABEL[c]}_total"] = round(((1 + seg[c]).prod() - 1) * 100, 2)
            row[f"{LABEL[c]}_corr300"] = round(seg[c].corr(seg[code300]), 3)
        rows.append(row)
    ep_df = pd.DataFrame(rows)

    q = ret[code300].quantile(0.05)
    worst = ret[ret[code300] <= q]
    wrow = {"sample": f"CSI300 worst 5% days (n={len(worst)})", "threshold": round(q * 100, 2)}
    for c in tr.columns:
        wrow[f"{LABEL[c]}_avg"] = round(worst[c].mean() * 100, 3)
        wrow[f"{LABEL[c]}_winrate"] = round((worst[c] > 0).mean() * 100, 1)
    return ep_df, pd.DataFrame([wrow])


def trend_positions(tr, window):
    """收盘价在 N 日均线上方则持仓；信号在 t 日收盘生成，t+1 日生效。"""
    ma = tr.rolling(window, min_periods=window).mean()
    return (tr > ma).astype(float).where(ma.notna(), 0.0)


def sleeve_return(asset_ret, pos, cash_ret, buy_fee, sell_fee):
    """单资产独立账户：持仓吃资产收益，空仓吃货币基金收益；换手按成交名义额收费。"""
    p = pos.shift(1).fillna(0.0)
    prev = p.shift(1).fillna(0.0)
    turnover = (p - prev).abs()
    fee = np.where((p > prev), buy_fee, sell_fee) * turnover
    r = p * asset_ret.fillna(0.0) + (1 - p) * cash_ret.reindex(asset_ret.index).fillna(0.0) - fee
    return pd.Series(r, index=asset_ret.index)


def stats(r, cash):
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    mdd = (eq / eq.cummax() - 1).min()
    ex = r - cash.reindex(r.index).fillna(0)
    sharpe = ex.mean() / ex.std(ddof=1) * np.sqrt(252) if ex.std(ddof=1) > 0 else np.nan
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                vol=r.std(ddof=1) * np.sqrt(252), total=eq.iloc[-1] - 1)


def signal_overlap(pos, codes):
    """两两统计：同时持仓、同时空仓、仅一方持仓、同时买入(0->1)、同时卖出(1->0)。"""
    rows = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            a, b = pos[codes[i]], pos[codes[j]]
            both = ((a == 1) & (b == 1)).mean()
            none = ((a == 0) & (b == 0)).mean()
            only_a = ((a == 1) & (b == 0)).mean()
            only_b = ((a == 0) & (b == 1)).mean()
            buy_a, buy_b = (a.diff() == 1), (b.diff() == 1)
            sell_a, sell_b = (a.diff() == -1), (b.diff() == -1)
            rows.append(dict(pair=f"{LABEL[codes[i]]}-{LABEL[codes[j]]}",
                             both_hold=round(both * 100, 1), both_flat=round(none * 100, 1),
                             only_first=round(only_a * 100, 1), only_second=round(only_b * 100, 1),
                             both_buy=round((buy_a & buy_b).mean() * 100, 2),
                             both_sell=round((sell_a & sell_b).mean() * 100, 2),
                             buy_days_first=int(buy_a.sum()), buy_days_second=int(buy_b.sum()),
                             expected_both_buy=round(buy_a.mean() * buy_b.mean() * 100, 2)))
    return pd.DataFrame(rows)


def main():
    log = []
    for name, codes, start in (("long", LONG, START["long"]), ("full", FULL, START["full"])):
        tr = panel(codes, start)
        print(f"\n===== {name}: {tr.index[0].date()} ~ {tr.index[-1].date()} / {len(tr)} obs =====")
        corrs = corr_table(tr, name)
        heatmap(corrs["daily"], f"Daily return correlation ({name})", OUT / f"heatmap_daily_{name}.png")
        heatmap(corrs["monthly"], f"Monthly return correlation ({name})", OUT / f"heatmap_monthly_{name}.png")
        pairs = [(codes[0], c) for c in codes[1:]] if name == "long" else \
            [("000216", "160706"), ("000216", "006484"), ("160706", "090010"),
             ("160706", "006484"), ("160706", "160119"), ("006484", "003358"),
             ("090010", "006989")]
        last = rolling_corr(tr, pairs, name=name)
        log.append((name, last))
        stab = rolling_stability(tr, pairs, name=name)
        stab.to_csv(OUT / f"rolling_stability_{name}.csv", index=False, encoding="utf-8-sig")
        print("\nrolling stability:\n", stab.to_string(index=False))

        ep, worst = crisis_stats(tr)
        ep.to_csv(OUT / f"crisis_episodes_{name}.csv", index=False, encoding="utf-8-sig")
        worst.to_csv(OUT / f"worst_days_{name}.csv", index=False, encoding="utf-8-sig")
        print("\ncrisis episodes:\n", ep.to_string(index=False))
        print("\nworst 5% CSI300 days:\n", worst.to_string(index=False))

        # ---------- 单资产基准统计 ----------
        ret = tr.pct_change(fill_method=None).dropna(how="all")
        cash = load_ret("000198").reindex(ret.index).fillna(0.0)
        rows_asset = []
        for c in codes:
            r = ret[c]
            s = stats(r, cash)
            rows_asset.append(dict(asset=LABEL[c], code=c, years=round(len(r) / 252, 1),
                                   **{k: round(v, 4) for k, v in s.items()}))
        pd.DataFrame(rows_asset).to_csv(OUT / f"asset_stats_{name}.csv", index=False, encoding="utf-8-sig")
        print("\nper-asset stats:\n", pd.DataFrame(rows_asset).to_string(index=False))

        # ---------- 策略持仓/收益/错位（基线：120日均线趋势） ----------
        ret = tr.pct_change(fill_method=None).dropna(how="all")
        cash = load_ret("000198").reindex(ret.index).fillna(0.0)
        pos = trend_positions(tr, 120).reindex(ret.index)
        ov = signal_overlap(pos, codes)
        ov.to_csv(OUT / f"signal_overlap_{name}.csv", index=False, encoding="utf-8-sig")
        print("\nsignal overlap (%):\n", ov.to_string(index=False))

        strat = {}
        for c in codes:
            buy = 0.0 if c == "000198" else 0.0015  # 先用统一保守申购费，第二轮按真实费率
            strat[c] = sleeve_return(ret[c], pos[c], cash, buy, 0.001)
        sret = pd.DataFrame(strat)
        sc = sret.corr()
        sc.round(4).to_csv(OUT / f"strategy_ret_corr_{name}.csv", encoding="utf-8-sig")
        print("\nstrategy return corr:\n", sc.round(3).to_string())

        # ---------- 边际贡献：等权多资产独立账户，空仓吃货币基金 ----------
        port = sret.mean(axis=1)
        base = stats(port, cash)
        rows = [dict(portfolio="ALL", assets=len(codes), **{k: round(v, 4) for k, v in base.items()})]
        for c in codes:
            if c == "000198":
                continue
            rest = [x for x in codes if x != c]
            r = sret[rest].mean(axis=1)
            s = stats(r, cash)
            rows.append(dict(portfolio=f"ALL_minus_{LABEL[c]}", assets=len(rest),
                             **{k: round(v, 4) for k, v in s.items()}))
        bh = ret[codes].mean(axis=1)
        rows.append(dict(portfolio="BuyHold_equal", assets=len(codes),
                         **{k: round(v, 4) for k, v in stats(bh, cash).items()}))
        mc = pd.DataFrame(rows)
        mc.to_csv(OUT / f"marginal_contribution_{name}.csv", index=False, encoding="utf-8-sig")
        print("\nmarginal contribution:\n", mc.to_string(index=False))

    (OUT / "rolling_last.txt").write_text(
        "\n".join(f"{n}: {v}" for n, v in log), encoding="utf-8")
    print("\nsaved ->", OUT)


if __name__ == "__main__":
    main()
