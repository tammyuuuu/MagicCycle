import copy
import unittest
import pandas as pd
from research_star50_robustness import robust_screen,rules_for
from broad_signal_rules import price_band_positions


class RobustnessTests(unittest.TestCase):
    def sample(self):
        keys=['center','left','right','up','down']
        full={k:{'return_pct':20.,'max_drawdown_pct':-10.} for k in keys}
        detail={'train':{'n':20,'joint_win_pct':60.,'median_excess_pp':1.},
                'validation':{'n':9,'joint_win_pct':60.,'median_excess_pp':1.}}
        details={'center':{'1_fixed':copy.deepcopy(detail),'1_monthly':copy.deepcopy(detail)}}
        return full,details,{'center':keys[1:]},{'return_pct':10.,'max_drawdown_pct':-20.}

    def test_one_parameter_peak_is_rejected(self):
        full,details,neighbors,reference=self.sample()
        for key in ('left','right','up','down'):full[key]['return_pct']=0.
        result=robust_screen(full,details,neighbors,reference)['center']
        self.assertFalse(result['training_eligible'])
        self.assertEqual(result['region_pass_fraction'],.2)

    def test_validation_does_not_select_training_candidate(self):
        inputs=self.sample()
        first=robust_screen(*inputs)['center']
        self.assertTrue(first['training_eligible'])
        inputs[1]['center']['1_fixed']['validation']['joint_win_pct']=0.
        second=robust_screen(*inputs)['center']
        self.assertEqual(second['training_eligible'],first['training_eligible'])
        self.assertFalse(second['validation_pass'])

    def test_prefix_signal_for_sma_and_ema(self):
        index=pd.bdate_range('2020-01-01',periods=100)
        close=pd.Series([100.]*20+[110.]*20+[90.]*20+[120.]*40,index=index)
        for kind in ('sma','ema'):
            full=rules_for(close,kind,16,.02)
            pd.testing.assert_series_equal(full.iloc[:70],rules_for(close.iloc[:70],kind,16,.02))
        pd.testing.assert_series_equal(rules_for(close,'sma',16,.02),price_band_positions(close))


if __name__=='__main__':unittest.main()
