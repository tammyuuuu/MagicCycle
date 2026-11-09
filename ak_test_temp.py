import akshare as a, time, json, traceback, concurrent.futures
cases=[('A列表','stock_info_a_code_name',{}),('港股列表','stock_hk_spot_em',{}),('美股列表','stock_us_spot_em',{}),('A前复权','stock_zh_a_hist',dict(symbol='600519',period='daily',start_date='20000101',end_date='20261106',adjust='qfq')),('港股前复权','stock_hk_hist',dict(symbol='00700',period='daily',start_date='20000101',end_date='20261106',adjust='qfq')),('美股前复权','stock_us_hist',dict(symbol='AAPL',period='daily',start_date='20000101',end_date='20261106',adjust='qfq')),('A估值','stock_a_indicator_lg',dict(symbol='600519')),('A财报','stock_financial_report_sina',dict(stock='sh600519',symbol='利润表')),('港股财报','stock_financial_hk_report_em',dict(stock='00700',symbol='利润表',indicator='年度')),('美股财报','stock_financial_us_report_em',dict(stock='AAPL',symbol='综合损益表',indicator='年报')),('A增长','stock_financial_analysis_indicator',dict(symbol='600519',start_year='2015')),('退市样本','stock_zh_a_hist',dict(symbol='600656',period='daily',start_date='20000101',end_date='20261106',adjust='qfq'))]
def run(c):
 name,fn,kw=c; t=time.perf_counter(); out={'name':name,'function':fn,'args':kw}
 try:
  d=getattr(a,fn)(**kw); out.update(ok=True,seconds=round(time.perf_counter()-t,2),rows=len(d),columns=list(map(str,d.columns)),first=d.head(1).astype(str).to_dict('records'),last=d.tail(1).astype(str).to_dict('records'))
 except Exception as e: out.update(ok=False,seconds=round(time.perf_counter()-t,2),error=str(e)[:500])
 print(json.dumps(out,ensure_ascii=False),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(run,cases))
