import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from purchase_monitor import parse_quota,parse_nav,FUNDS

class PurchaseMonitorTests(unittest.TestCase):
    html='''<h1>2026年10月14日额度表</h1><table><tr><th>基金代码</th><th>代销限额(元/日)</th><th>直销限额(元/日)</th><th>备注(公告日期)</th></tr><tr><td>021000</td><td>无代销</td><td>200</td><td>仅直销</td></tr><tr><td>017641</td><td>10</td><td>10</td><td>合并按公告</td></tr></table><li>广发F暂停，2026-10-15 生效</li>'''
    def test_quota_channels_and_future(self):
        rows,alerts=parse_quota(self.html,'2026-10-14')
        self.assertEqual(rows['021000']['direct_limit'],'200')
        self.assertEqual(rows['021000']['retail_limit'],'无代销')
        self.assertEqual(len(alerts),1)
    def test_reject_old_date_and_missing_tables(self):
        with self.assertRaises(ValueError):parse_quota(self.html,'2026-10-15')
        with self.assertRaises(ValueError):parse_quota('<h1>2026年10月14日</h1>','2026-10-14')
    def test_nav_not_purchase_confirmation(self):
        data={'Data':{'LSJZList':[{'FSRQ':'2026-10-13','DWJZ':'1.23','LJJZ':'1.3','SGZT':'开放申购'}]}}
        row=parse_nav(data,'us')
        self.assertEqual(row['unit_nav'],1.23)
        self.assertEqual(row['nav_date'],'2026-10-13')
        self.assertEqual(row['nav_purchase_status'],'开放申购')
    def test_invalid_nav(self):
        with self.assertRaises(ValueError):parse_nav({'Data':None},'bond')
        with self.assertRaises(ValueError):parse_nav({'Data':{'LSJZList':[{'FSRQ':'2026-10-13','DWJZ':'NaN'}]}},'bond')
    def test_no_money_monitor_or_unrequested_stock(self):
        self.assertEqual(len(FUNDS),6)
        self.assertNotIn('money',[f['kind'] for f in FUNDS])
        self.assertEqual([f['code'] for f in FUNDS if f['kind']=='bond'],['006484'])
    def test_export_refreshes_snapshot_and_embeds_same_result(self):
        import export_alerts
        snapshot={'rows':[],'errors':[],'future_alerts':[]}
        test_root=Path(__file__).resolve().parent/'results'/'test_purchase_monitor'
        test_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            self.assertEqual(Path(directory).resolve().parent,test_root.resolve())
            out=Path(directory)/'index.html'
            with patch('purchase_monitor.update_snapshot',return_value=snapshot) as refresh,patch.object(export_alerts.fetcher,'fetch_etf_daily',side_effect=ValueError('offline fixture')),patch.object(export_alerts,'_build_page',return_value='<html></html>') as build,patch.object(export_alerts.shutil,'copy2'),patch.object(export_alerts.shutil,'copytree'):
                export_alerts.main(str(out))
                self.assertEqual(Path(refresh.call_args.args[0]),Path(directory)/'purchase_monitor.json')
                self.assertIs(build.call_args.args[-1],snapshot)
                self.assertTrue(out.exists())

if __name__=='__main__':unittest.main()
