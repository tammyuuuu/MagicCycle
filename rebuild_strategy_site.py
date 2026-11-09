"""Rebuild strategy cards from the exact backtest caches, preserving account snapshots."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json
import pandas as pd
import config,strategies
from export_alerts import _build_page
from build_pwa_release import build_release
ROOT=Path(__file__).resolve().parent
def main():
 out=ROOT/'docs';items=[]
 for item in config.TARGET_ETFS:
  code=item['code'];p=pd.read_csv(ROOT/f'data_cache/etf_{code}_tencent.csv',index_col='date',parse_dates=True).sort_index()
  enriched=dict(item)
  if code in ['510300','510500']:
   h=pd.read_csv(ROOT/f'data_cache/valuation_{"000300" if code=="510300" else "000905"}_SH.csv')
   enriched['valuation_history']=h.to_dict('records')
   if code=='510500':
    from valuation_data import load_pb_cache
    enriched['pb_valuation_history']=load_pb_cache(p.index[-1]).to_dict('records')
  summary=strategies.analyze_asset(p,enriched)
  items.append({**item,'summary':summary,'rep':summary['details'].get('legacy') or {'date':summary['date'],'close':summary['metrics']['price']}})
 access=json.loads((out/'purchase_monitor.json').read_text(encoding='utf8'))
 stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
 html=_build_page(items,stamp,False,None,access,output_dir=str(out))
 (out/'index.html').write_text(html,encoding='utf8')
 (out/'index.json').write_text(json.dumps([i['summary'] for i in items],ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
 print('Local site rebuilt from dated caches; account and quota snapshots preserved.',build_release(out))
if __name__=='__main__':main()
