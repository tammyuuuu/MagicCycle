import unittest
from datetime import datetime
from unittest.mock import patch
import data_fetcher as d

class MarketSafety(unittest.TestCase):
    def test_holiday_and_close(self):
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,10,8,14))), '2026-09-30')
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,10,8,16))), '2026-10-08')
    def test_friday_catchup_after_midnight(self):
        import tempfile
        from pathlib import Path
        import pandas as pd
        from datetime import date
        with tempfile.TemporaryDirectory(dir=".") as directory:
            path = str(Path(directory) / "price.csv")
            pd.DataFrame({"close": [10.]}, index=pd.DatetimeIndex(["2026-11-05"], name="date")).to_csv(path)
            seen = []
            def fetch(start, end):
                seen.append(start)
                return pd.DataFrame({"close": [11.]}, index=pd.DatetimeIndex(["2026-11-06"], name="date"))
            with patch.object(d, "_expected_latest_trade_date", return_value=date(2026,11,6)), patch.object(d, "_ensure_cache_dir"):
                result = d._load_or_fetch(path, fetch, "20100101", "20500101", True, False)
                self.assertEqual(seen, ["20261106"])
                self.assertEqual(str(result.index[-1].date()), "2026-11-06")
                again = d._load_or_fetch(path, fetch, "20100101", "20500101", True, False)
                self.assertEqual(len(seen), 1)
                self.assertEqual(again.index[-1], result.index[-1])
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,11,7,0,7))), "2026-11-06")

    def test_stale_or_empty_source_fails(self):
        import pandas as pd
        from datetime import date
        with patch.object(d, "_expected_latest_trade_date", return_value=date(2026,11,6)):
            with self.assertRaises(d.DataNotReady):
                d._load_or_fetch("missing.csv", lambda *_: pd.DataFrame(), "20100101", "20500101", False, False)
            with self.assertRaises(d.DataNotReady):
                d._load_or_fetch("missing.csv", lambda *_: pd.DataFrame({"close": [1.]}, index=pd.to_datetime(["2026-11-05"])), "20100101", "20500101", False, False)

    def test_close_buffer(self):
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,11,9,15,59))), "2026-11-06")
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,11,9,16,0))), "2026-11-09")
    def test_fallback_state_distinguishes_not_ready_and_failure(self):
        import pandas as pd
        old = pd.DataFrame({"close": [1.2]}, index=pd.DatetimeIndex(["2026-11-06"], name="date"))
        with patch.object(d, "_load_or_fetch", side_effect=d.DataNotReady("waiting")), patch.object(d, "_stale_cache", return_value=(old.copy(), "eastmoney")), patch.object(d, "_src_cooling", return_value=False):
            result = d.fetch_etf_daily("510500")
            self.assertEqual(result.attrs["update_state"], "not_ready")
        with patch.object(d, "_load_or_fetch", side_effect=ConnectionError("offline")), patch.object(d, "_stale_cache", return_value=(old.copy(), "eastmoney")), patch.object(d, "_src_cooling", return_value=False):
            result = d.fetch_etf_daily("510500")
            self.assertEqual(result.attrs["update_state"], "error")

    def test_calendar_expiry(self):
        with self.assertRaises(ValueError): d._expected_latest_trade_date(datetime(2027,1,4,16))
    def test_failed_sources_do_not_use_sina(self):
        with patch.object(d, '_load_or_fetch', side_effect=ConnectionError('offline')), patch.object(d, '_stale_cache', return_value=(None,None)), patch.object(d, '_src_cooling', return_value=False), patch.object(d.ak, 'fund_etf_hist_sina', side_effect=AssertionError('unadjusted source called')):
            with self.assertRaises(ConnectionError): d.fetch_etf_daily('510500')

if __name__ == '__main__': unittest.main()

