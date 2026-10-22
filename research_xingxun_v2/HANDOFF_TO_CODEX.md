# 星循 → Codex 交接文档

版本：V2.3 结束（2026-10-22）
性质：研究阶段交接；**网站业务代码未按新结论修改**，正式策略配置未切换
读者：接手的 Codex（网站开发、策略整合、后续维护）

> 阅读顺序建议：先看第 1、2 节了解现状，再看第 3 节"不要用的结论"，最后看第 9、10 节决定先做什么。

---

## 1. 项目结构与运行方式

### 1.1 目录

```
d:\file\fun\code\cycle\                     # 站点根目录（Flask）
├─ app.py                                   # Flask 入口，渲染 templates/index.html
├─ main.py / config.py / strategy_config.py  # 旧策略入口与配置
├─ strategies.py / asset_states.py           # 统一策略入口、资产状态
├─ valuation_data.py / data_fetcher.py       # 估值（PE 分位）与行情抓取
├─ indicators.py / industry_strategy.py      # 指标与行业策略
├─ gold_strategy.py / broad_individual_strategy.py / broad_signal_rules.py / us_etf_strategy.py
├─ purchase_monitor.py / dca.py / monitor.py / backtest.py
├─ export_alerts.py                          # 生成 docs/index.html + docs/index.json
├─ correlation_data.py                       # 相关性工具 + V1 组合脚本注入
├─ portfolio_data.py                         # 生成 docs/portfolio_data.json（只读快照）
├─ portfolio_store.js                        # 前端档案/快照/持仓/日记/在途
├─ capital_pool.js                           # 前端资金池与买卖金额（与 Python 同规则）
├─ portfolio_v1.js                           # V1 五张卡片的渲染与交互
├─ templates/index.html                      # 主页面
├─ templates/_invest_tools.html              # 投资配置页（include V1 卡片）
├─ templates/_portfolio_v1.html              # V1 卡片结构与样式
├─ templates/_asset_guide.html / _status_rail.html
├─ docs/index.html / docs/index.json         # 静态发布产物（自动生成，勿手改）
├─ docs/portfolio_data.json                  # V1 只读快照（代码生成）
├─ research_xingxun_v1/                      # 第一至第五轮研究
└─ research_xingxun_v2/                      # 第六轮 + V2.0~V2.3 研究
```

### 1.2 运行

```bash
# 站点（当前工作区能跑通）
python app.py                 # http://127.0.0.1:5000

# 静态导出
python export_alerts.py       # 生成 docs/index.html、docs/index.json

# 刷新 V1 组合快照
python portfolio_data.py      # 生成 docs/portfolio_data.json
```

Windows 环境注意：
- 本机 Python 用绝对路径 `D:\loaddown\python\python.exe` 最稳。
- `run_in_terminal` 可能把 `Set-Location X; cmd` 简化为只跑 `cmd`，需要 `subprocess` 或 `-c "os.chdir(...)"` 指定工作目录。
- PowerShell 重定向默认 GBK/UTF-16，读日志用 `io.open(..., encoding='gbk', errors='replace')`。

### 1.3 测试

| 命令 | 覆盖 |
| --- | --- |
| `python -B -m unittest test_asset_strategies`（站点根目录） | 策略边界、JSON schema、接口、静态导出，11 项 |
| `cd research_xingxun_v1 && python -B -m unittest test_parity_capital_pool` | Python/JS 资金池对齐，10 项 |
| `cd research_xingxun_v1 && python test_capital_pool.py` | 资金池 9 项（自带 runner） |
| `cd research_xingxun_v1 && python test_capital_pool_acceptance.py` | 验收 12 项 |
| `cd research_xingxun_v1 && python test_signal_journal.py` | 信号快照 3 项 |

最近一次运行：11 项通过（2026-10-22）。

---

## 2. 研究结论（只保留最终有效部分）

### 2.1 各轮结论摘要

| 轮次 | 文件 | 仍然有效的结论 |
| --- | --- | --- |
| 第一轮 | `research_xingxun_v1/REPORT_01_AUDIT.md`、`REPORT_01_DATA_CORRELATION.md` | 旧 `dca.py` 存在同日收盘价偏误，已用 t+1 未知价引擎替代；真实费率与 T+2 必须建模；相关性结构（黄金-美股≈0、A股-债负相关） |
| 第二轮 | `REPORT_02_STRATEGY_BACKTEST.md` | 多数择时（均线/回撤/唐奇安）样本外跑输持有；持有是合理基准 |
| 第三轮 | `REPORT_03_WALKFORWARD_CAPITAL.md` | 2 年训练/1 年测试下择时不稳定；资金池/最小 10 元/在途资金规则可用 |
| 第四轮 | `REPORT_04_FINAL_RESEARCH.md` | 当时四资产下"逆波动（债券上限 40%）"优于固定权重；完整 ERC 不采用 |
| 第五轮 | `REPORT_05_WEB_V1.md` | 网站 V1 五卡片（总资产/资金池/持仓/今日操作/复盘）已实现并通过浏览器测试；限购跳过、在途、7 天规则可用 |
| 第六轮 | `research_xingxun_v1/REPORT_06_ASSET_SELECTION.md` | 四类资产分散真实；A 股（500/1000/科创）在 2017–2026 是拖累；纯逆波动/ERC 全类别会把 90%+ 配给债券，失效 |
| V2.0 | `REPORT_V2_PORTFOLIO.md` | 四只基金 A/B/C 三候选；B（债/金/纳）均衡；限购代价可量化；择时/动量/搜索选权重失败 |
| V2.1 | `REPORT_V21_ENTRY.md` | 76 个起点、3000 次回测：一次性建仓在多数起点收益更高；分批只在"买入后下跌"的起点占优；5 年后差异消失 |
| V2.2 | `REPORT_V22_EXECUTION.md` | 执行约束与建仓金额可落地；K4 为当时限购临时方案（**已被 V2.3 推翻**）；切换成本 1.3–1.6 元；网站缺状态机/动态权重/账户分离 |
| V2.3 | `REPORT_V23_OPEN_POOL.md` | 开放池后 K4 被"债+金"支配；中证500 不默认；三档候选 A/B/C；限购替代 L1/L2 |

### 2.2 最终候选（尚未实盘验证、尚未接入网站）

**正常申购时（161130 可买）**

| 方案 | 配置 | 主样本 2021-11~2026-10 | 长样本 2017-07~2024-12 | 样本外 2023-01~2026-07 | 2000 元 |
| --- | --- | --- | --- | --- | --- |
| A 收益优先 | 债 1/3、金 1/3、纳 1/3 | 11.11% / −7.03% | 11.60% / −7.72% | 20.21% / −2.85% | 666.66 / 666.67 / 666.67 |
| B 均衡 | 债 40%、金 30%、纳 30% | 10.37% / −6.20% | 10.85% / −6.82% | 18.52% / −2.57% | 800 / 600 / 600 |
| C 低回撤 | 债 60%、金 20%、纳 20% | 8.17% / −3.68% | 8.60% / −4.10% | 13.57% / −1.74% | 1200 / 400 / 400 |

**纳指受限时（161130 暂停/限额）**

| 方案 | 配置 | 主样本 | 长样本 | 样本外 | 2000 元 |
| --- | --- | --- | --- | --- | --- |
| L1 债+金 | 50/50 | 9.83% / −2.15% | 7.43% / −8.07% | 12.36% / −1.80% | 1000 / 1000 |
| L2 债/金/红利 | 各 1/3 | 8.76% / −2.66% | 7.69% / −5.29% | 11.29% / −1.87% | 666.66 / 666.67 / 666.67 |

> 以上均为**月度再平衡合成**结果（MDD 按月度净值计算），未用 OTC 引擎逐笔复核；费用仅按费率估算。V2.0 用引擎得到的 B（1/3 各）为 10.72% / −10.92%（日度 MDD），与上表不可直接比较，见第 7 节。

### 2.3 原始四只基金去留

| 基金 | 结论 |
| --- | --- |
| 000015 华夏纯债A | 保留（降波动核心；申购费 0.08%） |
| 008701 华夏黄金ETF联接A | 保留（与股票低相关；申购费 0.06%） |
| 161130 易方达纳指A | 保留（长样本/样本外收益来源；**当前暂停申购**） |
| 001214 华泰柏瑞中证500 | **不默认配置**，仅机会观察（短/长样本均拖累） |

---

## 3. 已被推翻 / 不要用的结论（重点）

| 旧结论 | 出处 | 为什么不能用 |
| --- | --- | --- |
| **K4（债/金/500 逆波动）作为限购默认方案** | V2.2 | 未与"债+金"比较；补测后被支配（短样本 5.39% vs 债+金 9.83%，回撤相近） |
| 含中证500 的默认配置（四只等权、债/金/500、四资产逆波动） | V1 第五/六轮、V2.0 | 中证500 在 2017–2026 短长样本均拖累；不为了凑类别而保留 |
| 全类别逆波动 / ERC | 第六轮、V2.3 | 债券被顶到 60%–90%，组合退化为"债券+现金"；不是收益方案 |
| 200 日均线择时、动量 top1/top2 | 第二/六轮、V2.0 | 样本外跑输持有；动量 top1 费用 142 元（本金 7.1%） |
| 滚动搜索选权重（每年重选） | V2.0 | 样本外 12.12%，被简单等权 15.90% 支配 |
| 分批 6/12 个月、8% 回调作为默认 | V2.1 | 多数起点收益更低；1 年期分 12 月收益 −6.3pp 换回撤 −2.3pp；5 年无差异 |
| 季度再平衡、5% 阈值带 | V2.0 | 月度 2% 带更优（9.93% vs 9.56%/9.86%） |
| 产品替换（广发纳指/南方500/华安黄金/中短债/1-3国开） | V2.0 | 差异在误差内，无实质改善 |
| "限购时留现金"是最优解 | V2.2 | 留现金损失 3.8–5.1pp/年；替代方案（债+金）更好，但需用户确认 |
| "风险平价"命名 | V1 早期 | 实为逆波动，已在 `REPORT_04` 更正 |

---

## 4. 中证500 / 沪深300 的定位

- 两者及中证1000、科创50、创业板、红利**仅作为机会观察池**，不是必须长期持有的资产。
- 现有网站的估值监测（PE 分位、资产状态、今日提醒）**继续保留**，用于观察，不自动生成组合买入。
- 若未来要重新纳入，必须重新做组合级边际贡献检验（本轮已证明当前纳入是拖累）。
- 红利（090010）只在"纳指限购"的 L2 方案中作为候选；不是常规必配。

---

## 5. 资金与执行规则（已确定）

| 规则 | 内容 |
| --- | --- |
| 总金融资产 | 约 20,000 元（按此计算），每月 1 日更新；未更新沿用上次并显示日期 |
| 投资预算 | 总资产 × 10% = 2,000 元 |
| 资金池超额 | 总资产下降导致池子超过 10% → 暂停新增，不强制卖出 |
| 池内调仓 | 允许；不算新增投入 |
| 杠杆/做空 | 禁止 |
| 下单 | 全部手动（支付宝/微信），不自动下单 |
| 最低持有 | 7 天；<7 天赎回 1.5% 真实扣除 |
| 确认/到账 | 场外 T+1/T+2；QDII T+2；卖出款到账前不能复用 |
| 历史持仓 | **不参与新策略**（网站尚未实现账户分离，见第 9 节） |
| 新策略起点 | 空仓，2,000 元 |

规则细节与金额计算在：
- `research_xingxun_v1/capital_pool.py`（Python 参考实现）
- `capital_pool.js`（前端同规则）
- `test_parity_capital_pool.py`（两端对齐测试，10 项）

---

## 6. 现有网站集成情况

**已开发并测试通过（第五轮）**

| 功能 | 文件 | 状态 |
| --- | --- | --- |
| 总资产快照（每月确认） | `portfolio_store.js` / `portfolio_v1.js` | 可用 |
| 10% 资金池 + 超额提示 | `capital_pool.js` / 池子卡片 | 可用 |
| 当前持仓（手动基线 + 日记同步） | `portfolio_store.js` | 可用 |
| 今日操作（金额/费用/原因） | `capital_pool.js` / 操作卡片 | 可用 |
| 限购/暂停跳过买入 | `capital_pool.js` | 可用（不生成买入，不提示切换） |
| 在途资金 + 手动到账 | `portfolio_store.js` | 可用 |
| 投资日记 + 成交记录 | 现有日记模块 | 可用 |
| 月度复盘（月初/月末/净流入/盈亏/笔数） | `portfolio_v1.js` | 可用（缺最大回撤/手续费/基准） |
| 功能开关 | `window.XINGXUN_V1` / `feature_flag` | 可用 |

**当前线上配置**

- `docs/portfolio_data.json` 的 `allocation.id = invvol4_cap40_v1`，资产为 000216 黄金、160706 沪深300、090010 红利、006484 1-3国开。
- **这不是最终候选**，与 V2.3 的 A/B/C/L1/L2 都不同；接入前必须替换。
- `docs/index.html` 由 `export_alerts.py` 生成；脚本已支持展开 `{% include %}`（第五轮修复）。

**未开发**

1. 新资产清单与配置（A/B/C/L1/L2）；
2. K4/L1 需要的动态逆波动权重（当前只有固定权重快照）；
3. 交易状态机：模拟信号 → 待执行 → 已提交 → 已确认/失败（现在只有买入/卖出日记）；
4. 新旧账户分离（历史持仓不进新策略）；
5. 月度复盘扩展（最大回撤、手续费合计、策略模拟、基准）；
6. 每月 1 日更新提醒；
7. 限购切换指引（K4/L1 → A/B/C）；
8. 份额确认（预计份额不能提前记成持仓，当前设计正确但需引导）。

**仅研究、未实现**

- 候选策略模拟账户；
- 版本切换 UI（正式/候选/归档）；
- 自动对账（日记 vs 基金确认份额）。

---

## 7. 风险、数据限制与需要重新验证的结论

### 7.1 数据与回测限制

- 主样本 2021-11~2026-10（4.9 年），长样本 2017-07~2024-12（7.5 年）；均含黄金与美股大牛市，收益不可外推。
- QDII 净值缺失日用前值填充（≤10 天），会**低估波动**（收益记 0），影响逆波动权重。
- 赎回统一按 T+2 处理（A 股基金实际 T+1~T+3），偏保守。
- 费率取天天基金页面折后价；**支付宝/微信渠道费率与限购未核实**。
- 161130 历史限购状态无法还原；限购情景是结构假设，不是历史回测。
- V2.0 的 A/B/C 与 V2.2 的 K4/切换模拟用 `engine_v2.py` 逐笔回测（日度 MDD）；**V2.3 的 A/B/C/L1/L2 用月度再平衡合成（月度 MDD），两者不可直接比较**，接入前需用引擎重跑。

### 7.2 需要重新验证的结论

1. **V2.3 的 A/B/C 与 L1/L2 用 `engine_v2.py` 逐笔回测**（T+1、T+2、7 天、费用、2% 带），确认合成结果不因口径差异（月度 vs 日度 MDD）反转。
2. **一次性建仓结论**在加入 6 只以上资产、限购切换后的稳定性。
3. **L2 的红利腿**（090010）与 500 的相关性、费率、限购状态再核实。
4. **A/B/C 三档的回撤上限**是否与用户真实风险承受度一致（目前无硬上限）。
5. **切换成本**：L1/L2 → A/B/C 的实际赎回费与到账时间（V2.2 只估了 K4→B）。
6. **支付宝/微信**四只基金的实际可买性、限额、折扣费率。

### 7.3 未解决问题

- 161130 可能长期暂停；期间只能跑 L1/L2，收益低于 A/B/C。
- 网站无状态机，无法区分"建议/已提交/已确认"，容易把建议当持仓。
- 新旧账户未分离，历史持仓可能污染复盘。
- 月度复盘没有最大回撤与基准，无法验证策略是否按预期运行。

---

## 8. 关键文件与复现

### 8.1 研究脚本（`research_xingxun_v2/`）

| 脚本 | 作用 |
| --- | --- |
| `fetch_v2.py` / `clean_v2.py` | 抓取四只基金原始快照 + 清洗（总收益、费率、状态） |
| `fetch_v22.py` | 抓取最新交易条件 → `trade_conditions_2026-10-22.json` |
| `fetch_v23.py` | 抓取创业板 110026 等 |
| `engine_v2.py` | 组合引擎（限购阻断、折起点建仓、T+2） |
| `entry_engine.py` | V2.1 建仓引擎（一次性/固定等额/回调） |
| `run_v2.py` | V2.0 策略家族全样本 |
| `oos_v2.py` | V2.0 滚动 2 年训练/1 年测试 |
| `extra_v2.py` / `extra2_v2.py` / `extra3_v2.py` | 候选 OOS、限购替代、资金规模、三只组合 |
| `run_v21.py` / `analyze_v21.py` | V2.1 多起点（3000 次）与统计 |
| `v22_exec.py` | 建仓表、切换模拟、限购节奏 |
| `run_v23.py` / `v23_extra.py` | V2.3 开放池组合比较、权重披露、限购替代 |

复现命令：

```bash
cd research_xingxun_v2
python fetch_v2.py && python clean_v2.py
python run_v2.py
python oos_v2.py
python run_v21.py && python analyze_v21.py
python fetch_v22.py && python v22_exec.py
python fetch_v23.py && python run_v23.py && python v23_extra.py
```

### 8.2 报告

- `research_xingxun_v1/REPORT_01_AUDIT.md`
- `research_xingxun_v1/REPORT_01_DATA_CORRELATION.md`
- `research_xingxun_v1/REPORT_02_STRATEGY_BACKTEST.md`
- `research_xingxun_v1/REPORT_03_WALKFORWARD_CAPITAL.md`
- `research_xingxun_v1/REPORT_04_FINAL_RESEARCH.md`
- `research_xingxun_v1/REPORT_04_INTEGRATION_PLAN.md`
- `research_xingxun_v1/REPORT_05_WEB_V1.md`
- `research_xingxun_v1/REPORT_06_ASSET_SELECTION.md`
- `research_xingxun_v2/REPORT_V2_PORTFOLIO.md`
- `research_xingxun_v2/REPORT_V21_ENTRY.md`
- `research_xingxun_v2/REPORT_V22_EXECUTION.md`
- `research_xingxun_v2/REPORT_V23_OPEN_POOL.md`

### 8.3 数据与产物

- `research_xingxun_v2/clean_v2/panel_v2.csv`（四只 + 现金，2020-07 起）
- `research_xingxun_v1/clean/tr_panel.csv`（扩展资产池）
- `research_xingxun_v2/clean_v23/110026.csv`（创业板）
- `research_xingxun_v2/out_v2/summary_full.csv`、`oos_summary.csv`、`candidates_full_oos.csv`
- `research_xingxun_v2/out_v21/v21_grid.csv`（3000 行）
- `research_xingxun_v2/out_v22/k4_entry_2000.csv`、`b_entry_2000.csv`、`switch_k4_to_b.csv`
- `research_xingxun_v2/out_v23/v23_compare.csv`、`v23_long.csv`
- `research_xingxun_v1/strategy_registry.json`（v2/v21/v22/v23 登记，均 `pending_review`）

---

## 9. 已开发 / 未开发 / 仅计划

| 类别 | 内容 |
| --- | --- |
| **已开发** | V1 五卡片、资金池与金额（Python+JS 双端）、日记、在途、限购跳过、静态导出、旧策略提醒与估值监测、测试套件 |
| **未开发（接入必需）** | 新配置（A/B/C/L1/L2）、动态权重、状态机、账户分离、复盘扩展、月度提醒、切换指引 |
| **仅研究计划** | 模拟账户、版本切换 UI、自动对账、限购日常监控、候选策略自动评估 |

**下一步不要做**：直接把 `docs/portfolio_data.json` 改成 A/B/C 就上线；没有状态机与账户分离时，用户会把建议当成持仓。

---

## 10. 建议开发顺序

1. **数据层**：`portfolio_data.py` 支持配置注册表（A/B/C/L1/L2），输出资产、权重、状态、限额、费率、净值日期；保留旧 `invvol4_cap40_v1` 作历史版本。
2. **账户层**：新旧账户分离；交易状态机（signal/pending/submitted/confirmed/failed）；份额确认前不计入持仓。
3. **计算层**：用 `capital_pool.py` 为新配置生成金额，并跑 `test_parity_capital_pool.py` 对齐；对 A/B/C/L1/L2 用 `engine_v2.py` 重跑（第 7.2 节）。
4. **复盘层**：补最大回撤（日度净值）、手续费合计、策略模拟、基准对比。
5. **提醒与切换**：每月 1 日总资产提醒；纳指限购状态变化提示；L1/L2 → A/B/C 切换检查清单。
6. **模拟账户与版本管理**：候选策略先模拟 6–12 个月，记录信号与结果，不覆盖历史。
7. **回归与文档**：每次接入跑 `test_asset_strategies` + 资金池测试；更新本文件。

### 验收标准（建议）

- 任意配置下，网站给出"买什么/买多少/为什么/何时再检查"。
- 限购/暂停时明确显示"不可买 + 替代方案 + 待确认渠道"。
- 建议、已提交、已确认三种状态可区分；预计份额不进入持仓。
- 月度复盘能把资金流入与投资收益分开，并给出最大回撤与基准差。
- 新旧账户互不污染。

---

## 11. 交接边界

- 本轮未修改任何网站业务代码、未改正式策略配置、未执行 Git 操作、未删除文件。
- 所有研究结论均为"候选/待验证"，**不得标记为正式实盘策略**。
- 初始四只基金只是偏好；替换与删除必须有组合级证据。
- 投资预算 10% / 2000 元是当前模拟口径，总资产变化时由用户确认后更新。
- 历史持仓不参与新策略资金池；统计总资产时要避免重复计算。

---

## 12. 快速索引：Codex 最先要看的 6 个文件

1. `research_xingxun_v2/REPORT_V23_OPEN_POOL.md` — 最新结论与限购替代
2. `research_xingxun_v1/strategy_registry.json` — 版本与状态
3. `capital_pool.js` + `research_xingxun_v1/capital_pool.py` — 金额规则
4. `portfolio_data.py` — 快照生成入口
5. `portfolio_v1.js` + `templates/_portfolio_v1.html` — 现有 UI 与缺口
6. `research_xingxun_v2/REPORT_V22_EXECUTION.md` — 执行约束与网站缺口
