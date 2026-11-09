import akshare as a, json, time, sys
cases={'a_valuation':('stock_value_em',{'symbol':'600519'}),'us_indicators':('stock_financial_us_analysis_indicator_em',{'symbol':'AAPL','indicator':'年报'}),'us_famous':('stock_us_famous_spot_em',{'symbol':'科技类'}),'hk_famous':('stock_hk_famous_spot_em',{}),'a_qfq':('stock_zh_a_hist',{'symbol':'600519','start_date':'20261001','end_date':'20261106','adjust':'qfq'}),'us_qfq':('stock_us_hist',{'symbol':'105.AAPL','start_date':'20261001','end_date':'20261106','adjust':'qfq'}),'hk_qfq':('stock_hk_hist',{'symbol':'00700','start_date':'20261001','end_date':'20261106','adjust':'qfq'})}
k=sys.argv[1]; fn,kw=cases[k]; t=time.monotonic()
try:
 d=getattr(a,fn)(**kw); print(json.dumps({'case':k,'function':fn,'args':kw,'ok':True,'seconds':round(time.monotonic()-t,2),'rows':len(d),'columns':list(d.columns),'first':d.head(1).astype(str).to_dict('records'),'last':d.tail(1).astype(str).to_dict('records')},ensure_ascii=False,default=str))
except Exception as e: print(json.dumps({'case':k,'function':fn,'ok':False,'seconds':round(time.monotonic()-t,2),'error':str(e)[:350]},ensure_ascii=False))
