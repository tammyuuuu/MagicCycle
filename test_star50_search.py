import unittest
import pandas as pd
from broad_signal_rules import price_band_positions
from research_star50_search import confirmed_ma,price_candidates
from research_broad_valuation import load
from research_broad_individual import execute
from research_csi300_search import batch_execute


class Star50Tests(unittest.TestCase):
    def test_band_persists_and_lower_boundary_exits(self):
        index=pd.bdate_range('2020-01-01',periods=20)
        close=pd.Series([100.]*16+[103.,101.,95.,100.],index=index)
        state=price_band_positions(close)
        self.assertEqual(state.iloc[15],0.)
        self.assertEqual(state.iloc[16],1.)
        self.assertEqual(state.iloc[17],1.)
        self.assertEqual(state.iloc[18],0.)
        self.assertEqual(state.iloc[19],0.)

    def test_live_rule_matches_research_and_uses_no_future(self):
        p,_,_=load('588000','000688')
        live=price_band_positions(p.close)
        pd.testing.assert_series_equal(live,confirmed_ma(p.close,16,buffer=.02))
        pd.testing.assert_series_equal(live.iloc[:600],price_band_positions(p.close.iloc[:600]))

    def test_twenty_percent_limit_matches_reference(self):
        dates=pd.bdate_range('2020-01-01',periods=4)
        p=pd.DataFrame({'open':[100.,115.,120.,120.],'close':[100.,115.,120.,120.],
                        'high':[100.,115.,121.,121.],'low':[100.,115.,119.,119.]},index=dates)
        p.attrs['code']='588000'
        target=pd.Series(1.,index=dates)
        stats,_,trades=execute(p,target,1)
        self.assertEqual(trades[0]['date'],str(dates[1].date()))
        values=batch_execute(p,target,[(1,4)])
        self.assertAlmostEqual(values['profit'][0],stats['profit_on_contributions_pct'],places=2)


if __name__=='__main__':unittest.main()
