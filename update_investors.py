import requests,re,xml.etree.ElementTree as ET,json,html,datetime,pathlib,sys,time
from bs4 import BeautifulSoup
import akshare
P=pathlib.Path(__file__).resolve().parent;D=P/'docs';D.mkdir(exist_ok=True)
S=requests.Session();S.headers.update({'User-Agent':'MagicCycle research contact support@magiccycle.app','Accept-Encoding':'gzip, deflate'})
def get(u,**kw):
 for attempt in range(3):
  try:
   r=S.get(u,timeout=30,**kw);r.raise_for_status();return r
  except requests.RequestException:
   if attempt==2:raise
   time.sleep(1+attempt)
def sec(cik):
 data=get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json').json()['filings']['recent'];fs=[{k:data[k][i] for k in ('reportDate','filingDate','acceptanceDateTime','accessionNumber','form')} for i in range(len(data['form'])) if data['form'][i] in ('13F-HR','13F-HR/A')]; periods=sorted(set(f['reportDate'] for f in fs if f['form']=='13F-HR'),reverse=True)[:2];out=[]
 for per in periods:
  versions=sorted((f for f in fs if f['reportDate']==per),key=lambda f:f['acceptanceDateTime']);hold={};refs=[]
  for f in versions:
   acc=f['accessionNumber'];base=f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-","")}/';r=get(base+acc+'.txt');docs=re.findall(r'<DOCUMENT>\s*<TYPE>([^\n]+).*?<FILENAME>([^\n]+).*?<TEXT>(.*?)</TEXT>\s*</DOCUMENT>',r.text,re.S|re.I);info=next((x[2] for x in docs if 'INFORMATION TABLE' in x[0].upper()),None)
   if not info:raise ValueError('missing information table '+acc)
   info=re.sub(r'</XML>\s*$','',re.sub(r'^\s*<XML>\s*','',info.strip(),flags=re.I),flags=re.I);root=ET.fromstring(info)
   def field(e,n):return next(((x.text or '').strip() for x in e.iter() if x.tag.split('}')[-1]==n),'')
   if f['form'].endswith('/A') and 'RESTATEMENT' in r.text.upper():hold={}
   for e in root.iter():
    if e.tag.split('}')[-1]!='infoTable':continue
    key=(field(e,'cusip'),field(e,'titleOfClass'),field(e,'putCall'));hold[key]={'name':field(e,'nameOfIssuer'),'code':key[0],'class':key[1],'option':key[2],'shares':int(field(e,'sshPrnamt') or 0),'unit':field(e,'sshPrnamtType'),'value':int(field(e,'value') or 0)}
   refs.append(dict(date=f['filingDate'],accepted=f['acceptanceDateTime'],url=base+acc+'-index.html',form=f['form']))
  out.append(dict(period=per,disclosures=refs,rows=hold))
 if len(out)<2:raise ValueError('less than two reports')
 a,b=out;rows=[]
 for k in set(a['rows'])|set(b['rows']):
  x=a['rows'].get(k);y=b['rows'].get(k);row=dict(x or y);row['previous']=y['shares'] if y else None;row['current']=x['shares'] if x else None
  row['change']='未再申报，是否退出未知' if not x else '首次申报，是否新建仓未知' if not y else '股数增加，待核公司行为' if x['shares']>y['shares'] else '股数减少，待核公司行为' if x['shares']<y['shares'] else '股数未变';rows.append(row)
 a['rows']=sorted(rows,key=lambda x:x['value'],reverse=True);a['prior_period']=b['period'];return a

def fund():
 h={'Referer':'https://fundf10.eastmoney.com/ccmx_161005.html','X-Requested-With':'XMLHttpRequest','User-Agent':'Mozilla/5.0'}
 anns=get('https://api.fund.eastmoney.com/f10/JJGG',headers=h,params={'fundcode':'161005','pageIndex':1,'pageSize':100,'type':3}).json()['Data']; idx={}
 for a in anns:
  t=a['TITLE'];date=a['PUBLISHDATEDesc'];m=int(date[5:7]);yr=int(date[:4]); q={1:4,4:1,7:2,10:3}.get(m)
  if q and ('季度报告' in t or '季度季报' in t) and '更正' not in t: idx.setdefault((yr-1 if m==1 else yr,q),a)
 dem=akshare.fund_portfolio_hold_em.__globals__['demjson']; quarters={}
 for yr in sorted(set(k[0] for k in idx),reverse=True)[:2]:
  r=get('https://fundf10.eastmoney.com/FundArchivesDatas.aspx',headers=h,params={'type':'jjcc','code':'161005','rt':'0.271828','topline':100,'year':yr,'month':''});t=r.text;j=dem.decode(t[t.find('{'):t.rfind('}')+1]);s=BeautifulSoup(j['content'],'html.parser')
  for box in s.select('div.boxitem'):
   match=re.search(r'(20\d{2})-(03|06|09|12)-(\d{2})',box.get_text(' ',strip=True)[:300]);
   if not match:continue
   y=int(match[1]);q={'03':1,'06':2,'09':3,'12':4}[match[2]];k=(y,q)
   if k not in idx:continue
   rr={}
   for tr in box.select('tbody tr')[:10]:
    tds=[x.get_text(' ',strip=True) for x in tr.select('td')]
    if len(tds)<7 or not tds[0].isdigit():continue
    rr[tds[1]]={'code':tds[1],'name':tds[2],'shares':round(float(tds[-2].replace(',',''))*10000),'unit':'股（约数）','value':float(tds[-1].replace(',',''))*10000}
   if len(rr)==10:quarters[k]=rr
 if len(quarters)<2:raise ValueError('fund insufficient quarterly data')
 keys=sorted(quarters,reverse=True)[:2];cur,prev=keys;rows=[]
 for k in set(quarters[cur])|set(quarters[prev]):
  x=quarters[cur].get(k);y=quarters[prev].get(k);r=dict(x or y);r['current']=x['shares'] if x else None;r['previous']=y['shares'] if y else None;r['change']='退出前十，是否清仓未知' if not x else '进入前十，是否新建仓未知' if not y else '股数增加（约数），待核公司行为' if x['shares']>y['shares'] else '股数减少（约数），待核公司行为' if x['shares']<y['shares'] else '股数约数未变';rows.append(r)
 a=idx[cur];return dict(period=f'{cur[0]}Q{cur[1]}',prior_period=f'{prev[0]}Q{prev[1]}',disclosures=[dict(date=a['PUBLISHDATEDesc'],url=f'https://fund.eastmoney.com/gonggao/161005,{a["ID"]}.html')],rows=sorted(rows,key=lambda x:x['value'],reverse=True))
def main():
 data={};errors=[]
 for key,fn in [('ackman',lambda:sec(2026053)),('berkshire',lambda:sec(1067983)),('zhu',fund)]:
  try:data[key]=fn();print(key,'ok',data[key]['period'])
  except Exception as e:errors.append(key+': '+str(e))
 if errors:raise RuntimeError('; '.join(errors))
 data['updated']=datetime.datetime.now(datetime.timezone.utc).isoformat();(D/'investors.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); (P/'data_cache').mkdir(exist_ok=True); (P/'data_cache'/'investors.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()

