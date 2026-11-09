"""独立复核外部指标研究的账户、信息可用时间与训练标签边界。"""
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    root=Path('results/gold_macro');accounts=days=external_trades=0
    for folder in root.glob('*_*_20*'):
        if not (folder/'all_daily.csv.gz').exists():continue
        daily=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date'])
        trades=pd.read_csv(folder/'all_trades.csv',parse_dates=['date','signal_date'])
        price=pd.read_csv(Path('results/gold_full_cycle/data')/(folder.name.split('_')[0]+'_qfq.csv'),parse_dates=['date']).set_index('date').close
        assert (trades.signal_date<trades.date).all()
        assert (trades.quantity%100==0).all()
        for name in ('real','dollar','yuan','gvz'):
            col=f'{name}_available_at'
            if col not in trades:continue
            valid=trades[col].notna()
            assert (pd.to_datetime(trades.loc[valid,col])<=pd.to_datetime(trades.loc[valid,'decision_at'])).all()
            assert (pd.to_datetime(trades.loc[valid,f'{name}_observation_date'])<pd.to_datetime(trades.loc[valid,col])).all()
            external_trades+=int(valid.sum())
        for name,g in daily.groupby('strategy',sort=False):
            t=trades[trades.strategy==name].copy()
            sign=np.where(t.action.isin(['减仓','清仓','退出','卖出/再平衡']),-1,1)
            t['cash_delta']=-sign*t.quantity*t.price-t.fee;t['qty_delta']=sign*t.quantity
            delta=t.groupby('date')[['cash_delta','qty_delta']].sum().reindex(g.date).fillna(0)
            cash=100000.+delta.cash_delta.cumsum().to_numpy();qty=delta.qty_delta.cumsum().to_numpy()
            equity=cash+qty*price.reindex(g.date).to_numpy()
            assert np.allclose(g.cash,cash,atol=1e-7)
            assert np.array_equal(g.quantity,qty)
            assert np.allclose(g.equity,equity,atol=1e-7)
            assert (cash>=-1e-7).all() and (qty>=0).all()
            dd=(equity/np.maximum.accumulate(np.r_[100000.,equity])[1:]-1)*100
            assert np.allclose(g.drawdown_pct,dd,atol=1e-7)
            accounts+=1;days+=len(g)
        html=(folder/'explorer.html').read_text(encoding='utf-8')
        payload=json.loads(re.search(r'const D=(.*?);const sel=',html,re.S).group(1))
        assert len(payload['rules'])==33
    for code in ('518850','518880'):
        a=pd.read_csv(root/f'{code}_availability_audit.csv',index_col=0,parse_dates=True)
        for name in ('real','dollar','yuan','gvz'):
            exists=a[f'{name}_available_at'].notna()
            assert (pd.to_datetime(a.loc[exists,f'{name}_available_at'])<=a.index[exists]+pd.Timedelta(hours=15)).all()
    folds=pd.read_csv(root/'cross_cycle.csv',parse_dates=['training_end'])
    assert (folds.training_end<pd.to_datetime(folds.year.astype(str)+'-01-01')).all()
    forecast=pd.read_csv(root/'predictive_oos.csv',parse_dates=['last_train_label_end','first_test_date'])
    assert (forecast.last_train_label_end<forecast.first_test_date).all()
    all_metrics=pd.read_csv(root/'all_metrics.csv')
    max_error=float(all_metrics.exposure_error_pp.abs().max())
    assert max_error<.1
    result={'accounts_verified':accounts,'account_days':days,'external_trade_information_checks':external_trades,
            'ledger':'passed','availability_before_signal':'passed','signal_before_trade':'passed','training_before_test':'passed',
            'forecast_labels_purged':'passed','max_exposure_matching_error_pp':max_error,
            'strict_first_release_vintage_verification':'NOT AVAILABLE; residual revision risk remains'}
    (root/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)


if __name__=='__main__':main()
