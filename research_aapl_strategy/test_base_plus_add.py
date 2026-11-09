"""Accounting and execution checks for the Apple research account."""
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

path = Path(__file__).with_name('base_plus_add.py')
namespace = {'__file__': str(path), '__name__': 'research_check'}
exec(path.read_text(encoding='utf-8').split('\nconfigs=')[0], namespace)


class AccountingChecks(unittest.TestCase):
    def test_initial_funded_benchmarks(self):
        idx = namespace['idx']; so = namespace['so']; sc = namespace['sc']
        bo = namespace['bo']; bc = namespace['bc']; simulate = namespace['simulate']
        a = idx.searchsorted(pd.Timestamp('2021-11-08')); z = idx.searchsorted(pd.Timestamp('2026-11-06'))
        cash, _ = simulate('base_cash', 0, idx[a], idx[z])
        fully, _ = simulate('all_in', 0, idx[a], idx[z])
        self.assertAlmostEqual(cash['final_nav'], .999 * (sc[z]/so[a]+bc[z]/bo[a]), places=10)
        self.assertAlmostEqual(fully['final_nav'], 1.998 * sc[z]/so[a], places=10)
        self.assertEqual(cash['twr_cagr'], cash['mwr_cagr'])

    def test_signal_rearms_and_flow_accounting(self):
        idx=namespace['idx']; month_end=namespace['month_end']; simulate=namespace['simulate']
        days=month_end[(idx[month_end]>=pd.Timestamp('2020-01-01')) & (idx[month_end]<pd.Timestamp('2020-06-01'))]
        signal=np.zeros(len(idx),dtype=bool); signal[days[[0,1,3,4]]]=True
        namespace['conditions']['synthetic']=signal
        result, events=simulate('synthetic', .25, '2020-01-02', '2020-06-30', full_log=True)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['signal_date'], str(idx[days[0]].date()))
        self.assertEqual(events[1]['signal_date'], str(idx[days[3]].date()))
        self.assertTrue(all(pd.Timestamp(x['trade_date']) > pd.Timestamp(x['signal_date']) for x in events))
        self.assertAlmostEqual(result['external_contributed'], 1.5)
        self.assertTrue(all(x['reserve_after_open'] >= -1e-10 for x in events))
        flows=[(pd.Timestamp(result['start']),-1.)]+[(pd.Timestamp(x['trade_date']),-x['amount']) for x in events]
        self.assertAlmostEqual(result['external_mwr_cagr'],namespace['irr'](flows,result['external_final'],pd.Timestamp(result['end'])))
        self.assertNotAlmostEqual(result['external_mwr_cagr'], result['external_twr_cagr'], places=5)


if __name__ == '__main__': unittest.main()
