# -*- coding: utf-8 -*-
"""第三轮：滚动样本外验证（walk-forward）。

每个 fold：
  训练 2 年（约 504 个交易日）→ 按第二轮协议选策略 → 测试 1 年（252 日）
  测试期资金重新从 2000 元开始，收益率逐年复利串成"滚动净值"。
  边界处会重新建仓一次，成本略高于连续持仓，属保守处理。

比较对象：
  - 协议选择的策略（hold 参与竞争，择时需 Sharpe 高 0.10）
  - 同资产买入持有
  - 组合：所选策略 vs 全部持有 vs 固定比例
"""
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_lib as SL
from otc_engine import run_sleeve, metrics
from run_round2 import (FULL, LONG, LABEL, build_panel, make_targets,
                        cash_equity, load_series)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_wf"
OUT.mkdir(exist_ok=True)

TRAIN = 504
TEST = 252


def select(train_rows, cash_cagr, margin=0.10):
    hold = train_rows[train_rows.strategy == "A_hold"].iloc[0]
    ok = train_rows[(train_rows.strategy != "A_hold") & (train_rows.trades >= 2) &
                    (train_rows.cagr > cash_cagr + 0.01)]
    best = ok.sort_values("sharpe", ascending=False).iloc[0] if len(ok) else hold
    if best.strategy != "A_hold" and best.sharpe < hold.sharpe + margin:
        best = hold
    return best.strategy


def run_panel(name, codes, start, tr, dates, cash, fees, pe_daily):
    n = len(dates)
    folds = []
    i = 0
    fold_id = 0
    while i + TRAIN + TEST <= n:
        train_s, train_e = i, i + TRAIN - 1
        test_s, test_e = i + TRAIN, i + TRAIN + TEST - 1
        rows = []
        for code in codes:
            prices = tr[code].to_numpy(float)
            tmap = make_targets(tr[code], code, pe_daily)
            for sname, target in tmap.items():
                t = target.reindex(dates).fillna(0.0).to_numpy(float)
                eq, f, trades = run_sleeve(prices, t, dates, cash, 2000.0,
                                           fees[code], train_s, train_e)
                m = metrics(eq, cash, train_s, train_e)
                rows.append(dict(code=code, strategy=sname, cagr=m["cagr"],
                                 mdd=m["mdd"], sharpe=m["sharpe"], trades=len(trades)))
        train_df = pd.DataFrame(rows)
        cash_tr = metrics(cash_equity(2000.0, cash, train_s, train_e), cash, train_s, train_e)["cagr"]

        chosen, chosen_eq, chosen_fees, chosen_trades = {}, {}, {}, {}
        chosen_daily, hold_daily = {}, {}
        for code in codes:
            g = train_df[train_df.code == code]
            sname = select(g, cash_tr)
            chosen[code] = sname
            t = make_targets(tr[code], code, pe_daily)[sname].reindex(dates).fillna(0.0).to_numpy(float)
            eq, f, trades = run_sleeve(tr[code].to_numpy(float), t, dates, cash, 2000.0,
                                       fees[code], test_s, test_e)
            chosen_eq[code] = eq
            chosen_fees[code] = f
            chosen_trades[code] = len(trades)
            chosen_daily[code] = eq[test_s:test_e + 1] / eq[test_s]
            eqh, _, _ = run_sleeve(tr[code].to_numpy(float),
                                   SL.hold(tr[code]).reindex(dates).fillna(1.0).to_numpy(float),
                                   dates, cash, 2000.0, fees[code], test_s, test_e)
            hold_daily[code] = eqh[test_s:test_e + 1] / eqh[test_s]
        folds.append(dict(panel=name, fold=fold_id,
                          train_start=str(dates[train_s].date()), train_end=str(dates[train_e].date()),
                          test_start=str(dates[test_s].date()), test_end=str(dates[test_e].date()),
                          chosen=chosen, cash_cagr=cash_tr,
                          chosen_eq={c: chosen_eq[c] for c in codes},
                          chosen_daily=chosen_daily, hold_daily=hold_daily,
                          cash_daily=cash[test_s + 1:test_e + 1],
                          fees=sum(chosen_fees.values()),
                          trades=sum(chosen_trades.values()),
                          test_s=test_s, test_e=test_e))
        i += TEST
        fold_id += 1
    return folds, train_df


def chain_daily(folds, key, codes=None):
    """把每折测试期的日收益拼接；组合为等权平均（日度再平衡近似）。"""
    rets = []
    for f in folds:
        arr = f[key]
        if codes is None and isinstance(arr, dict):
            rr = np.mean([arr[c][1:] / arr[c][:-1] - 1 for c in arr], axis=0)
        elif isinstance(arr, dict):
            rr = arr[codes][1:] / arr[codes][:-1] - 1
        else:
            rr = arr[1:] / arr[:-1] - 1
        rets.append(rr)
    r = np.concatenate(rets)
    curve = 2000.0 * np.cumprod(1 + r)
    curve = np.r_[2000.0, curve]
    return curve, r


def summarize(curve, r, folds):
    yrs = len(r) / 252.0
    cagr = (curve[-1] / curve[0]) ** (1 / yrs) - 1
    mdd = float((pd.Series(curve) / pd.Series(curve).cummax() - 1).min())
    ex = r - np.concatenate([f["cash_daily"] for f in folds])
    sharpe = ex.mean() / ex.std(ddof=1) * np.sqrt(252) if ex.std(ddof=1) > 0 else np.nan
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, total=curve[-1] / curve[0] - 1,
                folds=len(r) / 252, positive=float((r > 0).mean()))


def main():
    panels = [
        ("A", FULL, "2019-03-08", None, None),
        ("B", LONG, "2013-08-22", None, None),
    ]
    all_rows, all_picks, fold_rows = [], [], []

    for name, codes, start, _, _ in panels:
        tr, dates, cash, fees, pe_daily = build_panel(codes, start)
        folds, train_df = run_panel(name, codes, start, tr, dates, cash, fees, pe_daily)
        print(f"[{name}] folds={len(folds)} {dates[0].date()}..{dates[-1].date()}")

        # 单资产：选择策略 vs 持有
        for code in codes:
            ccurve, crets = chain_daily(folds, "chosen_daily", code)
            hcurve, hrets = chain_daily(folds, "hold_daily", code)
            per_c = [f["chosen_daily"][code][-1] - 1 for f in folds]
            per_h = [f["hold_daily"][code][-1] - 1 for f in folds]
            all_rows.append(dict(panel=name, asset=LABEL[code],
                                 **{f"chosen_{k}": v for k, v in summarize(ccurve, crets, folds).items()},
                                 **{f"hold_{k}": v for k, v in summarize(hcurve, hrets, folds).items()},
                                 folds_chosen_better=int(sum(a > b for a, b in zip(per_c, per_h))),
                                 folds_total=len(folds)))
            for f in folds:
                fold_rows.append(dict(panel=name, asset=LABEL[code], fold=f["fold"],
                                      train_end=f["train_end"], test_start=f["test_start"],
                                      test_end=f["test_end"], selected=f["chosen"][code],
                                      chosen_ret=round(f["chosen_daily"][code][-1] - 1, 4),
                                      hold_ret=round(f["hold_daily"][code][-1] - 1, 4)))

        # 组合：所选策略 vs 全部持有
        pcurve, prets = chain_daily(folds, "chosen_daily")
        phcurve, phrets = chain_daily(folds, "hold_daily")
        per_cp = [np.mean([f["chosen_daily"][c][-1] - 1 for c in codes]) for f in folds]
        per_hp = [np.mean([f["hold_daily"][c][-1] - 1 for c in codes]) for f in folds]
        all_rows.append(dict(panel=name, asset="组合",
                             **{f"chosen_{k}": v for k, v in summarize(pcurve, prets, folds).items()},
                             **{f"hold_{k}": v for k, v in summarize(phcurve, phrets, folds).items()},
                             folds_chosen_better=int(sum(a > b for a, b in zip(per_cp, per_hp))),
                             folds_total=len(folds)))
        fold_rows.append(dict(panel=name, asset="PORTFOLIO", fold=-1,
                              train_end="", test_start="", test_end="",
                              selected=",".join(LABEL[c] for c in codes),
                              chosen_ret=round(pcurve[-1] / 2000 - 1, 4),
                              hold_ret=round(phcurve[-1] / 2000 - 1, 4)))
        print("  portfolio fold returns chosen:", np.round(per_cp, 3))
        print("  portfolio fold returns hold:  ", np.round(per_hp, 3))

    res = pd.DataFrame(all_rows)
    res.to_csv(OUT / "walkforward_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(fold_rows).to_csv(OUT / "walkforward_folds.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(res.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
