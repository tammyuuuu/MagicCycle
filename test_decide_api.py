"""ETF decision API input boundary and genuine server failure behavior."""
import unittest
from unittest.mock import patch
import app, config
from test_asset_strategies import frame
class DecideApiTests(unittest.TestCase):
    def test_unknown_and_removed_symbols_do_not_load_data(self):
        with app.app.test_client() as client, patch.object(app, '_get_df') as load:
            for payload in ({}, {'etf':'688836'}, {'etf':'unknown'}, {'etf':['510300']}, ['invalid']):
                response=client.post('/api/decide',json=payload)
                self.assertEqual(response.status_code,400)
                self.assertIn('error',response.json)
            load.assert_not_called()
    def test_all_configured_etfs_still_use_decision_api(self):
        with app.app.test_client() as client, patch.object(app,'_get_df',return_value=frame(range(100,500))), patch.object(app.valuation_data,'attach_valuation',side_effect=lambda item,*a:item):
            for item in config.TARGET_ETFS:
                response=client.post('/api/decide',json={'etf':item['code'],'holding':True,'current_return':5})
                self.assertEqual(response.status_code,200,(item,response.json))
                self.assertEqual(response.json['summary']['symbol'],item['code'])
                self.assertIn('decision',response.json)
    def test_internal_failure_not_disguised_as_client_error(self):
        with app.app.test_client() as client, patch.object(app,'_get_df',side_effect=RuntimeError('synthetic data failure')):
            response=client.post('/api/decide',json={'etf':config.TARGET_ETFS[0]['code']})
            self.assertEqual(response.status_code,500)
            self.assertIn('RuntimeError',response.json['error'])
