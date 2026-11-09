import unittest
import numpy as np
import pandas as pd
from research_gold_macro import raw_signal,align_external,policies,target_backtest,predictive_test
from test_asset_strategies import frame


def sources():
    dates=pd.bdate_range('2012-01-02',periods=1000)
    return {k:pd.DataFrame({'observation_date':dates,'value':np.linspace(1 if k=='real' else 10,2 if k=='real' else 20,len(dates))}) for k in ('real','dollar','yuan','gvz')}


class MacroTests(unittest.TestCase):
    def test_publication_not_observation_date(self):
        s=sources();idx=pd.bdate_range('2013-06-03',periods=50)
        a=align_external(idx,sources=s)
        for k,lag in [('real',2),('dollar',2),('yuan',14),('gvz',2)]:
            self.assertTrue((a[f'{k}_available_at']<=idx+pd.Timedelta(hours=15)).all())
            self.assertTrue(((idx-a[f'{k}_observation_date']).dt.days>=lag).all())
        # 改写还未公布的原始观测，不得影响较早可用面板。
        cut=pd.Timestamp('2013-06-12');altered={k:v.copy() for k,v in s.items()}
        for k in altered:altered[k].loc[altered[k].observation_date>=cut,'value']*=10
        b=align_external(idx,sources=altered)
        cols=[c for c in a if c.startswith('yuan_')]
        pd.testing.assert_frame_equal(a.loc[a.index<cut+pd.Timedelta(days=14),cols],b.loc[b.index<cut+pd.Timedelta(days=14),cols])

    def test_direction_and_observation_window(self):
        s=sources()
        real=raw_signal('real',s['real']);yuan=raw_signal('yuan',s['yuan']);dollar=raw_signal('dollar',s['dollar'])
        self.assertFalse(bool(real.good.iloc[-1]));self.assertTrue(bool(yuan.good.iloc[-1]));self.assertFalse(bool(dollar.good.iloc[-1]))
        self.assertAlmostEqual(real.change20.iloc[-1],real.value.iloc[-1]-real.value.iloc[-21])

    def test_trading_ledger_and_prefix_invariance(self):
        d=frame(np.linspace(5.,9.,700));s=sources()
        # 将人工数据时间轴设在原始观测可用区间内。
        d.index=pd.bdate_range('2012-01-02',periods=700)
        a=align_external(d.index,sources=s);p=policies(d,a)
        c,t,_=target_backtest(d,a,p.real,'real',300,700)
        cash=100000.;qty=0
        for date,row in c.iterrows():
            for v in t:
                if v['date']!=str(date.date()):continue
                sign=-1 if v['action'] in ('减仓','清仓') else 1
                cash-=sign*v['quantity']*v['price']+v['fee'];qty+=sign*v['quantity']
                self.assertLess(v['signal_date'],v['date'])
                self.assertLessEqual(pd.Timestamp(v['real_available_at']),pd.Timestamp(v['decision_at']))
            self.assertAlmostEqual(cash,row.cash);self.assertEqual(qty,row.quantity)
            self.assertAlmostEqual(row.equity,cash+qty*d.loc[date,'close'])
        b=target_backtest(d.iloc[:450],a.iloc[:450],p.real.iloc[:450],'real',300,450)[0]
        pd.testing.assert_frame_equal(b,c.iloc[:150])

    def test_prediction_labels_purged_before_test(self):
        # 自造无噪声方向不用于证实盈利，仅验证训练标签时点约束。
        d=frame(8+np.sin(np.arange(1000)/20)+np.arange(1000)*.001)
        d.index=pd.bdate_range('2012-01-02',periods=1000)
        a=align_external(d.index,sources=sources())
        result=predictive_test(d,a,d.index[300],d.index[700],d.index[-1])
        self.assertIsNotNone(result)
        m,p=result
        self.assertLess(pd.Timestamp(m['last_train_label_end']),d.index[700])
        self.assertTrue((pd.to_datetime(p.label_end)<d.index[-1]).all())


if __name__=='__main__':unittest.main()
