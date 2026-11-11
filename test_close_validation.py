import unittest
from datetime import date
from close_validation import previous_session, validate_observations, validate_bar

class ClosingValidation(unittest.TestCase):
    def test_weekend_and_long_holiday(self):
        self.assertEqual(previous_session(date(2026,11,9)), date(2026,11,6))
        self.assertEqual(previous_session(date(2026,10,8)), date(2026,9,30))
    def test_calendar_expires(self):
        with self.assertRaises(ValueError): previous_session(date(2027,1,1))
    def test_bar_validation(self):
        import pandas as pd
        target = date(2026,11,6)
        frame = pd.DataFrame({"close": [2.604]}, index=pd.to_datetime(["2026-11-06"]))
        self.assertEqual(validate_bar(frame, target), (True, "valid"))
        self.assertEqual(validate_bar(frame, date(2026,11,9)), (False, "not_ready"))
        frame.iloc[0,0] = float("nan")
        self.assertEqual(validate_bar(frame, target), (False, "invalid_data"))
    def test_observations(self):
        target = date(2026,11,6)
        a = {'source':'a','date':'2026-11-06','close':2.604}
        b = {'source':'b','date':'2026-11-06','close':2.604}
        self.assertEqual(validate_observations(a,b,target), (True,'matched'))
        self.assertEqual(validate_observations(a,None,target), (False,'not_ready'))
        self.assertEqual(validate_observations(a,{**b,'date':'2026-11-05'},target), (False,'not_ready'))
        self.assertEqual(validate_observations(a,{**b,'close':2.605},target), (False,'mismatch'))
        self.assertEqual(validate_observations(a,{**b,'close':float('nan')},target), (False,'invalid_data'))
        self.assertEqual(validate_observations(a,{**b,'source':'a'},target), (False,'invalid_sources'))

if __name__ == '__main__': unittest.main()
