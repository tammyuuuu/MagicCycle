"""Isolated bond study; never writes product inputs. Monthly causal execution."""
from pathlib import Path
import sys,json,ast,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'research_xingxun_v2'),str(R/'research_xingxun_v1')]
from engine_v2 import run_portfolio_v2
from otc_engine import FundFee
from research_bond_entry import features
O=R/'results/bond_complete';O.mkdir(parents=True,exist_ok=True)
nav=pd.read_csv(R/'research_xingxun_v2/clean_v2/000015.csv',parse_dates=['date']).set_index('date')
raw=pd.DataFrame(json.loads((R/'research_bond_entry/treasury_history.json').read_text()))
rates=raw.rename(columns={'SOLAR_DATE':'date','EMM00166466':'y10'})[['date','y10']].dropna()
rates.date=pd.to_datetime(rates.date);rates=rates.drop_duplicates('date').set_index('date')
f=features(nav,rates);p=f.wealth;dates=p.index
f['ma']=p.rolling(120).mean();f['momentum']=p/p.shift(60)-1
meta=pd.read_csv(R/'research_xingxun_v2/clean_v2/fund_meta_v2.csv',dtype={'code':str}).set_index('code').loc['000015']
fee={'000015':FundFee('000015',ast.literal_eval(meta.purchase_fee_tiers),ast.literal_eval(meta.redeem_fee_tiers))}
names=['hold','fixed50','fixed75','dca6','wait63','rate_half','rate_exit','dd_half','dd_exit','trend_half','trend_exit','combined_half']
rows=[];curves={}
def run(name,start,end,lag=2,settle=2,mult=1,cashrate=0,weight=None,save=True):
    state={'entered':False,'risk':False}
    def rule(k):
        d=f.iloc[k];age=k-start
        if weight is not None:w=weight
        elif name=='hold':w=1
        elif name.startswith('fixed'):w=int(name[5:])/100
        elif name=='dca6':w=min(1,max(1,(dates[k].year-dates[start].year)*12+dates[k].month-dates[start].month+1)/6)
        elif name=='wait63':
            state['entered'] |= d.environment=='较好' or age>=63
            w=float(state['entered'])
        else:
            rate=d.trend_bp>=25;dd=d.drawdown<=-.01;trend=d.wealth<d.ma and d.momentum<0
            trigger=rate if name.startswith('rate') else dd if name.startswith('dd') else trend if name.startswith('trend') else rate or dd or trend
            recover=d.trend_bp<=0 if name.startswith('rate') else d.drawdown>-.003 if name.startswith('dd') else d.wealth>d.ma and d.momentum>0 if name.startswith('trend') else d.trend_bp<=0 and d.drawdown>-.003 and d.wealth>d.ma
            if trigger:state['risk']=True
            elif recover:state['risk']=False
            w=(0 if name.endswith('exit') else .5) if state['risk'] else 1
        return {'000015':w}
    r=run_portfolio_v2({'000015':p.to_numpy()},dates,np.full(len(p),(1+cashrate)**(1/252)-1),rule,100000,fee,start,end,information_lag=lag,confirm_days=1,settle=settle,fee_mult=mult,band=.02,once=name=='hold')
    c=pd.DataFrame({k:np.asarray(r[v])[start:end+1] for k,v in [('equity','equity'),('cash','cash'),('receivable','receivable'),('held','held')]},index=dates[start:end+1])
    c['position']=c.held/c.equity;c['cumulative_return']=c.equity/100000-1;c['drawdown']=c.equity/c.equity.cummax()-1
    ret=c.equity.pct_change().fillna(c.equity.iloc[0]/100000-1);ex=ret-((1+cashrate)**(1/252)-1)
    annual=(c.equity.iloc[-1]/100000)**(365.25/(c.index[-1]-c.index[0]).days)-1;mdd=-c.drawdown.min()
    metric=dict(strategy=name,cumulative_return=c.cumulative_return.iloc[-1],cagr=annual,mdd=mdd,calmar=annual/mdd if mdd else None,sharpe=ex.mean()/ex.std()*np.sqrt(252) if ex.std() else None,exposure=c.position.mean(),fees=r['fees'],trades=len(r['trades']))
    assert np.allclose(c.equity,c.cash+c.receivable+c.held)
    for t in r['trades']:assert t['known_through']<t['decision_date']<t['date']
    return metric,c,r
windows=[('cycle1','2013-05-06','2018-05-05',True),('cycle2','2018-05-06','2023-05-05',True),('cycle3_partial','2023-05-06','2026-10-21',False)]
for label,a,b,full in windows:
    s=dates.searchsorted(pd.Timestamp(a));e=dates.searchsorted(pd.Timestamp(b),side='right')-1
    folder=O/label;folder.mkdir(exist_ok=True);allc={}
    for name in names:
        m,c,r=run(name,s,e);m.update(cycle=label,start=str(dates[s].date()),end=str(dates[e].date()),full_five_year=full);rows.append(m);allc[name]=c
        c.to_csv(folder/f'{name}_daily.csv');pd.DataFrame(r['trades']).to_csv(folder/f'{name}_trades.csv',index=False);pd.DataFrame(r['signals']).to_csv(folder/f'{name}_signals.csv',index=False)
        if name in names[5:]:
            mm,cc,rr=run('matched_'+name,s,e,weight=m['exposure']);mm.update(cycle=label,start=m['start'],end=m['end'],full_five_year=full);rows.append(mm)
            cc.to_csv(folder/f'matched_{name}_daily.csv');pd.DataFrame(rr['trades']).to_csv(folder/f'matched_{name}_trades.csv',index=False)
    fig,ax=plt.subplots(4,1,figsize=(15,16),sharex=True)
    for name,c in allc.items():
        ax[0].plot(c.index,c.cumulative_return*100,label=name);ax[1].plot(c.index,c.drawdown*100);ax[2].plot(c.index,c.position)
    ax[3].plot(p.loc[dates[s]:dates[e]],color='gray')
    for name in names[5:]:
        t=pd.read_csv(folder/f'{name}_trades.csv')
        if not t.empty:
            td=pd.to_datetime(t.date);ax[3].scatter(td,p.reindex(td),s=12,marker='o',label=name)
    for x,title in zip(ax,['Cumulative return %','Drawdown %','Position','Trade dates on reinvested NAV']):x.set_title(title);x.grid(alpha=.2)
    ax[0].legend(ncol=4);ax[3].legend(ncol=4);fig.tight_layout();fig.savefig(folder/'curves.png');plt.close(fig)
df=pd.DataFrame(rows);df.to_csv(O/'summary.csv',index=False)
# Select only on first complete cycle; freeze and evaluate on next and partial cycle.
train=df[(df.cycle=='cycle1') & df.strategy.isin(names[5:])].copy()
train['score']=train.calmar.rank(pct=True)+train.sharpe.rank(pct=True)
selected=train.sort_values('score',ascending=False).iloc[0].strategy
sens=[]
for label,a,b,full in windows:
 s=dates.searchsorted(pd.Timestamp(a));e=dates.searchsorted(pd.Timestamp(b),side='right')-1
 for name in ['hold',selected]:
  for lag,settle,mult,cr in [(2,2,1,0),(5,5,1,0),(2,2,10,0),(2,2,1,.01),(2,2,1,.02)]:
   m,_,_=run(name,s,e,lag,settle,mult,cr);m.update(cycle=label,lag=lag,settle=settle,fee_multiplier=mult,cash_rate=cr);sens.append(m)
pd.DataFrame(sens).to_csv(O/'sensitivity.csv',index=False)
manifest={'selected_on_cycle1':selected,'selection':'sum of percentile ranks of Calmar and Sharpe among 7 active rules, no reselection','independent_complete_validation_cycles':1,'partial_cycle_not_five_year_validation':True,'cash_base':0,'sharpe':'daily excess return versus scenario cash rate, 252','execution':'monthly decisions, NAV known with 2 observation lag, next NAV execution, confirmation T+1, cash settlement T+2; lag5/settle5 sensitivity','dividends':'synthetic total-return shares, same reinvestment assumption as existing engine; actual reinvestment confirmation/lot ages not reconstructed','matched_control':'ex post constant mean exposure; diagnostic only, not deployable parameter','fees':'snapshot discounted tiers; 10x fee stress, historical fees not reconstructed','latest_backtest':'2026-10-21','rules':names,'hashes':{str(x.relative_to(R)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [Path(__file__),R/'research_bond_entry/treasury_history.json',R/'research_xingxun_v2/clean_v2/000015.csv',R/'research_xingxun_v2/engine_v2.py']}}
(O/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
print('SELECTED',selected);print(df[df.strategy.isin(['hold',selected,'matched_'+selected])].to_string(index=False))
