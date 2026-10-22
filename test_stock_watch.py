"""Removal boundary: stock archives cannot enter current ETF signals."""
import unittest
from pathlib import Path
import config, strategies
from strategy_config import STRATEGY_CONFIG
from test_asset_strategies import frame
class StockRemovalTests(unittest.TestCase):
    def test_stock_not_in_live_configuration(self):
        self.assertNotIn('stock', STRATEGY_CONFIG)
        self.assertFalse(any(x.get('asset_type') == 'stock' for x in config.TARGET_ETFS))
    def test_stock_input_rejected_even_with_holdings(self):
        for holding in ({}, {'holding': True, 'thesis_invalidated': True}):
            with self.assertRaisesRegex(ValueError, '未知资产类型'):
                strategies.analyze_asset(frame([100, 101]), {'code':'688836','asset_type':'stock'}, holding)
    def test_stock_archive_preserved(self):
        self.assertTrue(Path('archive/stock/stock_watch.py').is_file())
        self.assertFalse(Path('stock_watch.py').exists())
