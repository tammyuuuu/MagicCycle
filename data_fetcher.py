# -*- coding: utf-8 -*-
"""
数据获取模块
============
用 AkShare 拉取 ETF 日线行情并落地本地 CSV 缓存，避免每次运行都请求网络。

数据源策略（自动降级）：
    1) 主源  东方财富 fund_etf_hist_em  —— 默认【前复权】
    2) 备源  腾讯     fqkline/get        —— 同样【前复权】，价格口径与东财一致
    3) 备用  新浪     fund_etf_hist_sina —— 最后兜底（【不复权】）
三个源的缓存相互独立，互不污染。

对外主要接口：
    fetch_etf_daily(code, start, end, use_cache=True, force=False)
        -> DataFrame
           索引：date（DatetimeIndex，升序）
           列  ：open / high / low / close / volume / amount / pct_chg
"""

import os
import socket
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import requests

from config import ADJUST, CACHE_DIR

# akshare 内部有请求不带 timeout（如新浪源），网络半死时会一直挂着不返回。
# 设一个全局 socket 默认超时，保证任何请求最终都会失败退出，而不是卡死整个刷新。
socket.setdefaulttimeout(20)

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


def _retry(fn, tries: int = 3, wait: float = 1.0):
    """接口偶发 RemoteDisconnected / 超时，重试几次再放弃。

    否则东财源一旦抖一下就会误降级到新浪源（不复权），
    造成同一天的数据口径前后不一致。"""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(wait)
    raise last


# 数据源“失败记忆”：某个源刚失败过，短时间内不再重复尝试。
# 东财单次超时 15 秒 × 重试 3 次 ≈ 45 秒；一次运行往往要拉多只 ETF，
# 没必要每只都先陪它跑一遍。
_FAIL_COOLDOWN = 600.0        # 秒（同一源在此时间内被视为“刚挂过”）
_SRC_FAILS = {}               # {(code, source): 上次失败的时间戳}


def _src_cooling(code: str, source: str) -> bool:
    """该源是否处于“刚失败”的冷却期。"""
    ts = _SRC_FAILS.get((code, source))
    return ts is not None and (time.time() - ts) < _FAIL_COOLDOWN


def _mark_src(code: str, source: str, ok: bool) -> None:
    """记录某个源本次的成败，供冷却判断使用。"""
    key = (code, source)
    if ok:
        _SRC_FAILS.pop(key, None)
    else:
        _SRC_FAILS[key] = time.time()


def _cache_path(code: str, source: str) -> str:
    """每只 ETF、每个数据源各一份独立缓存文件。
    东财沿用旧命名（etf_{code}_{复权}.csv）以复用既有缓存；腾讯/新浪各单独一份。"""
    tag = ADJUST or "raw"
    if source == "sina":
        return os.path.join(CACHE_DIR, f"etf_{code}_sina.csv")
    if source == "tencent":
        return os.path.join(CACHE_DIR, f"etf_{code}_tencent.csv")
    return os.path.join(CACHE_DIR, f"etf_{code}_{tag}.csv")


def _expected_latest_trade_date(now: datetime = None):
    """粗略估算“此刻数据应已可用”的最新交易日（不依赖交易日历）。

    - 15:00 前：当天尚未收盘，最新可用数据算到上一工作日；
    - 周末：顺延回最近的周五。
    遇节假日只会“多请求一次”（拿不到新数据就沿用缓存），不会漏更新。
    """
    now = now or datetime.now()
    d = now.date()
    if now.hour < 15:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _cache_is_current(cached: pd.DataFrame) -> bool:
    """缓存里最后一条数据是否已到最近一个应已收盘的交易日。"""
    if cached is None or cached.empty:
        return False
    return cached.index.max().date() >= _expected_latest_trade_date()


def _trim_incomplete(df: pd.DataFrame) -> pd.DataFrame:
    """丢弃尚未收盘的“当日”K 线。

    东方财富源在盘中就会带上当天的行（收盘价=当前价），如果直接落盘，
    当天收盘后就不会再重新拉取，页面会一直停在盘中快照。"""
    if df is None or df.empty:
        return df
    limit = _expected_latest_trade_date()
    return df[df.index.date <= limit]


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


def _stale_cache(code: str):
    """挑一份可用的本地旧缓存（网络全挂时的兜底）。

    优先前复权口径（东财 / 腾讯，两者价格一致），并在其中取数据最新的那份；
    两个都没有才用新浪（不复权）。返回 (DataFrame, 源名)，都没有则 (None, None)。
    """
    def _load(source):
        path = _cache_path(code, source)
        if not os.path.exists(path):
            return None
        try:
            df = _trim_incomplete(_read_cache(path))
        except Exception:
            return None          # 缓存文件损坏，当作没有
        return df if df is not None and not df.empty else None

    best = None
    for source in ("eastmoney", "tencent"):
        df = _load(source)
        if df is not None and (best is None or df.index.max() > best[0].index.max()):
            best = (df, source)
    if best is not None:
        return best

    df = _load("sina")
    return (df, "sina") if df is not None else (None, None)


# =============================================================
# 腾讯日线（免费、无 token，价格口径与东财前复权一致）
# =============================================================
_TENCENT_URL = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                "?param={symbol},day,{start},{end},{count},{fq}")
_TENCENT_MAX_ROWS = 640          # 单次最多返回 640 根 K 线
_TENCENT_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_tencent(code: str, start: str, end: str) -> pd.DataFrame:
    """用腾讯行情拉日线（第三方备用源）。

    返回行格式为 [日期, 开, 收, 高, 低, 成交量(手)]，
    接口不提供成交额，故 amount 置空（不参与策略计算）。"""
    symbol = ("sh" if code[0] in ("5", "6") else "sz") + code
    fq = ADJUST if ADJUST in ("qfq", "hfq") else ""
    key = f"{fq}day" if fq else "day"

    s = datetime.strptime(start, "%Y%m%d").date()
    e = datetime.strptime(end, "%Y%m%d").date()
    today = datetime.now().date()
    if e > today:
        e = today

    rows = []
    cur = s
    while cur <= e:
        # 单次最多 640 根，按大约 2 年一个窗口分段（约 490 个交易日）
        stop = min(cur + timedelta(days=730), e)
        url = _TENCENT_URL.format(symbol=symbol, start=cur.isoformat(),
                                  end=stop.isoformat(),
                                  count=_TENCENT_MAX_ROWS, fq=fq)
        node = ((requests.get(url, timeout=15,
                              headers=_TENCENT_HEADERS).json()
                 .get("data") or {}).get(symbol) or {})
        rows += node.get(key) or node.get("day") or []
        cur = stop + timedelta(days=1)

    if not rows:
        return pd.DataFrame(columns=_KEEP)

    df = pd.DataFrame([r[:6] for r in rows])
    df.columns = ["date", "open", "close", "high", "low", "volume"]
    df["amount"] = pd.NA          # 腾讯日线不给成交额
    return _clean(df, {})         # 列名已是英文，无需 rename


def _load_or_fetch(path: str, fetch_fn, start: str, end: str,
                   use_cache: bool, force: bool) -> pd.DataFrame:
    """
    通用缓存逻辑：
      - 缓存已含最近交易日数据 -> 直接读本地；
      - 缓存落后               -> 从缓存末尾做增量拉取再合并；
      - 无缓存                 -> 全量拉取。
    fetch_fn(start, end) 负责调用具体 AkShare 接口并返回清理后的 DataFrame。
    """
    cached = None
    if use_cache and not force and os.path.exists(path):
        cached = _trim_incomplete(_read_cache(path))
        # 判定依据是“缓存里的数据日期”，不是文件修改时间：
        # 只要已包含最近一个应已收盘的交易日就直接复用，
        # 否则（哪怕文件刚写过不久）也做一次增量补齐，避免数据停在旧日期。
        if _cache_is_current(cached):
            return cached

    fetch_start = (cached.index.max() + timedelta(days=1)).strftime("%Y%m%d") \
        if cached is not None and not cached.empty else start

    fresh = _trim_incomplete(fetch_fn(fetch_start, end))
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
    获取单只 ETF 日线行情。降级顺序：东财（前复权）→ 腾讯（前复权）→ 新浪（不复权）。

    参数
    ----
    code      : 6 位 ETF 代码，如 "510500"
    start/end : 日期区间，格式 "YYYYMMDD"
    use_cache : 是否使用本地缓存（默认 True）
    force     : True 时忽略缓存，强制全量重新拉取

    返回
    ----
    DataFrame，date 为升序索引。

    三个源都拉不到时（通常断网/开机没联网），若允许用缓存则退回本地旧缓存，
    并在 df.attrs["stale_note"] 里标注数据截止日，供调用方提示用户。
    """
    _ensure_cache_dir()
    errors = []

    # ---- 主源：东方财富（前复权） ----
    if _src_cooling(code, "eastmoney"):
        errors.append("东财源刚失败过，本次直接跳过")
    else:
        try:
            path = _cache_path(code, "eastmoney")
            df = _load_or_fetch(
                path,
                lambda s, e: _retry(lambda: _clean(
                    ak.fund_etf_hist_em(symbol=code, period="daily",
                                        start_date=s, end_date=e,
                                        adjust=ADJUST),
                    _EM_COLUMN_MAP)),
                start, end, use_cache, force)
            if df is not None and not df.empty:
                _mark_src(code, "eastmoney", True)
                return df
            errors.append("东财源返回空数据")
            _mark_src(code, "eastmoney", False)
        except Exception as e:
            errors.append(f"东财源 {type(e).__name__}: {e}")
            _mark_src(code, "eastmoney", False)

    # ---- 备用源 1：腾讯（前复权，免费无 token，口径与东财一致） ----
    if _src_cooling(code, "tencent"):
        errors.append("腾讯源刚失败过，本次直接跳过")
    else:
        try:
            path = _cache_path(code, "tencent")
            df = _load_or_fetch(
                path,
                lambda s, e: _retry(lambda: _fetch_tencent(code, s, e)),
                start, end, use_cache, force)
            if df is not None and not df.empty:
                _mark_src(code, "tencent", True)
                print(f"    [提示] 东财源不可用，已切换腾讯源返回 {code}"
                      f"（{ADJUST or '不复权'}）")
                return df
            errors.append("腾讯源返回空数据")
            _mark_src(code, "tencent", False)
        except Exception as e:
            errors.append(f"腾讯源 {type(e).__name__}: {e}")
            _mark_src(code, "tencent", False)

    # ---- 备用源 2：新浪（不复权） ----
    symbol = ("sh" if code[0] in ("5", "6") else "sz") + code
    try:
        path = _cache_path(code, "sina")
        df = _load_or_fetch(
            path,
            lambda s, e: _retry(lambda: _clean(
                ak.fund_etf_hist_sina(symbol=symbol), _SINA_COLUMN_MAP)),
            start, end, use_cache, force)
        if df is not None and not df.empty:
            _mark_src(code, "sina", True)
            print(f"    [提示] 东财/腾讯源不可用，已切换新浪源返回 {code}（不复权）")
            return df
        errors.append("新浪源返回空数据")
        _mark_src(code, "sina", False)
    except Exception as e:
        errors.append(f"新浪源 {type(e).__name__}: {e}")
        _mark_src(code, "sina", False)

    # ---- 三个源全挂：退回本地旧缓存 ----
    # 断网/开机没联网时，本地哪怕只差一天的数据也比整页“数据/计算失败”有用。
    # 只在允许用缓存时兜底；force=True / use_cache=False 属显式要求联网，仍照旧报错。
    if use_cache and not force:
        stale, src_name = _stale_cache(code)
        if stale is not None:
            last = stale.index.max().date()
            note = f"{code} 截至 {last}"
            print(f"    [警告] 数据源均不可用，改用本地旧缓存：{code}“{src_name}”"
                  f"（数据截至 {last}）")
            stale.attrs["stale_note"] = note
            return stale

    raise ConnectionError(f"获取 {code} 失败：" + "；".join(errors))


def fetch_etf_spot() -> pd.DataFrame:
    """获取全市场 ETF 实时行情快照（含最新价/涨跌幅等）。"""
    return ak.fund_etf_spot_em()
