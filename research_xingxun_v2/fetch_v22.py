# -*- coding: utf-8 -*-
"""V2.2：核实四只基金最新交易条件（2026-10-22 抓取）。"""
from pathlib import Path
import datetime as dt
import json
import re
import sys

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_v22"
RAW.mkdir(exist_ok=True)
V1 = ROOT.parent / "research_xingxun_v1"
sys.path.insert(0, str(V1))
import data_prep as dp  # noqa: E402

FUNDS = {"000015": "华夏纯债债券A", "001214": "华泰柏瑞中证500ETF联接A",
         "008701": "华夏黄金ETF联接A", "161130": "易方达纳斯达克100ETF联接A(人民币)"}
dp.RAW = RAW

out = {}
for code, label in FUNDS.items():
    rec = dict(code=code, label=label)
    try:
        url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        (RAW / f"{code}.js").write_bytes(r.content)
        js = r.content.decode("utf-8-sig")
        rec["fetched_at"] = dt.datetime.now().isoformat(timespec="seconds")
        m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", js, re.S)
        rows = json.loads(m.group(1)) if m else []
        if rows:
            last = rows[-1]
            rec["nav"] = last.get("y")
            rec["nav_date"] = dt.datetime.fromtimestamp(last["x"] / 1000, dt.UTC).date().isoformat()
        for kind in ("jjfl", "jbgk"):
            rr = requests.get(f"https://fundf10.eastmoney.com/{kind}_{code}.html", timeout=25)
            rr.raise_for_status()
            (RAW / f"{code}_{kind}.html").write_bytes(rr.content)
        meta = dp.parse_meta(code, js)
        for k in ("name", "fund_type", "purchase_status", "daily_purchase_limit",
                  "purchase_min", "buy_confirm", "sell_confirm", "current_rate_pct",
                  "redeem_fee_tiers", "purchase_fee_tiers", "inception", "scale"):
            rec[k] = meta.get(k)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    out[code] = rec
    print(json.dumps(rec, ensure_ascii=False), flush=True)

(ROOT / "trade_conditions_2026-10-22.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
