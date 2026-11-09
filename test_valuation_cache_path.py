import os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import valuation_data as valuation
from research_dynamic_l34.study import signal_data
from csi500_pe_pb_strategy import analyze

class CachePathTest(unittest.TestCase):
    def test_cross_directory_and_frozen_signals(self):
        snippet = """import sys,hashlib,pandas as pd; sys.path.insert(0,sys.argv[1]); from research_dynamic_l34.study import signal_data; import valuation_data as v; s,f=signal_data(pd.Timestamp('2026-10-21')); print(str(v.CACHE_DIR)); print(hashlib.sha256(pd.util.hash_pandas_object(s['L3']).values.tobytes()).hexdigest())"""
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        outputs = [subprocess.check_output([sys.executable, '-B', '-c', snippet, str(ROOT)], cwd=d, env=env, text=True) for d in (ROOT, ROOT.parent)]
        self.assertEqual(outputs[0], outputs[1])
        signals, frames = signal_data(pd.Timestamp('2026-10-21'))
        frame = frames['L3']
        frozen = pd.read_csv(ROOT/'research_csi500_pe_pb_combinations/combination_signals.csv', index_col='date', parse_dates=True)['P5_OR_in_A_out'].reindex(frame.index)
        pd.testing.assert_series_equal(frame.position, frozen, check_names=False)
        pd.testing.assert_series_equal(signals['L3'].loc['2020-01-01':], frozen.loc['2020-01-01':], check_names=False)
        different = signals['L3'].ne(frozen)
        self.assertEqual(int(different.sum()), 110)
        self.assertEqual(str(different[different].index.min().date()), '2013-09-10')
        self.assertEqual(str(different[different].index.max().date()), '2014-03-27')
        self.assertFalse(frame.loc[different, 'ready'].any())
        self.assertEqual(str(frame.index[frame.ready][0].date()), '2014-03-28')

    def test_missing_pb_is_explicit_and_does_not_create_exit(self):
        with patch.object(valuation, 'CACHE_DIR', ROOT / '__missing_pb_cache_test__'):
            with self.assertRaisesRegex(OSError, 'PB'):
                valuation.load_pb_cache()
            # Force the remote fallback to fail without contacting the network.
            import builtins
            original_import = builtins.__import__
            def offline_import(name, *args, **kwargs):
                if name.startswith('akshare.stock_feature'):
                    raise ImportError('offline test')
                return original_import(name, *args, **kwargs)
            with patch('builtins.__import__', side_effect=offline_import):
                data = valuation.get_pb_history('2026-10-21', force=True)
            self.assertFalse(data['history'])
            self.assertIn('PB缓存读取错误', data['warning'])
            prices = pd.read_csv(ROOT/'data_cache/etf_510500_tencent.csv', index_col='date', parse_dates=True).loc[:'2026-10-21']
            pe = pd.read_csv(ROOT/'data_cache/valuation_000905_SH.csv').to_dict('records')
            output = analyze(prices, {'code':'510500','name':'500','valuation_history':pe,'pb_valuation_history':[], 'pb_data_warning':data['warning']}, {}, {})
            self.assertEqual(output['status'], 'watch')
            self.assertIn('PB缓存读取错误', output['details']['pb_data_warning'])

if __name__ == '__main__': unittest.main()
