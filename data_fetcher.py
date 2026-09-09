# -*- coding: utf-8 -*-
"""
数据获取模块
============
用 AkShare 拉取 ETF 日线行情并落地本地 CSV 缓存，避免每次运行都请求网络。

数据源策略（自动降级）：
    1) 主源  东方财富 fund_etf_hist_em  —— 默认【前复权】
    2) 备用  新浪     fund_etf_hist_sina —— 东财不可达时自动切换（【不复权】）
两个源的缓存相互独立，互不污染。

对外主要接口：
    fetch_etf_daily(code, start, end, use_cache=True, force=False)
        -> DataFrame
           索引：date（DatetimeIndex，升序）
           列  ：open / high / low / close / volume / amount / pct_chg
"""

import os
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from config import ADJUST, CACHE_DIR, CACHE_MAX_AGE

# AkShare 中文列名 -> 本项目统一使用的英文列名
# （东财源返回中文列名需要映射；新浪源返回的本来就是英文列名）
_EM_COLUMN_MAP = {
    "日期":   "date",
    "开盘":   "open",
    "收盘":   "close",
    "最高":   "high",
    "最低":   "low",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_chg",
}
_SINA_COLUMN_MAP = {}

# 数据集中真正用到的列（顺序即输出顺序）
_KEEP = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(code: str, source: str) -> str:
    """每只 ETF、每个数据源各一份独立缓存文件。
    东财沿用旧命名（etf_{code}_{复权}.csv）以复用既有缓存；新浪单独一份。"""
    tag = ADJUST or "raw"
    if source == "sina":
        return os.path.join(CACHE_DIR, f"etf_{code}_sina.csv")
    return os.path.join(CACHE_DIR, f"etf_{code}_{tag}.csv")


def _cache_age_days(path: str) -> float:
    """返回缓存文件距今多少天。"""
    return (datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))).days


def _read_cache(path: str) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _clean(df: pd.DataFrame, rename_map: dict) -> pd.DataFrame:
    """统一列名、按日期升序去重、设日期为索引；缺 pct_chg 时用收盘价换算。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=_KEEP)
    df = df.rename(columns=rename_map)
    keep = [c for c in _KEEP if c in df.columns]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume", "amount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
    if "pct_chg" not in df.columns:
        df["pct_chg"] = df["close"].pct_change() * 100  # 单位：%
    df = df.set_index("date")
    df.index.name = "date"
    return df


def _combine(cached: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """增量合并：保留日期唯一且按日期升序。"""
    if cached is not None and not cached.empty:
        return (pd.concat([cached, fresh])
                  .reset_index()
                  .drop_duplicates(subset="date", keep="last")
                  .set_index("date")
                  .sort_index())
    return fresh


def _load_or_fetch(path: str, fetch_fn, start: str, end: str,
                   use_cache: bool, force: bool) -> pd.DataFrame:
    """
    通用缓存逻辑：
      - 缓存足够新 -> 直接读本地；
      - 缓存过期   -> 从缓存末尾做增量拉取再合并；
      - 无缓存     -> 全量拉取。
    fetch_fn(start, end) 负责调用具体 AkShare 接口并返回清理后的 DataFrame。
    """
    cached = None
    if use_cache and not force and os.path.exists(path):
        if _cache_age_days(path) <= CACHE_MAX_AGE:
            return _read_cache(path)
        cached = _read_cache(path)

    fetch_start = (cached.index.max() + timedelta(days=1)).strftime("%Y%m%d") \
        if cached is not None and not cached.empty else start

    fresh = fetch_fn(fetch_start, end)
    if fresh is None or fresh.empty:
        # 网络没返回新数据 -> 退回旧缓存
        if cached is not None and not cached.empty:
            return cached
        return fresh  # 空结果交给上层判断

    combined = _combine(cached, fresh)
    if use_cache:
        _ensure_cache_dir()
        combined.to_csv(path)
    return combined


def fetch_etf_daily(code: str, start: str = "20150101", end: str = "20500101",
                    use_cache: bool = True, force: bool = False) -> pd.DataFrame:
    """
    获取单只 ETF 日线行情。优先东财（前复权），失败自动切换新浪（不复权）。

    参数
    ----
    code      : 6 位 ETF 代码，如 "510500"
    start/end : 日期区间，格式 "YYYYMMDD"
    use_cache : 是否使用本地缓存（默认 True）
    force     : True 时忽略缓存，强制全量重新拉取

    返回
    ----
    DataFrame，date 为升序索引。
    """
    _ensure_cache_dir()
    errors = []

    # ---- 主源：东方财富（前复权） ----
    try:
        path = _cache_path(code, "eastmoney")
        df = _load_or_fetch(
            path,
            lambda s, e: _clean(
                ak.fund_etf_hist_em(symbol=code, period="daily",
                                    start_date=s, end_date=e, adjust=ADJUST),
                _EM_COLUMN_MAP),
            start, end, use_cache, force)
        if df is not None and not df.empty:
            return df
        errors.append("东财源返回空数据")
    except Exception as e:
        errors.append(f"东财源 {type(e).__name__}: {e}")

    # ---- 备用源：新浪（不复权） ----
    symbol = ("sh" if code[0] in ("5", "6") else "sz") + code
    try:
        path = _cache_path(code, "sina")
        df = _load_or_fetch(
            path,
            lambda s, e: _clean(ak.fund_etf_hist_sina(symbol=symbol),
                                _SINA_COLUMN_MAP),
            start, end, use_cache, force)
        if df is not None and not df.empty:
            print(f"    [提示] 东财源不可用，已切换新浪源返回 {code}（不复权）")
            return df
        errors.append("新浪源返回空数据")
    except Exception as e:
        errors.append(f"新浪源 {type(e).__name__}: {e}")

    raise ConnectionError(f"获取 {code} 失败：" + "；".join(errors))


def fetch_etf_spot() -> pd.DataFrame:
    """获取全市场 ETF 实时行情快照（含最新价/涨跌幅等）。"""
    return ak.fund_etf_spot_em()
