"""研究用：验证并缓存对应指数估值，绝不使用其他行业指数替代。"""
from pathlib import Path
from datetime import datetime
import json
import socket
import sys
from bs4 import BeautifulSoup
import requests
import pandas as pd
from io import BytesIO
import akshare.stock_feature.stock_a_pe_and_pb as upstream
from valuation_data import normalize_history

socket.setdefaulttimeout(20)


def extract_public_history(html, code):
    """只解析普通公开页面已返回的JSON文本，不执行页面脚本。"""
    parts=[]
    for element in BeautifulSoup(html,'html.parser').find_all('script'):
        value=element.get_text().strip()
        prefix='self.__next_f.push('
        if value.startswith(prefix) and value.endswith(')'):
            item=json.loads(value[len(prefix):-1])
            if item[0]==1:parts.append(item[1])
    for line in ''.join(parts).splitlines():
        try:payload=json.loads(line.split(':',1)[1])
        except (ValueError,IndexError):continue
        if not isinstance(payload,list) or len(payload)<4 or not isinstance(payload[3],dict):continue
        props=payload[3]
        if 'compressedIndexDaily' not in props:continue
        if props['indexInfo']['code']!=code:raise ValueError('指数代码不匹配')
        history=props['compressedIndexDaily']
        frame=pd.DataFrame(history['values'],columns=history['fieldNames'])
        dates=pd.to_datetime(frame['date'])
        if dates.duplicated().any() or not dates.is_monotonic_increasing:raise ValueError('历史日期重复或无序')
        return frame,props['indexInfo']
    raise ValueError('公开页面未提供历史数据')


def main():
    directory=Path('data_cache');directory.mkdir(exist_ok=True)
    if '--public-pages' in sys.argv:
        for code in ('990001','950125'):
            url=f'https://www.etf.run/index/CSI/{code}'
            try:
                response=requests.get(url,timeout=20);response.raise_for_status()
                path=directory/f'research_etfrun_{code}.html'
                path.write_text(response.text,encoding='utf-8')
                frame,info=extract_public_history(response.text,code)
                frame.to_csv(directory/f'research_etfrun_valuation_{code}.csv',index=False)
                metadata={'url':url,'checked_at':datetime.now().isoformat(),
                          'index_code':code,'index_name':info['fullName'],
                          'valuation_method':'equal weighted, as labelled by source',
                          'rows':len(frame),'start':str(frame.date.min()),'end':str(frame.date.max()),
                          'publication_date':pd.Timestamp(info['listAt'],unit='ms',tz='UTC').tz_convert('Asia/Shanghai').date().isoformat()}
                (directory/f'research_etfrun_valuation_{code}.meta.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
                print(code,'public history saved',len(frame),frame.date.min(),frame.date.max())
            except Exception as exc:
                print(code,type(exc).__name__,str(exc)[:120])
        return
    engine=upstream.py_mini_racer.MiniRacer();engine.eval(upstream.hash_code)
    token=engine.call('hex',datetime.now().date().isoformat()).lower()
    cookies=upstream.get_cookie_csrf(url='https://legulegu.com/stockdata/sz50-ttm-lyr')
    checks=[]
    for code in ('990001.CSI','950125.CSI','990001.SH','950125.SH'):
        try:
            response=requests.get('https://legulegu.com/api/stockdata/index-basic-pe',
                                  params={'token':token,'indexCode':code},timeout=20,**cookies)
            response.raise_for_status();payload=response.json()
            data=normalize_history(payload.get('data',[]))
            if data.empty:raise ValueError('empty history')
            filename=directory/('research_valuation_'+code.replace('.','_')+'.csv')
            data.to_csv(filename,index=False)
            checks.append({'source':'legulegu','code':code,'rows':len(data),'file':str(filename)})
            print(code,len(data),str(data.date.min().date()),str(data.date.max().date()),'saved',filename)
        except Exception as exc:
            checks.append({'source':'legulegu','code':code,'error':str(exc)[:200]})
            print(code,type(exc).__name__,str(exc)[:120])
    for code in ('990001','950125'):
        url=f'https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/indicator/{code}indicator.xls'
        try:
            response=requests.get(url,timeout=20);response.raise_for_status()
            frame=pd.read_excel(BytesIO(response.content))
            filename=directory/f'research_official_valuation_{code}.csv'
            frame.to_csv(filename,index=False)
            checks.append({'source':'csindex','code':code,'url':url,'rows':len(frame),'columns':list(map(str,frame.columns)),'file':str(filename)})
            print('official',code,'rows',len(frame),'date range',frame.iloc[:,0].min(),frame.iloc[:,0].max())
        except Exception as exc:
            checks.append({'source':'csindex','code':code,'url':url,'error':str(exc)[:200]})
            print('official',code,type(exc).__name__,str(exc)[:120])
    (directory/'research_sector_valuation_sources.json').write_text(json.dumps({'checked_at':datetime.now().isoformat(),'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
