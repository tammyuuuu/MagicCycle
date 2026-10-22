import unittest
import pandas as pd
from verify_star50_strategy import daily_windows,joint


class VerificationTests(unittest.TestCase):
    def test_every_start_has_complete_calendar_horizon(self):
        index=pd.bdate_range('2020-01-01','2022-06-30')
        prices=pd.DataFrame(index=index)
        spans=daily_windows(prices,1,1)
        self.assertEqual([s for s,e in spans],list(range(1,len(spans)+1)))
        for s,e in spans:
            anniversary=index[s]+pd.DateOffset(years=1)
            self.assertLessEqual(anniversary,index[-1])
            self.assertLessEqual(index[e-1],anniversary)
            if e<len(index):
                self.assertGreater(index[e],anniversary)

    def test_money_contribution_profit_and_drawdown_both_required(self):
        baseline={'profit_on_contributions_pct':10.,'max_drawdown_pct':-20.}
        self.assertFalse(joint({'profit_on_contributions_pct':9.,'max_drawdown_pct':-10.},baseline))
        self.assertFalse(joint({'profit_on_contributions_pct':11.,'max_drawdown_pct':-21.},baseline))
        self.assertFalse(joint(baseline,baseline))
        self.assertTrue(joint({'profit_on_contributions_pct':11.,'max_drawdown_pct':-19.},baseline))


if __name__=='__main__':unittest.main()
