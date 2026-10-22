import json
import unittest
import numpy as np
import pandas as pd
from fetch_sector_valuation import extract_public_history
from research_sector_trend import backtest
from research_sector_valuation_comparison import historical_percentile, align_percentile, valuation_signal, weekly_signal


class SectorValuationResearchTests(unittest.TestCase):
    def test_percentile_requires_full_window_and_handles_ties(self):
        dates=pd.bdate_range('2020-01-01','2022-01-03')
        result=historical_percentile(pd.Series(10.,index=dates),1)
        self.assertTrue(result.loc[:'2020-12-31'].isna().all())
        self.assertEqual(result.iloc[-1],50.)
        missing=pd.Series(np.nan,index=dates)
        self.assertTrue(historical_percentile(missing,1).empty)

    def test_future_valuation_does_not_change_past_percentile(self):
        dates=pd.bdate_range('2020-01-01','2023-01-03')
        values=pd.Series(np.linspace(5,20,len(dates)),index=dates)
        old=historical_percentile(values,1)
        values.loc['2022-07-01':]=2000
        new=historical_percentile(values,1)
        pd.testing.assert_series_equal(old.loc[:'2022-06-30'],new.loc[:'2022-06-30'])

    def test_alignment_uses_past_only_and_respects_delay(self):
        dates=pd.bdate_range('2025-01-06',periods=5)
        source=pd.Series([10.,90.],index=[dates[0],dates[3]])
        result=align_percentile(source,dates,lag=1)
        self.assertTrue(pd.isna(result.iloc[0]))
        self.assertEqual(result.iloc[3],10.)
        self.assertEqual(result.iloc[4],90.)
        stale=align_percentile(source,pd.bdate_range('2025-03-01',periods=4),lag=0)
        self.assertTrue(stale.isna().all())

    def test_midrange_keeps_state_and_trend_break_exits(self):
        p=pd.Series([29.,50.,70.,71.,30.,29.])
        self.assertEqual(valuation_signal(p).tolist(),[True,True,True,False,False,True])
        self.assertEqual(valuation_signal(p,pd.Series([True,False,True,True,True,True])).tolist(),
                         [True,False,False,False,False,True])

    def test_weekly_rule_does_not_read_later_in_week(self):
        dates=pd.bdate_range('2025-01-06',periods=10)
        signal=pd.Series(True,index=dates)
        old=weekly_signal(signal)
        self.assertFalse(old.iloc[:4].any())
        self.assertTrue(old.iloc[4:9].all())
        signal.iloc[9]=False
        new=weekly_signal(signal)
        pd.testing.assert_series_equal(old.iloc[:9],new.iloc[:9])
        self.assertFalse(new.iloc[9])

    def test_small_capital_commission_is_accounted_for(self):
        dates=pd.bdate_range('2025-01-01',periods=4)
        data=pd.DataFrame({'open':1.,'close':1.},index=dates)
        signal=pd.Series([True,False,False,False],index=dates)
        stats,curve,trades=backtest(data,signal,1,4,slippage=0,initial_cash=1000,minimum_fee=5)
        self.assertEqual(stats['return_pct'],-1.)
        self.assertEqual(trades[0]['quantity'],900)
        self.assertEqual(curve.equity.iloc[-1],990.)
        cheaper=backtest(data,signal,1,4,slippage=0,initial_cash=1000,minimum_fee=0)[0]
        self.assertGreater(cheaper['return_pct'],stats['return_pct'])

    def test_public_page_parser_checks_exact_index(self):
        props={'indexInfo':{'code':'950125'},'compressedIndexDaily':{'fieldNames':['date','equalWeightedPeTtm'],
                   'values':[['2025-01-01',20],['2025-01-02',21]]}}
        flight='11:'+json.dumps(['$','$L1',None,props])+'\n'
        html='<script>self.__next_f.push('+json.dumps([1,flight])+')</script>'
        frame,info=extract_public_history(html,'950125')
        self.assertEqual(len(frame),2)
        self.assertEqual(frame.equalWeightedPeTtm.iloc[-1],21)
        with self.assertRaises(ValueError):extract_public_history(html,'990001')


if __name__=='__main__':unittest.main()
