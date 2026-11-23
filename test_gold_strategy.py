import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import gold_quotes
import gold_rolling_strategy as gold
import strategies
from asset_states import render_rail

ITEM = dict(code="518850",name="华夏黄金ETF",index="黄金",asset_type="macro_asset",subtype="gold")


class RollingGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.close = gold_quotes.read_quotes(gold_quotes.SEED).loc["2007":].close
        cls.path = gold.replay(cls.close)

    def test_all_daily_balances_and_75_fills(self):
        ref = pd.read_csv(gold.ROOT/"account_daily.csv",parse_dates=["date"]).set_index("date")
        self.assertTrue(self.path.index.equals(ref.index))
        for col in ["rule","close","weight","nav","cash","grams","signed_trade"]:
            np.testing.assert_allclose(self.path[col],ref[col],rtol=1e-10,atol=1e-13)
        self.assertEqual(len(self.path[self.path.signed_trade.ne(0)]),75)

    def test_every_confirmation_execution_and_reentry_reason(self):
        ep = pd.read_csv(gold.ROOT/"episodes.csv",parse_dates=["signal","sold","end"])
        p = self.path
        self.assertEqual(list(p.index[p.pending.eq("sell")]),list(ep.signal))
        self.assertEqual(list(p.index[p.signed_trade.lt(0)]),list(ep.sold))
        self.assertEqual(list(p.index[p.signed_trade.gt(0)])[1:],list(ep.end))
        for e in ep.itertuples():
            self.assertEqual(p.at[e.sold,"origin"],e.rule)
            self.assertEqual(p.at[e.sold,"close"],e.sell_price)
            self.assertEqual(p.at[e.end,"close"],e.end_price)
            before = p.index[p.index.get_loc(e.end)-1]
            self.assertEqual(p.at[before,"pending"],e.reason)
            self.assertEqual(p.at[e.end,"executed"],e.reason)

    def test_annual_choice_uses_only_prior_years(self):
        schedule = pd.read_csv(gold.ROOT/"schedule.csv")
        for row in schedule.itertuples():
            self.assertEqual(gold.Market(self.close.loc[:str(row.year-1)]).select(row.year),row.rule)
        extra = pd.Series(764.55,index=pd.bdate_range("2026-11-23","2027-01-04"))
        extended = pd.concat([self.close,extra])
        path = gold.replay(extended)
        self.assertEqual(path.iloc[-1].rule,gold.Market(extended.loc[:"2026"]).select(2027))
        np.testing.assert_allclose(path.nav.loc[self.path.index],self.path.nav)

    def test_site_and_api_show_position_before_next_close(self):
        import app
        for day,status,pos in [("2026-11-06","exit","持金"),("2026-11-09","watch","空仓"),
                                ("2026-11-10","buy","空仓"),("2026-11-11","watch","持金")]:
            idx = self.close.loc[:day].index[-60:]
            etf = pd.DataFrame({"close":np.full(len(idx),7.)},index=idx)
            with patch.object(app,"_load_data",return_value=(etf,ITEM)),app.app.test_client() as client:
                res = client.post("/api/decide",json={"etf":"518850"}).get_json()
                summary = res["summary"]
                alerts = client.post("/api/alerts",json={"etf":"518850"}).get_json()[0]
                self.assertEqual(alerts["summary"],summary)
                self.assertEqual(res["decision"]["action"],status)
                self.assertEqual(summary["metrics"]["price"],7.)
                self.assertEqual(summary["details"]["signal_price"],self.close.at[day])
                self.assertEqual(summary["details"]["model_position"],pos)
                self.assertEqual(summary["details"]["annual_rule"],4)
                self.assertIn("策略当前"+pos,render_rail(summary))

    def test_missing_spot_never_trades_on_etf(self):
        status,_,_,details = gold.analyze(self.close,pd.Timestamp("2026-11-23"))
        self.assertEqual(status,"watch")
        self.assertTrue(details["insufficient_history"])

    def test_quote_refresh_requires_every_new_session(self):
        prior = self.close.iloc[-2:].to_frame()
        prior["source"] = "fixture"
        sessions = pd.to_datetime(["2026-11-20","2026-11-23","2026-11-24"])
        table = """<table><tr><th>日期</th><th>合约</th><th>收盘价</th></tr>
          <tr><td>2026-11-24</td><td>Au99.99</td><td>780.20</td></tr></table>"""
        with patch.object(gold_quotes,"history",return_value=prior), patch.object(gold_quotes.requests,"get") as get:
            response = get.return_value
            response.content = table.encode()
            response.url = gold_quotes.URL
            with self.assertRaisesRegex(ValueError,"日线缺失"):
                gold_quotes.update(sessions)
            response.content = table.replace("</table>",
                "<tr><td>2026-11-23</td><td>Au99.99</td><td>781.40</td></tr></table>").encode()
            new = gold_quotes.update(sessions)
            self.assertEqual(new.loc[sessions].tolist(),[764.55,781.40,780.20])

    def test_rule_description_tracks_the_selected_parameters(self):
        from asset_states import render_basis
        from bs4 import BeautifulSoup

        rows = dict(gold.rule_rows(4))
        self.assertEqual(rows["卖出"], "前3日累计上涨至少3%，随后收跌，下一交易日卖出全部。")
        self.assertEqual(rows["买回"], "金价跌至卖价的98%或重新超过卖价，下一交易日全部买回。")
        self.assertEqual(gold.rule_rows(0), [("持有", "全年保持满仓。")])
        for key, (signal, method, fraction) in enumerate(gold.RULES[1:], 1):
            rows = dict(gold.rule_rows(key))
            (days, rise), confirm = gold.SIGNALS[signal]
            self.assertIn(f"前{days}日累计上涨至少{rise:.0%}", rows["卖出"])
            self.assertIn("随后收跌" if confirm == "down" else "回落至少1%", rows["卖出"])
            self.assertIn("卖出全部" if fraction == 1 else "卖出一半", rows["卖出"])
            self.assertEqual("98%" in rows["买回"], method == "discount10")
            self.assertEqual("反弹" in rows["买回"], method == "bounce15")
            self.assertEqual(rows["期限"], f"最迟第{gold.LIMITS[method]}个交易日买回。")

        for year, rule in [(2012,64),(2014,0),(2015,14),(2026,4)]:
            idx = self.close.loc[str(year)].index[:1]
            summary = strategies.analyze_asset(pd.DataFrame({"close":[7.]},index=idx),ITEM)
            basis = BeautifulSoup(render_basis(summary), "html.parser")
            self.assertEqual(basis.strong.get_text(), f"{year} 年黄金买卖规则")
            self.assertEqual([li.get_text() for li in basis.select("li")],
                             [f"{label}：{text}" for label,text in gold.rule_rows(rule)])
            self.assertEqual(basis.small.get_text(), "每年根据过去五年数据选择规则。")
