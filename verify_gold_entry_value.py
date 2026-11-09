"""独立复核本轮保存账户、事件观察期及仓位匹配误差。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    root=Path('results/gold_entry_value');accounts=0;days=0
    for folder in root.glob('*_*_20*'):
        if not (folder/'all_daily.csv.gz').exists():continue
        daily=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date'])
        trades=pd.read_csv(folder/'all_trades.csv',parse_dates=['date','signal_date'])
        price=pd.read_csv(Path('results/gold_full_cycle/data')/(folder.name.split('_')[0]+'_qfq.csv'),parse_dates=['date']).set_index('date').close
        assert (trades.signal_date<trades.date).all()
        for name,g in daily.groupby('strategy',sort=False):
            t=trades[trades.strategy==name].copy()
            sign=np.where(t.action.str.startswith('卖出')|t.action.isin(['减仓','清仓']),-1,1)
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
    table=pd.read_csv(root/'all_metrics.csv')
    max_error=float(table.exposure_error_pp.abs().max())
    assert max_error<.1
    folds=pd.read_csv(root/'cross_cycle.csv')
    assert (pd.to_datetime(folds.training_end)<pd.to_datetime(folds.year.astype(str)+'-01-01')).all()
    events=pd.read_csv(root/'analogue_outcomes.csv',parse_dates=['event_date','planned_end','actual_end'])
    assert (events.actual_end<=pd.Timestamp('2026-10-29')).all()
    assert (events.actual_end>=events.planned_end).all()
    for _,g in events.groupby(['code','level','event_date','months']):
        b=g[g.policy=='immediate'].iloc[0]
        assert np.allclose(g.waiting_cost_pp,b.return_pct-g.return_pct)
        assert np.allclose(g.risk_improvement_pp,b.max_drawdown_pct-g.max_drawdown_pct)
    result={'accounts':accounts,'account_days':days,'ledger_and_returns':'passed','signals_before_execution':'passed',
            'max_matched_average_exposure_error_pp':max_error,'training_before_test':'passed','event_observation_dates':'passed',
            'paired_opportunity_cost':'passed','event_outcome_rows':len(events)}
    (root/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)


if __name__=='__main__':main()
