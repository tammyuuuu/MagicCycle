"""Research-only OTC fund ledger. All decision inputs explicitly precede order NAV."""
from pathlib import Path
from dataclasses import dataclass
import re,json,math
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
CODES=['000216','160706','160119','090010','006484','006989']
NAMES=dict(zip(CODES,['黄金','沪深300','中证500','中证红利','国开债','中短债']))
BUY=dict(zip(CODES,[.0006,.0015,.0012,.0012,.0005,.0004]))
RULES=['hold','ma60','ma120','ma180','pullback','breakout','vol06','vol08','vol10']

def load():
    data={};divs={};trs={};events=[]
    for c in CODES:
        d=pd.read_csv(ROOT/f'{c}.csv',parse_dates=['date']).set_index('date').sort_index()
        assert d.index.is_unique and d.y.gt(0).all()
        soup=BeautifulSoup((ROOT/'raw'/f'{c}_fhsp.html').read_text(encoding='utf-8'),'html.parser')
        ev=[]
        for row in soup.select('tr'):
            cells=[t.get_text(' ',strip=True) for t in row.select('td')]
            if len(cells)==5 and re.fullmatch(r'\d{4}-\d{2}-\d{2}',cells[2]):
                m=re.search(r'派现金([\d.]+)元',cells[3])
                if m:
                    record=dict(code=c,record_date=cells[1],ex_date=cells[2],amount=float(m.group(1))/10,pay_date=cells[4]);ev.append(record);events.append(record)
        dv=pd.Series(0.,index=d.index)
        for e in ev:
            if pd.Timestamp(e['ex_date']) in dv.index:dv.loc[e['ex_date']]+=e['amount']
        # Cash-distribution-adjusted returns, never cumulative NAV percentage changes.
        ret=(d.y+dv)/d.y.shift(1)-1
        tr=(1+ret.fillna(0)).cumprod()
        data[c]=d.y;divs[c]=ev;trs[c]=tr
    dates=data['160706'].index.intersection(data['000216'].index)
    dates=dates[(dates>='2019-03-08')&(dates<='2026-10-21')]
    nav=pd.DataFrame(data).reindex(dates)
    tr=pd.DataFrame(trs).reindex(dates)
    # Do not manufacture a return or permit a trade on a missing NAV day.
    valid=nav.notna();nav=nav.ffill();tr=tr.ffill()
    s=(ROOT/'raw/000198.js').read_text(encoding='utf-8-sig')
    a=json.loads(re.search(r'var Data_millionCopiesIncome\s*=\s*(\[.*?\]);',s,re.S).group(1))
    m=pd.DataFrame(a,columns=['date','income']);m.date=pd.to_datetime(m.date,unit='ms',utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None).dt.normalize()
    m=m.set_index('date').income.sort_index()
    # Published values may combine early missing dates. Preserve source booking dates.
    daily=pd.date_range(m.index.min(),m.index.max());money=(1+m.reindex(daily).fillna(0)/10000).cumprod()
    money=money.reindex(dates)
    pd.DataFrame(events).to_csv(ROOT/'dividends.csv',index=False)
    return nav,tr,valid,divs,money

def signals(tr):
    out={}
    for c in tr:
        p=tr[c];ma=p.rolling(120,min_periods=120).mean()
        out[c]={}
        for rule in RULES:
            if rule=='hold':v=pd.Series(1.,index=p.index)
            elif rule.startswith('ma'):v=(p>p.rolling(int(rule[2:])).mean()).astype(float)
            elif rule=='pullback':
                state=False;vals=[];peak=p.rolling(20).max()
                for x,m,h in zip(p,ma,peak):
                    if not np.isfinite(m) or x<=m:state=False
                    elif x<=h*.98:state=True
                    vals.append(float(state))
                v=pd.Series(vals,index=p.index)
            elif rule=='breakout':
                state=False;vals=[];hi=p.rolling(60).max().shift(1);lo=p.rolling(20).min().shift(1)
                for x,h,l in zip(p,hi,lo):
                    if x<l:state=False
                    elif x>h:state=True
                    vals.append(float(state))
                v=pd.Series(vals,index=p.index)
            else:
                vol=p.pct_change(fill_method=None).rolling(60).std()*np.sqrt(252)
                v=(float(rule[3:])/100/vol).clip(upper=1).where(p>ma,0).fillna(0)
            out[c][rule]=v.fillna(0).to_numpy()
    return out

def redemption(code,days):
    if days<7:return .015
    if code=='000216':return .001 if days<365 else 0.
    if code in ['160706','090010']:return .005 if days<365 else .0025 if days<730 else 0.
    if code=='160119':return .005 if days<30 else .0025 if days<180 else 0.
    return .001 if days<30 else 0.

@dataclass
class Assumptions:
    lag:int=2                 # NAV date t-2 is assumed known before t cutoff
    settlement:int=3          # redemption proceeds unavailable until T+3
    confirm:int=1
    fee_mult:float=1.
    minimum:float=10.
    quota:float=5000000.
    blocked:bool=False        # synthetic deterministic outage, not historical fact

class Engine:
    def __init__(self,nav,tr,valid,divs,money,sig):
        self.nav=nav;self.tr=tr;self.valid=valid.to_numpy();self.divs=divs;self.money=money;self.sig=sig
        self.dates=nav.index;self.p=nav.to_numpy();self.cols=list(nav);self.vol=tr.pct_change(fill_method=None).rolling(60).std().to_numpy()*np.sqrt(252)
        self.cashret=money.pct_change(fill_method=None).fillna(0).to_numpy()
        self.ex={}
        for c,rows in divs.items():
            for e in rows:
                d=pd.Timestamp(e['ex_date'])
                if d in self.dates:
                    self.ex.setdefault(self.dates.get_loc(d),[]).append((self.cols.index(c),e['amount'],self.dates.searchsorted(pd.Timestamp(e['pay_date']))))
    def run(self,codes,rules,start,end,capital=2000.,allocation='equal',a=None,save=False):
        a=a or Assumptions();ids=[self.cols.index(c) for c in codes];n=len(ids)
        lo=self.dates.searchsorted(pd.Timestamp(start));hi=self.dates.searchsorted(pd.Timestamp(end),side='right')
        assert lo>=a.lag and hi>lo
        cash=float(capital);lots={j:[] for j in ids};receivables=[];trades=[];rows=[];totalfee=0.;rejects=0
        lastmonth=None;hold_initialized=False;requested=np.zeros(n)
        # Book starting capital at preceding close so first execution fees enter returns/drawdowns.
        rows.append(dict(date=self.dates[lo-1],equity=cash,cash=cash,receivable=0.,utilization=0.,fees=0.,**{c:0. for c in codes}))
        for i in range(lo,hi):
            date=self.dates[i]
            cash*=1+self.cashret[i] # optimistic cash-management sleeve; stressed separately
            due=[r for r in receivables if r[0]<=i];cash+=sum(r[1] for r in due)
            receivables=[r for r in receivables if r[0]>i]
            # Distributions belong to pre-order holdings. No reinvestment at unknown NAV.
            for j,amount,pay in self.ex.get(i,[]):
                if j in lots:
                    value=sum(l[0] for l in lots[j])*amount
                    if value:receivables.append((max(i+1,pay),value))
            # All pre-order sizing uses known NAV t-lag, not today's unknown execution NAV.
            k=i-a.lag
            marked=np.array([sum(l[0] for l in lots[j])*self.p[k,j] for j in ids])
            known=cash+sum(r[1] for r in receivables)+marked.sum()
            scheduled=(i==lo or self.dates[i-1].isocalendar()[:2]!=date.isocalendar()[:2])
            rebalance=allocation!='hold' and scheduled or allocation=='hold' and not hold_initialized
            if rebalance:
                weights=np.ones(n)/n if n else np.array([])
                if allocation=='invvol' and n:
                    inv=1/np.maximum(self.vol[k,ids],.02);inv=np.where(np.isfinite(inv),inv,0)
                    weights=inv/inv.sum() if inv.sum() else weights
                target=np.array([self.sig[c][rules[c]][k] for c in codes])
                # Equal fixed capital ceilings never transfer an inactive sleeve to an active winner.
                ceilings=np.full(n,capital/n) if allocation=='fixed' and n else known*weights
                requested=ceilings*target
                hold_initialized=True
                # Sell first; proceeds remain locked and cannot pay for today's purchases.
                for h,j in enumerate(ids):
                    c=codes[h];value=marked[h];delta=value-requested[h]
                    if delta<max(a.minimum,known*.01) or not lots[j]:continue
                    if not self.valid[i,j] or a.blocked and (i%53<5):rejects+=1;continue
                    qty=min(sum(l[0] for l in lots[j]),delta/self.p[k,j])
                    # Full exits and tiny remainder handling, shares rounded down to 0.01.
                    if requested[h]<a.minimum:qty=sum(l[0] for l in lots[j])
                    else:qty=math.floor(qty*100)/100
                    sold=0.;fee=0.;remaining=qty
                    for lot in lots[j]:
                        if i<lot[2] or remaining<=0:continue
                        q=min(lot[0],remaining);lot[0]-=q;remaining-=q;sold+=q
                        days=max(0,(date-self.dates[lot[2]]).days)
                        fee+=q*self.p[i,j]*redemption(c,days)
                    lots[j]=[l for l in lots[j] if l[0]>1e-9]
                    if sold:
                        proceeds=sold*self.p[i,j]-fee;totalfee+=fee
                        receivables.append((i+a.settlement,proceeds));trades.append(dict(date=date,signal_date=self.dates[k],code=c,side='sell',shares=sold,nav=self.p[i,j],fee=fee,amount=proceeds,available_index=i+a.settlement))
                # Simultaneous orders receive pro-rata available cash, independent of future returns.
                values=np.array([sum(l[0] for l in lots[j])*self.p[k,j] for j in ids])
                wanted=np.maximum(0,requested-values)
                for h,j in enumerate(ids):
                    if not self.valid[i,j] or a.blocked and (i%53<5):
                        if wanted[h]>=a.minimum:rejects+=1
                        wanted[h]=0.
                wanted=np.minimum(wanted,a.quota)
                wanted=np.where(wanted>=max(a.minimum,known*.01),wanted,0)
                if wanted.sum()>cash:wanted*=max(0,cash)/wanted.sum()
                for h,j in enumerate(ids):
                    amount=math.floor(wanted[h]*100)/100;c=codes[h]
                    if amount<a.minimum:continue
                    fee=amount-amount/(1+BUY[c]*a.fee_mult)
                    qty=math.floor((amount-fee)/self.p[i,j]*100)/100
                    if not qty:continue
                    # Orders specified in RMB before cutoff; actual NAV determines confirmed shares.
                    used=qty*self.p[i,j]*(1+BUY[c]*a.fee_mult);fee=used-qty*self.p[i,j]
                    cash-=used;totalfee+=fee;lots[j].append([qty,i,i+a.confirm])
                    trades.append(dict(date=date,signal_date=self.dates[k],code=c,side='buy',shares=qty,nav=self.p[i,j],fee=fee,amount=used,available_index=i+a.confirm))
            values={c:sum(l[0] for l in lots[j])*self.p[i,j] for c,j in zip(codes,ids)}
            receivable=sum(r[1] for r in receivables);equity=cash+receivable+sum(values.values())
            assert cash>=-1e-7 and equity>0 and np.isfinite(equity),(date,cash,equity)
            rows.append(dict(date=date,equity=equity,cash=cash,receivable=receivable,utilization=sum(values.values())/equity,fees=totalfee,**values))
        frame=pd.DataFrame(rows).set_index('date');t=pd.DataFrame(trades)
        metrics=measure(frame,self.money,capital)
        metrics.update(trades=len(trades),fees=totalfee,rejected=rejects,capital=capital)
        return metrics,frame,t

def measure(f,money,capital=None):
    eq=f.equity;initial=float(eq.iloc[0] if capital is None else capital)
    ret=eq.pct_change(fill_method=None).iloc[1:];rf=money.pct_change(fill_method=None).reindex(ret.index).fillna(0)
    excess=ret-rf;std=excess.std(ddof=1)
    days=(eq.index[-1]-eq.index[0]).days;cagr=(eq.iloc[-1]/initial)**(365.25/max(1,days))-1
    dd=eq/eq.cummax()-1;mdd=dd.min();longest=0;peakdate=eq.index[0];peakvalue=initial;underwater=False
    for d,v in eq.items():
        if v>=peakvalue-1e-8:
            if underwater:longest=max(longest,(d-peakdate).days)
            peakvalue=v;peakdate=d;underwater=False
        else:underwater=True;longest=max(longest,(d-peakdate).days)
    return dict(cagr=cagr,total=eq.iloc[-1]/initial-1,mdd=mdd,sharpe=excess.mean()/std*np.sqrt(252) if std>1e-10 else np.nan,calmar=cagr/abs(mdd) if mdd< -1e-10 else np.nan,utilization=f.utilization.iloc[1:].mean(),recovery_days=longest,unrecovered=underwater,end_value=eq.iloc[-1])
