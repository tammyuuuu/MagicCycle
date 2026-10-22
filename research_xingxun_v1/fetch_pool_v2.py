"""第六轮：新增资产池原始快照（不动第一批快照）。"""
from pathlib import Path
import requests
import json
import re
import hashlib
import datetime

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

FUNDS = {
    "270042": "纳指100",
    "050025": "标普500",
    "011860": "中证1000",
    "011612": "科创50",
    "160213": "纳指100备选",
    "161125": "标普500备选",
    "162413": "中证1000长样本",
    "011609": "科创50备选",
}


def main():
    manifest = []
    for code, label in FUNDS.items():
        url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
        path = RAW / f"{code}.js"
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        path.write_bytes(r.content)
        raw = path.read_bytes()
        s = raw.decode("utf-8-sig")
        m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", s, re.S)
        rows = json.loads(m.group(1)) if m else []
        name = re.search(r'var fS_name\s*=\s*"([^"]+)"', s)
        span = []
        if rows:
            dates = [datetime.datetime.fromtimestamp(x["x"] / 1000, datetime.UTC).date() for x in rows]
            span = [str(min(dates)), str(max(dates))]
        manifest.append(dict(code=code, label=label, name=name.group(1) if name else None, url=url,
                             sha256=hashlib.sha256(raw).hexdigest(),
                             retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             span=span, rows=len(rows)))
        print(code, name.group(1) if name else "", len(rows), span, flush=True)
        for kind in ("jjfl", "jbgk"):
            p = RAW / f"{code}_{kind}.html"
            try:
                rr = requests.get(f"https://fundf10.eastmoney.com/{kind}_{code}.html", timeout=25)
                rr.raise_for_status()
                p.write_bytes(rr.content)
            except Exception as e:
                print("metadata failure", code, kind, type(e).__name__, flush=True)
    (ROOT / "manifest_pool2.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
