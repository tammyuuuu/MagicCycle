"""V2.0：核实用户指定四只基金的基础信息、历史区间、费率与申购状态。"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

FUNDS = {
    "000015": "华夏纯债债券A",
    "001214": "华泰柏瑞中证500ETF联接A",
    "008701": "华夏黄金ETF联接A",
    "161130": "易方达纳斯达克100ETF联接A(人民币)",
    "000198": "天弘余额宝货币",
}


def fetch(code):
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
    r = requests.get(url, timeout=40)
    r.raise_for_status()
    (RAW / f"{code}.js").write_bytes(r.content)
    s = r.content.decode("utf-8-sig")
    name = re.search(r'var fS_name\s*=\s*"([^"]+)"', s)
    code_ = re.search(r'var fS_code\s*=\s*"([^"]+)"', s)
    m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", s, re.S)
    rows = json.loads(m.group(1)) if m else []
    first = last = None
    if rows:
        first = dt.datetime.fromtimestamp(rows[0]["x"] / 1000, dt.UTC).date().isoformat()
        last = dt.datetime.fromtimestamp(rows[-1]["x"] / 1000, dt.UTC).date().isoformat()
    src = re.search(r"var\s+fund_sourceRate\s*=\s*\"([\d.]+)\"", s)
    cur = re.search(r"var\s+fund_Rate\s*=\s*\"([\d.]+)\"", s)
    for kind in ("jjfl", "jbgk", "fhsp"):
        p = RAW / f"{code}_{kind}.html"
        try:
            rr = requests.get(f"https://fundf10.eastmoney.com/{kind}_{code}.html", timeout=25)
            rr.raise_for_status()
            p.write_bytes(rr.content)
        except Exception as e:
            print("meta fail", code, kind, type(e).__name__, flush=True)
    meta = dict(code=code, name=name.group(1) if name else None,
                rows=len(rows), first=first, last=last,
                source_rate=src.group(1) if src else None,
                discount_rate=cur.group(1) if cur else None,
                sha256=hashlib.sha256(r.content).hexdigest())
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    return meta


def main():
    out = {c: fetch(c) for c in FUNDS}
    (ROOT / "manifest_v2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
