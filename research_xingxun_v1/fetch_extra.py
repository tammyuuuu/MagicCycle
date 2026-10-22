# -*- coding: utf-8 -*-
"""补充抓取：长期利率债基金 + 指数估值（月度，乐咕乐股）原始快照。

只做“下载并落盘”，不做任何清洗；清洗在 data_prep.py。
所有下载均保留 sha256 与抓取时间，便于复现。
"""
from pathlib import Path
import hashlib
import json
import re
import datetime as dt

import requests
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

# 追加标的：7-10 年国开债（长期利率债）。支付宝/微信均可小额申购。
EXTRA_FUNDS = {
    "003358": "7-10年国开债",
}

# 估值：只用当时已公布的数据，后面按“次月可用”处理。
# 乐咕乐股 index-basic-pe 接口只支持下列指数；中证红利(000922)不在其中，
# 因此用“上证红利(000015)”作代理，文件名带 proxy 标记，报告中也必须分开说明。
INDEX_PE = {
    "沪深300": ("000300", None),
    "中证500": ("000905", None),
    "上证红利": ("000015", "proxy_for_中证红利"),
}


def download_fund(code: str) -> dict:
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
    path = RAW / f"{code}.js"
    if not path.exists():
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        path.write_bytes(r.content)
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    m = re.search(r'var fS_name\s*=\s*"([^"]+)"', text)
    rows = re.search(r"var Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
    data = json.loads(rows.group(1)) if rows else []
    return dict(
        code=code,
        name=m.group(1) if m else None,
        url=url,
        sha256=hashlib.sha256(raw).hexdigest(),
        retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        rows=len(data),
    )


def download_fhsp(code: str) -> None:
    for kind in ("fhsp", "jbgk", "jjfl"):
        path = RAW / f"{code}_{kind}.html"
        if path.exists():
            continue
        r = requests.get(f"https://fundf10.eastmoney.com/{kind}_{code}.html", timeout=25)
        r.raise_for_status()
        path.write_bytes(r.content)


def download_pe() -> list:
    import akshare as ak

    log = []
    out_dir = ROOT / "raw"
    for name, (code, role) in INDEX_PE.items():
        df = ak.stock_index_pe_lg(symbol=name)
        path = out_dir / f"pe_{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        log.append(
            dict(
                index=name,
                index_code=code,
                role=role or "direct",
                rows=len(df),
                span=[str(df["日期"].min()), str(df["日期"].max())],
                source="akshare stock_index_pe_lg (乐咕乐股)",
                path=str(path.relative_to(ROOT)),
            )
        )
        print("PE", name, len(df), log[-1]["span"], flush=True)
    return log


def main() -> None:
    manifest = []
    for code, label in EXTRA_FUNDS.items():
        info = download_fund(code)
        info["label"] = label
        download_fhsp(code)
        manifest.append(info)
        print("FUND", info, flush=True)
    (ROOT / "manifest_extra.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pe = download_pe()
    (ROOT / "manifest_pe.json").write_text(
        json.dumps(pe, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
