# -*- coding: utf-8 -*-
"""V2.3：补充创业板等候选资产，并核实最新状态。"""
from pathlib import Path
import datetime as dt
import json
import re
import sys

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_v23"
RAW.mkdir(exist_ok=True)
V1 = ROOT.parent / "research_xingxun_v1"
sys.path.insert(0, str(V1))
import data_prep as dp  # noqa: E402

FUNDS = {
    "110026": "易方达创业板ETF联接A",
    "003766": "广发创业板ETF联接A",
    "001594": "天弘中证银行ETF联接A",
}
dp.RAW = RAW

out = {}
for code, label in FUNDS.items():
    rec = dict(code=code, label=label)
    try:
        r = requests.get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js", timeout=40)
        r.raise_for_status()
        (RAW / f"{code}.js").write_bytes(r.content)
        js = r.content.decode("utf-8-sig")
        m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", js, re.S)
        rows = json.loads(m.group(1)) if m else []
        if rows:
            rec["nav"] = rows[-1].get("y")
            rec["nav_date"] = dt.datetime.fromtimestamp(rows[-1]["x"] / 1000, dt.UTC).date().isoformat()
            rec["first"] = dt.datetime.fromtimestamp(rows[0]["x"] / 1000, dt.UTC).date().isoformat()
        for kind in ("jjfl", "jbgk", "fhsp"):
            rr = requests.get(f"https://fundf10.eastmoney.com/{kind}_{code}.html", timeout=25)
            rr.raise_for_status()
            (RAW / f"{code}_{kind}.html").write_bytes(rr.content)
        meta = dp.parse_meta(code, js)
        for k in ("name", "fund_type", "purchase_status", "daily_purchase_limit",
                  "purchase_min", "current_rate_pct", "inception"):
            rec[k] = meta.get(k)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    out[code] = rec
    print(json.dumps(rec, ensure_ascii=False), flush=True)

(ROOT / "trade_conditions_v23.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
