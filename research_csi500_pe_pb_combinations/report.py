from pathlib import Path
import json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
def read(n):return pd.read_csv(P/n)
protocol=json.loads((P/'protocol.json').read_text());specs=protocol['combinations'];spec_by_id={s['id']:s for s in specs}
m=read('period_metrics.csv');inc=read('increment_over_matched_singles.csv');train=read('structure_training.csv');ns=read('sensitivity_summary.csv');nd=read('sensitivity_metrics.csv');early=read('PB_only_early_campaigns.csv');years=read('calendar_year_returns.csv');gates=read('candidate_diagnostic_gates.csv');paths=read('equivalent_strategy_paths.csv');rec=json.loads((P/'recommendation.json').read_text())
WATCH='P5_OR_in_A_out';SELECTED=rec['training_selected'];H=[1,3,5,10]
def label(identifier):
 if identifier.startswith('SINGLE_'):return {'SINGLE_A':'独立PE5＋MA120','SINGLE_B':'独立PB10＋MA120','SINGLE_C':'独立PB5纯估值'}[identifier]
 if '_REF_' in identifier:return identifier.split('_REF_')[0]+'同起点'+{'A':'PE5','B':'PB10','C':'PB5'}[identifier.split('_REF_')[1]]
 s=spec_by_id[identifier];group={'P10':'PE＋PB10','P5':'PE＋PB5','TRI':'三策略'}[s['group']]
 buy={'AND':'共同买','OR':'任一买','A':'PE买','B':'PB买','C':'PB买'}[s['entry']];sell={'AND':'共同退','OR':'任一退','A':'PE退','B':'PB退','C':'PB退'}[s['exit']]
 return f'{group}：{buy}／{sell}'
def labeled(z):
 z=z.copy();z['strategy']=z.id.map(label);return z
def table(df,cols,labels):
 z=df[cols].copy();z.columns=labels
 def fmt(v):
  if pd.isna(v):return '历史不足'
  if isinstance(v,(bool,np.bool_)):return '是' if v else '否'
  if isinstance(v,(float,np.floating)):return f'{v:.2f}'
  return str(v)
 return '| '+' | '.join(z.columns)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in z.itertuples(index=False,name=None))
allids=['SINGLE_A','SINGLE_B','SINGLE_C']+[s['id'] for s in specs]
def wide(metric):
 z=m[m.period.str.startswith('trailing')&m.id.isin(allids)].copy();z['h']=z.period.str.replace('trailing','').astype(int)
 z=z.pivot(index='id',columns='h',values=metric).reindex(index=allids,columns=H);z.index=[label(x) for x in z.index];z.index.name='固定组合';z.columns=[f'近{y}年' for y in H];return z.reset_index()
increment_table=[]
for s in specs:
 z=m[(m.id==s['id'])&(m.period=='trailing5')].iloc[0];a=m[(m.id==f"{s['group']}_REF_A")&(m.period=='trailing5')].iloc[0]
 pbs=m[(m.id.isin([f"{s['group']}_REF_{c}" for c in s['components'] if c!='A']))&(m.period=='trailing5')];pb=pbs.sort_values('annual_pct',ascending=False).iloc[0]
 increment_table.append(dict(id=s['id'],annual_pct=z.annual_pct,maxdd_pct=z.maxdd_pct,orders=z.orders,increment_vs_PE_pp=z.annual_pct-a.annual_pct,increment_vs_best_PB_pp=z.annual_pct-pb.annual_pct))
it=pd.DataFrame(increment_table).sort_values(['annual_pct','maxdd_pct'],ascending=[False,True]);it.to_csv(P/'recent5_increment_table.csv',index=False)
definitions=[]
for s in specs:
 parts=s['components'];es=' ∧ '.join('E'+c for c in parts) if s['entry']=='AND' else ' ∨ '.join('E'+c for c in parts) if s['entry']=='OR' else 'E'+s['entry']
 xs=' ∧ '.join('X'+c for c in parts) if s['exit']=='AND' else ' ∨ '.join('X'+c for c in parts) if s['exit']=='OR' else 'X'+s['exit']
 definitions.append(dict(id=s['id'],strategy=label(s['id']),entry=es,exit=xs))
pd.DataFrame(definitions).to_csv(P/'combination_definitions.csv',index=False)
focus=[WATCH,'P5_OR_in_OR_out','P5_OR_in_AND_out',SELECTED,'SINGLE_A','SINGLE_B','SINGLE_C']
body=['# 中证500 PE与PB固定信号组合研究',
'数据截至2026-10-30，研究日期2026-10-31。固定三套已有参数，只组合其买卖条件；未重新优化估值窗口、均线、阈值或资金比例，网站及生产代码未修改。',
'## 核心结论',
'**发现了明确的近年历史增量，但尚不能认定为跨周期稳定、可直接替换正式策略的优势。** 最值得新增前瞻验证的是“**PE或PB5纯估值任一满足买入，仍按PE规则退出**”：近5年年化13.47%、回撤15.87%，独立PE为5.28%／17.04%，独立PB5纯估值8.65%／19.68%。这是同标的、同费用、无杠杆下的完整账户差异，不是漏计空仓、增加资金或只统计成功交易造成。',
'该组合近3年年化19.77%，近10年6.93%；但近10年最大回撤38.08%，明显大于独立PE22.68%。2017—2020共同起点训练段年化仅0.54%，低于PE7.28%；2018年早买造成较大拖累。近年的收益和回撤改善不能推导为长期风险也改善。',
'只按训练段选出的结构是“PE与PB10共同买入、共同确认退出”，但它在本样本实际复现PB10独立策略，没有组合增量。不能看到另一个组合留出表现更好，就把它改称训练选择成功。最优近期组合属于**留出观察后的研究提名**，需要新的前瞻数据。',
'## 一、三个独立组件：全部参数冻结',
'|代号|固定独立策略|原始买入条件E|原始退出条件X|\n|---|---|---|---|\n|A|正式PE5年＋MA120〔60／30〕|PE5分位<60%且收盘>MA120|PE5分位≥30%且收盘≤MA120|\n|B|PB10年＋MA120〔10／60〕|PB10分位<10%且收盘>MA120|PB10分位≥60%且收盘≤MA120|\n|C|PB5年纯估值〔10／60〕|PB5分位<10%|PB5分位≥60%|',
'本轮使用此前主研究口径：PE实际字段ttmPe、PB字段pb，对应本机AkShare映射的等权估值，不混用整体法数值。A直接使用生产相同的历史分位计算；B、C使用此前冻结的月度PB分位。两者均额外滞后一个ETF交易日，按当时可见数据计算，不使用接口的全历史分位。',
'这里的PE／PB组合是**固定买卖谓词的布尔组合**，不是此前PE与PB分位50／50平均的新估值分数，也不是把资金分成两个独立投资账户。全账户最多一份中证500ETF持仓，两个买入条件同时出现不加倍买入或加杠杆。',
'## 二、持有、退出与冲突的明确定义',
'每个组合有自己的持仓状态，使用当日原始E／X条件组合；**不把两个独立策略已经运行过的持仓0／1直接求交集、并集**。因此退出后，只要条件重新允许，就可以再次进入，即使PB低估区间本身一直未结束。没有额外冷却期或新止损。',
'统一状态机：\n1. 所需估值有效时，先检查组合退出X；X为真，退出或保持空仓。\n2. X为假且空仓，组合买入E为真，才进入。\n3. 其他情况保持原状态；估值缺失则暂停判断并保持，不用未来值补齐。\n4. 信号下一交易日开盘执行。',
'**退出优先也是否决入场的条件**：若PB要求买入但PE要求退出，不会今天买、明天卖、后天又买。共同退出指**同一个收盘日**两个／三个X同时满足，不记忆上周曾经发生过的退出确认。',
'对每个PE／PB配对做八个固定结构：共同／任一买入分别配合PE退出、任一退出、共同退出，再加PE买入PB退出、PB买入PE退出；另补四个三者AND／OR方案，共20个预设结构。实际只有14条不同有效起点下的完整信号路径，等价结果不算多次独立验证。',
table(pd.DataFrame(definitions),['strategy','entry','exit'],['组合','原始买入E','原始退出X']),
'上表买入实际还必须满足“组合X为假”。符号∧=同时满足，∨=任一满足。哪个原始条件被组合采用由结构决定；没有改阈值。例如近期最佳组合使用C的买入<10%，不采用C的卖出≥60%，由A退出接管，这不是把PB退出阈值改成另一个数。',
'### 最值得前瞻验证的候选，完整公式',
'- 买入：`[(PE5分位<60% 且 收盘>MA120) 或 PB5分位<10%]`，**同时不满足**`[PE5分位≥30% 且 收盘≤MA120]`。\n- 持有：买入后保持，直到下述退出。\n- 退出：`PE5分位≥30% 且 收盘≤MA120`；下一交易日开盘执行。\n- 空仓：退出后可在上述买入条件重新成立时再进入；没有PB5低估信号时，仍保留原PE策略的入场机会。',
'其所需活动阈值只有PE买入60、PE卖出30、PB5买入10；PB5卖出60在这个结构中未被采用，因此稳定性检验不把改变这一无效参数当作额外成功样本。',
'## 三、执行、区间与公平对照',
'固定10万元起始资金，100份整数手，信号次日开盘，单边0.1%滑点、佣金万一且最低5元；无入金、无10%资金限制、空仓现金收益0。全部交易、亏损和空仓计入，期末标记收盘市值、不强制清仓。收益已扣实际费用，不再二次扣除。',
'沿用同一条连续账户状态切片，近1／3／5／10年基准收盘日依次为2025-10-30、2023-10-30、2021-10-29、2016-10-28，均结束于2026-10-30。回溯区间不重启账户，区间最大回撤从基准净值起算，年化按365.25／实际日历天数计算。',
'PE＋PB5从2014-03-31具备有效历史；所有含PB10的组合从2017-01-04才有效，近10年标不足，不用无效期现金凑满。独立A、C原账户自2014年运行，B自2017年运行。为测增量，另把各独立策略从对应组合的**同一有效起点、同一10万元本金**重放：P10、三者组合对照从2017年起，P5对照从2014年起。后文增量表采用这些匹配对照，原独立表现也保留。',
'成交次数是买、卖分别计单，跨区间带入的持仓可只有退出一单；不能除2当作新完整交易。持仓占比按收盘持有份额的交易日比例统计，另存平均资金暴露。',
'来源复用此前冻结OHLC、PE缓存和PB特征文件，未下载新数据。估值历史可能被供应商修订、月度快照不等于真实日度估值全记录、前复权价格与整数份模型不是实际现金分红逐笔账本，仍是可执行性与因果解释限制。',
'## 四、全部固定组合与独立策略：横向表现']
for metric,title in [('annual_pct','年化收益率（%）'),('maxdd_pct','最大回撤（%）'),('orders','实际成交单数'),('holding_time_pct','持仓交易日占比（%）')]:
 z=wide(metric);z.to_csv(P/f'wide_{metric}_LABELED.csv',index=False);body+=['### '+title,table(z,list(z.columns),list(z.columns))]
body+=['所有累计收益、Sharpe（无风险0）、Calmar、佣金和区间交易数也已保存于period_metrics.csv，不因本报告主要展示年化而省略账户数据。',
'## 五、收益优先、回撤其次：近5年完整诊断排序',
table(labeled(it),['strategy','annual_pct','maxdd_pct','orders','increment_vs_PE_pp','increment_vs_best_PB_pp'],['组合','年化%','最大回撤%','成交单数','较同起点PE年化差pp','较同起点最佳PB年化差pp']),
'这是结果诊断排序，不用于事后重新选择训练冠军。近期第一名“PE＋PB5任一买／PE退”近5年较PE增加约8.19个年化百分点，较PB5纯估值增加4.82个百分点；回撤分别减少约1.17与3.81个百分点。交易单数与PE同为21，持仓时间从52.15%增至59.90%，收益差不是简单增加杠杆或免费交易造成，但其中包含更多时段承担股票风险，并非市场中性Alpha测量。',
'次优“PE＋PB5任一买／共同退”近5年年化12.06%、回撤19.68%，近10年年化7.10%、回撤41.75%；它更长时间持有，但风险更高，不优先于较简单的PE退出方案。',
'“任一买／任一退”近5年11.29%、回撤15.86%，也有较好历史表现，但近3年11.38%并未超过独立PE11.48%，近1年为0；不同区间并非全面胜出。',
'## 六、PB10组合为何没有显示真正增量',
'在本样本2017年以来，PB10原始买入为真的138个信号日，PE买入都已经为真；PB10退出为真的106日，PE退出也已为真。因此共同买入实际等于PB10买入，共同确认退出实际等于PB10退出，“共同买／共同退”完全复现独立PB10，而非组合发现新机会。',
'同样，“任一买／PE退”在PE＋PB10中复现PE；“任一买／任一退”也近似同一条路径。三者OR中加入PB10没有明显新信息，少量收益差主要来自起始本金、整数份和费用路径差异，应使用匹配起点对照而不是称为增量。',
table(read('raw_predicate_overlap.csv'),['group','valid_days','PE_entry_days','PB_entry_days','both_entry_days','PB_only_entry_days','PE_exit_days','PB_exit_days','both_exit_days','PB_only_exit_days'],['配对','有效信号日','PE买入日','PB买入日','共同买入日','仅PB买入日','PE退出日','PB退出日','共同退出日','仅PB退出日']),
'这些是条件满足的天数，不是独立买入事件或交易样本数。PB5纯估值在PE没有买入条件时另有312个信号日，但在真实空仓状态下最终只形成下述四段PB单独驱动的提前入场。完整路径等价见equivalent_strategy_paths.csv和common_signal_equivalence.csv。',
'## 七、近年增量来自哪里：四段新增早买全部列出',
table(early,['entry','exit','combination_trade_return_pct','combination_account_return_pct','matched_PE_account_return_pct','matched_PB_account_return_pct','increment_over_PE_pp'],['PB提前买入','PE规则退出','该笔净收益%','组合该段账户收益%','PE同段账户收益%','PB同段账户收益%','较PE增量pp']),
'这张表的账户收益在同一段起止收盘归一，PE或PB独立账户在其中可能稍后才买、也可能持续持有；不是删除未来坏交易的可执行新规则。四段互不重叠，但仍只有四个事件，不足以作稳定预测概率估计。',
'- **2018-05-03至2020-03-17**：组合提前买后整笔−7.69%，同段PE账户+19.58%，提前买相对等待PE亏损约27.25个百分点，是长周期风险恶化的重要来源。\n- **2022-05-06至2023-04-26**：组合账户+12.71%，同段PE−3.88%，提前买增量约16.59个百分点；当时较早进入低位，优于等PE后来的趋势买入。\n- **2024-02-02至2024-06-07**：组合+13.78%，同段PE−3.26%，增量约17.04个百分点；PB捕获趋势确认前的反弹，随后PE退出避免继续全程持有。\n- **2024-08-02至2025-04-07**：组合此前已按PE退出，PB仍便宜时允许再次进入；组合+17.53%，同段PE+11.48%，增量约6.05个百分点。',
'组合并不要求PB低估信号先消失再重新出现；其自己的持仓状态决定是否可以买。因此2024年8月这次是PE退出后的PB重新许可，不是PB独立策略新增的一笔交易。2025年后PB单独策略已空仓，组合又能保留PE的后续趋势机会，这也解释其超过纯PB的总账户收益。',
'### 年度收益：同时展示坏年份',
table(years[years.id.isin(['P5_OR_in_A_out','P5_REF_A','P5_REF_C'])].pivot(index='year',columns='id',values='return_pct').reset_index(),['year','P5_OR_in_A_out','P5_REF_A','P5_REF_C'],['年份','任一买／PE退%','独立PE%','独立PB5%']),
'2018年组合−30.45%，独立PE仅−1.34%；2022年组合+2.05%，PE−12.97%；2024年组合+34.19%，PE+8.23%；2025年组合与PE都约+27.1%，PB单独约+2.05%。近期增益来源清楚，但改善没有覆盖所有历史市场环境。',
'年度表的2014年从有效起点开始、2026年截至10月30日，均是各段累计收益，不是完整年度预测。',
'## 八、训练选择与回顾性样本外：必须分开',
'组合结构训练比较使用2017-01-04至2020-12-31共同起点10万元账户；每套所需估值此时都已有效，阈值固定。仅按训练年化优先、回撤其次、较少组件和固定名称打破平局，先将结构选择写入文件并哈希冻结，再运行留出账户。',
table(labeled(train[train.id.isin(focus)]),['strategy','annual_pct','maxdd_pct','orders'],['结构/独立策略','共同起点训练年化%','训练最大回撤%','成交单数']),
'训练选中的是“PE＋PB10共同买／共同退”，其10.76%年化、1次成交也与PB10单独相同；没有识别出额外组合收益。近期第一名“PE＋PB5任一买／PE退”训练年化0.54%、回撤38.02%，当时不会被收益优先的训练流程选出。',
'PE＋PB5共同买／共同退、三者共同买／共同退在训练段也同为10.76%、只有一次买入，最终按预定组件数和名称打破平局。训练期无法充分区分这些退出规则的效果，确定性选中PB10不代表已经证明它优于其他同分结构。',
'### 2021年以来及非重叠阶段',
table(labeled(m[m.id.isin(focus)&m.period.isin(['holdout','stage2021_22','stage2023_24','stage2025_26'])]),['strategy','period','annual_pct','maxdd_pct','orders','holding_time_pct'],['方案','阶段','年化%','最大回撤%','成交单数','持仓交易日%']),
'holdout基准为2020-12-31收盘，截至2026-10-30，组合任一买／PE退年化11.78%、回撤15.87%，对照PE4.82%／20.09%、PB5 7.37%／19.68%。三个阶段分别为2021—2022、2023—2024、2025—2026年截止日，净值边界连续，无重置。',
'**不能把这叫作训练选择成功。** 输入的三个候选此前已经由多轮同一历史研究提名，新组合也有20种结构比较；即使本轮先冻结训练结构，仍不能消除既有候选和已知行情带来的选择偏差。所有留出段已被看过，只能称为回顾性样本外，重叠的近1／3／5／10年不构成独立验证。',
'近期第一名是留出结果后的研究提名；新前瞻时间段尚不存在于本轮数据。其近3／5年及2021年后确有完整账户历史增量，不等于已经证明未来可重复。',
'## 九、参数稳定性：不重新选中心',
'只扰动每个结构实际使用的阈值：各自±5个百分点单变量变化，并加两组所有活动阈值一起±5。没有扫描全部高维参数组合或挑最好邻点。每个邻点还重算相同扰动参数下的独立策略，对照其最佳者，防止把单指标参数变好误归因于组合结构。',
table(labeled(ns[(ns.period=='trailing5')]),['strategy','scenarios','unique_paths','median_annual_pct','minimum_annual_pct','maximum_annual_pct','worst_maxdd_pct','positive_income_increment_scenarios'],['结构','扰动情景数','不同信号路径数','近5年中位年化%','最低年化%','最高年化%','最差回撤%','优于扰动独立策略情景数']),
'近期第一名有3个活动阈值，8个情景形成8条路径；近5年年化9.90%—13.70%，8／8均超过对应扰动后的最佳独立策略，最差情景回撤17.04%。近3年和2021年以来也都是8／8存在收益增量。它不是一个孤立阈值尖峰，但固定小邻域不能代表全部参数空间，更不能消除2018年那类提前买入风险。',
'共同确认退出的PB5组合近5年扰动范围2.70%—12.28%，最差回撤39.36%，稳定性较弱。PB10共同买／共同退的中心精确复现PB10独立策略，全部扰动均未超过相应扰动下的最佳独立策略，中位增量为0，没有显示新增收益优势。',
'### 成本加倍压力',
table(labeled(read('cost_stress.csv')),['strategy','annual_pct','maxdd_pct','best_single_annual_pct','increment_over_best_pp'],['结构','单边0.2%滑点近5年年化%','回撤%','同成本最佳独立年化%','增量pp']),
'任一买／PE退在加倍滑点后近5年仍为12.99%年化，优于同成本最佳独立8.55%，增量约4.45个百分点。成本没有解释掉近期收益优势。',
'## 十、首选研究候选与部署判断',
'1. **首选新增前瞻研究候选：PE或PB5任一买入、PE退出。** 参数与公式保持本文不变，近期收益优先排序第一，小邻域及成本压力中的增量较连续。\n2. **暂不替换正式策略。** 训练选择没有选中它，近10年回撤38.08%高于独立PE22.68%；提前买入在2018年明显有害，跨周期安全性未解决。\n3. **不把PB10共同确认组合当作新增策略优势。** 它大体是单独PB10的重现，多个等价结构不是多次成功验证。\n4. **下一步若继续，应冻结本次新增候选后使用新数据前瞻验证。** 不再按同一留出段寻找更好的阈值、结构或特殊止损，本轮不修改网站，也不创建实盘或监测任务。',
'“真实增量”的本轮结论是：**近年存在可对账、含成本、不是杠杆或初始资金差异造成的历史增量；仍缺跨周期、真正未见数据上的可重复性证明。**',
'## 交付与复现',
'- `combination_definitions.csv`、`fixed_structures.json`、`protocol.json`：20个固定结构、公式、冲突处理与阈值。\n- `period_metrics.csv`、各`wide_*_LABELED.csv`：近1／3／5／10年、2021年以来及分阶段的完整指标。\n- `increment_over_matched_singles.csv`、`recent5_increment_table.csv`：相同有效起点与成本下，对最佳独立策略的增量。\n- `structure_training.csv`、`training_selected_structure.json`、`recommendation.json`：训练结构冻结及其未通过增量验证的记录。\n- `candidate_diagnostic_gates.csv`：逐结构留出后诊断，明确不冒充新独立选参成功。\n- `campaigns.csv`、`PB_only_early_campaigns.csv`、`calendar_year_returns.csv`：每笔交易、新增早买与全部年度收益。\n- `raw_predicate_overlap.csv`、`entry_exit_overlap.csv`、`equivalent_strategy_paths.csv`、`common_signal_equivalence.csv`：信号互补、入场否决及等价路径。\n- `accounts`、`sensitivity`目录保留连续净值与成交，`sensitivity_metrics.csv`和SUMMARY保留所有扰动数据，`cost_stress.csv`保留费用压力。',
'审计通过：三个独立账户与前轮逐日结果完全复现；所有中心逐笔盈亏对账；中心信号及账户历史截断前缀一致；组合与结构选择文件在留出前冻结且哈希不变；所有原始参数、来源文件和网站文件前后哈希一致。见audit.json。复现`python -B research_csi500_pe_pb_combinations/study.py`，然后`python -B research_csi500_pe_pb_combinations/report.py`。',
'![连续账户近5年与近10年表现](combination_curves.png)',
'![相对扰动独立策略的增量稳定性](increment_sensitivity.png)']
(P/'REPORT.md').write_text('\n\n'.join(body)+'\n',encoding='utf8')
(P/'forward_watchlist.json').write_text(json.dumps(dict(id=WATCH,nomination='Post-holdout research candidate only',parameters=protocol['parameters'],no_deployment=True,requires_new_forward_data=True,formula='Entry: (EA OR EC) AND NOT XA; exit: XA; own persistent position; next-open execution.'),ensure_ascii=False,indent=2),encoding='utf8')
plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
fig,axs=plt.subplots(2,1,figsize=(12,9))
for ax,anchor,identifiers,title in [(axs[0],pd.Timestamp('2021-10-29'),[WATCH,'SINGLE_A','SINGLE_B','SINGLE_C'],'近5年：历史增量明显'),(axs[1],pd.Timestamp('2016-10-28'),[WATCH,'SINGLE_A','SINGLE_C'],'近10年：2018年风险不能忽略')]:
 for identifier in identifiers:
  v=pd.read_csv(P/'accounts'/f'{identifier}_daily.csv.gz',index_col='date',parse_dates=True);z=v.loc[anchor:];ax.plot(z.index,z.equity/v.equity.loc[anchor],label=label(identifier))
 ax.set_title(title);ax.set_ylabel('基准日净值=1');ax.legend(fontsize=9);ax.grid(alpha=.2)
fig.tight_layout();fig.savefig(P/'combination_curves.png',dpi=160);plt.close(fig)
fig,ax=plt.subplots(figsize=(11,4))
show=[WATCH,'P5_OR_in_OR_out','P5_OR_in_AND_out',SELECTED]
for i,identifier in enumerate(show):
 values=nd[(nd.id==identifier)&(nd.period=='trailing5')].increment_over_perturbed_best_pp.to_numpy();ax.scatter(values,np.repeat(i,len(values)),s=30,alpha=.65);ax.scatter([np.median(values)],[i],marker='D',s=60,color='black')
ax.axvline(0,color='gray',ls='--');ax.set_yticks(range(len(show)),[label(i) for i in show]);ax.set_xlabel('近5年年化相对同参数扰动下最佳独立策略的增量（百分点）');ax.set_title('固定小邻域诊断：每点为一个情景，黑菱形为中位数');ax.grid(axis='x',alpha=.2);fig.tight_layout();fig.savefig(P/'increment_sensitivity.png',dpi=160);plt.close(fig)
print(P/'REPORT.md')
