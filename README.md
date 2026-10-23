# 星循投资决策网站

星循包含今日提醒、投资配置、投资复盘、策略实验四页。**唯一正式静态入口是 `docs/index.html`**，由 `export_alerts.py` 生成，不手工复制预览页覆盖。

当前没有启用正式投资组合策略。A/B/C/D/E/F、L1/L2/L3/L4均为研究或模拟，未经过实盘验证；渠道开放不等于投资买点。既有ETF提醒与新组合账户相互独立，历史持仓不参与新账户调仓。

## 入口和日常使用

- 正式本地页面：`docs/index.html`。直接打开可查看；PWA需要HTTP本机地址或HTTPS。
- 静态本地服务：项目根目录运行 `python -B -m http.server 8000 --bind 127.0.0.1 --directory docs`，访问 `http://127.0.0.1:8000/index.html`。这不会发布到互联网。
- Flask开发入口：`python -B app.py`，访问 `http://127.0.0.1:5000`，源模板为 `templates/index.html`。
- `workspace_ui_20261022/static_preview.html`及Flask预览仅为测试产物，不是正式入口。保留原路径以免打断旧浏览器存储使用；新改动只在正式导出后生效。
- 首次投资账户空仓、默认预算2000元；实际现金、份额、在途款由账本确认事件计算。研究权重参考不代表已启用真实建议。

## 账本备份与恢复

在“投资复盘”导出JSON，文件包括账户上下文、资产快照和完整交易事件。恢复前先保留原备份，在相同账户类型的空账户中导入；恢复会校验结构、交易和重算结果，不会合并覆盖已有非空账本。

账本仅在当前浏览器存储，不在Git仓库或研究文件中。切换浏览器、设备、端口或访问地址前，先从原地址导出JSON；新地址不会自动获得旧账户。不要清除浏览器数据后才寻找备份。浏览器测试使用独立合成账户，不访问个人账本。

## 核心目录和文件

| 路径 | 用途 |
| --- | --- |
| `docs/` | 唯一正式静态站点、PWA脚本/图标、公开渠道快照；`portfolio_data.json`仍用于历史兼容测试，保留 |
| `templates/` | 当前Flask模板、投资工作区和共用状态展示 |
| `app.py`、`export_alerts.py`、`correlation_data.py` | 本地接口、正式导出、公开版本数据与当前JS装配 |
| `config.py`、`strategies.py`、`asset_states.py`、`strategy_config.py` | 现行ETF观察配置与信号解释；没有个股配置 |
| `alerts.py`、`broad_individual_strategy.py`、`broad_signal_rules.py`、`us_etf_strategy.py`、`us_guidance.py`、`gold_strategy.py`、`industry_strategy.py` | ETF提醒共用计算，名称中的individual表示单只ETF，并非个股 |
| `portfolio_store.js`、`capital_pool.js`、`portfolio_valuation.js` | 交易账本、资金池、账户估值；保留已验证核心逻辑 |
| `investment_planner.js`、`investment_workspace.js`、`purchase_monitor.js` | 模拟计划、配置/复盘/实验交互、渠道监测 |
| `data_cache/`、`valuation_data.py`、`data_fetcher.py` | ETF行情和估值缓存、获取逻辑；原始历史输入不要随意删除 |
| `workspace_data/` | 版本化公开研究JSON及`manifest.json`；当前版本由manifest指定，测试引用的旧版本保留原路径 |
| `research_def_20261022/` | 当前十组组合、多个区间的统一日度重验与结果、输入哈希、分红修正证据 |
| `research_l34_20261022/`、`correctness_20261022/` | L3/L4及账本/日度因果修复的研究证据，包含仍被测试引用的数据 |
| `research_xingxun_v1/`、`research_xingxun_v2/` | 原始数据、费率元数据、清洗面板和仍被当前研究导入的引擎；旧名称不等于失效 |
| 根目录`research_*.py`、`test_*.py` | ETF研究及回归测试。脚本相互导入，保留稳定路径；不属于正式页面装配 |
| `audit_codex_20261022/` | 审计报告、保护输入哈希及研究结论限制 |
| `archive/` | 旧报告、旧UI、个股专用历史文件及历史结果压缩包；不装配到正式页面 |
| `maintenance/20261022/` | 清理前清单、逐项动作/SHA256、测试日志、验收报告；一次性整理脚本不可重复运行 |
| `workspace_ui_20261022/` | 预览生成器、桌面/375px浏览器测试、合成备份及截图，均为开发验收材料 |
| `results/` | ETF临时回测输出。归档的历史输出可按原路径恢复，重跑研究可能再次生成 |

## 安装和数据更新

Python依赖：`python -m pip install -r requirements.txt`。测试另需Node；浏览器验收需Playwright和Chrome，当前脚本使用本机已安装路径，换机器需调整该路径。

```powershell
# 安全的本地缓存构建：不联网，不提交或发布
python -B export_alerts.py --offline
# 正常刷新公开行情、估值与渠道数据后生成本地静态页：会联网，不会提交或发布
python -B export_alerts.py
# 仅构建开发验收预览
python -B workspace_ui_20261022/build_previews.py
```

缓存构建明确显示缓存截至日期，渠道和净值快照保留其原始日期，不把生成时间当作数据更新时间。

`update_alerts.ps1`、`update_alerts.bat`和`refresh_local_startup.vbs`属于原自动提交/推送链路，**不是本地构建命令**。本轮不运行；保留原入口避免破坏已有启动依赖。ETF提醒计算和该自动化脚本未重写。

## 测试

```powershell
# 统一入口：全部根目录Python测试、V1函数/脚本测试、全部根目录Node测试、保护输入检查
python -B run_tests.py
# 同一入口追加当前五组UI验收（1440/375/320px）、JSON恢复及PWA真实离线测试
python -B run_tests.py --browser
# 指定单个组；例如接口快速检查可直接运行unittest
python -B -m unittest test_decide_api test_stock_watch -v
```

统一入口遇到失败立即返回非零并停止，逐组日志写入`maintenance/20261022/test_results/`。测试临时目录限制在项目内；浏览器只使用隔离的合成账户。PWA测试只启动回环地址服务器，受限环境可能需要允许Chrome访问本机。

旧`workspace_ui_20261022/run_checks.py`及`correctness_20261022/run_validation.py`保留调用路径，统一转调`run_tests.py`，原版本留在`archive/legacy_checks/`。

## 研究复现与版本

- 当前组合参数和状态从`workspace_data/manifest.json`所指JSON读取；不手工填写收益。正式组合策略仍未启用，十组均为候选。
- A/B/C及D/E/F归正常申购情景；D/E/F分别只将A/B/C纳指替换为标普。L1–L4为纳指受限情景，不能跨情景直接排名。
- 当前统一日度重验：`python -B research_def_20261022/reaccept.py`，写其本目录`results/`；实际基金与指数代理区间分开标识。运行前保留已有结果，核对源码/输入哈希，不将历史重跑当作新的样本外验证。
- 公开版本打包：`python -B build_workspace_data.py`。同版本内容不同会拒绝覆盖；只有审阅研究变更后才打包，再运行导出。打包不启用实盘策略。
- 被推翻的月度合成、选参泄漏等结论保存在版本数据的淘汰说明及审计报告中，不列为推荐。旧V1注册表保留作历史证据，不代表当前十组的启用配置。
- ETF历史报告已移入`archive/reports/etf_studies/`；对应`research_*.py`仍在项目根目录。旧研究脚本可能按原位置重新生成报告与`results/`，应在复现副本操作，避免混入日常运行。
- V1/V2原始数据、元数据、`clean_backup_r5`及仍被引用的输出保留；不对研究数据作哈希批量去重。旧输出可能是历史分析输入，不能按名字删除。

归档索引和恢复：

```powershell
python -B maintenance/archive_catalog.py
# 先创建项目内独立恢复目录（例如maintenance/restored），再按原相对路径恢复
python -B maintenance/archive_catalog.py --restore results --destination maintenance/restored
```

工具核对归档成员SHA256，恢复到指定目录下的原相对路径，拒绝覆盖内容不同的现有文件。`maintenance/20261022/actions.json`记录原路径和归档去向。压缩归档保留完整文件，`source_before_cleanup.zip`为整理前源码快照；不要直接覆盖当前项目。历史报告中的相对路径以原项目根目录为基准，在恢复副本中使用。

## 自选买入与每日盈亏（2026-10-22更新）

投资配置中的方案仅作研究参考。“我的买入决定”可以选择基金、自定金额，例如L1下黄金先买500元：先等待会保存计划、不冻结资金；已在渠道买入才记为待确认，实际确认份额另补。无需一次买齐目标配置。低频更正/撤销/资金流放在“记录管理”弹窗，复盘不再放这些表单。

复盘展示当日估值盈亏、累计盈亏、持仓、日月明细和曲线。账户净值与策略历史数据隔离：`account_nav.py`获取公开实际基金净值，写`docs/account_nav.json`；不会覆盖`workspace_data`或研究CSV。更新错误、未来日期、无效净值及未核实的新分红/折算不强行用于计算。

- Flask：`python -B app.py`。进入页面及回到页面后自动请求`/api/account-nav`，可见时每5分钟检查；公开来源抓取缓存15分钟，无需录入持仓给外部接口。
- 静态站：通常的`python -B export_alerts.py`同时刷新账户净值、嵌入HTML并生成独立JSON。已部署静态站依靠日常数据构建更新，浏览器每5分钟重读JSON；本轮不发布。
- 单独更新公开净值：`python -B account_nav.py --refresh`；`--force`可绕过15分钟缓存。离线导出不会请求网络。
- 直接双击HTML仅使用导出时嵌入的净值，浏览器文件模式无法自动请求本地服务。自动取得新披露净值请使用Flask入口。

场外基金按日披露净值，非盘中实时行情；QDII可能延后。每项盈亏随已确认交易与最新可用净值自动重算，净值日期和沿用状态在页面注明；新分红信息未核实或历史缺数时保守停算，不虚构收益。


### 当前UI样式与首屏

`templates/_styles.html` 是动态模板和静态导出共用的唯一关键样式入口，在 `<head>` 内嵌加载；不要在正文末尾追加布局覆盖。`_status_rail.html` 保留信号展示交互，`_invest_tools.html` 保留当前四页组件，账户、研究图表及购买监测各自保留独立脚本职责。宽度和居中完全由CSS生效。

旧参数编辑、旧定投回测界面和旧持仓前端不再装配；相应后端API、研究函数和被回归测试使用的 `archive/legacy_ui/` 保留。页面清理恢复包和首帧检测见 `ui_cleanup/`。可执行 `node ui_cleanup/check_first_paint.js` 检查分段加载及禁用JavaScript时的宽度（需要本机回环服务器）。

### 2026-10-22 最新版轻量清理

正式入口仍为 `docs/index.html`，使用 `python export_alerts.py --offline` 重新生成。完整检查使用 `python run_tests.py --browser`；首屏检查使用 `node ui_cleanup/check_first_paint.js`。

历史UI基线的未压缩HTML已转为可校验恢复的ZIP；可选历史探针通过 `maintenance/read_html_snapshot.js` 读取，当前网站不加载该工具。仍被测试引用的旧模块、Flask预览文件、原静态预览路径、所有研究数据和既有依赖均保留。详情与恢复清单见 [清理验收报告](maintenance/20261022/cleanup_latest/REPORT.md)。

## 加载与 PWA 更新（2026-10-23）

静态首页由现有 `export_alerts.py` 生成。HTML 只包含今日提醒和轻量导航；账户数据及工作区脚本在打开投资配置/复盘时加载，研究曲线仅在打开策略实验时解析。所有完整公开历史数据仍保留在内容哈希命名的 `docs/assets/*.js` 中。

导出会自动生成 `docs/bundle-assets.json`、`docs/pwa-manifest.json`，并更新 `docs/sw.js` 的发布版本，无需人工递增。必须将 HTML、清单、SW 和所有引用的 assets 同批提交；`update_alerts.ps1` 已同步支持这一发布范围。旧的已发布哈希资源保留给尚未刷新的页面使用。

PWA 从当前版本缓存立即启动，后台检查更新。新版本的全部离线资源通过 SHA-256 验证后显示“刷新更新”，点击后激活并刷新；未保存填写会再次确认。更新失败继续保留旧版。不会清除 localStorage 或 IndexedDB，账本、设置及交易使用原存储键和原地址。首次完整离线包就绪仍需联网下载；之后未变化的曲线直接复用已有缓存。

验证：`node maintenance/20261022/test_pwa.js` 测试真实旧版提交到新版的升级、二次更新、安装失败保留旧版、未保存内容取消刷新、账户/交易/设置逐字保留、子目录托管及全部四页离线。`maintenance/pwa_load/` 保存同条件前后测速结果和说明。
