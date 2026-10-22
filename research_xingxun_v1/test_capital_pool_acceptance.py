# -*- coding: utf-8 -*-
"""第四轮验收测试：资金池与买卖金额计算。

运行：python test_capital_pool_acceptance.py
"""
from capital_pool import FundInfo, Position, plan_day, pool_budget


def f(code, price=1.0, status="开放申购", buy=0.15, redeem=None, limit=None):
    return FundInfo(code=code, name=code, price=price, status=status,
                    buy_tiers=[{"condition": "小于100万元", "original_pct": buy,
                                "discount_pct": buy, "flat_fee": None}],
                    redeem_tiers=redeem or [
                        {"condition": "小于7天", "original_pct": 1.5, "discount_pct": 1.5, "flat_fee": None},
                        {"condition": "大于等于7天，小于365天", "original_pct": 0.5, "discount_pct": 0.5, "flat_fee": None},
                        {"condition": "大于等于365天", "original_pct": 0.0, "discount_pct": 0.0, "flat_fee": None}],
                    daily_limit=limit)


def test_first_entry_cash_never_negative():
    funds = {"A": f("A"), "B": f("B", buy=0.05)}
    r = plan_day(20000, 2000, [], {"A": 0.5, "B": 0.5}, funds)
    buys = [x for x in r["rows"] if x["action"] == "买入"]
    assert len(buys) == 2
    assert abs(sum(x["amount"] for x in buys) - 2000) < 0.05
    assert r["totals"]["post_cash"] >= -1e-9
    assert r["budget"]["new_used"] == 0
    # 费用必须为正
    assert all(x["fee_est"] > 0 for x in buys)


def test_settlement_gap_then_available():
    funds = {"A": f("A"), "B": f("B")}
    r1 = plan_day(20000, 0, [Position("A", "A", 300, hold_days=200)],
                  {"A": 0.0, "B": 0.5}, funds)
    assert next(x for x in r1["rows"] if x["code"] == "A")["action"] == "卖出"
    assert next(x for x in r1["rows"] if x["code"] == "B")["action"] != "买入"
    # T+2 后回款到账，才可买入
    r2 = plan_day(20000, 299, [], {"A": 0.0, "B": 0.5}, funds)
    assert next(x for x in r2["rows"] if x["code"] == "B")["action"] == "买入"


def test_external_cash_cap():
    funds = {"A": f("A")}
    r = plan_day(20000, 0, [], {"A": 1.0}, funds, external_cash=500)
    assert abs(r["budget"]["new_used"] - 500) < 1e-9
    assert r["rows"][0]["amount"] <= 500


def test_over_target_blocks_new_money():
    funds = {"A": f("A")}
    r = plan_day(19000, 2000, [], {"A": 1.0}, funds, external_cash=1000)
    assert r["budget"]["new_allowed"] == 0
    assert r["budget"]["new_used"] == 0
    assert any("超过目标" in w for w in r["warnings"])


def test_pro_rata_when_cash_short():
    funds = {"A": f("A"), "B": f("B")}
    r = plan_day(20000, 100, [], {"A": 0.5, "B": 0.5}, funds)
    buys = {x["code"]: x["amount"] for x in r["rows"] if x["action"] == "买入"}
    assert abs(buys["A"] - buys["B"]) < 0.02
    assert abs(sum(buys.values()) - 100) < 0.05


def test_min_amount_not_traded():
    funds = {"A": f("A"), "B": f("B")}
    r = plan_day(20000, 15, [], {"A": 0.5, "B": 0.5}, funds)
    assert all(x["action"] != "买入" for x in r["rows"])
    assert abs(r["totals"]["post_cash"] - 15) < 1e-9


def test_seven_day_penalty():
    funds = {"A": f("A")}
    r = plan_day(20000, 0, [Position("A", "A", 1000, hold_days=3)],
                 {"A": 0.0}, funds)
    row = r["rows"][0]
    assert row["action"] == "卖出"
    assert abs(row["fee_est"] - 15.0) < 0.01


def test_unknown_holding_days_is_conservative():
    funds = {"A": f("A")}
    r = plan_day(20000, 0, [Position("A", "A", 1000, hold_days=None)],
                 {"A": 0.0}, funds)
    row = r["rows"][0]
    assert row["action"] == "卖出"
    assert row["fee_est"] > 0
    assert "保守" in row["reason"]


def test_paused_and_limit():
    funds = {"A": f("A", status="暂停申购"), "B": f("B", limit=100)}
    r = plan_day(20000, 500, [], {"A": 0.5, "B": 0.5}, funds)
    a = next(x for x in r["rows"] if x["code"] == "A")
    b = next(x for x in r["rows"] if x["code"] == "B")
    assert a["action"] != "买入" and "暂停" in a["reason"]
    assert b["action"] == "买入" and b["amount"] <= 100 and "限额" in b["reason"]


def test_weights_below_100_leaves_cash():
    funds = {"A": f("A")}
    r = plan_day(20000, 1000, [], {"A": 0.5}, funds)
    assert r["rows"][0]["action"] == "买入"
    assert r["totals"]["post_cash"] >= 480


def test_idempotent():
    funds = {"A": f("A"), "B": f("B")}
    args = dict(total_assets=20000, pool_cash=500, positions=[], targets={"A": 0.5, "B": 0.5},
                funds=funds)
    r1 = plan_day(**args)
    r2 = plan_day(**args)
    assert r1["totals"] == r2["totals"]
    assert [(x["code"], x["action"], x["amount"]) for x in r1["rows"]] == \
           [(x["code"], x["action"], x["amount"]) for x in r2["rows"]]


def test_pool_value_formula():
    b = pool_budget(20000, 1234.5, 100)
    assert abs(b["pool_target"] - 2000) < 1e-9
    assert abs(b["new_allowed"] - 765.5) < 1e-9
    assert b["over_target"] == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("acceptance tests passed")
