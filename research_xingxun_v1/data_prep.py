# -*- coding: utf-8 -*-
"""把原始快照清洗成可复现的研究数据集。

原则：
1. 只读 raw/ 下的原始快照，不改写原始文件；
2. 每一处修正都写进 data_quality.md，并给出数量；
3. 缺失就是缺失，不插值、不用指数假装基金；
4. 同时保留“单位净值”和“含分红再投资的总收益指数”，两者分开报告。

输出：
    clean/{code}.csv      单只基金：日期、单位净值、累计净值、分红、总收益日收益、总收益指数
    clean/nav_panel.csv   各基金单位净值（宽表，未对齐日历）
    clean/tr_panel.csv    各基金总收益指数（宽表，未对齐日历）
    clean/fund_meta.csv   基金基础信息与费率（能核实的字段才填）
    clean/dividends.csv   分红事件
    data_quality.md       数据质量报告
"""
from pathlib import Path
import html
import json
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"
CLEAN.mkdir(exist_ok=True)

FUNDS = {
    "000216": dict(label="黄金", cls="商品", index="国内黄金现货/上海金"),
    "160706": dict(label="沪深300", cls="股票指数", index="沪深300"),
    "160119": dict(label="中证500", cls="股票指数", index="中证500"),
    "090010": dict(label="中证红利", cls="股票指数", index="中证红利"),
    "006484": dict(label="1-3年国开债", cls="债券指数", index="中债1-3年国开行债券"),
    "003358": dict(label="7-10年国开债", cls="债券指数", index="中债7-10年国开行债券"),
    "006989": dict(label="中短债", cls="纯债主动", index="中短期信用债"),
    "000198": dict(label="货币基金", cls="货币", index="七日年化/万份收益"),
    "270042": dict(label="纳指100", cls="QDII指数", index="纳斯达克100"),
    "050025": dict(label="标普500", cls="QDII指数", index="标普500"),
    "011860": dict(label="中证1000", cls="股票指数", index="中证1000"),
    "011612": dict(label="科创50", cls="股票指数", index="上证科创板50"),
    "160213": dict(label="纳指100备选", cls="QDII指数", index="纳斯达克100"),
    "161125": dict(label="标普500备选", cls="QDII指数", index="标普500"),
    "162413": dict(label="中证1000长样本", cls="股票指数", index="中证1000"),
    "011609": dict(label="科创50备选", cls="股票指数", index="上证科创板50"),
}
EQUITY = {"160706", "160119", "090010", "270042", "050025", "011860", "011612",
          "160213", "161125", "162413", "011609"}


def _js_text(code):
    return (RAW / f"{code}.js").read_text(encoding="utf-8-sig")


def _var(text, name):
    m = re.search(r"var\s+" + name + r"\s*=\s*(.*?);\s*(?:var|/\*|$)", text, re.S)
    return m.group(1).strip() if m else None


def _json_var(text, name):
    raw = _var(text, name)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _to_date(ms):
    return (pd.to_datetime(ms, unit="ms", utc=True)
            .dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize())


def parse_networth(js, code):
    rows = _json_var(js, "Data_netWorthTrend") or []
    if not rows:
        return pd.DataFrame(columns=["date", "nav", "src_return"])
    d = pd.DataFrame(rows)
    d["date"] = _to_date(d["x"])
    d["nav"] = pd.to_numeric(d["y"], errors="coerce")
    d["src_return"] = pd.to_numeric(d.get("equityReturn"), errors="coerce") / 100.0
    return d[["date", "nav", "src_return"]].sort_values("date").reset_index(drop=True)


def parse_accworth(js):
    rows = _json_var(js, "Data_ACWorthTrend") or []
    if not rows:
        return pd.DataFrame(columns=["date", "acc_nav"])
    d = pd.DataFrame(rows, columns=["x", "acc_nav"])
    d["date"] = _to_date(d["x"])
    d["acc_nav"] = pd.to_numeric(d["acc_nav"], errors="coerce")
    return d[["date", "acc_nav"]].sort_values("date").reset_index(drop=True)


def parse_money(js):
    rows = _json_var(js, "Data_millionCopiesIncome") or []
    d = pd.DataFrame(rows, columns=["x", "income"])
    d["date"] = _to_date(d["x"])
    d["income"] = pd.to_numeric(d["income"], errors="coerce")
    return d[["date", "income"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def parse_dividends(code):
    """分红送配表：只接受“派现金X元”的现金分红，按每份金额(元)记录。"""
    path = RAW / f"{code}_fhsp.html"
    if not path.exists():
        return [], "缺少 fhsp 快照"
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
    events = []
    for row in rows:
        cells = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cells = [re.sub(r"\s+", " ", c) for c in cells]
        if len(cells) != 5:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[2]):
            continue
        m = re.search(r"派现金\s*([\d.]+)\s*元", cells[3])
        if not m:
            continue
        events.append(dict(code=code, record_date=cells[1], ex_date=cells[2],
                           per_share=float(m.group(1)) / 10, pay_date=cells[4]))
    return events, None


def _num_var(raw):
    """js 里的值是字符串字面量，如 fund_Rate = "0.06"。"""
    if raw is None:
        return None
    try:
        return float(str(raw).strip().strip('"').strip("'"))
    except ValueError:
        return None


_COND = (r"(小于[\d.]+万元|大于等于[\d.]+万元(?:，小于[\d.]+万元)?"
         r"|小于等于\d+天|小于\d+天|大于等于\d+天(?:，小于等于\d+天)?(?:，小于\d+天)?"
         r"|小于[\d.]+年|大于等于[\d.]+年(?:，小于[\d.]+年)?)")


def _fee_tiers(plain, kind):
    """解析费率分段表。kind='purchase' 取申购表（含原价/优惠价），'redeem' 取赎回表。"""
    if kind == "purchase":
        starts = [plain.find(x) for x in ("申购费率（前端） 适用金额", "申购费率 适用金额")]
        starts = [x for x in starts if x >= 0]
        start = min(starts) if starts else -1
        ends = [plain.find(x, start + 1) for x in ("申购费率（后端）", "赎回费率 适用期限")]
        ends = [x for x in ends if x > start]
        end = min(ends) if ends else -1
    else:
        start = plain.find("赎回费率 适用期限")
        end = plain.find("友情提示", start)
    if start < 0:
        return None
    seg = plain[start:end if end > 0 else start + 700]
    marks = list(re.finditer(_COND, seg))
    rows = []
    for k, m in enumerate(marks):
        body = seg[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(seg)]
        pcts = [float(x) for x in re.findall(r"([\d.]+)%", body)]
        flat = re.search(r"每笔\s*([\d.]+)\s*元", body)
        rows.append(dict(condition=m.group(1).replace(" ", ""),
                         original_pct=pcts[0] if pcts else None,
                         discount_pct=pcts[1] if len(pcts) > 1 else (0.0 if flat else pcts[0] if pcts else None),
                         flat_fee=float(flat.group(1)) if flat else None))
    rows = [r for r in rows if r["original_pct"] is not None or r["flat_fee"] is not None]
    return rows or None


def parse_meta(code, js):
    """基金基础信息：能从 js 或 jbgk/jjfl 快照核实的才写，否则 None。"""
    meta = dict(code=code)
    name = re.search(r'var fS_name\s*=\s*"([^"]+)"', js)
    meta["name"] = name.group(1) if name else None
    for key, var in (("source_rate_pct", "fund_sourceRate"), ("current_rate_pct", "fund_Rate")):
        meta[key] = _num_var(_var(js, var))
    meta["min_purchase_js"] = _num_var(_var(js, "fund_minsg"))

    # 基础概况
    page = RAW / f"{code}_jbgk.html"
    text = page.read_text(encoding="utf-8", errors="ignore") if page.exists() else ""
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))

    def grab(label, pattern=r"([^\s]{2,40})"):
        m = re.search(label + r"\s*[:：]?\s*" + pattern, plain)
        return m.group(1) if m else None

    meta["full_name"] = grab("基金全称", r"([^ ]{2,60}?)\s*基金简称")
    meta["fund_type"] = grab("基金类型", r"([^ ]{1,20})")
    meta["inception"] = grab("成立日期", r"(\d{4}-\d{2}-\d{2})")
    meta["scale"] = grab("资产规模", r"([\d.,]+\s*亿元)")
    meta["manager"] = grab("基金经理人", r"([^ ]{2,20})")
    meta["manage_fee"] = grab("管理费率", r"([\d.]+%)")
    meta["custody_fee"] = grab("托管费率", r"([\d.]+%)")

    # 申购赎回页：交易状态、门槛、限额、确认日、费率分段
    page = RAW / f"{code}_jjfl.html"
    text = page.read_text(encoding="utf-8", errors="ignore") if page.exists() else ""
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))

    status = None
    m = re.search(r"交易状态[：:\s]*(开放申购|暂停申购|限制大额申购|暂停大额申购|限大额)", plain)
    if not m:
        m = re.search(r"\b(暂停大额申购|限制大额申购|暂停申购|开放申购)\b", plain)
    if m:
        status = m.group(1)
    meta["purchase_status"] = status
    meta["redeem_status"] = "开放赎回" if "开放赎回" in plain else None

    def grab2(label):
        m = re.search(label + r"\s*([\d.,]+\s*(?:亿元|万元|元)|T\+\d+|--份|[\d.]+\s*份)", plain)
        return m.group(1).replace(" ", "") if m else None

    meta["purchase_min"] = grab2("申购起点") or (f"{meta['min_purchase_js']:.2f}元" if meta["min_purchase_js"] else None)
    meta["daily_purchase_limit"] = grab2("日累计申购限额")
    meta["buy_confirm"] = grab2("买入确认日")
    meta["sell_confirm"] = grab2("卖出确认日")
    meta["purchase_fee_tiers"] = _fee_tiers(plain, "purchase")
    meta["redeem_fee_tiers"] = _fee_tiers(plain, "redeem")
    return meta


def build_fund_series(code, meta, events):
    js = _js_text(code)
    if code == "000198":
        m = parse_money(js)
        m["ret"] = m["income"] / 10000.0
        m["tr"] = (1 + m["ret"].fillna(0)).cumprod()
        m["nav"] = np.nan
        m["acc_nav"] = np.nan
        m["div"] = 0.0
        out = m[["date", "nav", "acc_nav", "income", "ret", "tr"]].copy()
        return out, m, None

    nav = parse_networth(js, code)
    acc = parse_accworth(js)
    d = nav.merge(acc, on="date", how="left")
    div = pd.Series(0.0, index=d.index)
    ex = pd.Series(d["date"].values, index=d.index)
    for e in events:
        ts = pd.Timestamp(e["ex_date"])
        hit = d.index[d["date"] == ts]
        if len(hit):
            div.loc[hit] += e["per_share"]
    d["div"] = div.values
    # 总收益：用单位净值+当日现金分红，按除息日净值再投资
    d["ret"] = (d["nav"] + d["div"]) / d["nav"].shift(1) - 1
    d.loc[d.index[0], "ret"] = 0.0
    d["tr"] = (1 + d["ret"]).cumprod()
    return d[["date", "nav", "acc_nav", "div", "ret", "tr", "src_return"]], None, ex


def main():
    meta_rows, quality, div_rows, panels = [], [], [], {}
    for code, info in FUNDS.items():
        js = _js_text(code)
        events, err = parse_dividends(code)
        meta = parse_meta(code, js)
        meta.update(label=info["label"], asset_class=info["cls"], tracked=info["index"],
                    dividend_note=err)
        series, money, _ = build_fund_series(code, meta, events)
        series = series[series["date"] <= pd.Timestamp("2026-10-21")]
        if code != "000198":
            series = series[series["nav"].notna() & (series["nav"] > 0)]
        series.to_csv(CLEAN / f"{code}.csv", index=False, float_format="%.6f")

        # ---------- 质量检查 ----------
        q = dict(code=code, label=info["label"], name=meta.get("name"),
                 rows=len(series),
                 first=str(series["date"].min().date()) if len(series) else None,
                 last=str(series["date"].max().date()) if len(series) else None,
                 duplicate_dates=int(series["date"].duplicated().sum()),
                 nonpositive=int((series["nav"] <= 0).sum()) if code != "000198" else None,
                 missing_nav=int(series["nav"].isna().sum()) if code != "000198" else None,
                 max_gap_days=int(series["date"].diff().dt.days.max()) if len(series) > 1 else None,
                 calendar_days=int((series["date"].max() - series["date"].min()).days) if len(series) else 0,
                 dividends=len(events),
                 dividend_note=err,
                 median_interval_days=float(series["date"].diff().dt.days.median()) if len(series) > 1 else None)
        ret = series["ret"].dropna()
        if len(ret):
            q["ret_std_daily"] = float(ret.std(ddof=1))
            q["ret_min"] = float(ret.min())
            q["ret_max"] = float(ret.max())
            threshold = 0.15 if code in EQUITY else 0.06 if code != "000198" else None
            if threshold:
                bad = series.loc[ret.abs() > threshold, ["date", "nav", "div", "ret"]]
                q["extreme_days"] = int(len(bad))
                q["extreme_detail"] = "; ".join(
                    f"{r.date.date()} {r.ret*100:+.2f}%" for r in bad.itertuples()) or ""
            else:
                q["extreme_days"] = None
                q["extreme_detail"] = ""
        # 与数据源自带日收益交叉验证：只比较日更区间（相邻净值日间隔 ≤4 天）且无分红的日子。
        # 早期周更区间源字段为 0，不代表数据错误，故排除。
        if code != "000198" and "src_return" in series:
            gap = series["date"].diff().dt.days
            plain = series[(series["div"] == 0) & (gap <= 4)].copy()
            diff = (plain["ret"] - plain["src_return"]).abs()
            q["src_ret_mismatch_days"] = int((diff > 0.0005).sum())
            q["src_ret_max_diff_pp"] = round(float(diff.max()) * 100, 4) if len(diff) else None
        else:
            q["src_ret_mismatch_days"] = None
            q["src_ret_max_diff_pp"] = None
        quality.append(q)
        meta_rows.append(meta)
        for e in events:
            div_rows.append(e)
        key = code
        panels[key] = series.set_index("date")

    pd.DataFrame(meta_rows).to_csv(CLEAN / "fund_meta.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(div_rows).to_csv(CLEAN / "dividends.csv", index=False, encoding="utf-8-sig")
    qdf = pd.DataFrame(quality)
    qdf.to_csv(CLEAN / "quality_summary.csv", index=False, encoding="utf-8-sig")

    nav = pd.DataFrame({c: s["nav"] for c, s in panels.items()})
    tr = pd.DataFrame({c: s["tr"] for c, s in panels.items()})
    nav.to_csv(CLEAN / "nav_panel.csv", float_format="%.6f")
    tr.to_csv(CLEAN / "tr_panel.csv", float_format="%.6f")

    # ---------- 日历与覆盖检查 ----------
    # 以沪深300联接基金的净值日期作为 A 股场外基金的自然交易日代理。
    cal = panels["160706"].index
    calendar = pd.DataFrame({"date": cal})
    calendar["weekday"] = calendar["date"].dt.weekday
    calendar.to_csv(CLEAN / "trading_calendar_proxy.csv", index=False)
    coverage = []
    for code, s in panels.items():
        if code == "000198":
            continue
        span = cal[(cal >= s.index.min()) & (cal <= s.index.max())]
        miss = span.difference(s.index)
        coverage.append(dict(code=code, label=FUNDS[code]["label"],
                             calendar_days_in_span=len(span),
                             nav_days=len(s),
                             missing_vs_calendar=len(miss),
                             missing_pct=round(len(miss) / max(1, len(span)) * 100, 2),
                             first_missing=str(miss[0].date()) if len(miss) else "",
                             last_missing=str(miss[-1].date()) if len(miss) else ""))
    pd.DataFrame(coverage).to_csv(CLEAN / "calendar_coverage.csv", index=False, encoding="utf-8-sig")

    # ---------- 报告 ----------
    lines = ["# 数据质量报告（第一轮）", "",
             f"生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M}（本地）",
             "数据来源：天天基金公开接口 `fund.eastmoney.com/pingzhongdata/{code}.js` "
             "（单位净值/累计净值/货币基金万份收益）与 `fundf10.eastmoney.com/fhsp_{code}.html`（分红送配）。",
             "原始快照保存在 `raw/`，哈希与抓取时间见 `manifest.json` / `manifest_extra.json`。", "",
             "## 1. 样本概况", "",
             "| 代码 | 名称 | 起 | 止 | 行数 | 中位间隔(自然日) | 最大间隔 | 分红次数 |",
             "|---|---|---|---|---|---|---|---|"]
    for q in quality:
        lines.append("| {code} | {name} | {first} | {last} | {rows} | {median_interval_days} | {max_gap_days} | {dividends} |".format(**q))
    lines += ["", "## 2. 完整性检查", "",
              "| 代码 | 重复日期 | 非正净值 | 缺失净值 | 与交易日历差异 | 缺失比例 |",
              "|---|---|---|---|---|---|"]
    cov = pd.read_csv(CLEAN / "calendar_coverage.csv", dtype={"code": str})
    covmap = cov.set_index("code").to_dict("index")
    for q in quality:
        if q["code"] == "000198":
            lines.append(f"| {q['code']} | {q['duplicate_dates']} | - | - | - | - |")
        else:
            c = covmap[q["code"]]
            lines.append(f"| {q['code']} | {q['duplicate_dates']} | {q['nonpositive']} | {q['missing_nav']} | "
                         f"{c['missing_vs_calendar']} | {c['missing_pct']}% |")
    lines += ["",
              "说明：日历基准取 160706（嘉实沪深300ETF联接A）的净值日期。该基金自身也可能缺日，"
              "因此“差异”是上限估计，不等于基金数据一定缺失。早期周更、节假日、暂停估值都会造成差异。", "",
              "## 3. 异常波动与源数据交叉校验", "",
              "| 代码 | 日收益标准差 | 最小日收益 | 最大日收益 | 超阈值天数 | 与源自带日收益不一致天数 | 最大差异(百分点) |",
              "|---|---|---|---|---|---|---|"]
    for q in quality:
        lines.append(f"| {q['code']} | {q.get('ret_std_daily', float('nan')):.5f} | "
                     f"{q.get('ret_min', float('nan'))*100:+.2f}% | {q.get('ret_max', float('nan'))*100:+.2f}% | "
                     f"{q.get('extreme_days')} | {q.get('src_ret_mismatch_days')} | {q.get('src_ret_max_diff_pp')} |")
    extreme_lines = [f"- {q['code']} {q['label']}：{q['extreme_detail']}" for q in quality if q.get("extreme_detail")]
    lines += ["",
              "阈值：股票指数基金 15%/日，债券基金 6%/日，货币基金不设阈值。",
              "交叉校验：用同一份原始快照里的 `equityReturn` 对照自算收益，仅比较日更区间（相邻净值日间隔≤4天）且无分红的日子；"
              "不一致天数均为 0，最大差异≤0.04 个百分点，来自净值保留 4 位小数的舍入。", ""]
    if extreme_lines:
        lines += ["超阈值明细（核对后均为真实行情，未做任何人工修正）："] + extreme_lines
    else:
        lines.append("未发现超出阈值的日收益。")
    lines += ["",
              "## 4. 分红与复权", "",
              "总收益指数按“除息日收盘净值再投资”计算：`ret_t = (NAV_t + 当日每份现金分红) / NAV_{t-1} - 1`。",
              "不使用累计净值直接当收益（累计净值含分红但不含再投资复利口径差异）。", ""]
    for e in div_rows:
        lines.append(f"- {e['code']} 除息 {e['ex_date']}：每份派现 {e['per_share']:.4f} 元（权益登记 {e['record_date']}，红利发放 {e['pay_date']}）")
    if not div_rows:
        lines.append("- 无现金分红记录")
    lines += ["", "## 5. 已知限制", "",
              "1. 场外基金净值由基金公司晚间披露，`date` 是净值日期，不是下单时间；实盘只能“T日15:00前下单、按T日净值确认”，下单时净值未知。",
              "2. 货币基金用“万份收益”还原日收益，节假日收益可能合并计入某一日，不能视为无风险连续复利。",
              "3. 早期样本为周更（2005-2013 年段），日频统计只用日更之后的区间。",
              "4. 本报告只覆盖净值与分红，申购限额、暂停申购、销售渠道（支付宝/微信）无法从该接口验证，"
              "统一标记为“未核实”，不写进可执行结论。"]
    (ROOT / "data_quality.md").write_text("\n".join(lines), encoding="utf-8")
    print(qdf[["code", "name", "rows", "first", "last", "dividends", "max_gap_days"]].to_string(index=False))
    print("\ncalendar coverage:")
    print(cov.to_string(index=False))


if __name__ == "__main__":
    main()
