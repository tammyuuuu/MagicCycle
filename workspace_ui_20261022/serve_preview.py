"""Local-only preview. Read cached ETF data; never refresh or publish."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pandas as pd
import app as site
import config,strategies,valuation_data,export_alerts
def cached_valuation(item,as_of,force=False):
 code=item.get('valuation_index') or valuation_data.INDEX_CODES.get(item.get('index'))
 file=Path(valuation_data.CACHE_DIR)/('valuation_'+code.replace('.','_')+'.csv') if code else None
 if file is None or not file.exists():return {'error':'预览仅使用本地估值缓存'}
 history=pd.read_csv(file,parse_dates=['date']);result=valuation_data.summarize(history,as_of)
 result['windows']={str(years):valuation_data.summarize(history,as_of,years) for years in (3,5,10)}
 return result
valuation_data.get_valuation=cached_valuation
def cached(code,force=False):
 if code in site._DATA:return site._DATA[code]
 paths=list((ROOT/'data_cache').glob(f'etf_{code}_*.csv'))
 if not paths:raise ValueError('本地缓存不可用，不在预览中联网抓取')
 path=next((p for p in paths if 'tencent' in p.name),paths[0])
 frame=pd.read_csv(path,index_col=0,parse_dates=True).sort_index();site._DATA[code]=frame;return frame
site._get_df=cached
@site.app.route('/static-preview')
def static_preview(write_snapshot=False):
 rows=[]
 for item in config.TARGET_ETFS:
  try:
   frame=cached(item['code']);s=strategies.analyze_asset(frame,valuation_data.attach_valuation(item,frame.index[-1].date().isoformat()))
   rows.append({**item,'summary':s,'rep':s['details']['legacy'] or {'date':s['date'],'close':s['metrics']['price']}})
  except Exception as e:rows.append({**item,'rep':{'error':str(e)}})
 html=export_alerts._build_page(rows,'本地缓存预览 · 未发布',False)
 if write_snapshot:(Path(__file__).parent/'static_preview.html').write_text(html,encoding='utf8')
 return html
if __name__=='__main__':site.app.run(host='127.0.0.1',port=5019,debug=False,use_reloader=False)
