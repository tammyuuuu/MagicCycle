# -*- coding: utf-8 -*-
"""第六轮：探测候选场外基金是否可抓取、历史长度与申购状态。"""
import json
import re

import requests

CAND = {
    "270042": ("广发纳斯达克100ETF联接(QDII)A", "纳指100"),
    "160213": ("国泰纳斯达克100指数(QDII)", "纳指100-备"),
    "050025": ("博时标普500ETF联接A", "标普500"),
    "161125": ("易方达标普500指数(QDII-LOF)A", "标普500-备"),
    "161039": ("富国中证1000指数(LOF)A", "中证1000"),
    "011612": ("华夏上证科创板50成份ETF联接A", "科创50"),
}


def main():
    out = {}
    for code, (label, tag) in CAND.items():
        row = dict(code=code, label=label, tag=tag)
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            r = requests.get(url, timeout=40)
            r.raise_for_status()
            s = r.content.decode("utf-8-sig")
            m = re.search(r'fS_name\s*=\s*"([^"]+)"', s)
            row["name"] = m.group(1) if m else None
            m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", s, re.S)
            if m:
                data = json.loads(m.group(1))
                row["rows"] = len(data)
                if data:
                    import datetime as dt
                    row["first"] = dt.datetime.utcfromtimestamp(data[0]["x"] / 1000).strftime("%Y-%m-%d")
                    row["last"] = dt.datetime.utcfromtimestamp(data[-1]["x"] / 1000).strftime("%Y-%m-%d")
            m = re.search(r"var\s+Data_ACWorthTrend\s*=\s*(\[.*?\]);", s, re.S)
            row["has_acc"] = bool(m)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        try:
            url2 = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
            h = requests.get(url2, timeout=25)
            h.raise_for_status()
            t = h.text
            t = re.sub(r"<[^>]+>", " ", t)
            t = re.sub(r"\s+", " ", t)
            m = re.search(r"购买手续费[^0-9]{0,12}([\d.]+%)", t)
            row["buy_fee"] = m.group(1) if m else None
            m = re.search(r"(限大额|暂停申购|开放申购|暂停交易)", t)
            row["status"] = m.group(1) if m else None
        except Exception as e:
            row["meta_error"] = f"{type(e).__name__}"
        out[code] = row
        print(json.dumps(row, ensure_ascii=False), flush=True)
    with open("probe_pool.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
