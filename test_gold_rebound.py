import unittest
import pandas as pd
from research_gold_rebound import rebound_targets


class GoldReboundTests(unittest.TestCase):
    def test_entry_recovery_and_boundaries(self):
        close=pd.Series([100.]*250+[90.,95.,98.])
        signal=rebound_targets(close)
        self.assertFalse(signal.iloc[249])
        self.assertTrue(signal.iloc[250])
        self.assertTrue(signal.iloc[251])
        self.assertFalse(signal.iloc[252])

    def test_old_high_expiry_does_not_lower_exit_target(self):
        close=pd.Series([100.]*250+[90.]*260+[95.,98.])
        signal=rebound_targets(close)
        self.assertTrue(signal.iloc[-2])
        self.assertFalse(signal.iloc[-1])

    def test_no_future_information(self):
        close=pd.Series([100.]*250+[90.,95.,98.,80.,120.])
        changed=close.copy();changed.iloc[-2:]=200.
        pd.testing.assert_series_equal(rebound_targets(close).iloc[:-2],rebound_targets(changed).iloc[:-2])


if __name__=='__main__':unittest.main()
