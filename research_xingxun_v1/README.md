# research_xingxun_v1 — 星循个人量化投资决策系统（研究目录）

> **独立研究目录。不修改网站业务代码，不连接真实交易。**
> 第一轮：现有系统审计 + 真实数据采集 + 数据质量验证 + 资产相关性研究。

---

## 目录结构

```
research_xingxun_v1/
├── fetch_data.py              抓取 7 只基金净值快照（原样落盘 + sha256）
├── fetch_extra.py             抓取 7-10 年国开债 + 三大指数月度 PE
├── data_prep.py               清洗、分红调整、总收益指数、质量报告
├── correlation_study.py       相关性/滚动/下跌期/错位/边际贡献
├── cost_model.py              真实费率 → 单笔成本与年化拖累
├── otc_engine.py              场外基金回测引擎（t 收盘信号 → t+1 净值成交、T+2 到账）
├── strategy_lib.py            第二轮策略库（A–F）
├── run_round2.py              策略网格、组合回测、敏感性分析
├── summarize_round2.py        汇总成报告用 Markdown 表
├── plot_round2.py             组合净值/回撤图与月度盈亏
├── walk_forward.py            滚动样本外验证（2年训练/1年测试）
├── param_surface.py           C/B 类参数曲面
├── cash_study.py              空仓资金工具对比
├── capital_pool.py            统一资金池与买卖金额计算（纯函数）
├── test_capital_pool.py       资金校验测试（9 项）
├── demo_plan.py               今日计划演示
├── strategy_registry.json     策略版本与状态登记
├── weight_engine.py           带再平衡的组合引擎
├── allocation_study.py        配置方案比较与稳定性
├── signal_journal.py          信号冻结（只增不改）
├── test_capital_pool.py       资金校验测试（9 项）
├── test_capital_pool_acceptance.py 验收测试（12 项）
├── test_signal_journal.py     信号版本测试（3 项）
├── CHANGELOG.md               变更记录
├── RESEARCH_BACKLOG.md        保留的后续研究方向
├── engine.py                  （早期草稿：场外账户引擎原型，含 lag/settlement 建模，第二轮重写）
├── fetch_status.py            （早期草稿：历史净值接口探测，当前未使用）
├── raw/                       原始快照（JS / HTML / CSV），只增不改
├── clean/                     清洗结果（可直接用于回测）
├── out_corr/                  相关性矩阵、图表、成本影响
├── out_bt/                    第二轮回测：网格、组合、交易、净值曲线
├── out_wf/                    第三轮：walk-forward、参数曲面、现金对比、资金计划
├── out_alloc/                 第四轮：配置比较、稳定性、权重序列
├── signals/                   信号快照（按日期冻结，只增不改）
├── data_quality.md            数据质量报告
├── REPORT_01_AUDIT.md         现有系统代码审计
├── REPORT_01_DATA_CORRELATION.md  数据与相关性研究报告
├── REPORT_02_STRATEGY_BACKTEST.md 策略与组合回测报告
├── REPORT_03_WALKFORWARD_CAPITAL.md 滚动验证与资金管理报告
├── REPORT_04_FINAL_RESEARCH.md   完整研究报告（汇总 + 回答 10 个验收问题）
└── REPORT_04_INTEGRATION_PLAN.md 网站最小改造方案
```

---

## 复现步骤

```powershell
cd research_xingxun_v1
python fetch_data.py          # 已存在 raw/ 时不会重复下载
python fetch_extra.py
python data_prep.py           # -> clean/, data_quality.md
python correlation_study.py   # -> out_corr/, 控制台日志
python cost_model.py          # -> clean/fee_table.csv, out_corr/cost_*.csv
python run_round2.py          # -> out_bt/grid_*.csv, portfolio*.csv, trades_*.csv
python summarize_round2.py    # -> out_bt/summary_tables.md
python plot_round2.py         # -> out_bt/equity_curves.png, drawdown.png, monthly_pnl_2000.csv
python walk_forward.py        # -> out_wf/walkforward_*.csv
python param_surface.py       # -> out_wf/param_surface*.csv, surface_*.png
python cash_study.py          # -> out_wf/cash_compare.csv, cash_scenarios.csv
python test_capital_pool.py   # 资金校验测试
python demo_plan.py           # -> out_wf/plan_demo.txt, signals_latest.csv
python allocation_study.py    # -> out_alloc/allocation_compare.csv, stability_*.csv
python test_capital_pool_acceptance.py
python test_signal_journal.py
```

依赖：`pandas numpy matplotlib requests beautifulsoup4 akshare`。

---

## 数据口径（必须记住）

| 项 | 口径 |
|---|---|
| 收益 | 单位净值 + 除息日现金分红再投资：`ret_t=(NAV_t+div_t)/NAV_{t-1}-1` |
| 复权 | 不使用"累计净值"直接当收益；不使用 ETF 前复权价格 |
| 缺失 | 不插值、不前向填充；只做日期交集 |
| 相关性 | 共同日期的日收益 Pearson；周频 W-FRI、月频 ME |
| 净值日期 | 是"净值日"，不是下单日；场外 T 日 15:00 前下单按**未知** T 日净值确认 |
| 到账 | 赎回 T+1 确认，资金 T+1~T+7；组合回测必须建"在途资金"账户 |

---

## clean/ 文件说明

| 文件 | 内容 |
|---|---|
| `{code}.csv` | 单基金：date, nav, acc_nav, div, ret, tr（货币基金为 income/ret/tr） |
| `nav_panel.csv` / `tr_panel.csv` | 宽表（未对齐日历，使用方自行取交集） |
| `fund_meta.csv` | 名称/类型/成立日/规模/经理/管理费/托管费/申购状态/限额/费率阶梯 |
| `fee_table.csv` | 各持有期的申购+赎回往返费率 |
| `dividends.csv` | 分红事件（权益登记日、除息日、每份金额、发放日） |
| `quality_summary.csv` | 样本数、重复、缺失、异常波动 |
| `calendar_coverage.csv` | 相对沪深300联接净值日的缺失统计 |
| `trading_calendar_proxy.csv` | 交易日代理（160706 的净值日期） |

## out_corr/ 文件说明

| 文件 | 内容 |
|---|---|
| `corr_{daily,weekly,monthly}_{long,full}.csv` | 收益相关矩阵 |
| `heatmap_daily_*.png` / `heatmap_monthly_*.png` | 热力图（英文标签，避免字体缺失） |
| `rolling_corr_*.png` / `.csv` | 60/120/250 日滚动相关 |
| `rolling_stability_*.csv` | 滚动相关的分布与稳定性 |
| `crisis_episodes_*.csv` | 沪深300 峰→谷下跌段内各资产表现与相关性 |
| `worst_days_*.csv` | 沪深300 最差 5% 交易日的各资产表现 |
| `signal_overlap_*.csv` | 同时持仓/空仓/仅一方/同时买卖比例 |
| `strategy_ret_corr_*.csv` | 策略净收益相关 |
| `marginal_contribution_*.csv` | 留一法边际贡献 + 等权买入持有 |
| `asset_stats_*.csv` | 单资产年化/回撤/Sharpe |
| `cost_impact.csv` / `cost_frequency.csv` | 成本金额与频率敏感性 |
| `run_log.txt` | 最近一次完整运行日志 |

---

## 第一轮的关键负面结论（不要跳过）

1. 基线 120 日均线择时在 2013+ 与 2019+ 两个面板都**跑输等权买入持有**。
2. 黄金与 A 股长期接近零相关，但 250 日相关当前 0.41，接近历史最高 0.46，分散性在减弱。
3. 三只债券基金彼此相关 0.64–0.90，同时持有等于重复买同一风险。
4. 红利在 2015 与"最差 5% 日"里没有防御性，不能用它替代债券。
5. 现有网站回测把申购费按 0.01%、赎回费按 0 计算，低估 4–15 倍，且同日收盘成交。

---

## 第四轮的关键结论

1. 配置比较：逆波动率四资产（债券≤40%）全样本 7.79%/−6.83%/Sharpe 0.846，样本外 10.86%/−5.81%/1.208；30/35/15/20 收益更高（13.12%）但回撤 −12.66%。
2. 推荐默认：逆波动率（120 日，债券上限 40%，月度再平衡）——用约 2pct 年化换一半回撤。完整协方差 ERC 已对照，改善有限且样本外回撤更大，不采用。
3. 资金池验收：21 项测试全过（10% 池、超池暂停、T+2、限额、暂停申购、7 天罚息、幂等）。
4. 版本管理：`strategy_registry.json` + `signals/` 日期冻结 + `CHANGELOG.md`；同日不同内容拒绝覆盖。
5. 待用户确认后进入第五轮，按 `REPORT_04_INTEGRATION_PLAN.md` 分 5a–5d 实施。

---

## 下一步（第五轮，需确认）

- 5a 只读：总资产快照 + 资金池
- 5b 今日操作（与 Python 金额一致性测试）
- 5c 成交确认 + 月度复盘
- 5d 默认开启 + 手机端回归
