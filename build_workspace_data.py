"""Package audited research + raw fund NAV for both local and static views.
No live account data, network requests, strategy activation, or publishing.
"""
from pathlib import Path
import hashlib,json,sys,ast
import pandas as pd
ROOT=Path(__file__).resolve().parent
VERSION='daily_causal_v3_def_20261022'
WEIGHTS={'A':{'000015':1/3,'008701':1/3,'161130':1/3},'B':{'000015':.4,'008701':.3,'161130':.3},'C':{'000015':.6,'008701':.2,'161130':.2},'L1':{'000015':.5,'008701':.5},'L2':{'000015':1/3,'008701':1/3,'090010':1/3}}
WEIGHTS.update({'L3':{'000015':1/3,'008701':1/3,'001214':1/3},'L4':{'000015':1/3,'008701':1/3,'160706':1/3}})
for a,b in [('A','D'),('B','E'),('C','F')]:WEIGHTS[b]={('050025' if c=='161130' else c):v for c,v in WEIGHTS[a].items()}
NAMES={'000015':'华夏纯债债券A','008701':'华夏黄金ETF联接A','161130':'易方达纳指100联接A','090010':'大成中证红利指数A'}
NAMES['050025']='博时标普500ETF联接A'
NAMES.update({'001214':'华泰柏瑞中证500ETF联接A','160706':'嘉实沪深300ETF联接A'})
def build_payload():
 base=ROOT/'research_def_20261022/results';meta=json.loads((base/'manifest.json').read_text(encoding='utf8'));summary=pd.read_csv(base/'summary.csv')
 extension=base
 conditions={}
 for folder,file in [('research_xingxun_v1/clean','fund_meta.csv'),('research_xingxun_v2/clean_v2','fund_meta_v2.csv')]:
  for row in pd.read_csv(ROOT/folder/file,dtype={'code':str}).fillna('').to_dict('records'):
   if row['code'] in NAMES:conditions[row['code']]={'buy_pct':float(row['current_rate_pct']), 'redeem_tiers':ast.literal_eval(row['redeem_fee_tiers']), 'status':row['purchase_status'], 'limit':row.get('daily_purchase_limit',''), 'as_of':'2026-10-22', 'source':folder+'/'+file}
 snapshot=json.loads((ROOT/'research_xingxun_v2/trade_conditions_2026-10-22.json').read_text(encoding='utf8'))
 for code,row in snapshot.items():
  if code in conditions:conditions[code].update(status=row['purchase_status'],limit=row.get('daily_purchase_limit') or '',buy_pct=row['current_rate_pct'],redeem_tiers=row['redeem_fee_tiers'])
 digest=hashlib.sha256(json.dumps([WEIGHTS,conditions],sort_keys=True).encode())
 inputs=[base/'summary.csv',base/'manifest.json',*sorted(base.glob('*_daily.csv'))]
 inputs += [base/'availability.json',base/'050025_corrected.csv',ROOT/'research_def_20261022/050025_dividends.json']
 for code in NAMES:
  folder='research_xingxun_v1' if code in ['090010','160706','050025'] else 'research_xingxun_v2'
  inputs.append(ROOT/folder/('clean' if code in ['090010','160706','050025'] else 'clean_v2')/f'{code}.csv')
  dividend=ROOT/folder/'raw'/f'{code}_fhsp.html'
  if dividend.exists():inputs.append(dividend)
 for file in inputs:digest.update(file.read_bytes())
 digest.update(Path(__file__).read_bytes())
 version=VERSION+'_'+digest.hexdigest()[:10]
 strategies=[]
 for code,w in WEIGHTS.items():
  runs=[]
  for r in summary[summary.scheme==code].itertuples():
   prefix=f'{r.segment}_{code}_{r.mode}';source=extension if code in ['L3','L4'] else base;d=pd.read_csv(source/f'{prefix}_daily.csv');eq=d.equity.to_numpy(float);unit=eq/eq[0];peak=pd.Series(unit).cummax().to_numpy()
   runs.append(dict(segment=r.segment,mode=r.mode,first=r.first,last=r.last,cagr=r.cagr,mdd=r.mdd,fees=r.fees,days=r.days,final=r.final,data_type=r.data_type,actual_weights=json.loads(r.actual_weights),substitutions=json.loads(r.substitutions),
     curve=[[str(date),round(float(u),8),round(float(u/p-1),8)] for date,u,p in zip(d.iloc[:,0],unit,peak)]))
  strategies.append(dict(id=code,version=f'{version}_{code}',status='research_conditional',scenario='nasdaq_available' if code in ['A','B','C','D','E','F'] else 'nasdaq_unavailable',weights=w,runs=runs,source=str((extension if code in ['L3','L4'] else base).relative_to(ROOT)),lab_only=code in ['L3','L4','D','E','F'],simulation_validation='conditional',unavailable=[r for r in json.loads((base/'availability.json').read_text(encoding='utf8')) if r['scheme']==code]))
 research=dict(schema_version=1,version=version,engine=meta['engine'],source='research_def_20261022/results',assumptions=meta,strategies=strategies,
   scenarios={'nasdaq_available':'正常申购理论情景（纳指或标普）','nasdaq_unavailable':'纳指不可买的结构性情景'},
   rejected=[{'name':'V2.3原月度主表','reason':'全资产统一删缺失值导致样本实际截至2025-01，月频回撤也隐藏日度风险。'},
   {'name':'V2.3动态逆波动/ERC漂亮收益','reason':'用当月末信息设置当月权重，存在未来信息泄漏；原数字不再展示。'},
   {'name':'V2.1回调8%最优结论','reason':'原三年训练收益跨入测试时期；修复后训练窗口不足，拒绝选参。'},
   {'name':'K4被L1/L2严格支配','reason':'收益与回撤存在交换，严格支配表述不成立；这也不构成默认买中证500的证据。'},
   {'name':'旧月初持仓复盘公式','reason':'遗漏月中买卖、现金和费用，已由全账户日度净资产核算替代。'}])
 research['segments']=[{'id':i,'label':label,'data_type':kind} for i,label,kind in [('main','2021-11至2026-10 · 主样本','actual_fund'),('real_2020','2020-07起 · 真实基金共同起点','actual_fund'),('historical_2023','2023起历史分段 · 非严格样本外','actual_fund'),('real_2013','2013起 · 原基金（检查覆盖）','actual_fund'),('real_2017','2017–2024 · 原基金（检查覆盖）','actual_fund'),('real_2019','2019起 · 原基金（检查覆盖）','actual_fund'),('long_proxy','2017–2024 · 指数代理研究','index_proxy'),('proxy_2013','2013-08起 · 指数代理研究','index_proxy'),('proxy_2019','2019-04起 · 指数代理研究','index_proxy')]]
 research['data_types']={'actual_fund':'真实基金历史净值回测','index_proxy':'指数代理研究（以替代基金净值代表指数类别，非原组合回测）'}
 research['pairs']=[['A','D'],['B','E'],['C','F']]
 research['asset_names']={r.code:r.name for r in pd.read_csv(ROOT/'research_xingxun_v1/clean/fund_meta.csv',dtype={'code':str}).itertuples()}
 sys.path.insert(0,str(ROOT/'research_xingxun_v1'));import data_prep as dp
 funds={}
 for code,name in NAMES.items():
  v2=code not in ['090010','160706','050025'];clean=ROOT/('research_xingxun_v2/clean_v2' if v2 else 'research_xingxun_v1/clean')
  file=(base/'050025_corrected.csv') if code=='050025' else clean/f'{code}.csv';d=pd.read_csv(file);dp.RAW=ROOT/('research_xingxun_v2/raw' if v2 else 'research_xingxun_v1/raw');events,error=dp.parse_dividends(code)
  if code=='050025':events=json.loads((ROOT/'research_def_20261022/050025_dividends.json').read_text(encoding='utf8'));error='已按三次基金分红公告补正；研究按除息日自动再投，真实账户以渠道确认单为准'
  funds[code]=dict(name=name,source=str(file.relative_to(ROOT)),sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
    nav=[[str(r.date),float(r.nav)] for r in d.itertuples()],dividends=events,dividend_warning=error,as_of=str(d.date.iloc[-1]))
 return {'trading_conditions':conditions,'research':research,'funds':funds,'schema_version':1,'as_of':max(f['as_of'] for f in funds.values()),'calendar':[p[0] for p in funds['000015']['nav']]}
def main():
 payload=build_payload();out=ROOT/'workspace_data';out.mkdir(exist_ok=True)
 version=payload['research']['version'];encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)
 target=out/f'{version}.json'
 if target.exists() and target.read_text(encoding='utf8')!=encoded:raise ValueError('同版本文件内容发生改变，必须更换数据版本，禁止覆盖')
 target.write_text(encoded,encoding='utf8')
 (out/'manifest.json').write_text(json.dumps({'current':f'{version}.json','version':version},ensure_ascii=False,indent=2),encoding='utf8')
 print('Packaged',version,len(payload['research']['strategies']),'research strategies; no account data')
if __name__=='__main__':main()
