"""完整账户状态机研究，独立五年窗口、跨周期冻结选型与最新行情。"""
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path('results/gold_full_cycle')
CASH=100000.
ASOF='2026-10-29'


@dataclass(frozen=True)
class Rule:
    key:str
    entry:str='immediate'
    size:str='full'
    risk:str='none'
    reentry:str='trend'


def candidates():
    result=[Rule('buy_hold'),Rule('monthly60',entry='monthly')]
    for entry in ('immediate','trend','pullback'):
        for size in ('full','half','quarter'):
            for risk in ('none','trend','heat10','heat15','heat10trend'):
                for reentry in (('trend','trend20') if risk in ('trend','heat10trend') else ('trend',)):
                    result.append(Rule('_'.join([entry,size,risk,reentry]),entry,size,risk,reentry))
    return result


def features(data):
    c=data.close
    f=pd.DataFrame(index=data.index)
    for n in (20,60,120):f[f'ma{n}']=c.rolling(n,min_periods=n).mean()
    f['rise20']=c.pct_change(20,fill_method=None)
    f['dev60']=c/f.ma60-1
    f['dd250']=c/c.rolling(250,min_periods=250).max()-1
    f['trend']=(c>f.ma120)&(f.ma120>f.ma120.shift(5))
    f['pullback']=(f.dd250<=-.10)&(c>f.ma20)&(f.ma20>=f.ma20.shift(5))
    f['add_ok']=(c>f.ma20)&(c>f.ma120)
    f['exit_trend']=(c<=f.ma120)&(c.shift(1)<=f.ma120.shift(1))
    f['cold']=(f.rise20<=.05)&(f.dev60<=.05)
    for threshold in (.10,.15):
        active=False;values=[]
        for hot,cold in zip((f.rise20>=threshold)&(f.dev60>=threshold),f.cold):
            if cold:active=False
            if hot:active=True
            values.append(active)
        f[f'heated{int(threshold*100)}']=values
    return f


def simulate(data,f,rule,start,end,slippage=.001):
    """信号仅用i-1及更早数据；成交使用i开盘；开窗清空所有账户状态。"""
    cash=CASH;qty=0;entered=False;last_buy=-10000;last_exit=-10000
    nominal=0.;cut=False;trades=[];orders=[];daily=[];dca_spent=0.
    initial,cap={'full':(1.,1.),'half':(.5,1.),'quarter':(.25,.75)}[rule.size]
    opening=data.open.to_numpy(float);closing=data.close.to_numpy(float)
    high=data.high.to_numpy(float);low=data.low.to_numpy(float)
    idx=data.index
    flags={x:f[x].to_numpy() for x in f.columns}
    threshold=15 if rule.risk=='heat15' else 10
    heat_rule=rule.risk.startswith('heat')
    for i in range(start,end):
        j=i-1;intent=None;target=0.;reason='';budget=None
        heated=bool(flags[f'heated{threshold}'][j])
        cold=bool(flags['cold'][j]);trend=bool(flags['trend'][j])
        if rule.key=='monthly60':
            # 60笔预算全部来自开窗10万元；不追加资金，不用未来日期。
            month=(idx[i].year-idx[start].year)*12+idx[i].month-idx[start].month
            if month<60 and (i==start or idx[i].month!=idx[i-1].month):
                intent='buy';budget=min(cash,CASH/60);reason='每月首个交易日投入初始现金的1/60（含佣金预算）'
        elif rule.key=='buy_hold':
            if not entered:intent='buy';target=1.;reason='长期持有基准首次投入全部可用资金'
        else:
            eligible=(rule.entry=='immediate' or bool(flags[rule.entry][j])) and j>=119
            if qty==0:
                gate=eligible if not entered else trend and (rule.reentry!='trend20' or j-last_exit>=20)
                if heat_rule:gate=gate and not heated
                if gate:
                    intent='buy';target=initial
                    reason=('首次建仓：'+rule.entry if not entered else '清仓后重新入场：上穿120日均线且均线上行'+('，清仓后至少20交易日' if rule.reentry=='trend20' else ''))
            elif 'trend' in rule.risk and bool(flags['exit_trend'][j]):
                intent='exit';reason='连续两次收盘不高于120日均线，清仓'
            elif heat_rule and heated and not cut:
                intent='reduce';reason=f'20日涨幅及60日均线偏离均达{threshold}%，当前持仓减半一次'
            elif cut:
                if cold and trend:
                    intent='restore';target=nominal;reason='双指标均≤5%且120日趋势向上，恢复减仓前计划比例'
            elif nominal<cap-1e-9 and j-last_buy>=20 and bool(flags['add_ok'][j]):
                intent='add';target=min(cap,nominal+.25);reason='距上次买入至少20交易日，价格高于20及120日均线，加25个百分点'
        if intent:
            one=high[i]==low[i]
            buy=intent in ('buy','add','restore')
            blocked=one and ((buy and opening[i]/closing[j]-1>=.097) or (not buy and opening[i]/closing[j]-1<=-.097))
            units=0;fee=0.;execution=opening[i]*(1+slippage if buy else 1-slippage)
            if not blocked:
                if buy:
                    equity_open=cash+qty*opening[i]
                    budget=min(cash,max(0.,target*equity_open-qty*opening[i])) if budget is None else budget
                    units=int(budget/(execution*1.0001)//100)*100
                    while units>0 and units*execution+max(5.,units*execution*.0001)>budget+1e-8:units-=100
                else:units=qty if intent=='exit' else int(qty*.5//100)*100
            order={'signal_date':str(idx[j].date()),'date':str(idx[i].date()),'intent':intent,'reason':reason,
                   'status':'limit_blocked' if blocked else 'filled' if units else 'lot_or_budget_blocked'}
            orders.append(order)
            if units:
                fee=max(5.,units*execution*.0001)
                if buy:
                    cash-=units*execution+fee;qty+=units
                    action='定期买入' if rule.key=='monthly60' else '首次建仓' if not entered else '重新入场' if intent=='buy' else '加仓' if intent=='add' else '冷却买回'
                    if intent=='buy':nominal=initial;entered=True
                    elif intent=='add':nominal=target
                    if rule.key=='monthly60':entered=True;dca_spent+=units*execution+fee
                    if intent=='restore':cut=False
                    last_buy=i
                else:
                    cash+=units*execution-fee;qty-=units
                    action='清仓' if intent=='exit' else '减仓'
                    if intent=='exit':last_exit=i;nominal=0.;cut=False
                    else:cut=True
                trades.append(dict(**order,action=action,quantity=units,price=execution,fee=fee,
                                   cash_after=cash,quantity_after=qty,planned_fraction=target if buy else 0.,
                                   signal_close=closing[j],signal_ma20=float(flags['ma20'][j]),signal_ma120=float(flags['ma120'][j]),
                                   signal_return20_pct=float(flags['rise20'][j]*100),signal_dev60_pct=float(flags['dev60'][j]*100)))
        equity=cash+qty*closing[i]
        daily.append((idx[i],cash,qty,equity,qty*closing[i]/equity))
    curve=pd.DataFrame(daily,columns=['date','cash','quantity','equity','exposure']).set_index('date')
    curve['return_pct']=(curve.equity/CASH-1)*100
    curve['drawdown_pct']=(curve.equity/curve.equity.cummax().clip(lower=CASH)-1)*100
    return curve,trades,orders


def statistics(curve,begin,stop,trades):
    years=(stop-begin).days/365.2425
    cagr=(curve.equity.iloc[-1]/CASH)**(1/years)-1
    r=pd.Series(np.r_[CASH,curve.equity.to_numpy()]).pct_change().dropna()
    vol=r.std(ddof=1);dd=-curve.drawdown_pct.min()/100
    return dict(annual_return_pct=float(cagr*100),max_drawdown_pct=float(dd*100),
                calmar=float(cagr/dd) if dd>1e-12 else np.nan,
                sharpe=float(r.mean()/vol*np.sqrt(252)) if vol>1e-12 else np.nan,
                return_pct=float(curve.return_pct.iloc[-1]),trades=len(trades),
                average_exposure_pct=float(curve.exposure.mean()*100),fees=float(sum(t['fee'] for t in trades)))


def rank_training(table):
    # 固定等权Calmar、Sharpe百分位；不把收益最高作为选型目标；现金不交易不得胜出。
    g=table.copy();eligible=(g.trades>0)&g.calmar.notna()&g.sharpe.notna()
    g['score']=-1.
    g.loc[eligible,'score']=(g.loc[eligible,'calmar'].rank(pct=True)+g.loc[eligible,'sharpe'].rank(pct=True))/2
    # 与基准相同的策略按参数少优先，避免无意义复杂化。
    g['complexity']=g.rule.map(lambda k:0 if k=='buy_hold' else 1 if k=='monthly60' else 2+int('heat' in k)+int('trend20' in k))
    return g.sort_values(['score','complexity','rule'],ascending=[False,True,True])


def chart(folder,code,label,selected,curves,trades):
    fig,axes=plt.subplots(4,1,figsize=(14,14),sharex=True)
    for key in selected:
        c=curves[key]
        axes[0].plot(c.index,c.return_pct,label=key)
        axes[1].plot(c.index,c.drawdown_pct,label=key)
        axes[3].plot(c.index,c.exposure*100,label=key)
    focus=selected[-1];c=curves[focus]
    data=pd.read_csv(OUT/'data'/f'{code}_qfq.csv',index_col='date',parse_dates=True)
    axes[2].plot(c.index,data.close.reindex(c.index),color='goldenrod',label=focus)
    for action,color,marker in [('首次建仓','green','^'),('重新入场','cyan','^'),('加仓','blue','^'),('冷却买回','navy','^'),('减仓','red','v'),('清仓','purple','v'),('定期买入','green','.')]:
        t=[x for x in trades[focus] if x['action']==action]
        if t:axes[2].scatter(pd.to_datetime([x['date'] for x in t]),[x['price'] for x in t],c=color,marker=marker,label=action,s=25,zorder=3)
    for ax,title in zip(axes,['累计收益 (%)','回撤 (%)','ETF价格与聚焦策略成交 (元)','实际仓位 (%)']):
        ax.set_ylabel(title);ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
    fig.suptitle(f'{code} {label} / 聚焦 {focus}');fig.tight_layout();fig.savefig(folder/'overview.png',dpi=110);plt.close(fig)


def explorer(folder,code,curves,trades,rows,data):
    """离线HTML为所有候选提供真实曲线与完整交易表，避免静态叠放65条线。"""
    dates=[str(x.date()) for x in next(iter(curves.values())).index]
    payload={'dates':dates,'price':[round(float(v),5) for v in data.close.reindex(pd.to_datetime(dates))],
             'rules':{k:{'ret':c.return_pct.round(6).tolist(),'dd':c.drawdown_pct.round(6).tolist(),'weight':(c.exposure*100).round(5).tolist(),
                         'trades':trades[k],'metrics':next(x for x in rows if x['rule']==k)} for k,c in curves.items()}}
    raw=json.dumps(payload,ensure_ascii=False,allow_nan=False,default=lambda x:None if isinstance(x,float) and math.isnan(x) else str(x))
    html='''<!doctype html><meta charset="utf-8"><title>黄金五年账户研究</title>
<style>body{font:14px system-ui;margin:24px;background:#f6f7f9;color:#16202d}canvas{width:100%;height:260px;background:white;border:1px solid #ccc}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccc;padding:5px}select{padding:8px;width:90%}h3{margin-bottom:6px}</style>
<h1>黄金ETF完整策略研究</h1><p>全部候选均独立从10万元开始。基准：黑色长期持有、灰色定期买入；所选策略蓝色。此页面是研究结果，不是产品信号。</p><select id="rule"></select><p id="metric"></p>
<h3>累计收益率 (%)</h3><canvas id="ret"></canvas><h3>回撤 (%)</h3><canvas id="dd"></canvas><h3>ETF价格与成交点（绿：买入；红：卖出）</h3><canvas id="price"></canvas><h3>实际仓位 (%)</h3><canvas id="weight"></canvas><p id="range"></p><h3>完整交易记录</h3><div style="overflow:auto"><table id="trades"></table></div>
<script>const D=PAYLOAD;const sel=document.querySelector('#rule');Object.keys(D.rules).forEach(k=>{let o=document.createElement('option');o.value=o.textContent=k;sel.append(o)});
function draw(id,lines,marks=[]){let e=document.getElementById(id);e.width=1400;e.height=300;let c=e.getContext('2d');let a=lines.flatMap(x=>x.v);let lo=Math.min(...a),hi=Math.max(...a);if(hi===lo)hi=lo+1;let x=i=>55+i/(D.dates.length-1)*1310,y=v=>260-(v-lo)/(hi-lo)*235;c.fillStyle='#777';c.font='14px sans-serif';for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4;c.fillText(v.toFixed(2),2,y(v));c.strokeStyle='#eee';c.beginPath();c.moveTo(55,y(v));c.lineTo(1370,y(v));c.stroke()}lines.forEach(z=>{c.strokeStyle=z.color;c.lineWidth=1.8;c.beginPath();z.v.forEach((v,i)=>i?c.lineTo(x(i),y(v)):c.moveTo(x(i),y(v)));c.stroke()});marks.forEach(t=>{let i=D.dates.indexOf(t.date);c.fillStyle=['减仓','清仓'].includes(t.action)?'#d33':'#16914c';c.beginPath();c.arc(x(i),y(t.price),4,0,7);c.fill()});c.fillStyle='#333';c.fillText(D.dates[0],55,288);c.fillText(D.dates.at(-1),1260,288)}
function update(){let r=D.rules[sel.value];['ret','dd','weight'].forEach(id=>draw(id,[{v:D.rules.buy_hold[id],color:'#111'},{v:D.rules.monthly60[id],color:'#aaa'},{v:r[id],color:'#1674c0'}]));draw('price',[{v:D.price,color:'#bb8b13'}],r.trades);document.getElementById('metric').textContent=JSON.stringify(r.metrics);let tb=document.getElementById('trades');tb.replaceChildren();let cols=['signal_date','date','action','quantity','price','fee','cash_after','quantity_after','reason'];let h=document.createElement('tr');cols.forEach(k=>{let th=document.createElement('th');th.textContent=k;h.append(th)});tb.append(h);r.trades.forEach(t=>{let tr=document.createElement('tr');cols.forEach(k=>{let td=document.createElement('td');td.textContent=t[k];tr.append(td)});tb.append(tr)});document.querySelector('#range').textContent=D.dates[0]+' — '+D.dates.at(-1)+' / 买卖点为含滑点成交价';}sel.onchange=update;update();</script>'''
    (folder/'explorer.html').write_text(html.replace('PAYLOAD',raw),encoding='utf-8')


def clean_records(records):
    return [{k:(None if isinstance(v,(float,np.floating)) and not np.isfinite(v) else v) for k,v in r.items()} for r in records]


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    rules=candidates();(OUT/'rules.json').write_text(json.dumps([asdict(r) for r in rules],ensure_ascii=False,indent=2),encoding='utf-8')
    result=[];manifest={};all_windows={};sections=[]
    for code,first in [('518880',2015),('518850',2021)]:
        path=OUT/'data'/f'{code}_qfq.csv';data=pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:ASOF]
        assert not data.index.has_duplicates and (data[['open','close','high','low']]>0).all().all()
        assert np.isfinite(data[['open','close','high','low']]).all().all()
        manifest[code]={'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'start':str(data.index[0].date()),'end':str(data.index[-1].date()),'rows':len(data),
                        'source':'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get','adjustment':'qfq','type':'真实ETF原标的' if code=='518850' else '真实ETF；原标的同类代理'}
        f=features(data)
        specs=[('fixed',y,y+5,'full') for y in range(first,2022,5)]+[('rolling',y,y+5,'full') for y in range(first,2022)]
        specs += [('holdout',2025,2030,'partial')]
        for mode,year,endyear,kind in specs:
            begin=pd.Timestamp(year,1,1);stop=pd.Timestamp(endyear,1,1)
            start=int(data.index.searchsorted(begin));end=int(data.index.searchsorted(stop));effective_stop=stop if kind=='full' else data.index[-1]+pd.Timedelta(days=1)
            folder=OUT/f'{code}_{mode}_{year}';folder.mkdir(exist_ok=True);curves={};trades={};rows=[];orders_all=[]
            for rule in rules:
                curve,t,o=simulate(data,f,rule,start,end)
                row=dict(code=code,mode=mode,year=year,kind=kind,rule=rule.key,start=str(curve.index[0].date()),end=str(curve.index[-1].date()),
                         initial_cash=CASH,first_entry=t[0]['date'] if t else '',**statistics(curve,begin,effective_stop,t))
                result.append(row);rows.append(row);curves[rule.key]=curve;trades[rule.key]=t
                orders_all.extend([dict(rule=rule.key,**v) for v in o])
            all_windows[(code,mode,year)]=(curves,trades,rows,folder,data)
            daily=pd.concat(curves,names=['rule','date']);daily.to_csv(folder/'all_daily.csv.gz',compression='gzip')
            pd.DataFrame([dict(rule=k,**v) for k,t in trades.items() for v in t]).to_csv(folder/'all_trades.csv',index=False)
            pd.DataFrame(orders_all).to_csv(folder/'all_orders.csv',index=False)
            pd.DataFrame(rows).to_csv(folder/'metrics.csv',index=False)
            explorer(folder,code,curves,trades,clean_records(rows),data)
            print('Computed',code,mode,year,flush=True)
    table=pd.DataFrame(result);table.to_csv(OUT/'all_metrics.csv',index=False)
    # 每个测试窗使用紧邻且不重叠的前五年518880训练窗，不在测试结果上重选。
    folds=[]
    for (code,mode,year),(curves,trades,rows,folder,data) in all_windows.items():
        training=table[(table.code=='518880')&(table['mode']=='rolling')&(table.year==year-5)]
        if training.empty and year==2025:
            training=table[(table.code=='518880')&(table['mode']=='rolling')&(table.year==2020)]
        selected=None
        if len(training):
            ranked=rank_training(training);selected=ranked.iloc[0].rule
            ranked.to_csv(folder/'training_ranking.csv',index=False)
            selected_row=next(r for r in rows if r['rule']==selected)
            for key in dict.fromkeys(('buy_hold','monthly60',selected)):
                r=next(x for x in rows if x['rule']==key)
                folds.append(dict(test_code=code,test_mode=mode,test_year=year,kind=r['kind'],training_start=training.start.iloc[0],training_end=training.end.iloc[0],
                                  selected_rule=selected,evaluated_rule=key,**{m:r[m] for m in ['annual_return_pct','max_drawdown_pct','calmar','sharpe','trades']}))
        # 展示预先固定代表及冻结选型；无训练窗时不把当窗最优包装成建议。
        fixed='trend_half_heat10trend_trend20'
        plotted=list(dict.fromkeys(['buy_hold','monthly60',fixed]+([selected] if selected else [])))
        chart(folder,code,f'{mode} {year} / '+rows[0]['kind'],plotted,curves,trades)
        focus=selected or fixed
        cols=['rule','first_entry','annual_return_pct','max_drawdown_pct','calmar','sharpe','trades','average_exposure_pct']
        summary=pd.DataFrame(rows);summary=summary[summary.rule.isin(plotted)][cols]
        sections += [f'### {code} / {mode} / {year} / {rows[0]["kind"]}','',f'实际区间 {rows[0]["start"]}—{rows[0]["end"]}，各账户独立从100,000元现金启动。',
                     ('冻结训练选择：'+selected+'；训练截止'+training.end.iloc[0] if selected else '此前没有可用完整五年训练窗，本窗仅作开发比较，不称为样本外。'),'',
                     summary.to_markdown(index=False),'',f'![收益、回撤、交易及仓位]({folder.name}/overview.png)','',
                     f'[所有候选交互曲线及逐笔交易]({folder.name}/explorer.html) · [全部指标]({folder.name}/metrics.csv) · [全部交易]({folder.name}/all_trades.csv) · [订单含未成交原因]({folder.name}/all_orders.csv) · [逐日账户压缩CSV]({folder.name}/all_daily.csv.gz)','',
                     f'聚焦策略 {focus} 的完整交易：','',pd.DataFrame(trades[focus])[['signal_date','date','action','quantity','price','fee','reason']].to_markdown(index=False) if trades[focus] else '本窗口没有成交。','']
    foldtable=pd.DataFrame(folds);foldtable.to_csv(OUT/'cross_cycle_validation.csv',index=False)
    # 最新指标只作为当前时点输入，不参与既往参数选择。
    latest=[]
    for code in ('518850','518880'):
        d=pd.read_csv(OUT/'data'/f'{code}_qfq.csv',index_col='date',parse_dates=True).sort_index();f=features(d);c=d.close.iloc[-1];r=f.iloc[-1]
        latest.append(dict(code=code,date=str(d.index[-1].date()),close=float(c),ma20=float(r.ma20),ma60=float(r.ma60),ma120=float(r.ma120),
                           return20_pct=float(r.rise20*100),deviation60_pct=float(r.dev60*100),drawdown250_pct=float(r.dd250*100),
                           trend=bool(r.trend),pullback=bool(r.pullback),cold=bool(r.cold),heated10=bool(r.heated10)))
    (OUT/'latest_indicators.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 黄金ETF完整买卖与仓位策略：独立五年研究','',
           '## 结论的证据等级','',
           f'截至{ASOF}。本轮重新研究首次建仓、加仓、减仓、清仓和再入场，不预设既有过热策略有效。共{len(rules)}个预先列明候选（含长期持有、每月买入基准）。产品策略及提醒未修改。',
           '已验证指：代码机制、账户核算以及历史时间留出结果得到复现；不表示已证明未来有效。所有历史已被查看过，本次跨周期冻结选型是回顾性时间样本外模拟，不能冒充严格未见或实盘样本外。',
           '## 完整周期、基准与账户规则','',
           '518880固定2015—2019、2020—2024；滚动2015—2019至2021—2025。518850固定及滚动均只有2021—2025。每窗独立10万元现金，账户、持仓成本、加仓进度与交易状态重置；均线等指标可用窗口以前数据预热。518880是另一只真实黄金ETF，作为518850同类代理，分别计算，不拼接。2025—2029计划窗口截至今天仅部分历史，单独列出，不参加完整五年排名。',
           '长期持有：首个可成交日全投入。定期买入：每月首个交易日投入初始资金的1/60（约1666.67元，含佣金预算），共60笔；全部钱开窗已在账户中，不追加。未投入现金收益0；二者均按整个10万元账户计算风险收益，避免定投外部现金流造成不可比。',
           '执行：前日收盘信号、次日开盘成交；单边滑点0.1%，佣金万一最低5元，100份整数，买入受可用现金约束；一字涨跌停采用10%近似限制。末日不强平；收盘账户净值计算回撤，包含初始现金和首笔费用；没有杠杆、借款、外部追加及逐日强制再平衡。',
           '## 系统候选空间','',
           '- 首次入场：立即开始；收盘高于120日均线且均线高于5日前；近250日高点回撤至少10%、价格回到20日线上且该均线不低于5日前。',
           '- 比例：一次100%；先50%每次加25%至100%；先25%每次加25%至75%。加仓间隔至少20交易日且价格高于20和120日均线。比例指下单时账户权益的计划投入水平，持仓市值会随价格漂移，不是每天硬性仓位上限。',
           '- 卖出：不主动卖出；连续两日不高于120日线清仓；双指标10%或15%过热减半；10%过热减半并叠加120日清仓。过热仅减半一次，双指标冷却至5%以内且120日趋势向上后恢复原计划比例；若触发清仓则优先清仓。',
           '- 清仓后再入场：120日趋势重新向上；或同样条件且距清仓至少20交易日。重新从该候选的初始比例开始。只有涉及清仓的方案比较等待期，避免复制无意义候选。热度策略空仓时不在尚未冷却阶段建仓。',
           '所有候选组合见rules.json。研究覆盖有限规则空间，不声称找到全体可能策略的最优解。',
           '## 评价与跨周期冻结选型','',
           '主指标Calmar=CAGR/最大回撤绝对值；Sharpe=交易日日均收益/样本标准差×√252，现金及无风险利率均0。CAGR用自然日长度；无波动/无回撤比率记NA，不让全现金账户靠无定义比率胜出。交易次数为实际成交订单。',
           '训练窗内按Calmar和Sharpe百分位等权评分，平分优先简单规则，选型代码预先固定。不按测试收益重选。测试2020—2024仅用2015—2019训练；测试2021—2025仅用2016—2020训练。2025起的未满五年留出用2020—2024训练并冻结。518850测试使用518880对应更早五年训练，另标注跨产品代理验证。',
           '固定与滚动重复窗口不当成新证据；两个较新完整测试窗彼此重叠，不能把胜率当独立样本统计。2015—2024仅有两个不重叠完整周期，结论必须保守。','',
           '### 冻结选择的测试结果','',foldtable.to_markdown(index=False),'',
           '## 截至当前的最新行情','',pd.DataFrame(latest).to_markdown(index=False),'',
           '行情来自腾讯前复权日线，输入SHA256及日期见manifest.json；下载时间见data/fetch.json。518850今天收盘8.315、518880收盘8.224，分别与[518850公开行情](https://xueqiu.com/S/SH518850/finance)、[518880公开行情](https://xueqiu.com/S/SH518880/notices)核对。ETF市价与基金净值不是同一指标，不用昨日净值代替今日收盘。',
           '## 各周期可复核图表及交易','',
           '静态图展示长期持有、定期买入、预先固定代表及跨周期冻结选择；完整交互HTML可选择所有候选，逐一查看累计收益、回撤、价格买卖点、实际仓位及全部成交记录。预先固定代表不是当窗优选，也不是默认推荐。','']+sections
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    synthesize()
    print('Saved',len(result),'runs',len(all_windows),'windows',flush=True)


def synthesize():
    table=pd.read_csv(OUT/'all_metrics.csv',dtype={'code':str})
    definitions={r.key:r for r in candidates()}
    # 对相同窗口及其余规则做匹配比较；不将复杂策略整体收益归功于单一动作。
    paired=[]
    for (code,mode,year),g in table[table.kind=='full'].groupby(['code','mode','year']):
        q=g.set_index('rule')
        for key in q.index:
            if key in ('buy_hold','monthly60'):continue
            r=definitions[key]
            for component,reference in [('entry','immediate'),('size','full'),('risk','none'),('reentry','trend')]:
                if getattr(r,component)==reference:continue
                values=asdict(r);values[component]=reference
                if component=='risk':values['reentry']='trend'
                counterpart='_'.join(values[x] for x in ('entry','size','risk','reentry'))
                if counterpart not in q.index:continue
                a=q.loc[key];b=q.loc[counterpart]
                paired.append(dict(code=code,mode=mode,year=year,component=component,value=getattr(r,component),reference=reference,rule=key,counterpart=counterpart,
                                   delta_calmar=a.calmar-b.calmar,delta_sharpe=a.sharpe-b.sharpe,delta_cagr_pp=a.annual_return_pct-b.annual_return_pct,
                                   dd_improvement_pp=b.max_drawdown_pct-a.max_drawdown_pct))
    pairs=pd.DataFrame(paired);pairs.to_csv(OUT/'matched_components.csv',index=False)
    # 固定、不重叠的完整周期单列；不把滚动复制和相关ETF汇成一个胜率。
    comp=pairs[(pairs.code=='518880')&(pairs['mode']=='fixed')].groupby(['component','value'])[['delta_calmar','delta_sharpe','delta_cagr_pp','dd_improvement_pp']].median().reset_index()
    comp.to_csv(OUT/'component_medians.csv',index=False)
    folds=pd.read_csv(OUT/'cross_cycle_validation.csv',dtype={'test_code':str}).drop_duplicates()
    folds.to_csv(OUT/'cross_cycle_validation.csv',index=False)
    latest=json.loads((OUT/'latest_indicators.json').read_text(encoding='utf-8'))
    # 可复核的历史局限：没有使用当前指标来重选2025以来规则。
    r=latest[0]
    narrative=['## 研究结论与当前买入判断','',
               '### 完整策略的稳定性','',
               '没有证据支持一个在所有五年周期都占优的首次建仓、加仓、减仓及清仓组合。训练选型从定期买入转为立即建仓加10%减半，再转回定期买入，说明选型对所处周期敏感。不能把每窗事后最优拼接成可实现策略。',
               '518880独立完整测试2020—2024：先前选出的定期买入Calmar约1.011、Sharpe约1.077，高于持有的0.582、0.927，但年化收益6.87%低于持有11.91%。2021—2025：先前选出的立即建仓+10%减半Calmar约1.676、Sharpe约1.516，高于持有1.646、1.391，改善幅度有限。两测试窗重叠，后者不是额外独立的五年周期。',
               '2025年至2026-10-29未满五年：冻结选出的定期买入518880 Calmar约0.041、Sharpe约0.096，低于持有0.606、0.848，尽管最大回撤8.56%显著低于持有31.38%。降低风险不自动等于风险收益指标更优。518850的结果方向相近；它和518880跟踪同类资产，不构成独立市场验证。',
               '### 动作与仓位比例的匹配比较','',
               '下表是518880两个固定完整周期内、其余规则匹配后的指标差中位数；差值不等于严格因果效应，组合数并非独立样本数。入场及仓位影响可能大于减仓阈值，不能只看过热卖点。完整逐窗口配对见matched_components.csv。','',comp.to_markdown(index=False),'',
               '### 截至2026-10-29的可执行判断','',
               '**不支持当前一次性大额买入或把下跌当作已验证的抄底机会。若目标是择时，新投入建议为预留黄金预算的0%，等待条件改善；若明确接受五年定期买入，可以按固定计划小额开始，不能把它解释成今天出现了优势买点。**',
               f"518850今日收盘{r['close']:.3f}元，20日均线{r['ma20']:.4f}、120日均线{r['ma120']:.4f}；近20交易日{r['return20_pct']:.2f}%，距250日高点{r['drawdown250_pct']:.2f}%。当前低于20及120日线，120日趋势条件和回撤反弹条件均未通过。虽然双指标已满足≤5%的冷却条件，这仅表示不热，并不能单独证明下跌结束。",
               '建议比例的分母是已经单独预留的黄金投资预算，不是家庭全部资产。定期买入路径：首笔及随后每月首个交易日各不超过预算1/60（约1.67%）；以10万元为例约1666.67元、含佣金且100份取整，不因下跌提前投入未来月份。第一笔可在下一可成交日启动，此后按月执行，共60笔，期间无需借款或追加。研究未证明家庭资产应配置多少黄金，不能把研究账户比例直接当家庭资产建议。',
               '择时观察路径：先等待收盘重新高于实时20日均线且均线不再下行；更严格的研究候选还要求收盘高于实时120日均线、该均线高于5交易日前。今天的均线只是参考值，每日更新，不是固定挂单价。达到条件只意味着进入候选入场状态；若要试用分批方案，应另行明确选择25%起步、至少20交易日后在20/120日线上每次加25%至75%的探索性规则，本报告不把它列为已验证建议。',
               '暂缓一次性买入的理由：趋势尚未修复；回撤约30%并不等于内在低估；较早周期选出的规则已在近期留出段失效；现有历史只有两个不重叠五年周期，缺少真正新增行情样本外。选择长期定投则需接受其风险收益表现也可能落后持有。',
               '### 已验证与探索性的边界','',
               '已验证：账户现金与份额约束、次日执行、订单记录、费用与取整；所列历史窗口及冻结选型结果可复现。未验证：未来收益、任何单一完整策略持续优于两个基准，以及今天是低点。上述择时观察和试用比例属于探索性判断。下一步应冻结规则后记录新增行情表现，不能继续依据已知测试期重选再称为样本外。','']
    p=OUT/'report.md';text=p.read_text(encoding='utf-8')
    if '## 研究结论与当前买入判断' not in text:text=text.replace('## 各周期可复核图表及交易','\n'.join(narrative)+'\n## 各周期可复核图表及交易')
    p.write_text(text,encoding='utf-8')
    (OUT/'current_advice.md').write_text('\n'.join(narrative),encoding='utf-8')


if __name__=='__main__':main()
