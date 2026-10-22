# -*- coding: utf-8 -*-
"""Python 资金池计算与网页 JS 结果的对齐回归测试。

JS 侧（capital_pool.js）没有本地 Node 环境，因此期望值取自浏览器实测：
2026-10-22 在真实站点「投资配置 → 今日操作」卡片上，用
  总金融资产 20000、池内现金 1693.28、持仓 沪深300 107.48 + 黄金 613.44
得到的建议为：
  买入 沪深300 317.15（费用 0.48）、中证红利 504.68（0.60）、国开债 871.44（0.44）
  卖出 黄金 183.11（0.18），合计买入 1693.27、卖出 183.11、费用 1.70、交易后现金 0.01
本测试用同一输入调用 Python plan_day，若另一端（Python）改动导致数字漂移会立即失败；
JS 侧改动需要重新在浏览器核对并更新这里的常量。

运行：python -B -m unittest test_parity_capital_pool -v
"""
import json
from pathlib import Path
import unittest

from capital_pool import FundInfo, Position, plan_day

ROOT = Path(__file__).resolve().parent
SITE = ROOT.parent
DATA = json.loads((SITE / "docs" / "portfolio_data.json").read_text(encoding="utf-8"))

TOL = 0.01


def _tiers(code):
    f = DATA["funds"][code]
    bt = [{"condition": "小于100万元", "original_pct": f["buy_pct"],
           "discount_pct": f["buy_pct"], "flat_fee": None}] if f.get("buy_pct") is not None else None
    return bt, f.get("redeem_tiers")


def _funds(overrides=None):
    out = {}
    for code, f in DATA["funds"].items():
        bt, rt = _tiers(code)
        out[code] = FundInfo(
            code=code, name=f["name"], price=f["nav"], status=f.get("status"),
            buy_tiers=bt, redeem_tiers=rt, buy_confirm=f.get("confirm") or "T+1",
            sell_settle_days=f.get("settle_days") or 2,
            daily_limit=None,
        )
    for code, patch in (overrides or {}).items():
        for k, v in patch.items():
            setattr(out[code], k, v)
    return out


def _targets():
    return {c: w for c, w in DATA["allocation"]["weights"].items()}


class PlanParityTest(unittest.TestCase):
    def test_browser_scenario_2026_10_22(self):
        """与网页实测完全一致的一组建议。"""
        positions = [
            Position(code="160706", name="嘉实沪深300ETF联接A", value=107.48),
            Position(code="000216", name="华安黄金ETF联接A", value=613.44),
        ]
        r = plan_day(20000, 1693.28, positions, _targets(), _funds(), ratio=0.10)
        rows = {x["code"]: x for x in r["rows"]}
        self.assertEqual(rows["160706"]["action"], "买入")
        self.assertAlmostEqual(rows["160706"]["amount"], 317.15, delta=TOL)
        self.assertAlmostEqual(rows["160706"]["fee_est"], 0.48, delta=TOL)
        self.assertEqual(rows["000216"]["action"], "卖出")
        self.assertAlmostEqual(rows["000216"]["amount"], 183.11, delta=TOL)
        self.assertAlmostEqual(rows["000216"]["fee_est"], 0.18, delta=TOL)
        self.assertAlmostEqual(rows["090010"]["amount"], 504.68, delta=TOL)
        self.assertAlmostEqual(rows["006484"]["amount"], 871.44, delta=TOL)
        self.assertAlmostEqual(r["totals"]["buys"], 1693.27, delta=TOL)
        self.assertAlmostEqual(r["totals"]["sells"], 183.11, delta=TOL)
        self.assertAlmostEqual(r["totals"]["fees"], 1.70, delta=TOL)
        self.assertAlmostEqual(r["totals"]["post_cash"], 0.01, delta=TOL)

    def test_weights_and_codes_order(self):
        a = DATA["allocation"]
        self.assertEqual(list(a["weights"].keys()), list(a["codes"]))
        self.assertLessEqual(sum(a["weights"].values()), 1 + 1e-9)

    def test_pool_over_target_blocks_new_money(self):
        r = plan_day(20000, 0, [Position("000216", "黄金", 2500.0)], _targets(), _funds(), ratio=0.10)
        self.assertGreater(r["budget"]["over_target"], 0)
        self.assertAlmostEqual(r["budget"]["new_allowed"], 0.0, delta=TOL)
        self.assertTrue(any("超过目标" in w for w in r["warnings"]))
        self.assertAlmostEqual(r["totals"]["buys"], 0.0, delta=TOL)

    def test_min_amount_blocks_tiny_buy(self):
        t = {"006484": 1.0}
        r = plan_day(200, 5.0, [], t, _funds(), ratio=0.10)
        row = [x for x in r["rows"] if x["code"] == "006484"][0]
        self.assertEqual(row["action"], "无操作")
        self.assertAlmostEqual(r["totals"]["buys"], 0.0, delta=TOL)

    def test_daily_limit_truncates(self):
        funds = _funds({"006484": {"daily_limit": 800.0}})
        r = plan_day(20000, 2000.0, [], {"006484": 1.0}, funds, ratio=0.10)
        row = [x for x in r["rows"] if x["code"] == "006484"][0]
        self.assertEqual(row["action"], "买入")
        self.assertAlmostEqual(row["amount"], 800.0, delta=TOL)

    def test_paused_fund_gets_no_trade(self):
        funds = _funds({"090010": {"status": "暂停申购"}})
        r = plan_day(20000, 2000.0, [], {"090010": 1.0}, funds, ratio=0.10)
        row = [x for x in r["rows"] if x["code"] == "090010"][0]
        self.assertEqual(row["action"], "无操作")
        self.assertFalse(row["executable"])

    def test_missing_nav_gets_no_trade(self):
        funds = _funds({"090010": {"price": None}})
        r = plan_day(20000, 2000.0, [], {"090010": 1.0}, funds, ratio=0.10)
        row = [x for x in r["rows"] if x["code"] == "090010"][0]
        self.assertEqual(row["action"], "无操作")
        self.assertIn("净值", row["reason"])

    def test_sell_proceeds_not_reused_today(self):
        positions = [Position("000216", "黄金", 1000.0, hold_days=None)]
        r = plan_day(20000, 0.0, positions, {"000216": 0.1, "090010": 0.5}, _funds(), ratio=0.10)
        buys = sum(x["amount"] for x in r["rows"] if x["action"] == "买入")
        self.assertAlmostEqual(buys, 0.0, delta=TOL)
        sells = sum(x["amount"] for x in r["rows"] if x["action"] == "卖出")
        self.assertGreater(sells, 0)

    def test_never_negative_cash(self):
        positions = [Position("160706", "沪深300", 300.0)]
        r = plan_day(5000, 100.0, positions, _targets(), _funds(), ratio=0.10)
        self.assertGreaterEqual(r["totals"]["post_cash"], -1e-6)
        self.assertLessEqual(r["totals"]["buys"], 100.0 + 1e-6)

    def test_weights_over_100_raises(self):
        with self.assertRaises(ValueError):
            plan_day(20000, 1000.0, [], {"006484": 0.7, "090010": 0.5}, _funds())


if __name__ == "__main__":
    unittest.main(verbosity=2)
