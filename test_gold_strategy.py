import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import gold_combination_strategy as combo
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
        for day,status,pos in [("2026-11-06","exit","半仓"),("2026-11-09","watch","空仓"),
                                ("2026-11-10","buy","空仓"),("2026-11-11","watch","半仓")]:
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
                from bs4 import BeautifulSoup
                rail = BeautifulSoup(render_rail(summary),"html.parser")
                self.assertEqual([step.get_text() for step in rail.select(".state-step")], ["空仓","半仓","满仓"])
                self.assertEqual(rail.select_one('[aria-current="step"]').get_text(), pos)
                self.assertIn("策略当前"+pos,rail.get_text())

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
                             [f"{label}：{text}" for label,text in combo.rule_rows(rule)])
            self.assertEqual(basis.small.get_text(), "每年根据过去五年数据选择规则。")

    def test_combination_every_session_order_and_signal(self):
        out = gold.ROOT/"combination"
        p = combo.replay(self.close)
        ref = pd.read_csv(out/"daily.csv",index_col="date",parse_dates=True)
        pd.testing.assert_index_equal(p.index,ref.index)
        for prod, research in [("nav","nav"),("close","close"),("weight","weight"),("signed_trade","order1")]:
            np.testing.assert_allclose(p[prod],ref[research],rtol=1e-10,atol=1e-13)
        schedule = pd.read_csv(out/"schedule.csv",index_col="year").heat
        np.testing.assert_array_equal(schedule.loc[p.index.year], p.rule)
        orders = pd.read_csv(out/"instructions.csv",parse_dates=["date","signal_cutoff"]).set_index("date")
        fills = p.loc[p.signed_trade.abs().gt(1e-12)]
        self.assertEqual(len(fills),101)
        pd.testing.assert_index_equal(fills.index, orders.index)
        self.assertEqual(list(p.index[p.pending.ne("")]),list(orders.signal_cutoff))
        np.testing.assert_array_equal(p.loc[orders.signal_cutoff,"next_target"], orders.combined_target)
        np.testing.assert_array_equal(fills.cap,orders.limit)
        np.testing.assert_array_equal(fills.executed.eq("sell"),orders.heat_sale)
        restored = fills.executed.isin(["above_sale","discount","bounce","timeout"])
        np.testing.assert_array_equal(restored,orders.heat_restore)
        self.assertEqual(sum(restored & fills.cap.eq(.5)),12)

    def test_month_end_tie_restores_full_and_midmonth_cannot_anticipate(self):
        dates = pd.date_range("2025-01-31",periods=9,freq="BME")
        close = pd.Series([100.,100.,100.,100.,100.,100.,80.,100.,70.],index=dates)
        caps,next_cap = combo.monthly_limits(close.iloc[:8],dates[8])
        self.assertEqual(caps.iloc[-1],.5)
        self.assertEqual(next_cap,1.)
        partial = pd.concat([close.iloc[:8],pd.Series([70.],index=pd.to_datetime(["2025-09-15"]))])
        self.assertEqual(combo.monthly_limits(partial,pd.Timestamp("2025-09-16"))[1],1.)
        self.assertEqual(combo.next_session(pd.Timestamp("2026-09-30")),pd.Timestamp("2026-10-08"))

    def test_combination_trade_dates_have_stable_cutoff_signals(self):
        full = combo.replay(self.close)
        for day in ["2013-07-31","2026-04-30","2026-11-06","2026-11-10","2026-11-20"]:
            end = combo.replay(self.close.loc[:day]).iloc[-1]
            for key in ["nav","weight","target","next_cap","next_target","pending"]:
                self.assertEqual(end[key],full.at[end.name,key])

    def test_monthly_and_heat_signals_net_to_one_order(self):
        dates = pd.bdate_range("2012-01-02", periods=5)
        close = pd.Series([100.,100.,105.,110.,90.],index=dates)
        signals = pd.DataFrame(dict(close=close.iloc[1:],origin=[0,4,4,0],
            pending=["sell","","timeout",""],executed=["initial","sell","","timeout"]))
        # Sell and lower the limit together, raise it during the exit, then
        # lower it on the restoration close. Only two net trades are due.
        caps = pd.Series([1.,1.,.5,1.,.5],index=dates)
        with patch.object(gold,"replay",return_value=signals), patch.object(combo,"monthly_limits",return_value=(caps,.5)):
            actual = combo.replay(close)
        self.assertEqual(actual.target.tolist(),[1.,0.,0.,.5])
        self.assertEqual(actual.pending.tolist(),["sell","","timeout",""])
        self.assertEqual(np.sign(actual.signed_trade).tolist(),[0,-1,0,1])
        self.assertAlmostEqual(actual.weight.iloc[-1],.5)

    def test_cap_recovery_while_flat_waits_for_heat_reentry(self):
        # Synthetic extension of the frozen research series across a month end.
        extension = pd.Series(
            [781.40, 1100., 1150., 1145., 1140., 1140., 1140., 1141., 1143.],
            index=pd.bdate_range("2026-11-23", "2026-12-03"),
        )
        close = pd.concat([self.close, extension])
        path = combo.replay(close)
        self.assertEqual(path.at["2026-11-27", "executed"], "sell")
        self.assertEqual(path.at["2026-11-30", "cap"], .5)
        self.assertEqual(path.at["2026-11-30", "next_cap"], 1.)
        for day in ("2026-11-30", "2026-12-01"):
            status, _, _, details = combo.analyze(close, pd.Timestamp(day))
            self.assertEqual(status, "watch")
            self.assertEqual(details["pending"], "")
            self.assertEqual(details["next_target_exposure"], 0.)
            self.assertEqual(path.at[day, "signed_trade"], 0.)
        self.assertEqual(path.at["2026-12-02", "pending"], "above_sale")
        self.assertAlmostEqual(path.at["2026-12-03", "weight"], 1.)
