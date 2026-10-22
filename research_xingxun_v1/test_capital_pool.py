# -*- coding: utf-8 -*-
"""capital_pool 的基本资金校验测试。运行：python test_capital_pool.py"""
from capital_pool import FundInfo, Position, plan_day, pool_budget


def fund(code, price=1.0, status="开放申购", buy_tiers=None, redeem_tiers=None,
         limit=None, settle=2):
    return FundInfo(code=code, name=code, price=price, status=status,
                    buy_tiers=buy_tiers or [{"condition": "小于100万元", "original_pct": 0.15,
                                             "discount_pct": 0.15, "flat_fee": None}],
                    redeem_tiers=redeem_tiers or [
                        {"condition": "小于7天", "original_pct": 1.5, "discount_pct": 1.5, "flat_fee": None},
                        {"condition": "大于等于7天，小于365天", "original_pct": 0.5, "discount_pct": 0.5, "flat_fee": None},
                        {"condition": "大于等于365天", "original_pct": 0.0, "discount_pct": 0.0, "flat_fee": None}],
                    daily_limit=limit, sell_settle_days=settle)


def test_budget():
    b = pool_budget(20000, 0, 5000)
    assert abs(b["pool_target"] - 2000) < 1e-9
    assert abs(b["new_allowed"] - 2000) < 1e-9
    assert abs(b["new_used"] - 2000) < 1e-9
    b = pool_budget(20000, 2500, 5000)
    assert b["new_allowed"] == 0 and abs(b["over_target"] - 500) < 1e-9
    b = pool_budget(20000, 500, 300)
    assert abs(b["new_allowed"] - 1500) < 1e-9
    assert abs(b["new_used"] - 300) < 1e-9


def test_pro_rata():
    funds = {"A": fund("A", price=1.0), "B": fund("B", price=1.0)}
    r = plan_day(total_assets=2000, pool_cash=100, positions=[], targets={"A": 0.5, "B": 0.5},
                 funds=funds, external_cash=0)
    # 池子 100，两只各 50；扣 0.15% 申购费
    buys = [x for x in r["rows"] if x["action"] == "买入"]
    assert len(buys) == 2
    assert abs(sum(x["amount"] for x in buys) - 100) < 0.02
    assert r["totals"]["post_cash"] >= -1e-9


def test_min_amount():
    funds = {"A": fund("A"), "B": fund("B")}
    r = plan_day(total_assets=2000, pool_cash=15, positions=[],
                 targets={"A": 0.5, "B": 0.5}, funds=funds)
    assert all(x["action"] != "买入" for x in r["rows"])
    assert abs(r["totals"]["post_cash"] - 15) < 1e-9


def test_sell_cannot_fund_buy():
    funds = {"A": fund("A"), "B": fund("B")}
    r = plan_day(total_assets=2000, pool_cash=0,
                 positions=[Position("A", "A", 1000, hold_days=400)],
                 targets={"A": 0.0, "B": 0.5}, funds=funds)
    a = next(x for x in r["rows"] if x["code"] == "A")
    b = next(x for x in r["rows"] if x["code"] == "B")
    assert a["action"] == "卖出"
    assert b["action"] != "买入"          # 卖出款 T+2 才到账
    assert b["executable"] is False
    assert r["totals"]["post_cash"] == 0


def test_paused_and_missing_price():
    funds = {"A": fund("A", status="暂停申购"), "B": fund("B", price=None)}
    r = plan_day(total_assets=2000, pool_cash=500, positions=[],
                 targets={"A": 0.5, "B": 0.5}, funds=funds)
    assert all(x["action"] != "买入" for x in r["rows"])
    assert "暂停" in next(x for x in r["rows"] if x["code"] == "A")["reason"]
    assert "净值" in next(x for x in r["rows"] if x["code"] == "B")["reason"]


def test_weight_validation():
    funds = {"A": fund("A")}
    try:
        plan_day(20000, 100, [], {"A": 1.2}, funds)
        raise AssertionError("应当拒绝超过 100% 的权重")
    except ValueError:
        pass


def test_daily_limit():
    funds = {"A": fund("A", limit=100.0)}
    r = plan_day(total_assets=2000, pool_cash=500, positions=[],
                 targets={"A": 1.0}, funds=funds)
    a = r["rows"][0]
    assert a["action"] == "买入"
    assert a["amount"] <= 100.0 + 1e-9
    assert "限额" in a["reason"]


def test_no_negative_cash():
    funds = {c: fund(c) for c in "ABCD"}
    r = plan_day(20000, 333.33, [], {c: 0.25 for c in "ABCD"}, funds, external_cash=1000)
    assert r["totals"]["post_cash"] >= -1e-9
    assert abs(sum(x["amount"] for x in r["rows"] if x["action"] == "买入") - 1333.33) < 0.05


def test_over_target_pauses_new_money():
    funds = {"A": fund("A")}
    r = plan_day(total_assets=10000, pool_cash=1500, positions=[Position("A", "A", 0)],
                 targets={"A": 1.0}, funds=funds, external_cash=5000)
    assert r["budget"]["new_allowed"] == 0
    assert r["budget"]["new_used"] == 0
    assert any("超过目标" in w for w in r["warnings"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("all tests passed")
