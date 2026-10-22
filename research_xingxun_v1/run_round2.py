# -*- coding: utf-8 -*-
"""第二轮：各资产独立策略 + 组合回测 + 初步筛选。

流程：
1. 全资产面板 A（2019-03-08 起）：策略网格 → 样本内(IS)选策略 → 样本外(OOS)检验；
2. 长期面板 B（2013-08-22 起，4 资产）：同流程，用于观察不同市场环境；
3. 组合回测：8 种组合 × 3 档资金（2000/5000/10000）；
4. 成本敏感性：费率 ×0.5 / ×1 / ×2；
5. 输出 CSV 到 out_bt/。
"""
from pathlib import Path
import itertools
import json

import numpy as np
import pandas as pd

import strategy_lib as SL
from otc_engine import load_fee, run_sleeve, metrics

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "out_bt"
OUT.mkdir(exist_ok=True)

LABEL = {"000216": "黄金", "160706": "沪深300", "160119": "中证500", "090010": "中证红利",
         "006484": "1-3年国开", "003358": "7-10年国开", "006989": "中短债", "000198": "货基"}
FULL = ["160706", "160119", "090010", "000216", "006484", "003358", "006989"]
LONG = ["000216", "160706", "160119", "090010"]
BOND = {"006484", "003358", "006989"}
EQUITY_PE = {"160706": "沪深300", "160119": "中证500", "090010": "上证红利"}


def load_series(code, field="tr"):
    d = pd.read_csv(CLEAN / f"{code}.csv", parse_dates=["date"]).set_index("date")
    return d[field].astype(float)


def money_daily(dates):
    """货币基金：先在自然日上累积，再对齐到交易日，避免丢掉周末收益。"""
    m = load_series("000198", "tr")
    full = m.reindex(pd.date_range(m.index.min(), m.index.max())).ffill()
    aligned = full.reindex(dates).ffill().bfill()
    return aligned.pct_change(fill_method=None).fillna(0.0).to_numpy()


def pe_series(name):
    d = pd.read_csv(ROOT / "raw" / f"pe_{name}.csv", parse_dates=["日期"])
    return pd.Series(pd.to_numeric(d["滚动市盈率"], errors="coerce").values, index=d["日期"]).dropna()


def build_panel(codes, start):
    tr = pd.DataFrame({c: load_series(c) for c in codes})
    tr = tr[tr.index >= pd.Timestamp(start)].dropna(how="any")
    dates = tr.index
    cash = money_daily(dates)
    metas = pd.read_csv(CLEAN / "fund_meta.csv", dtype={"code": str}).set_index("code")
    fees = {c: load_fee(metas.loc[c]) for c in codes if c != "000198"}
    pe_daily = {}
    for c, name in EQUITY_PE.items():
        if c in codes:
            pe_daily[c] = SL.valuation_overlay(pe_series(name), dates)
    return tr, dates, cash, fees, pe_daily


def make_targets(tr, code, pe_daily):
    """返回 {strategy_name: target Series}。"""
    out = {"A_hold": SL.hold(tr)}
    for n in (60, 120, 200):
        out[f"B_ma{n}"] = SL.ma(tr, n=n)
    for th in (0.03, 0.05, 0.08):
        out[f"C_pullback{int(th*100)}"] = SL.pullback(tr, threshold=th)
    out["D_donchian60_20"] = SL.donchian(tr, 60, 20)
    out["D_donchian120_40"] = SL.donchian(tr, 120, 40)
    for vt in (0.10, 0.15, 0.20):
        out[f"E_vol{int(vt*100)}"] = SL.vol_target(tr, target_vol=vt)
    if code == "000216":
        out["F_gold_heat"] = SL.gold_heat(tr)
    if code in BOND:
        out["F_bond_momentum120"] = SL.bond_momentum(tr, 120)
    if code in pe_daily:
        out["F_ma200_val"] = SL.ma_valuation(tr, pe_daily[code])
    return out


def run_grid(panel_name, codes, start, is_end, oos_start, end, capital=2000):
    tr, dates, cash, fees, pe_daily = build_panel(codes, start)
    positions = {d: i for i, d in enumerate(dates)}
    segs = {"IS": (positions[dates[0]], positions[pd.Timestamp(is_end)] if pd.Timestamp(is_end) in positions else positions[dates[dates <= is_end][-1]]),
            "OOS": (positions[dates[dates >= oos_start][0]], len(dates) - 1),
            "FULL": (0, len(dates) - 1)}
    rows = []
    for code in codes:
        prices = tr[code].to_numpy(float)
        tmap = make_targets(tr[code], code, pe_daily)
        for name, target in tmap.items():
            t = target.reindex(dates).fillna(0.0).to_numpy(float)
            for seg, (s, e) in segs.items():
                eq, fees_paid, trades = run_sleeve(
                    prices, t, dates, cash, capital, fees[code], s, e)
                m = metrics(eq, cash, s, e)
                rows.append(dict(panel=panel_name, code=code, asset=LABEL[code],
                                 strategy=name, segment=seg, capital=capital,
                                 trades=len(trades), fees=fees_paid,
                                 **{k: v for k, v in m.items()}))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"grid_{panel_name}.csv", index=False, encoding="utf-8-sig")
    return df, tr, dates, cash, fees, pe_daily


def choose(df, cash_is_cagr, margin=0.10):
    """IS 选策略。

    规则（事先写死）：
    1) 默认策略"买入持有"必须参与比较；
    2) 择时策略需满足 IS 年化高于货基 1 个百分点、交易≥2 次；
    3) 只有当择时策略的 IS Sharpe 比买入持有高出 margin(0.10) 时才替换默认。
    这样避免"为了择时而择时"，也让默认策略有资格胜出。
    """
    is_rows = df[(df.segment == "IS") & (df.capital == 2000)]
    picked = []
    for code, g in is_rows.groupby("code"):
        hold = g[g.strategy == "A_hold"].iloc[0]
        ok = g[(g.strategy != "A_hold") & (g.trades >= 2) & (g.cagr > cash_is_cagr + 0.01)]
        best = ok.sort_values("sharpe", ascending=False).iloc[0] if len(ok) else hold
        if best.strategy != "A_hold" and best.sharpe < hold.sharpe + margin:
            best = hold
        picked.append(dict(code=code, asset=LABEL[code], strategy=best.strategy,
                           is_cagr=best.cagr, is_mdd=best.mdd, is_sharpe=best.sharpe,
                           is_trades=best.trades, hold_sharpe=hold.sharpe))
    return pd.DataFrame(picked)


def cash_equity(capital, cash, s, e):
    eq = np.full(len(cash), np.nan)
    eq[s] = capital
    for i in range(s + 1, e + 1):
        eq[i] = eq[i - 1] * (1 + cash[i])
    return eq


def portfolio(tr, dates, cash, fees, strategy_map, codes, capital, s, e,
              weights=None, trade_log=None):
    """独立账户、等额（或指定权重）资金上限；空仓现金计货基收益。"""
    n = len(codes)
    w = weights or {c: 1.0 / n for c in codes}
    eq_total = np.zeros(len(dates))
    fee_total = 0.0
    invested = 0.0
    for c in codes:
        cap = capital * w[c]
        invested += cap
        target = strategy_map[c].reindex(dates).fillna(0.0).to_numpy(float)
        eq, f, trades = run_sleeve(tr[c].to_numpy(float), target, dates, cash,
                                   cap, fees[c], s, e, trade_log=trade_log)
        eq_total += np.nan_to_num(eq, nan=0.0)
        fee_total += f
    # 未分配资金放货基
    rest = capital - invested
    if rest > 1e-9:
        ce = cash_equity(rest, cash, s, e)
        eq_total += np.nan_to_num(ce, nan=0.0)
    return eq_total, fee_total


def main():
    results = {}
    log = []

    # ---------------- Panel A ----------------
    a = dict(codes=FULL, start="2019-03-08", is_end="2023-12-29",
             oos_start="2024-01-02", end="2026-10-21")
    dfA, trA, datesA, cashA, feesA, peA = run_grid("A", **a)
    # 货基 IS 年化（作为选策略的最低门槛）
    posA = {d: i for i, d in enumerate(datesA)}
    sA, eA = 0, posA[datesA[datesA <= a["is_end"]][-1]]
    cash_is = float(metrics(cash_equity(2000, cashA, sA, eA), cashA, sA, eA)["cagr"])
    pickA = choose(dfA, cash_is)
    pickA["panel"] = "A"
    log.append(("Panel A", len(datesA), str(datesA[0].date()), str(datesA[-1].date()),
                cash_is))

    # ---------------- Panel B ----------------
    b = dict(codes=LONG, start="2013-08-22", is_end="2019-12-31",
             oos_start="2020-01-02", end="2026-10-21")
    dfB, trB, datesB, cashB, feesB, peB = run_grid("B", **b)
    posB = {d: i for i, d in enumerate(datesB)}
    sB, eB = 0, posB[datesB[datesB <= b["is_end"]][-1]]
    cash_is_b = float(metrics(cash_equity(2000, cashB, sB, eB), cashB, sB, eB)["cagr"])
    pickB = choose(dfB, cash_is_b)
    pickB["panel"] = "B"
    log.append(("Panel B", len(datesB), str(datesB[0].date()), str(datesB[-1].date()),
                cash_is_b))

    pick = pd.concat([pickA, pickB], ignore_index=True)
    pick.to_csv(OUT / "chosen.csv", index=False, encoding="utf-8-sig")
    print(pick.to_string(index=False))

    # ---------------- 组合回测（Panel A） ----------------
    chosen = dict(zip(pickA.code, pickA.strategy))
    print("\nchosen A:", chosen)

    def tmap_for(panel_tr, code, pe_daily):
        return make_targets(panel_tr[code], code, pe_daily)

    stratA = {}
    for c in FULL:
        stratA[c] = tmap_for(trA, c, peA)[chosen[c]]

    # 强制择时（不看持有门槛，直接用 IS 最优择时）——仅用于诊断
    isA = dfA[(dfA.segment == "IS") & (dfA.capital == 2000)]
    forced = {}
    for c in FULL:
        g = isA[isA.code == c]
        g = g[g.strategy != "A_hold"]
        forced[c] = g.sort_values("sharpe", ascending=False).iloc[0].strategy
    stratF = {c: tmap_for(trA, c, peA)[forced[c]] for c in FULL}
    print("\nforced timing:", forced)

    # 固定比例买入持有：30% 黄金 / 35% 沪深300 / 15% 红利 / 20% 债券
    fixed_w = {"000216": 0.30, "160706": 0.35, "090010": 0.15, "006484": 0.20}

    combos = [
        ("1_全现金", [], None),
        ("2_黄金单资产", ["000216"], None),
        ("3_沪深300单资产", ["160706"], None),
        ("4_黄金+沪深300", ["000216", "160706"], None),
        ("5_黄金+红利", ["000216", "090010"], None),
        ("6_黄金+300+债券", ["000216", "160706", "006484"], None),
        ("7_黄金+300+红利+债券", ["000216", "160706", "090010", "006484"], None),
        ("8_固定比例买入持有", ["000216", "160706", "090010", "006484"], fixed_w),
    ]

    port_rows = []
    equity_store = {}
    for cap in (2000, 5000, 10000):
        for name, codes, weights in combos:
            log_trades = []
            if not codes:
                eq = cash_equity(cap, cashA, 0, len(datesA) - 1)
                ftotal = 0.0
            elif weights:
                eq, ftotal = portfolio(
                    trA, datesA, cashA, feesA,
                    {c: SL.hold(trA[c]) for c in codes}, codes, cap,
                    0, len(datesA) - 1, weights=weights, trade_log=log_trades)
            else:
                eq, ftotal = portfolio(trA, datesA, cashA, feesA,
                                       {c: stratA[c] for c in codes}, codes, cap,
                                       0, len(datesA) - 1, trade_log=log_trades)
            mF = metrics(eq, cashA, 0, len(datesA) - 1)
            sO, eO = posA[datesA[datesA >= a["oos_start"]][0]], len(datesA) - 1
            mO = metrics(eq, cashA, sO, eO)
            port_rows.append(dict(capital=cap, combo=name, legs=len(codes) if codes else 0,
                                  trades=len(log_trades), fees=ftotal,
                                  full_cagr=mF["cagr"], full_mdd=mF["mdd"],
                                  full_sharpe=mF["sharpe"], full_calmar=mF["calmar"],
                                  oos_cagr=mO["cagr"], oos_mdd=mO["mdd"],
                                  oos_sharpe=mO["sharpe"], oos_calmar=mO["calmar"],
                                  end_value=mF["end_value"]))
            if cap == 2000:
                equity_store[name] = pd.Series(eq, index=datesA).dropna()
                if log_trades:
                    pd.DataFrame(log_trades).to_csv(
                        OUT / f"trades_{name}.csv", index=False, encoding="utf-8-sig")

            # 同资产、等权、买入持有对照（只买一次，之后不动）
            if codes:
                bh_trades = []
                eqh, fh = portfolio(trA, datesA, cashA, feesA,
                                    {c: SL.hold(trA[c]) for c in codes}, codes, cap,
                                    0, len(datesA) - 1, trade_log=bh_trades)
                mFh = metrics(eqh, cashA, 0, len(datesA) - 1)
                mOh = metrics(eqh, cashA, sO, eO)
                if cap == 2000:
                    equity_store[name + "_BH"] = pd.Series(eqh, index=datesA).dropna()
                port_rows.append(dict(capital=cap, combo=name + "_BH", legs=len(codes),
                                      trades=len(bh_trades), fees=fh,
                                      full_cagr=mFh["cagr"], full_mdd=mFh["mdd"],
                                      full_sharpe=mFh["sharpe"], full_calmar=mFh["calmar"],
                                      oos_cagr=mOh["cagr"], oos_mdd=mOh["mdd"],
                                      oos_sharpe=mOh["sharpe"], oos_calmar=mOh["calmar"],
                                      end_value=mFh["end_value"]))
    port = pd.DataFrame(port_rows)
    port.to_csv(OUT / "portfolio.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(equity_store).to_csv(OUT / "equity_2000.csv")
    print("\nportfolio:\n", port[port.capital == 2000].to_string(index=False))
    print("\ncapital sensitivity (CAGR):\n",
          port.pivot_table(index="combo", columns="capital", values="full_cagr").round(4).to_string())

    # ---------------- 费率敏感性 ----------------
    fee_rows = []
    for mode, smap in (("selected", stratA), ("forced", stratF)):
        for mult in (0.5, 1.0, 2.0):
            for name, codes, weights in combos:
                if not codes:
                    continue
                eqs = np.zeros(len(datesA))
                ftotal = 0.0
                n = len(codes)
                for c in codes:
                    cap = 2000 * (weights[c] if weights else 1.0 / n)
                    tgt = SL.hold(trA[c]) if weights else smap[c]
                    eq, f, _ = run_sleeve(trA[c].to_numpy(float),
                                          tgt.reindex(datesA).fillna(0).to_numpy(float),
                                          datesA, cashA, cap, feesA[c], 0,
                                          len(datesA) - 1, fee_mult=mult)
                    eqs += np.nan_to_num(eq, nan=0.0)
                    ftotal += f
                rest = 2000 - sum(2000 * (weights[c] if weights else 1.0 / n) for c in codes)
                if rest > 1e-9:
                    eqs += np.nan_to_num(cash_equity(rest, cashA, 0, len(datesA) - 1), nan=0.0)
                m = metrics(eqs, cashA, 0, len(datesA) - 1)
                fee_rows.append(dict(mode=mode, combo=name, fee_mult=mult, fees=ftotal,
                                     cagr=m["cagr"], mdd=m["mdd"], sharpe=m["sharpe"]))
    fee_df = pd.DataFrame(fee_rows)
    fee_df.to_csv(OUT / "fee_sensitivity.csv", index=False, encoding="utf-8-sig")
    print("\nfee sensitivity (selected):\n",
          fee_df[fee_df['mode'] == 'selected'].pivot_table(
              index="combo", columns="fee_mult", values="cagr").round(4).to_string())
    print("\nfee sensitivity (forced):\n",
          fee_df[fee_df['mode'] == 'forced'].pivot_table(
              index="combo", columns="fee_mult", values="cagr").round(4).to_string())

    # ---------------- Panel B 组合复核（2013 起） ----------------
    chosenB = dict(zip(pickB.code, pickB.strategy))
    stratB = {c: make_targets(trB[c], c, peB)[chosenB[c]] for c in LONG}
    combosB = [("2_黄金", ["000216"]), ("3_沪深300", ["160706"]),
               ("4_黄金+沪深300", ["000216", "160706"]),
               ("5_黄金+红利", ["000216", "090010"]),
               ("7_四资产", LONG)]
    sOB = posB[datesB[datesB >= b["oos_start"]][0]]
    eOB = len(datesB) - 1
    rowsB = []
    for name, codes in combosB:
        tr_log = []
        eq, f = portfolio(trB, datesB, cashB, feesB, {c: stratB[c] for c in codes},
                          codes, 2000, 0, len(datesB) - 1, trade_log=tr_log)
        mF = metrics(eq, cashB, 0, len(datesB) - 1)
        mO = metrics(eq, cashB, sOB, eOB)
        rowsB.append(dict(combo=name, kind="timing", trades=len(tr_log), fees=f,
                          full_cagr=mF["cagr"], full_mdd=mF["mdd"], full_sharpe=mF["sharpe"],
                          oos_cagr=mO["cagr"], oos_mdd=mO["mdd"], oos_sharpe=mO["sharpe"]))
        eqh, fh = portfolio(trB, datesB, cashB, feesB,
                            {c: SL.hold(trB[c]) for c in codes}, codes, 2000,
                            0, len(datesB) - 1)
        mFh = metrics(eqh, cashB, 0, len(datesB) - 1)
        mOh = metrics(eqh, cashB, sOB, eOB)
        rowsB.append(dict(combo=name, kind="buy_hold", trades=len(codes), fees=fh,
                          full_cagr=mFh["cagr"], full_mdd=mFh["mdd"], full_sharpe=mFh["sharpe"],
                          oos_cagr=mOh["cagr"], oos_mdd=mOh["mdd"], oos_sharpe=mOh["sharpe"]))
    portB = pd.DataFrame(rowsB)
    portB.to_csv(OUT / "portfolio_B.csv", index=False, encoding="utf-8-sig")
    print("\nPanel B portfolio (2013+):\n", portB.round(4).to_string(index=False))

    # ---------------- 强制择时诊断（不看持有门槛） ----------------
    for name, codes, weights in combos:
        if not codes or weights:
            continue
        tr_log = []
        eq, f = portfolio(trA, datesA, cashA, feesA, {c: stratF[c] for c in codes},
                          codes, 2000, 0, len(datesA) - 1, trade_log=tr_log)
        mF = metrics(eq, cashA, 0, len(datesA) - 1)
        mO = metrics(eq, cashA, sO, eO)
        port_rows.append(dict(capital=2000, combo="F_" + name, legs=len(codes),
                              trades=len(tr_log), fees=f,
                              full_cagr=mF["cagr"], full_mdd=mF["mdd"],
                              full_sharpe=mF["sharpe"], full_calmar=mF["calmar"],
                              oos_cagr=mO["cagr"], oos_mdd=mO["mdd"],
                              oos_sharpe=mO["sharpe"], oos_calmar=mO["calmar"],
                              end_value=mF["end_value"]))
    pd.DataFrame(port_rows).to_csv(OUT / "portfolio.csv", index=False, encoding="utf-8-sig")

    # ---------------- 交易带宽敏感性（换手 / 可操作性） ----------------
    band_rows = []
    for band in (0.02, 0.05, 0.10):
        for name, codes, weights in combos:
            if not codes or weights:
                continue
            eqs = np.zeros(len(datesA))
            ftotal = 0.0
            log_t = []
            n = len(codes)
            for c in codes:
                eq, f, _ = run_sleeve(trA[c].to_numpy(float),
                                      stratF[c].reindex(datesA).fillna(0).to_numpy(float),
                                      datesA, cashA, 2000.0 / n, feesA[c], 0,
                                      len(datesA) - 1, band=band, trade_log=log_t)
                eqs += np.nan_to_num(eq, nan=0.0)
                ftotal += f
            rest = 2000.0 - 2000.0
            m = metrics(eqs, cashA, 0, len(datesA) - 1)
            band_rows.append(dict(combo=name, band=band, trades=len(log_t),
                                  trades_per_year=len(log_t) / (len(datesA) / 252),
                                  fees=ftotal, cagr=m["cagr"], mdd=m["mdd"],
                                  sharpe=m["sharpe"]))
    band_df = pd.DataFrame(band_rows)
    band_df.to_csv(OUT / "band_sensitivity.csv", index=False, encoding="utf-8-sig")
    print("\nband sensitivity:\n",
          band_df.pivot_table(index="combo", columns="band",
                              values=["trades", "cagr"]).round(4).to_string())

    # 波动率目标策略的换手对带宽极敏感，单独检查
    vt_rows = []
    for panel, tr, dates, cash, fees, pos_map in (
            ("A", trA, datesA, cashA, feesA, posA), ("B", trB, datesB, cashB, feesB, posB)):
        for code in ("000216", "160706", "090010"):
            target = SL.vol_target(tr[code], target_vol=0.10)
            for band in (0.02, 0.05, 0.10):
                eq, f, trades = run_sleeve(tr[code].to_numpy(float),
                                           target.reindex(dates).fillna(0).to_numpy(float),
                                           dates, cash, 2000.0, fees[code], 0,
                                           len(dates) - 1, band=band)
                m = metrics(eq, cash, 0, len(dates) - 1)
                vt_rows.append(dict(panel=panel, code=code, asset=LABEL[code], band=band,
                                    trades=len(trades),
                                    trades_per_year=len(trades) / (len(dates) / 252),
                                    fees=f, cagr=m["cagr"], mdd=m["mdd"],
                                    sharpe=m["sharpe"]))
    vt = pd.DataFrame(vt_rows)
    vt.to_csv(OUT / "band_voltarget.csv", index=False, encoding="utf-8-sig")
    print("\nvol-target band sensitivity:\n", vt.round(4).to_string(index=False))

    # ---------------- 参数敏感性（OOS） ----------------
    oosA = dfA[(dfA.segment == "OOS") & (dfA.capital == 2000)]
    sens = oosA.pivot_table(index="asset", columns="strategy", values="cagr")
    sens.to_csv(OUT / "param_sensitivity_oos.csv", encoding="utf-8-sig")
    print("\nOOS CAGR dispersion by asset:\n",
          pd.DataFrame({"min": sens.min(axis=1), "max": sens.max(axis=1),
                        "median": sens.median(axis=1), "best": sens.idxmax(axis=1)}).round(4).to_string())

    with open(OUT / "run_notes.txt", "w", encoding="utf-8") as f:
        for row in log:
            f.write(repr(row) + "\n")
    print("\nsaved ->", OUT)


if __name__ == "__main__":
    main()
