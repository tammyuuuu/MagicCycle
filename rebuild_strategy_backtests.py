"""Reproduce only active strategies, from cached inputs. No selection or networking."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
import config
from broad_individual_strategy import individual_frame,CSI500_VERSION
from csi500_pe_pb_strategy import STRATEGY_VERSION as COMBO_VERSION
from valuation_data import load_pb_cache
import shutil
from research_broad_individual import execute
from research_sector_partial_exit import backtest_partial
from us_guidance import guidance_frame,VERSION as US_VERSION
from gold_strategy import stages,STRATEGY_VERSION as GOLD_VERSION
from industry_strategy import partial_exit_targets,trend_positions,STRATEGY_VERSION as SECTOR_VERSION

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results/active_strategy_backtests'
def main():
 OUT.mkdir(parents=True,exist_ok=True);assets={};hashes={};report=[]
 archive=OUT/'archive_csi500_v3'
 if (OUT/'summary.json').exists() and not archive.exists():
  archive.mkdir()
  for old in list(OUT.glob('510500_*'))+[OUT/'summary.json',OUT/'summary.csv',OUT/'ACCEPTANCE.md']:
   if old.is_file():shutil.copy2(old,archive/old.name)
 for item in config.TARGET_ETFS:
  code=item['code'];path=ROOT/f'data_cache/etf_{code}_tencent.csv';p=pd.read_csv(path,index_col='date',parse_dates=True).sort_index().loc[:'2026-10-30'];p.attrs['code']=code;hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest();tests={}
  if item.get('strategy_mode')=='broad_individual':
   sid=item['broad_strategy'];version=COMBO_VERSION if code=='510500' else 'csi300_value_confirm_v2' if code=='510300' else 'star50_buffer_v2'
   if code!='588000':
    pe=ROOT/f'data_cache/valuation_{"000905" if code=="510500" else "000300"}_SH.csv';h=pd.read_csv(pe,parse_dates=['date']);hashes[str(pe.relative_to(ROOT))]=hashlib.sha256(pe.read_bytes()).hexdigest()
   else:h=pd.DataFrame(columns=['date','pe'])
   pb=load_pb_cache() if code=='510500' else None
   if code=='510500':
    path_pb=ROOT/'data_cache/valuation_pb_000905_SH.csv';hashes[str(path_pb.relative_to(ROOT))]=hashlib.sha256(path_pb.read_bytes()).hexdigest()
   for year in [3,5,10] if code=='510300' else [5]:
    f=individual_frame(p,h,sid,year,pb_history=pb);valid=np.flatnonzero(f.ready)
    if not len(valid) or valid[0]+1>=len(p):continue
    start=int(valid[0])+1;stats,curve,trades=execute(p,f.position,start);tests[str(year)]=pack(curve,version,stats['trades'],year)
    curve.to_csv(OUT/f'{code}_{year}_daily.csv');pd.DataFrame(trades).to_csv(OUT/f'{code}_{year}_trades.csv',index=False)
    if code=='510500' and year==5:
     research=pd.read_csv(ROOT/'research_csi500_pe_pb_combinations/accounts/P5_OR_in_A_out_daily.csv.gz',index_col='date',parse_dates=True)
     assert curve.index.equals(research.index) and np.allclose(curve.equity,research.equity)
     expected=pd.read_csv(ROOT/'research_csi500_pe_pb_combinations/accounts/P5_OR_in_A_out_orders.csv')
     actual=pd.DataFrame(trades)
     assert len(actual)==len(expected)
     for col in ['date','action','quantity','signal_date']:
      assert actual[col].astype(str).tolist()==expected[col].astype(str).tolist(),col
  else:
   if code in ['513500','513100']:
    f=guidance_frame(p.close);target=f.target;entry=f.entry_allowed;version=US_VERSION;start=int(np.flatnonzero(f.ready)[0])+1;limit=.10
   elif code=='518850':
    f=stages(p.close);target=f.target;entry=target==1.;version=GOLD_VERSION;start=120;limit=.10
   else:target=partial_exit_targets(p.close);entry=trend_positions(p.close);version=SECTOR_VERSION;start=20;limit=.20
   stats,curve,trades=backtest_partial(p,target,start,len(p),entry_allowed=entry,limit_pct=limit)
   tests['default']=pack(curve,version,len(trades));curve.to_csv(OUT/f'{code}_daily.csv');pd.DataFrame(trades).to_csv(OUT/f'{code}_trades.csv',index=False)
  assets[code]=dict(version=version,backtests=tests)
  bt=tests.get('5') or tests.get('default');report.append(dict(code=code,version=version,**bt))
 # Bond is a separate reinvested NAV buy-and-hold model, not an ETF timing strategy.
 path=ROOT/'research_xingxun_v2/clean_v2/000015.csv';b=pd.read_csv(path,index_col='date',parse_dates=True);v=b.tr/b.tr.iloc[0]/1.0008;curve=pd.DataFrame({'equity':100000*v},index=b.index)
 bt=pack(curve,'bond_hold_v1',1);bt['note']='分红再投资长期持有；申购费0.08%，期末长期赎回费0；历史条件模拟。';assets['000015']=dict(version='bond_hold_v1',backtests={'default':bt});hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
 result=dict(schema='active-strategy-backtests-v1',as_of='2026-10-31',assets=assets,input_hashes=hashes)
 (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');pd.DataFrame(report).to_csv(OUT/'summary.csv',index=False)
 c=assets['510500']['backtests']['5'];assert round(c['annual_pct'],2)==12.21 and round(c['max_drawdown_pct'],2)==56.09
 print(pd.DataFrame(report)[['code','version','start','end','annual_pct','max_drawdown_pct']].to_string(index=False))
def pack(curve,version,orders,years=None):
 values=np.r_[100000.,curve.equity.to_numpy()];ann=(values[-1]/100000)**(365.25/(curve.index[-1]-curve.index[0]).days)-1;dd=1-np.min(values/np.maximum.accumulate(values))
 note='10万元固定本金；次日开盘，单边0.1%滑点、佣金万一最低5元，空仓现金收益0。历史条件模拟。'
 if years:note=f'近{years}年估值参考。'+note if version!='star50_buffer_v2' else note
 if version==CSI500_VERSION:note+=' 2021年后年化4.83%，低于旧版7.80%；尚未证明样本外更优。'
 return dict(start=str(curve.index[0].date()),end=str(curve.index[-1].date()),annual_pct=ann*100,annual_method='CAGR',max_drawdown_pct=dd*100,total_pct=(values[-1]/100000-1)*100,orders=orders,note=note)
if __name__=='__main__':main()
