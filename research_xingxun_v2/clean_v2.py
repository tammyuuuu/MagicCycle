"""V2.0：清洗四只指定基金 + 现金工具，输出统一面板。

复用第一轮 data_prep 的解析函数（pingzhongdata / jjfl / jbgk），只改数据目录。
"""
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean_v2"
CLEAN.mkdir(exist_ok=True)
V1 = ROOT.parent / "research_xingxun_v1"

sys.path.insert(0, str(V1))
import data_prep as dp  # noqa: E402

dp.RAW = ROOT / "raw"
dp.CLEAN = CLEAN

FUNDS = {
    "000015": "华夏纯债债券A",
    "001214": "华泰柏瑞中证500ETF联接A",
    "008701": "华夏黄金ETF联接A",
    "161130": "易方达纳斯达克100ETF联接A(人民币)",
}


def clean_one(code):
    js = (dp.RAW / f"{code}.js").read_text(encoding="utf-8-sig")
    meta = dp.parse_meta(code, js)
    events, _ = dp.parse_dividends(code)
    series, _, _ = dp.build_fund_series(code, meta, events)
    series["date"] = pd.to_datetime(series["date"])
    series = series.drop_duplicates("date").set_index("date").sort_index()
    cols = [c for c in ("nav", "acc_nav", "div", "ret", "tr") if c in series.columns]
    out = series[cols]
    out.to_csv(CLEAN / f"{code}.csv", float_format="%.6f")
    return meta, out


def main():
    rows = []
    panel = {}
    for code, label in FUNDS.items():
        meta, s = clean_one(code)
        meta["label"] = label
        rows.append(meta)
        panel[code] = s["tr"]
        print(f"{code} {meta['name']} {s.index.min().date()}~{s.index.max().date()} rows={len(s)} "
              f"type={meta.get('fund_type')} status={meta.get('purchase_status')} "
              f"limit={meta.get('daily_purchase_limit')} min={meta.get('purchase_min')} "
              f"buy={meta.get('current_rate_pct')}%", flush=True)

    # 现金：复用第一轮货基总收益序列
    cash = pd.read_csv(V1 / "clean" / "000198.csv", parse_dates=["date"]).set_index("date")["tr"]
    panel["000198"] = cash

    meta_df = pd.DataFrame(rows)
    meta_df.to_csv(CLEAN / "fund_meta_v2.csv", index=False)

    # 对齐 001214 的 A 股交易日历（四只里唯一的纯 A 股指数基金）
    cal = panel["001214"].dropna().index
    cal = cal[(cal >= pd.Timestamp("2020-07-16")) & (cal <= pd.Timestamp("2026-10-21"))]
    wide = pd.DataFrame({c: panel[c].reindex(cal).ffill(limit=10) for c in panel})
    wide.to_csv(CLEAN / "panel_v2.csv", float_format="%.6f")
    print("panel", wide.shape, wide.index.min().date(), wide.index.max().date())
    print(wide.isna().sum().to_string())
    print("\n费率与状态：")
    for r in rows:
        print(r["code"], r.get("purchase_status"), "| buy", r.get("current_rate_pct"),
              "| tiers", r.get("purchase_fee_tiers"), "| redeem", r.get("redeem_fee_tiers"),
              "| confirm", r.get("buy_confirm"), r.get("sell_confirm"), flush=True)


if __name__ == "__main__":
    main()
