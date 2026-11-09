"""账户账本、同卖点条件实验、消融贡献及无事件周期独立复核。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    root=Path('results/gold_rebuy_final');accounts=days=0
    common_trades=pd.read_csv(root/'common_event_trades.csv',dtype={'code':str})
    attributes=pd.read_csv(root/'cycle_contributions.csv',dtype={'code':str})
    checks=0
    for folder in root.iterdir():
        if not folder.is_dir() or not (folder/'all_daily.csv.gz').exists():continue
        event_folder=folder.name.startswith('event_')
        code=folder.name.split('_')[1 if event_folder else 0]
        prices=pd.read_csv(Path('results/gold_full_cycle/data')/f'{code}_qfq.csv',index_col='date',parse_dates=True).close
        daily=pd.read_csv(folder/'all_daily.csv.gz',parse_dates=['date'])
        if event_folder:
            event=folder.name.split('_',2)[2]
            trades=common_trades[(common_trades.code==code)&(common_trades.common_event==event)].copy()
            sale=trades[trades.action=='减仓'][['date','quantity','price']]
            assert len(sale)==7 and len(sale.drop_duplicates())==1
        else:trades=pd.read_csv(folder/'all_trades.csv')
        trades['date']=pd.to_datetime(trades.date);trades['signal_date']=pd.to_datetime(trades.signal_date)
        dated=trades.signal_date.notna()
        assert (trades.loc[dated,'signal_date']<trades.loc[dated,'date']).all()
        assert (trades.loc[~dated,'preplanned']).all()
        assert (trades.quantity%100==0).all()
        for name,g in daily.groupby('variant',sort=False):
            t=trades[trades.variant==name].copy()
            sign=np.where(t.action=='减仓',-1,1)
            t['cash_delta']=-sign*t.quantity*t.price-t.fee;t['qty_delta']=sign*t.quantity
            delta=t.groupby('date')[['cash_delta','qty_delta']].sum().reindex(g.date).fillna(0)
            cash=100000.+delta.cash_delta.cumsum().to_numpy();qty=delta.qty_delta.cumsum().to_numpy()
            equity=cash+qty*prices.reindex(g.date).to_numpy()
            assert np.allclose(g.cash,cash,atol=1e-7)
            assert np.array_equal(g.quantity,qty)
            assert np.allclose(g.equity,equity,atol=1e-7)
            assert (cash>=-1e-7).all() and (qty>=0).all()
            dd=(equity/np.maximum.accumulate(np.r_[100000.,equity])[1:]-1)*100
            assert np.allclose(g.drawdown_pct,dd,atol=1e-7)
            accounts+=1;days+=len(g)
        if not event_folder and (folder/'event_counterfactuals.csv.gz').exists():
            cf=pd.read_csv(folder/'event_counterfactuals.csv.gz',parse_dates=['date']).set_index(['counterfactual','date'])
            m=pd.read_csv(folder/'metrics.csv').set_index('variant')
            block=attributes[(attributes.code==code)&(attributes['mode']==folder.name.split('_')[1])&(attributes.window_start==str(daily.date.min().date()))]
            for r in block.itertuples(index=False):
                for kind,returncol,ddcol in [('skip_sale','full_cycle_final_return_contribution_pp','full_cycle_drawdown_improvement_pp'),
                                            ('skip_buyback','buyback_and_followup_return_contribution_pp','buyback_and_followup_drawdown_improvement_pp')]:
                    c=cf.loc[f'{r.variant}_{r.event}_{kind}']
                    expected=m.loc[r.variant,'return_pct']-c.return_pct.iloc[-1]
                    expected_dd=-c.drawdown_pct.min()-m.loc[r.variant,'max_drawdown_pct']
                    assert abs(getattr(r,returncol)-expected)<1e-7
                    assert abs(getattr(r,ddcol)-expected_dd)<1e-7
                    checks+=1
    metrics=pd.read_csv(root/'all_metrics.csv')
    old=metrics[metrics.end<'2025-01-01']
    assert (old.reductions==0).all() and (old.return_vs_hold_pp.abs()<1e-9).all()
    events=pd.read_csv(root/'common_event_metrics.csv')
    assert np.allclose(events.reduction_only_return_pp+events.buyback_increment_return_pp,events.total_vs_hold_return_pp)
    compatibility=json.loads((root/'compatibility.json').read_text(encoding='utf-8'))
    assert all(x['equal'] and len(x['raw_hot_pulses'])==3 for x in compatibility)
    result={'accounts_verified':accounts,'account_days':days,'ledger':'passed','next_day_execution':'passed','common_event_same_sale':'passed',
            'counterfactual_contribution_checks':checks,'common_event_return_identity':'passed','pre2025_no_events':'passed',
            'current_thermal_stage_compatibility':'same 3 market opportunities in actual data',
            'strict_unseen_out_of_sample':'INSUFFICIENT; all underlying events occurred in previously examined 2025–2026'}
    (root/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)


if __name__=='__main__':main()
