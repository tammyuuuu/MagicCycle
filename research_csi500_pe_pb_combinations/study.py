"""Fixed Boolean policy combinations, no indicator threshold optimization."""
from pathlib import Path
import sys,json,hashlib,itertools
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parent;sys.path.insert(0,str(ROOT));P.mkdir(exist_ok=True)
from research_broad_individual import execute
from broad_individual_strategy import individual_frame
V=ROOT/'research_csi500_valuation_grid';T=ROOT/'research_csi500_trailing_fixed'
SOURCES=[V/'stock_input.csv',V/'current_pe_input.csv',V/'features.csv',V/'frozen_parameters.json',T/'trailing_metrics_ALL.csv']
SITE=[ROOT/n for n in ['docs/index.html','docs/index.json','docs/pwa-manifest.json','config.py','broad_signal_rules.py','broad_individual_strategy.py','valuation_data.py']]
def hashes(fs):return {str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in fs}
before=hashes(SOURCES+SITE)
prices=pd.read_csv(SOURCES[0],index_col='date',parse_dates=True);prices.attrs['code']='510500'
pehistory=pd.read_csv(SOURCES[1],parse_dates=['date']);features=pd.read_csv(SOURCES[2],index_col='date',parse_dates=True)
official=individual_frame(prices,pehistory,'value_trend_confirm120',5)
scores={'A':official.percentile.to_numpy(),'B':features.equal_10_PB.to_numpy(),'C':features.equal_5_PB.to_numpy()}
MA=prices.close.rolling(120).mean().to_numpy();above=prices.close.to_numpy()>MA;warm=prices.close.rolling(250).max().notna().to_numpy()
PARAMS={'A_buy':60,'A_sell':30,'B_buy':10,'B_sell':60,'C_buy':10,'C_sell':60};COMP_MODES={'A':'MA120','B':'MA120','C':'value'}
END=prices.index[-1];assert END==pd.Timestamp('2026-10-30')
HORIZONS=[1,3,5,10];anchors={y:prices.index[prices.index.searchsorted(END-pd.DateOffset(years=y),side='right')-1] for y in HORIZONS}
COMMON=prices.index.searchsorted('2017-01-04');TRAIN_END=prices.index.searchsorted('2021-01-01')
specs=[]
for group,pb in [('P10','B'),('P5','C')]:
 for entry,exit_ in [('AND','A'),('OR','A'),('AND','OR'),('OR','OR'),('AND','AND'),('OR','AND'),('A',pb),(pb,'A')]:
  suffix=f'{entry}_in_{exit_}_out';specs.append(dict(id=f'{group}_{suffix}',group=group,components=['A',pb],entry=entry,exit=exit_))
for entry,exit_ in [('AND','OR'),('OR','OR'),('AND','AND'),('OR','AND')]:specs.append(dict(id=f'TRI_{entry}_in_{exit_}_out',group='TRI',components=['A','B','C'],entry=entry,exit=exit_))
protocol=dict(date='2026-10-31',cutoff=str(END.date()),parameters=PARAMS,components={'A':'Actual official PE5year: PE<60 AND close>MA120 enter; PE>=30 AND close<=MA120 exit.','B':'Frozen equal-PB10year: PB<10 AND close>MA120 enter; PB>=60 AND close<=MA120 exit.','C':'Frozen equal-PB5year pure value: PB<10 enter; PB>=60 exit.'},combinations=specs,signals='Combine current raw entry/exit predicates, NOT independent strategy historical position bits. Each combination owns state. Same-day AND exits require all current exit predicates, no remembered confirmations.',state='Valid data: exit dominates. If chosen exit predicate true, remain/go flat; otherwise if flat and chosen entry true, enter. Otherwise hold state. Can reenter when conditions recover; no cooldown or special stop. Missing needed valuation: retain state.',startup='Each continuous account starts next session after250-price-day warmup and complete valuation history for all used inputs. PB10 combinations start2017-01-04; PE+PB5 start2014-03-31. Near10year unavailable if no anchor equity; never backfill invalid years with cash.',execution='100000 initial, next open, lot100, slippage10bp each leg, commission1bp min5, cash yield0, no allocation cap/inflows, end marked not liquidated.',train='Structure comparison only:2017-01-04 to2020-12-31 common fresh100000 accounts, indicators/state use prehistory. Select highest training annual, then smaller maxDD, fewer components, lexical id. All thresholds fixed. Write selection before running holdout.',holdout='2020-12-31 close to2026-10-30; history previously seen, retrospective pseudo-OOS only. Rank recent5year outcomes diagnostic, never reselect structure from holdout.',sensitivity='For each structure perturb ONLY parameters actually used, one-at-time +/-5pp, plus two all-active-parameter +/-5pp scenarios. Do not select best neighbor. Recompute perturbed standalone references too. Report scenario count and unique paths; no full high-dimensional robustness claim.',increment='Compare each combined account with BOTH standalone components replayed from same valid inception and cost. Also retain original standalone continuous portfolios. Annual differences<=0.05pp treated as numerical ties, not meaningful alpha. Three-way compared to all3 components.',acceptance='Frozen training-selected structure needs recent3/recent5/holdout annual greater than every matched standalone by0.05pp, recent5 maxDD no larger than best-annual standalone by0.05pp, and majority of parameter scenarios retain positive recent5 increment. Record failures; no retuning.',no_website_modifications=True)
(P/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf8')
(P/'fixed_structures.json').write_text(json.dumps(dict(parameters=PARAMS,structures=specs),ensure_ascii=False,indent=2),encoding='utf8');fixed_hash=hashlib.sha256((P/'fixed_structures.json').read_bytes()).hexdigest()

def raw(component,params):
 v=scores[component];good=np.isfinite(v)&np.isfinite(MA)
 e=(v<params[component+'_buy'])&(above if COMP_MODES[component]=='MA120' else True)
 x=(v>=params[component+'_sell'])&(~above if COMP_MODES[component]=='MA120' else True)
 return e,x,good
def aggregate(values,selector,components):
 if selector=='AND':return np.logical_and.reduce([values[k] for k in components])
 if selector=='OR':return np.logical_or.reduce([values[k] for k in components])
 return values[selector]
def signal(spec,params=PARAMS,limit=None):
 comps=spec['components'];r={c:raw(c,params) for c in comps};es={c:r[c][0] for c in comps};xs={c:r[c][1] for c in comps};good=np.logical_and.reduce([r[c][2] for c in comps])
 e=aggregate(es,spec['entry'],comps);x=aggregate(xs,spec['exit'],comps);held=False;out=[]
 n=len(prices) if limit is None else limit
 for i in range(n):
  if good[i]:
   if x[i]:held=False
   elif not held and e[i]:held=True
  out.append(float(held))
 return pd.Series(out,index=prices.index[:n]),good,e,x
def single_spec(c):return dict(id=f'SINGLE_{c}',group='SINGLE',components=[c],entry=c,exit=c)
def inception(spec):
 good=np.logical_and.reduce([np.isfinite(scores[c]) for c in spec['components']])&np.isfinite(MA)&warm
 return int(np.flatnonzero(good)[0])+1
def metric(v,base=100000.):
 a=np.r_[base,v.equity.to_numpy()];ratio=a[-1]/base;ann=(ratio**(365.25/(v.index[-1]-v.index[0]).days)-1)*100;dd=(1-np.min(a/np.maximum.accumulate(a)))*100;r=a[1:]/a[:-1]-1
 return dict(annual_pct=ann,total_pct=(ratio-1)*100,maxdd_pct=dd,sharpe=r.mean()/r.std(ddof=1)*252**.5 if r.std(ddof=1)>0 else 0,calmar=ann/dd if dd else np.nan,holding_time_pct=(v.quantity>0).mean()*100,average_exposure_pct=v.exposure.mean()*100)
def slice_metric(v,anchor,end=END):
 if anchor not in v.index:return dict(available=False,annual_pct=np.nan,total_pct=np.nan,maxdd_pct=np.nan,holding_time_pct=np.nan,average_exposure_pct=np.nan)
 z=v.loc[(v.index>anchor)&(v.index<=end)];base=v.equity.loc[anchor];a=np.r_[base,z.equity.to_numpy()];ratio=a[-1]/base;r=a[1:]/a[:-1]-1;ann=(ratio**(365.25/(end-anchor).days)-1)*100;dd=(1-np.min(a/np.maximum.accumulate(a)))*100
 return dict(available=True,annual_pct=ann,total_pct=(ratio-1)*100,maxdd_pct=dd,sharpe=r.mean()/r.std(ddof=1)*252**.5 if r.std(ddof=1)>0 else 0,calmar=ann/dd if dd else np.nan,holding_time_pct=(z.quantity>0).mean()*100,average_exposure_pct=z.exposure.mean()*100)
def orders_in(t,anchor,end=END):
 q=[o for o in t if str(anchor.date())<o['date']<=str(end.date())]
 return dict(orders=len(q),entries=sum(o['action']=='买入' for o in q),exits=sum(o['action']=='退出' for o in q),fees_yuan=sum(o['fee'] for o in q))

# Stage1: freeze structure choice before looking at new composite holdout accounts.
training=[];signals={}
for spec in specs+[single_spec(c) for c in ['A','B','C']]:
 target,_,_,_=signal(spec);signals[spec['id']]=target
 _,v,t=execute(prices,target,COMMON,end=TRAIN_END)
 training.append(dict(id=spec['id'],group=spec['group'],components='+'.join(spec['components']),**metric(v),orders=len(t)))
train=pd.DataFrame(training);train.to_csv(P/'structure_training.csv',index=False)
eligible=train[train.group!='SINGLE'].copy();eligible['ncomponents']=eligible.components.str.count(r'\+')+1
chosen=eligible.sort_values(['annual_pct','maxdd_pct','ncomponents','id'],ascending=[False,True,True,True]).iloc[0].id
(P/'training_selected_structure.json').write_text(json.dumps(dict(selected=chosen,parameters=PARAMS,selection='Training only, annual priority; no threshold tuning'),ensure_ascii=False,indent=2),encoding='utf8');selection_hash=hashlib.sha256((P/'training_selected_structure.json').read_bytes()).hexdigest()

# Stage2: continuous account replays at each valid inception.
curves={};books={};metrics=[];campaigns=[];overlap=[];trace={}
out=P/'accounts';out.mkdir(exist_ok=True)
periods={f'trailing{h}':(a,END) for h,a in anchors.items()};periods['holdout']=(pd.Timestamp('2020-12-31'),END)
for label,a,b in [('stage2021_22','2020-12-31','2022-12-30'),('stage2023_24','2022-12-30','2024-12-31'),('stage2025_26','2024-12-31',str(END.date()))]:periods[label]=(pd.Timestamp(a),pd.Timestamp(b))
def record(identifier,spec,start,params=PARAMS):
 target,good,e,x=signal(spec,params);_,v,t=execute(prices,target,start);curves[identifier]=v;books[identifier]=t
 v.to_csv(out/f'{identifier}_daily.csv.gz');pd.DataFrame(t).to_csv(out/f'{identifier}_orders.csv',index=False)
 for period,(a,b) in periods.items():
  m=slice_metric(v,a,b);om=orders_in(t,a,b) if m['available'] else dict(orders=np.nan,entries=np.nan,exits=np.nan,fees_yuan=np.nan)
  metrics.append(dict(id=identifier,group=spec['group'],components='+'.join(spec['components']),entry_rule=spec['entry'],exit_rule=spec['exit'],inception=str(v.index[0].date()),period=period,anchor=str(a.date()),end=str(b.date()),**m,**om))
 # Closed and open campaigns must exactly account for total equity change.
 entry=None;pnls=[]
 for o in t+[dict(action='mark',date=str(END.date()))]:
  if o['action']=='买入':entry=o;continue
  if entry is None:continue
  q=entry['quantity'];debit=q*entry['price']+entry['fee'];closed=o['action']=='退出';credit=-o['quantity']*o['price']-o['fee'] if closed else q*prices.close.loc[END]
  pnl=credit-debit;pnls.append(pnl);campaigns.append(dict(id=identifier,entry=entry['date'],exit=o['date'],closed=closed,net_return_pct=(credit/debit-1)*100,pnl_yuan=pnl));entry=None
 assert np.isclose(sum(pnls),v.equity.iloc[-1]-100000.)
 if spec['group'] not in ['REF','SINGLE']:
  r={c:raw(c,params) for c in spec['components']};mask=np.arange(len(prices))>=start-1;valid=mask&good
  conflict=valid&e&x;flat_before=~target.shift(fill_value=0).astype(bool).to_numpy()
  overlap.append(dict(id=identifier,valid_signal_days=int(valid.sum()),raw_entry_days=int((valid&e).sum()),raw_exit_days=int((valid&x).sum()),conflict_days=int(conflict.sum()),entry_veto_while_flat_days=int((conflict&flat_before).sum())))
  trace[identifier]=target
 # Account and state prefix causality.
 cut=2500;short,_,_,_=signal(spec,params,limit=cut);assert np.array_equal(short,target.iloc[:cut]);_,pv,_=execute(prices,target,start,end=cut);assert np.allclose(pv.equity,v.equity.iloc[:len(pv)])
 return v,t
for spec in specs:record(spec['id'],spec,inception(spec))
for c,oldid in [('A','current_5'),('B','equal_10_PB_MA120'),('C','equal_5_PB_value')]:
 spec=single_spec(c);v,t=record(spec['id'],spec,inception(spec));old=pd.read_csv(T/f'{oldid}_daily.csv',index_col='date',parse_dates=True)
 assert v.index.equals(old.index) and np.allclose(v.equity,old.equity)
for group,comps in [('P10',['A','B']),('P5',['A','C']),('TRI',['A','B','C'])]:
 pair=next(s for s in specs if s['group']==group);start=inception(pair)
 for c in comps:
  spec=single_spec(c);spec['group']='REF';record(f'{group}_REF_{c}',spec,start)
pd.DataFrame(metrics).to_csv(P/'period_metrics.csv',index=False);pd.DataFrame(campaigns).to_csv(P/'campaigns.csv',index=False);pd.DataFrame(overlap).to_csv(P/'entry_exit_overlap.csv',index=False);pd.DataFrame(trace).to_csv(P/'combination_signals.csv')
m=pd.DataFrame(metrics);inc=[]
# Exact duplicate paths are not independent successful variants.
path_rows=[]
for spec in specs:
 t=signals[spec['id']];start=inception(spec);h=hashlib.sha256(t.iloc[start-1:].to_numpy().tobytes()).hexdigest()
 path_rows.append(dict(id=spec['id'],inception=str(prices.index[start].date()),signal_hash=h))
paths=pd.DataFrame(path_rows);paths['equivalent_ids']=paths.groupby(['inception','signal_hash']).id.transform(lambda z:';'.join(z));paths.to_csv(P/'equivalent_strategy_paths.csv',index=False)
common_equivalence=[]
for spec in specs:
 t=signals[spec['id']].iloc[COMMON-1:]
 common_equivalence.append(dict(id=spec['id'],**{f'same_as_{c}_since2017':bool(np.array_equal(t,signals[f'SINGLE_{c}'].iloc[COMMON-1:])) for c in ['A','B','C']}))
pd.DataFrame(common_equivalence).to_csv(P/'common_signal_equivalence.csv',index=False)
raw_overlap=[]
for group,comps in [('P10',['A','B']),('P5',['A','C'])]:
 spec=next(s for s in specs if s['group']==group);start=inception(spec);a=raw('A',PARAMS);b=raw(comps[1],PARAMS);mask=(np.arange(len(prices))>=start-1)&a[2]&b[2]
 raw_overlap.append(dict(group=group,valid_days=int(mask.sum()),PE_entry_days=int((mask&a[0]).sum()),PB_entry_days=int((mask&b[0]).sum()),both_entry_days=int((mask&a[0]&b[0]).sum()),PB_only_entry_days=int((mask&~a[0]&b[0]).sum()),PE_exit_days=int((mask&a[1]).sum()),PB_exit_days=int((mask&b[1]).sum()),both_exit_days=int((mask&a[1]&b[1]).sum()),PB_only_exit_days=int((mask&~a[1]&b[1]).sum())))
pd.DataFrame(raw_overlap).to_csv(P/'raw_predicate_overlap.csv',index=False)
# Diagnose every actual early PB-only campaign, including the losing training episode.
early=[];identifier='P5_OR_in_A_out';a=raw('A',PARAMS);c=raw('C',PARAMS)
for campaign in [z for z in campaigns if z['id']==identifier]:
 buy=next(o for o in books[identifier] if o['action']=='买入' and o['date']==campaign['entry']);k=prices.index.get_loc(pd.Timestamp(buy['signal_date']))
 if c[0][k] and not a[0][k]:
  entry_date=pd.Timestamp(campaign['entry']);anchor=prices.index[prices.index.get_loc(entry_date)-1];end=pd.Timestamp(campaign['exit'])
  values={key:slice_metric(curves[key],anchor,end)['total_pct'] for key in [identifier,'P5_REF_A','P5_REF_C']}
  early.append(dict(entry=campaign['entry'],exit=campaign['exit'],signal_date=buy['signal_date'],PE_entry=False,PB_entry=True,combination_trade_return_pct=campaign['net_return_pct'],combination_account_return_pct=values[identifier],matched_PE_account_return_pct=values['P5_REF_A'],matched_PB_account_return_pct=values['P5_REF_C'],increment_over_PE_pp=values[identifier]-values['P5_REF_A'],increment_over_PB_pp=values[identifier]-values['P5_REF_C']))
pd.DataFrame(early).to_csv(P/'PB_only_early_campaigns.csv',index=False)
calendar=[]
for identifier in ['P5_OR_in_A_out','P5_REF_A','P5_REF_C','P10_AND_in_AND_out','P10_REF_B']:
 v=curves[identifier]
 for year,z in v.groupby(v.index.year):
  before_year=v.loc[v.index<z.index[0]];base=before_year.equity.iloc[-1] if len(before_year) else 100000.
  calendar.append(dict(id=identifier,year=int(year),return_pct=(z.equity.iloc[-1]/base-1)*100,holding_time_pct=(z.quantity>0).mean()*100))
pd.DataFrame(calendar).to_csv(P/'calendar_year_returns.csv',index=False)
for spec in specs:
 for period in periods:
  z=m[(m.id==spec['id'])&(m.period==period)].iloc[0];refs=m[(m.id.isin([f"{spec['group']}_REF_{c}" for c in spec['components']]))&(m.period==period)]
  valid=bool(z.available and refs.available.all());bestref=refs.sort_values(['annual_pct','maxdd_pct'],ascending=[False,True]).iloc[0]
  inc.append(dict(id=spec['id'],group=spec['group'],period=period,available=valid,annual_pct=z.annual_pct,maxdd_pct=z.maxdd_pct,best_single_id=bestref.id,best_single_annual_pct=bestref.annual_pct,best_single_maxdd_pct=bestref.maxdd_pct,annual_increment_over_best_pp=z.annual_pct-bestref.annual_pct,maxdd_change_over_best_pp=z.maxdd_pct-bestref.maxdd_pct,income_increment=bool(valid and z.annual_pct>bestref.annual_pct+.05),income_and_risk_improvement=bool(valid and z.annual_pct>bestref.annual_pct+.05 and z.maxdd_pct<=bestref.maxdd_pct+.05)))
increments=pd.DataFrame(inc);increments.to_csv(P/'increment_over_matched_singles.csv',index=False)

# Sensitivity only: active parameter OAT +/-5 and two joint moves; no neighborhood winner.
def used_params(spec):
 keys=set()
 for side,selector in [('buy',spec['entry']),('sell',spec['exit'])]:
  cs=spec['components'] if selector in ['AND','OR'] else [selector]
  keys.update(c+'_'+side for c in cs)
 return sorted(keys)
reference_cache={};neighbors=[];sensdir=P/'sensitivity';sensdir.mkdir(exist_ok=True)
def reference_metrics(component,params,start):
 key=(component,params[component+'_buy'],params[component+'_sell'],start)
 if key not in reference_cache:
  t,_,_,_=signal(single_spec(component),params);_,v,_=execute(prices,t,start)
  reference_cache[key]={p:slice_metric(v,a,b) for p,(a,b) in periods.items() if p in ['trailing3','trailing5','holdout']}
 return reference_cache[key]
for spec in specs:
 active=used_params(spec);scenarios=[]
 for key in active:
  for step in [-5,5]:
   p=dict(PARAMS);p[key]+=step;scenarios.append((f'{key}_{step:+d}',p))
 for step in [-5,5]:
  p=dict(PARAMS)
  for key in active:p[key]+=step
  scenarios.append((f'all_active_{step:+d}',p))
 start=inception(spec)
 for scenario,params in scenarios:
  t,_,_,_=signal(spec,params);_,v,orders=execute(prices,t,start);sig_hash=hashlib.sha256(t.to_numpy().tobytes()).hexdigest()
  v.to_csv(sensdir/f"{spec['id']}_{scenario}_daily.csv.gz");pd.DataFrame(orders).to_csv(sensdir/f"{spec['id']}_{scenario}_orders.csv",index=False)
  for period in ['trailing3','trailing5','holdout']:
   a,b=periods[period];z=slice_metric(v,a,b);refs=[reference_metrics(c,params,start)[period] for c in spec['components']];best=max(r['annual_pct'] for r in refs)
   neighbors.append(dict(id=spec['id'],scenario=scenario,active_parameters=','.join(active),params=json.dumps(params,sort_keys=True),period=period,signal_hash=sig_hash,**z,best_perturbed_single_annual_pct=best,increment_over_perturbed_best_pp=z['annual_pct']-best,beats_perturbed_singles=bool(z['annual_pct']>best+.05)))
nd=pd.DataFrame(neighbors);nd.to_csv(P/'sensitivity_metrics.csv',index=False);ns=[]
for (identifier,period),g in nd.groupby(['id','period']):
 ns.append(dict(id=identifier,period=period,scenarios=len(g),unique_paths=g.signal_hash.nunique(),median_annual_pct=g.annual_pct.median(),minimum_annual_pct=g.annual_pct.min(),maximum_annual_pct=g.annual_pct.max(),worst_maxdd_pct=g.maxdd_pct.max(),positive_income_increment_scenarios=int(g.beats_perturbed_singles.sum()),median_increment_over_perturbed_best_pp=g.increment_over_perturbed_best_pp.median()))
summary=pd.DataFrame(ns);summary.to_csv(P/'sensitivity_summary.csv',index=False)
diagnostic_gates=[]
for spec in specs:
 z=increments[increments.id==spec['id']].set_index('period');s=summary[(summary.id==spec['id'])&(summary.period=='trailing5')].iloc[0]
 rg=bool(all(z.loc[p].income_increment for p in ['trailing3','trailing5','holdout']));dg=bool(z.loc['trailing5'].maxdd_change_over_best_pp<=.05);ng=bool(s.positive_income_increment_scenarios>s.scenarios/2)
 diagnostic_gates.append(dict(id=spec['id'],training_selected=spec['id']==chosen,return_gate=rg,risk_gate=dg,neighbor_gate=ng,diagnostic_pass=bool(rg and dg and ng),warning='Post-holdout diagnosis, not new independent selection success'))
pd.DataFrame(diagnostic_gates).to_csv(P/'candidate_diagnostic_gates.csv',index=False)

# Fixed cost stress for centers and matched references, no changing rules.
stress=[]
for spec in specs:
 start=inception(spec);t,_,_,_=signal(spec);_,v,_=execute(prices,t,start,slippage=.002)
 a,b=periods['trailing5'];z=slice_metric(v,a,b);refs=[]
 for c in spec['components']:
  rt,_,_,_=signal(single_spec(c));_,rv,_=execute(prices,rt,start,slippage=.002);refs.append(slice_metric(rv,a,b)['annual_pct'])
 stress.append(dict(id=spec['id'],slippage=.002,**z,best_single_annual_pct=max(refs),increment_over_best_pp=z['annual_pct']-max(refs)))
pd.DataFrame(stress).to_csv(P/'cost_stress.csv',index=False)
rank=m[(m.period=='trailing5')&m.id.isin([s['id'] for s in specs]+['SINGLE_A','SINGLE_B','SINGLE_C'])].sort_values(['annual_pct','maxdd_pct','id'],ascending=[False,True,True]);rank.to_csv(P/'recent5_ranking_DIAGNOSTIC.csv',index=False)
sel=increments[increments.id==chosen].set_index('period');sns=summary[(summary.id==chosen)&(summary.period=='trailing5')].iloc[0]
return_gate=bool(all(sel.loc[p].income_increment for p in ['trailing3','trailing5','holdout']));risk_gate=bool(sel.loc['trailing5'].maxdd_change_over_best_pp<=.05);neighbor_gate=bool(sns.positive_income_increment_scenarios>sns.scenarios/2)
(P/'recommendation.json').write_text(json.dumps(dict(training_selected=chosen,return_gate=return_gate,risk_gate=risk_gate,neighbor_gate=neighbor_gate,replace_official=bool(return_gate and risk_gate and neighbor_gate),note='Even a pass is retrospective research evidence, not genuinely unseen forward validation; no deployment authorized.'),ensure_ascii=False,indent=2),encoding='utf8')
assert hashes(SOURCES+SITE)==before
assert hashlib.sha256((P/'fixed_structures.json').read_bytes()).hexdigest()==fixed_hash
assert hashlib.sha256((P/'training_selected_structure.json').read_bytes()).hexdigest()==selection_hash
(P/'audit.json').write_text(json.dumps(dict(inputs_and_site_before=before,inputs_and_site_after=hashes(SOURCES+SITE),parameters_unchanged=True,independent_original_accounts_reproduced=True,all_center_prefix_checks=True,all_center_campaign_pnl_reconciled=True,structure_choice_frozen_before_holdout=True,selected_structure=chosen,fixed_structures_hash=fixed_hash,selected_hash=selection_hash,no_site_modifications=True,structures=len(specs),sensitivity_scenarios=len(nd[nd.period=='trailing5'])),indent=2),encoding='utf8')
print('TRAINING SELECTED',chosen,flush=True);print(rank[['id','annual_pct','maxdd_pct','orders']].to_string(index=False));print((P/'recommendation.json').read_text(),flush=True)
