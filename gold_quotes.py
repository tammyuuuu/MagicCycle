"""Verified CycleTest history and incremental Shanghai Gold Exchange daily closes."""
from datetime import timedelta
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "gold_au9999/verified_daily.csv"
TAIL = ROOT / "docs/au9999_recent.csv"
URL = "https://www.sge.com.cn/sjzx/quotation_daily_new"


def read_quotes(path):
    frame = pd.read_csv(path, index_col="date", parse_dates=True)
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing or not (
            np.isfinite(frame.close) & frame.close.gt(0)).all():
        raise ValueError("Au99.99 日线日期或收盘价异常")
    return frame


def history():
    seed = read_quotes(SEED).loc["2007":]
    if TAIL.exists():
        tail = read_quotes(TAIL)
        if not tail.empty and tail.index[0] <= seed.index[-1]:
            raise ValueError("新增金价与研究快照重叠")
        return pd.concat([seed, tail])
    return seed


def update(sessions, *, persist=False):
    data = history()
    previous = data.index[-1]
    end = sessions.max()
    if end <= previous:
        return data.close.loc[:end]
    if previous not in sessions:
        raise ValueError("ETF 交易日序列未覆盖上次已核实的金价日期")
    start = data.index[-1] + timedelta(days=1)
    rows = []
    while start <= end:
        stop = min(end, start + timedelta(days=6))
        response = requests.get(URL, params=dict(start_date=str(start.date()), end_date=str(stop.date()),
                                inst_ids="Au99.99"), headers={"User-Agent":"Mozilla/5.0"}, timeout=20)
        response.raise_for_status()
        header = None
        for tr in BeautifulSoup(response.content, "html.parser", from_encoding="utf8").select("tr"):
            cells = [cell.get_text(strip=True) for cell in tr.select("td,th")]
            if {"日期", "合约", "收盘价"}.issubset(cells):
                header = cells
            elif header and "Au99.99" in cells:
                record = dict(zip(header, cells))
                day = pd.Timestamp(record["日期"])
                if record["合约"] == "Au99.99" and start <= day <= stop:
                    rows.append((day, float(record["收盘价"].replace(",", "")), response.url))
        start = stop + timedelta(days=1)
    if rows:
        new = pd.DataFrame(rows, columns=["date","close","source"]).set_index("date").sort_index()
        if not new.index.is_unique or not (np.isfinite(new.close) & new.close.gt(0)).all():
            raise ValueError("上金所新增报价异常")
        data = pd.concat([data,new])
    seed_end = read_quotes(SEED).index[-1]
    expected = sessions[sessions > seed_end]
    if len(expected.difference(data.index)) or data.index[-1] < end:
        raise ValueError("Au99.99 日线缺失，无法确认交易信号")
    if rows and persist:
        with tempfile.NamedTemporaryFile(dir=TAIL.parent, delete=False, suffix=".csv") as tmp:
            path = Path(tmp.name)
        try:
            data.loc[data.index > seed_end].to_csv(path)
            path.replace(TAIL)
        finally:
            path.unlink(missing_ok=True)
    return data.close.loc[:end]
