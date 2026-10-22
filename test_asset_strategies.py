import json
import unittest
import numpy as np
import pandas as pd
import config
import strategies
import indicators
import export_alerts
import app


def frame(values):
    c=np.asarray(values,dtype=float)
    return pd.DataFrame({"close":c,"open":c,"high":c*1.01,"low":c*.99,"volume":np.full(len(c),1000)},index=pd.bdate_range(end="2026-09-30",periods=len(c)))

class AssetTests(unittest.TestCase):
    def test_rsi_boundaries(self):
        self.assertEqual(float(indicators.rsi(pd.Series(range(30))).iloc[-1]),100)
        self.assertEqual(float(indicators.rsi(pd.Series([1.]*30)).iloc[-1]),50)
    def test_short_history_never_buys(self):
        for item in config.TARGET_ETFS:
            s=strategies.analyze_asset(frame([100,99,98]),item)
            self.assertNotIn(s['status'],['buy','buy_more','normal_buy','starter','small_buy','allocate'])
            self.assertTrue(s['details']['insufficient_history'])
            json.dumps(s,allow_nan=False)
    def test_broad_price_valuation_only(self):
        item={'code':'510500','name':'test','asset_type':'broad_etf'}
        high=frame(np.linspace(100,200,1300))
        low=frame(np.linspace(200,100,1300))
        missing=strategies.analyze_asset(high,item)
        self.assertEqual(missing['status'],'watch')
        self.assertEqual(len(missing['decision_conditions']),2)
        medium=frame(np.r_[np.full(299,100.),85.])
        large=frame(np.r_[np.full(299,100.),75.])
        for df, vp, expected in [(large,10,'buy_more'),(medium,10,'buy'),(frame(np.r_[np.full(299,100.),80.]),10,'buy_more'),(frame(np.r_[np.full(299,100.),90.]),10,'buy'),(high,10,'watch'),(large,50,'watch'),(high,80,'reduce'),(large,90,'exit')]:
            configured={**item,'valuation':{'percentile':vp,'date':df.index[-1].date().isoformat(),'metric':'PE','source':'test'}}
            empty=strategies.analyze_asset(df,configured)
            held=strategies.analyze_asset(df,configured,{'holding':True,'position_ratio':1.,'return_rate':-0.5})
            self.assertEqual(empty['status'],expected)
            self.assertEqual(held['status'],expected)
            self.assertIn(empty['details']['price_band'],['回撤较小','回撤中等','回撤较大'])
        stale={**item,'valuation':{'percentile':10,'date':'2026-09-29','metric':'PE','source':'test'}}
        self.assertEqual(strategies.analyze_asset(low,stale)['status'],'watch')
    def test_macro_pullback_and_risk(self):
        item={'code':'518850','name':'gold','asset_type':'macro_asset','subtype':'gold'}
        df=frame(np.r_[np.linspace(100,150,280),np.linspace(149,142.4,20)])
        s=strategies.analyze_asset(df,item)
        self.assertEqual(s['status'],'watch')
        self.assertEqual(s['subtype'],'gold')
    def test_removed_stock_type_rejected(self):
        with self.assertRaisesRegex(ValueError, '未知资产类型'):
            strategies.analyze_asset(frame([100, 101]), {'code':'688836','asset_type':'stock'})
    def test_no_incomplete_week_confirmation(self):
        import industry_strategy
        idx=pd.to_datetime(['2026-09-18','2026-09-25','2026-09-30'])
        d=pd.DataFrame({'close':[11,9,9],'ma_slow':[10,10,10]},index=idx)
        self.assertFalse(industry_strategy._weekly_below_slow(d))
    def test_confirmed_sector_and_macro_risk(self):
        df=frame(np.linspace(200,100,400))
        s=strategies.analyze_asset(df,{'code':'024418','name':'sector','asset_type':'sector_etf'},{'holding':True})
        self.assertEqual(s['status'],'exit')
        s=strategies.analyze_asset(df,{'code':'518850','name':'gold','asset_type':'macro_asset','subtype':'gold'})
        self.assertEqual(s['status'],'watch')
    def test_removed_stock_is_not_configured(self):
        self.assertFalse(any(x.get('asset_type') == 'stock' for x in config.TARGET_ETFS))
    def test_flat_price_export(self):
        item={'code':'510500','name':'flat','asset_type':'broad_etf','index':''}
        s=strategies.analyze_asset(frame(np.full(300,100.)),item)
        html=export_alerts._build_page([{**item,'summary':s,'rep':s['details']['legacy']}],'2026-09-30',False)
        self.assertIn('flat',html)
    def test_short_export_and_error_card(self):
        items=[]
        for item in config.TARGET_ETFS:
            s=strategies.analyze_asset(frame([100,99,98]),item)
            items.append({**item,'summary':s,'rep':s['details']['legacy'] or {'date':s['date'],'close':s['metrics']['price']}})
        items.append({'code':'000000','name':'missing','asset_type':'broad_etf','index':'','rep':{'error':'数据不足'}})
        html=export_alerts._build_page(items,'2026-09-30 16:00',False)
        self.assertIn('策略实验',html)
        self.assertIn('数据不足',html)
    def test_export_and_api_schema(self):
        items=[]
        for item in config.TARGET_ETFS:
            df=frame(np.linspace(100,150,1300))
            if item['asset_type']=='stock': df=df.tail(30)
            s=strategies.analyze_asset(df,item)
            json.dumps(s,allow_nan=False)
            items.append({**item,'summary':s,'rep':s['details']['legacy'] or {'date':s['date'],'close':s['metrics']['price']}})
            app._DATA[item['code']]=df
        html=export_alerts._build_page(items,'2026-09-30 16:00',False)
        self.assertIn('黄金/大类资产',html)
        self.assertNotIn('宇树科技',html)
        self.assertIn('策略实验',html)
        from pathlib import Path
        Path('results/test_export.html').write_text(html,encoding='utf-8')
        with app.app.test_client() as client:
            response=client.post('/api/alerts',json={})
            self.assertEqual(response.status_code,200)
            self.assertTrue(all('summary' in row for row in response.json))
            response=client.post('/api/decide',json={'etf':'688836','holding':True,'thesis_invalidated':True})
            self.assertEqual(response.status_code,400)
if __name__=='__main__': unittest.main()
