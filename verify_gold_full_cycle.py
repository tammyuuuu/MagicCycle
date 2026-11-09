"""复核报告产物中的每个账户，不重新调用策略决策。"""
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    root=Path('results/gold_full_cycle');count=0;days=0
    for folder in sorted(root.glob('*_*_20*')):
        if not folder.is_dir():continue
        daily=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date'])
        trades=pd.read_csv(folder/'all_trades.csv',parse_dates=['date','signal_date'])
        metrics=pd.read_csv(folder/'metrics.csv')
        code=folder.name.split('_')[0]
        price=pd.read_csv(root/'data'/f'{code}_qfq.csv',parse_dates=['date']).set_index('date').close
        assert (trades.signal_date<trades.date).all()
        assert (trades.quantity%100==0).all()
        for key,g in daily.groupby('rule',sort=False):
            t=trades[trades.rule==key].copy();sign=np.where(t.action.isin(['减仓','清仓']),-1,1)
            t['qty_delta']=t.quantity*sign;t['cash_delta']=-t.quantity*t.price*sign-t.fee
            delta=t.groupby('date')[['qty_delta','cash_delta']].sum().reindex(g.date).fillna(0)
            expected_cash=100000.+delta.cash_delta.cumsum().to_numpy()
            expected_qty=delta.qty_delta.cumsum().to_numpy()
            assert np.allclose(g.cash,expected_cash,atol=1e-7)
            assert np.array_equal(g.quantity,expected_qty)
            expected_equity=expected_cash+expected_qty*price.reindex(g.date).to_numpy()
            assert np.allclose(g.equity,expected_equity,atol=1e-7)
            assert (g.cash>=-1e-7).all() and (g.quantity>=0).all()
            dd=(expected_equity/np.maximum.accumulate(np.r_[100000.,expected_equity])[1:]-1)*100
            m=metrics[metrics.rule==key].iloc[0]
            assert abs(m.max_drawdown_pct+dd.min())<1e-7
            assert abs(m.return_pct-(expected_equity[-1]/100000.-1)*100)<1e-7
            assert m.trades==len(t)
            count+=1;days+=len(g)
        html=(folder/'explorer.html').read_text(encoding='utf-8')
        payload=json.loads(re.search(r'const D=(.*?);const sel=',html,re.S).group(1))
        assert len(payload['rules'])==65
        assert all(len(x['ret'])==len(payload['dates']) for x in payload['rules'].values())
        assert (folder/'overview.png').exists()
    folds=pd.read_csv(root/'cross_cycle_validation.csv',parse_dates=['training_end'])
    assert (folds.training_end<pd.to_datetime(folds.test_year.astype(str)+'-01-01')).all()
    result={'accounts_verified':count,'account_days_verified':days,'ledger':'passed','next_day_signals':'passed',
            'initial_cash':100000,'whole_lots':'passed','drawdowns_and_returns':'passed','training_before_test':'passed','html_payloads':'passed'}
    (root/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)


if __name__=='__main__':main()
