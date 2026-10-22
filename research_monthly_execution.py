"""Test current non-rolling monthly budget; no parameter search or historical IOPV fabrication."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from us_guidance import guidance_frame
from research_broad_valuation import xirr

START = pd.Timestamp('2015-03-01')
OUT = Path('results/monthly_execution')

def order(amount, price, minimum_fee=5., fee_rate=.0001):
    quantity = max(0, int(amount / (price * (1+fee_rate)) // 100) * 100)
    while quantity and quantity*price + max(minimum_fee, quantity*price*fee_rate) > amount + 1e-8:
        quantity -= 100
    fee = max(minimum_fee, quantity*price*fee_rate) if quantity else 0.
    return quantity, fee

def simulate(data, actions, start, end=None, mode='strategy', monthly=1000.,
             minimum_fee=5., slippage=.001, keep=True, buy_fraction=.5):
    end = len(data) if end is None else end
    if not 1 <= start < end <= len(data) or mode not in ('strategy','dca','half_dca'):
        raise ValueError('invalid simulation range or mode')
    if not actions.index.equals(data.index) or actions.isna().any():
        raise ValueError('invalid signals')
    prices=data[['open','high','low','close']].to_numpy();signals=actions.to_numpy()
    dates=data.index;months=dates.to_period('M').astype(str).to_numpy()
    cash=principal=units=fees=month_spent=month_fees=0.;qty=0;last_month=None
    rows=[];trades=[];flows=[];navs=[1.];equities=[];exposures=[];cash_only_months=0
    month_bought=False;dca_done=False
    for i in range(start,end):
        opening,high,low,closing=prices[i];date=dates[i]
        if months[i]!=last_month:
            if last_month is not None and not month_bought:cash_only_months+=1
            before=cash+qty*opening;nav=before/units if units else 1.
            units+=monthly/nav;cash+=monthly;principal+=monthly
            flows.append((date,-monthly));month_spent=month_fees=0.
            last_month=months[i];month_bought=dca_done=False
        action=signals[i-1] if mode=='strategy' else 'buy'
        change=opening/prices[i-1,3]-1
        blocked_buy=high==low and change>=.097
        blocked_sell=high==low and change<=-.097
        sell=qty if action=='exit' else qty//200*100 if action=='reduce' else 0
        price=opening*(1-slippage)
        if sell and not blocked_sell:
            fee=max(minimum_fee,sell*price*.0001)
            # Avoid a sale with costs exceeding proceeds in pathological small-price data.
            if sell*price>fee:
                cash+=sell*price-fee;qty-=sell;fees+=fee
                if keep:trades.append(dict(date=str(date.date()),signal_date=str(dates[i-1].date()),action=action,quantity=-sell,price=price,fee=fee,month_spent=month_spent))
        fraction=1. if mode=='dca' else .5 if mode=='half_dca' else {'buy':buy_fraction,'add':1.}.get(action,0.)
        if mode!='strategy' and dca_done:fraction=0.
        available=min(cash,max(0.,monthly*fraction-month_spent),max(0.,monthly-month_spent-month_fees))
        price=opening*(1+slippage)
        buy,fee=order(available,price,minimum_fee)
        if buy and not blocked_buy:
            spent=buy*price;cash-=spent+fee;qty+=buy;fees+=fee;month_spent+=spent;month_fees+=fee;month_bought=True;dca_done=True
            if keep:trades.append(dict(date=str(date.date()),signal_date=str(dates[i-1].date()) if mode=='strategy' else None,action=action,quantity=buy,price=price,fee=fee,month_spent=month_spent))
        equity=cash+qty*closing;nav=equity/units
        assert cash>=-1e-7 and qty>=0 and qty%100==0 and month_spent+month_fees<=monthly+1e-7
        navs.append(nav);equities.append(equity);exposures.append(qty*closing/equity)
        if keep:rows.append(dict(date=date,equity=equity,nav=nav,cash=cash,quantity=qty,principal=principal,month_spent=month_spent,month_fees=month_fees))
    if not month_bought:cash_only_months+=1
    navs=np.array(navs);flows.append((dates[end-1],equities[-1]))
    metrics=dict(principal_yuan=round(principal,2),ending_yuan=round(equities[-1],2),profit_yuan=round(equities[-1]-principal,2),
                 profit_on_contributions_pct=round((equities[-1]/principal-1)*100,2),xirr_pct=xirr(flows),
                 max_drawdown_pct=round(float((navs/np.maximum.accumulate(navs)-1).min())*100,2),
                 nav_return_pct=round((navs[-1]-1)*100,2),average_exposure_pct=round(float(np.mean(exposures))*100,2),
                 ending_cash_yuan=round(cash,2),fees_yuan=round(fees,2),cash_only_months=cash_only_months,
                 months=int(principal/monthly))
    return metrics,pd.DataFrame(rows).set_index('date') if keep else None,trades

def comparison(s,b):
    return dict(profit_difference_yuan=round(s['profit_yuan']-b['profit_yuan'],2),
                xirr_difference_pp=round(s['xirr_pct']-b['xirr_pct'],2),
                drawdown_improvement_pp=round(s['max_drawdown_pct']-b['max_drawdown_pct'],2),
                both_better=bool(s['profit_yuan']>b['profit_yuan'] and s['max_drawdown_pct']>b['max_drawdown_pct']))

def main():
    OUT.mkdir(parents=True,exist_ok=True);result={}
    for code,name in [('513500','标普500'),('513100','纳指100')]:
        path=Path('data_cache')/f'etf_{code}_tencent.csv'
        data=pd.read_csv(path,index_col='date',parse_dates=True).sort_index()
        values=data[['open','high','low','close']].to_numpy()
        assert not data.index.has_duplicates and np.isfinite(values).all() and (values>0).all()
        frame=guidance_frame(data.close);actions=frame.status
        start=max(int(data.index.searchsorted(START)),int(np.flatnonzero(frame.ready)[0])+1)
        full={}
        for mode in ('strategy','dca','half_dca'):
            metrics,curve,trades=simulate(data,actions,start,mode=mode)
            full[mode]=metrics;curve.to_csv(OUT/f'{code}_{mode}_curve.csv');pd.DataFrame(trades).to_csv(OUT/f'{code}_{mode}_trades.csv',index=False)
        spans={}
        starts=[max(start,int(data.index.searchsorted(d))) for d in pd.date_range(data.index[start],data.index[-1],freq='MS')]
        starts=sorted(set([start]+starts))
        for years in (1,3,5):
            records=[]
            for a in starts:
                anniversary=data.index[a]+pd.DateOffset(years=years)
                if anniversary>data.index[-1]:continue
                b=int(data.index.searchsorted(anniversary,side='right'))
                s=simulate(data,actions,a,b,keep=False)[0];d=simulate(data,actions,a,b,mode='dca',keep=False)[0]
                records.append(dict(start=str(data.index[a].date()),end=str(data.index[b-1].date()),strategy=s,dca=d,comparison=comparison(s,d)))
            comp=[r['comparison'] for r in records]
            spans[str(years)]=dict(count=len(comp),profit_win_pct=round(np.mean([r['profit_difference_yuan']>0 for r in comp])*100,2),
                                  drawdown_win_pct=round(np.mean([r['drawdown_improvement_pp']>0 for r in comp])*100,2),
                                  both_win_pct=round(np.mean([r['both_better'] for r in comp])*100,2),
                                  median_xirr_difference_pp=round(float(np.median([r['xirr_difference_pp'] for r in comp])),2),records=records)
        sensitivity={}
        for label,kwargs in [('no_minimum_fee',{'minimum_fee':0.}),('double_slippage',{'slippage':.002})]:
            s=simulate(data,actions,start,keep=False,**kwargs)[0];b=simulate(data,actions,start,mode='dca',keep=False,**kwargs)[0]
            sensitivity[label]=dict(strategy=s,dca=b,comparison=comparison(s,b))
        # Constant half-budget reference separates cash dilution from signal value.
        segments={}
        for year in (2021,2023,2025):
            a=int(data.index.searchsorted(pd.Timestamp(year,1,1)))
            s=simulate(data,actions,a,keep=False)[0];b=simulate(data,actions,a,mode='dca',keep=False)[0]
            segments[str(year)]=dict(start=str(data.index[a].date()),strategy=s,dca=b,comparison=comparison(s,b))
        result[code]=dict(name=name,start=str(data.index[start].date()),end=str(data.index[-1].date()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          full=full,comparison=comparison(full['strategy'],full['dca']),rolling=spans,sensitivity=sensitivity,segments=segments)
        print(code,json.dumps(dict(full=full,comparison=result[code]['comparison'],rolling={y:{k:v for k,v in r.items() if k!='records'} for y,r in spans.items()}),ensure_ascii=False),flush=True)
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    write_report(result)
    plot_results(result)

def plot_results(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family']='Microsoft YaHei'
    plt.rcParams['axes.unicode_minus']=False
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex='col')
    labels={'strategy':'当前月预算＋信号（未含溢价过滤）','dca':'普通定投1000元','half_dca':'固定买500元＋现金500元'}
    colors={'strategy':'#366f9d','dca':'#c57933','half_dca':'#879694'}
    for column,(code,r) in enumerate(results.items()):
        for mode in labels:
            c=pd.read_csv(OUT/f'{code}_{mode}_curve.csv',index_col='date',parse_dates=True)
            axes[0,column].plot(c.index,c.equity/10000,label=labels[mode],color=colors[mode])
            dd=(c.nav/c.nav.cummax()-1)*100
            axes[1,column].plot(c.index,dd,color=colors[mode])
        axes[0,column].plot(c.index,c.principal/10000,color='#333333',linestyle=':',label='累计入金')
        axes[0,column].set_title(r['name']+'：每月独立投入1000元')
        axes[0,column].set_ylabel('总资产（万元，含未投入现金）')
        axes[1,column].set_ylabel('回撤（%，剔除入金影响）')
        axes[0,column].legend(fontsize=8,loc='upper left')
        for row in range(2):axes[row,column].grid(alpha=.2)
    fig.suptitle('2015-03—2026-09｜100份一手，最低佣金5元，单边滑点0.1%，现金利息0',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'comparison.png',dpi=170);plt.close(fig)

def write_report(results):
    lines=['# 每月1000元：标普与纳指独立执行回测','',
           '研究日期：2026-10-14。标普513500和纳指513100分别投入每月1000元，不是组合合计1000元。固定现有参数，不按结果调参。',
           '', '## 验证边界', '',
           '**本次不含历史2%溢价过滤，不能证明整套上线策略产生超额收益。** 没有全区间同步、点时可见的IOPV。不能将今天的溢价或公告倒灌进历史，也不能把缺失的历史溢价设为0。生产遇到缺失溢价会停止新买；研究有意单独测试其余规则，结果不是生产策略的完整回放。',
           '', '## 结论', '',
           '在本次历史近似中，两只ETF均没有获得相对普通定投的超额收益。最大回撤下降，但资金加权收益明显降低。未用预算与卖出所得不再投入，使长期现金占比过高；尤其退出或减仓后仅靠以后月份的500/1000元额度重建持仓，难以重新参与上涨。固定买500元、留500元现金也比现行信号规则收益更高，不能把低回撤全部解释为择时有效。',
           '', '## 执行口径', '',
           '每月首个交易日入金1000元；前一收盘现行信号，次日开盘执行。买入累计使用本月额度50%，加仓累计100%，反复买入只补差额；首次过热减半，方向转弱退出。未用预算及卖出款留现金，不自动滚入以后月份买入额度。每月实际买入与买入佣金合计不超过1000元。',
           '普通定投：每月首个可成交日用当月1000元买入并长期持有；同样不动用以前月份余款。半额定投：每月用500元买入，其余留现金，用于区分低仓位与择时的效果。100份一手，佣金万一最低5元，单边0.1%滑点，现金利息0，末日不强制清仓。一字10%涨跌停近似阻止交易。',
           '价格为腾讯前复权人民币场内ETF缓存，含汇率、溢价变化和基金费用影响；无法精确重建实际分红、份数和历史成交价。填写的限价不是保证成交价，历史统一用次日开盘加滑点假设，不用事后最优价。临时停牌、真实买卖价差与排队不在模型中。',
           '收益包括所有未投入现金；最大回撤按剔除入金影响的份额化净值计算，避免每月入金掩盖亏损。XIRR为资金加权年化收益；利润/本金不是年化收益。滚动窗口重叠，并非独立样本或未来胜率。',
           '', '## 全区间', '',
           '|ETF / 区间|规则|累计本金|期末总资产|利润/本金|XIRR年化|最大回撤|平均持仓占比|', '|---|---|---:|---:|---:|---:|---:|---:|']
    labels={'strategy':'当前预算＋信号（不含溢价过滤）','dca':'普通定投1000','half_dca':'固定买500＋现金500'}
    for code,r in results.items():
        for mode,m in r['full'].items():
            lines.append(f"|{r['name']} {r['start']}—{r['end']}|{labels[mode]}|{m['principal_yuan']:.0f}|{m['ending_yuan']:.2f}|{m['profit_on_contributions_pct']:.2f}%|{m['xirr_pct']:.2f}%|{abs(m['max_drawdown_pct']):.2f}%|{m['average_exposure_pct']:.2f}%|")
    lines+=['','## 不同起点：相对普通定投','','|ETF|期限|窗口数|收益胜出比例|回撤更小比例|两项均改善比例|年化收益差中位数|','|---|---:|---:|---:|---:|---:|---:|']
    for r in results.values():
        for year,s in r['rolling'].items():lines.append(f"|{r['name']}|{year}年|{s['count']}|{s['profit_win_pct']}%|{s['drawdown_win_pct']}%|{s['both_win_pct']}%|{s['median_xirr_difference_pp']:+.2f}个百分点|")
    lines+=['','## 费用与滑点敏感性','','|ETF|条件|策略年化|定投年化|策略最大回撤|定投最大回撤|','|---|---|---:|---:|---:|---:|']
    for r in results.values():
        for label,v in r['sensitivity'].items():
            s=v['strategy'];b=v['dca'];lines.append(f"|{r['name']}|{label}|{s['xirr_pct']}%|{b['xirr_pct']}%|{abs(s['max_drawdown_pct'])}%|{abs(b['max_drawdown_pct'])}%|")
    lines+=['','复现：`python research_monthly_execution.py`。完整逐笔成交、每日现金与净值、起点统计保存于 `results/monthly_execution/`。本轮不改生产策略参数。']
    Path('monthly_execution_research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':main()
