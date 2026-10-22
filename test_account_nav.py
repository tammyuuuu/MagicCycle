import unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch, Mock
import account_nav, app
class AccountNavTests(unittest.TestCase):
    def run_snapshot(self,rows,existing=None):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'nav.json'
            if existing:path.write_text(json.dumps(existing),encoding='utf8')
            data={'funds':{'008701':{'nav':[['2026-10-20',1.9]],'dividends':[]}}}
            response=Mock();response.json.return_value={'Data':{'LSJZList':rows}}
            with patch.object(account_nav,'CACHE',path),patch.object(account_nav,'baseline',return_value=data),patch.object(account_nav.requests,'get',return_value=response):
                result=account_nav.build_snapshot(refresh=True,force=True)
                self.assertEqual(json.loads(path.read_text(encoding='utf8')),result)
                return result
    def test_new_nav_is_separate_from_research(self):
        result=self.run_snapshot([{'FSRQ':'2026-10-21','DWJZ':'1.9550','FHSP':''}])
        self.assertEqual(result['funds']['008701']['nav'],[['2026-10-21',1.955]])
        self.assertFalse(result['errors'])
    def test_invalid_and_future_nav_rejected(self):
        for row in [{'FSRQ':'2099-01-01','DWJZ':'2'},{'FSRQ':'2026-10-21','DWJZ':'NaN'}]:
            result=self.run_snapshot([row]);self.assertIn('008701',result['errors']);self.assertEqual(result['funds']['008701']['nav'],[])
    def test_unknown_dividend_stops_extension(self):
        result=self.run_snapshot([{'FSRQ':'2026-10-21','DWJZ':'1.8','FHSP':'每份派现金0.1元'}])
        self.assertIn('分红',result['errors']['008701'])
    def test_previous_updates_survive_new_snapshot(self):
        result=self.run_snapshot([{'FSRQ':'2026-10-22','DWJZ':'2'}],{'funds':{'008701':{'nav':[['2026-10-21',1.955]],'updated_at':'old'}}})
        self.assertEqual(len(result['funds']['008701']['nav']),2)
    def test_no_network_in_offline_build(self):
        with patch.object(account_nav.requests,'get',side_effect=AssertionError('network')):
            self.assertEqual(account_nav.build_snapshot(False)['schema'],'xingxun-account-nav-v1')
    def test_null_provider_payload_and_endpoint(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(account_nav,'CACHE',Path(folder)/'nav.json'),patch.object(account_nav,'baseline',return_value={'funds':{'008701':{'nav':[['2026-10-20',1.9]]}}}),patch.object(account_nav.requests,'get') as get:
            get.return_value.json.return_value={'Data':None}
            result=account_nav.build_snapshot(True,force=True);self.assertIn('008701',result['errors'])
        with app.app.test_client() as client,patch.object(account_nav,'build_snapshot',return_value={'schema':'xingxun-account-nav-v1','funds':{}}):
            self.assertEqual(client.get('/api/account-nav').status_code,200)

    def test_monitor_products_use_actual_nav_without_research_mutation(self):
        data=account_nav.baseline()
        self.assertIn('021000',data['funds'])
        self.assertEqual(data['funds']['021000']['name'],'南方纳指100 I')
        self.assertTrue(data['funds']['021000']['account_only'])
        manifest=json.loads((account_nav.ROOT/'workspace_data/manifest.json').read_text(encoding='utf8'))
        original=json.loads((account_nav.ROOT/'workspace_data'/manifest['current']).read_text(encoding='utf8'))
        self.assertNotIn('021000',original['funds'])

    def test_new_product_backfills_true_history_and_rejects_unverified_dividends(self):
        for event in ['', '每份派现金0.1元']:
            with tempfile.TemporaryDirectory() as temp:
                data={'funds':{'021000':{'nav':[['2026-10-20',2.269]],'dividends':[],'account_only':True}}}
                response=Mock();response.json.return_value={'TotalCount':2,'Data':{'LSJZList':[{'FSRQ':'2026-10-20','DWJZ':'2.269','FHSP':''},{'FSRQ':'2026-10-01','DWJZ':'2.1','FHSP':event}]}}
                with patch.object(account_nav,'CACHE',Path(temp)/'nav.json'),patch.object(account_nav,'baseline',return_value=data),patch.object(account_nav.requests,'get',return_value=response) as get:
                    result=account_nav.build_snapshot(True,force=True)
                    self.assertEqual(get.call_args.kwargs['params']['pageSize'],200)
                    if event:self.assertIn('021000',result['errors']);self.assertEqual(result['funds']['021000']['nav'],[])
                    else:self.assertTrue(result['funds']['021000']['history_complete']);self.assertEqual(result['funds']['021000']['nav'][0][0],'2026-10-01')
