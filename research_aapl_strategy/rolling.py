"""Fresh-account monthly cohorts and chronological annual validation."""
import pandas as pd
import compare as c

starts=[c.idx[i+1] for i in c.month_end if c.idx[i+1]>=pd.Timestamp('2013-01-02')]
names=('buy_hold','pe_50','drawdown_20')
rows=[]
for years in (1,3,5):
    for start in starts:
        finish=start+pd.DateOffset(years=years)-pd.Timedelta(days=1)
        if finish>c.end:continue
        for name in names:
            m,_=c.simulate(name,start,finish);m['years_window']=years;rows.append(m)
d=pd.DataFrame(rows);d.to_csv(c.ROOT/'rolling_cohorts.csv',index=False)
summary=[]
for years in (1,3,5):
    sample=d[d.years_window==years]
    benchmark=sample[sample.strategy=='buy_hold'].set_index(['start','end'])
    for name in names:
        z=sample[sample.strategy==name].set_index(['start','end']);delta=z.CAGR-benchmark.reindex(z.index).CAGR
        summary.append({'years':years,'strategy':name,'n':len(z),'cagr_median':z.CAGR.median(),
           'drawdown_median':z.max_drawdown.median(),'mean_wait_sessions':z.wait_sessions.mean(),
           'buys':int(z.buy_date.ne('').sum()),'win':int((delta>1e-10).sum()),
           'loss':int((delta< -1e-10).sum()),'tie':int((delta.abs()<=1e-10).sum())})
pd.DataFrame(summary).to_csv(c.ROOT/'rolling_summary.csv',index=False)

oos=[];select=[]
for years in (1,3,5):
    for year in range(2018,2027-years):
        start=c.idx[c.idx.year==year][0];finish=start+pd.DateOffset(years=years)-pd.Timedelta(days=1)
        if finish>c.end:continue
        train=d[(d.years_window==years)&(d.start>=str((start-pd.DateOffset(years=10)).date()))&(d.end<str(start.date()))]
        if any(len(train[train.strategy==name])<12 for name in names):continue
        scores=[(train[train.strategy==name].CAGR.mean(),-train[train.strategy==name].stock_orders_per_year.mean(),name) for name in names]
        chosen=max(scores)[2]
        select.append({'years':years,'start':str(start.date()),'train_last_end':train.end.max(),'chosen':chosen,'train_count':len(train[train.strategy==chosen])})
        for name in names:
            m,_=c.simulate(name,start,finish);m.update(years_window=years,chosen=chosen,selected=name==chosen);oos.append(m)
pd.DataFrame(oos).to_csv(c.ROOT/'rolling_oos.csv',index=False)
pd.DataFrame(select).to_csv(c.ROOT/'rolling_oos_selection.csv',index=False)
print('cohorts',len(d),'rolling selections',len(select))
