# 星循最新版代码清理验收报告

日期：2026-10-22。范围：当前源码与原导出器；未提交、未推送、未发布，未操作真实交易或用户浏览器账本。

## 结果

- 当前四页、界面、交易与估值口径保持不变。
- 完整测试32组全部通过，其中Python主套件187项。清理前为33组；减少的1组仅测试已废弃的CSV成交文件导入器，当前逐笔成交、确认、删除重算及JSON备份测试全部保留并通过。
- 四页在1440px、375px和320px下，清理前后的可见元素计算样式与布局一致；全部无横向溢出。
- 首屏分段慢加载、刷新、禁用JavaScript时：桌面宽度始终460px，375px/320px分别始终375px/320px；未使用隐藏页面或宽度动画。
- PWA安装、旧缓存升级、离线导航及四页离线启动通过。

## 清理和优化

1. 删除不再装配的 `trade_receipts.js` 及其专用旧测试 `test_trade_receipts.js`。它们只属于已经移除的成交文件导入功能，没有当前页面或导出器调用。删除前源码已收入恢复ZIP。当前成交录入与JSON备份恢复不变。
2. 清理已不存在的开户按钮、旧费用单位行、旧费用预览、旧资产标题按钮选择器，以及被后续important规则覆盖的重复hidden规则。保留实际使用的空状态样式。两处相同下拉箭头合并为共享CSS变量，计算样式完全一致。
3. `correlation_data.py`统一安全JSON输出，只移除序列化空白，并统一保留脚本转义；不删字段、指标、日期或净值点。移除该模块已经不用的pandas/config导入，但它们在其他业务和研究代码仍有依赖，因此没有移除已声明的第三方依赖。
4. `investment_workspace.js`每轮渲染复用一次资产目录和已经算出的当日估值，避免重复复制全部基金净值、重复计算同一轮报告；没有更改估值算法或跨事件缓存结果。
5. 历史UI快照的未压缩副本转为ZIP，使用SHA256逐个验证相同内容。可选旧基线探针改为按需读取ZIP。当前站点不依赖此读取工具，也不增加浏览器请求。
6. 本地 `/static-preview` 请求不再每次额外写出整页HTML。显式运行原 `build_previews.py` 时仍生成原静态预览路径，保留原访问地址和存储来源。
7. 原导出器重新生成 `docs/index.html`；PWA版本更新至 `v42-compact-shell`，首屏关键样式继续在head内。

## 主动保留和停止扩大清理

引用检查发现，历史验收脚本会通过拼接路径读取 `workspace_ui_20261022/flask_preview.html`。该文件已立即按原SHA256恢复，未继续删除；静态旧预览路径也保留。仍被旧兼容测试引用的 `archive/legacy_ui`、公共导出方法、全部研究与结果数据、原图资源、JSON备份、Python缓存及用途不确定的文件均未扩大删除。

未发现当前功能测试回归。发现历史依赖后停止扩大删除范围，仅完成已确认清理项的验收。

## 数据与计算保护

检查了952个研究、行情和核心模块文件。研究版本、回测数据、策略参数、账本存储、资金池、费用、收益与回撤引擎均未改动。

五类内嵌数据逐项解析比对：PRODUCT_ASSETS、WORKSPACE_DATA、FUND_ACCESS_MONITOR、ACCOUNT_NAV_SNAPSHOT的净值数据、STRATEGY_SUMMARIES全部一致。唯一文件哈希变化是既有后台刷新写入的账户净值缓存状态时间和来源错误提示；净值序列保持一致，没有回滚后台状态。详见 `data_equivalence.json`。

## 空间统计

统计包括保留的压缩恢复包及本次验收截图，不包括 `.git`；MB使用十进制。

| 范围 | 清理前 | 清理后 | 节省 |
|---|---:|---:|---:|
| 整个项目 | 223.30 MB | 207.85 MB | 15.46 MB |
| 正式HTML | 10.21 MB | 9.44 MB | 0.76 MB（7.5%） |

两份历史HTML原大小合计20,193,461字节：`ui_optimization/before.html`归档压缩；`ui_cleanup/before.html`复用已有ZIP中的逐字节相同版本。删除的旧模块及旧测试合计6,888字节。恢复包合计5,959,096字节，已计入上述净空间结果。

完整研究数据依旧内嵌，因此正式页仍接近9.45MB。这次没有通过删研究资料、曲线、账本能力或破坏离线使用来压缩体积。

## 修改文件

以下大小单位为字节：

| 文件 | 清理前 | 清理后 |
|---|---:|---:|
| `correlation_data.py` | 2,169 | 2,056 |
| `investment_workspace.js` | 37,194 | 37,176 |
| `templates/_styles.html` | 25,981 | 25,198 |
| `docs/sw.js` | 2,700 | 2,696 |
| `workspace_ui_20261022/serve_preview.py` | 1,957 | 2,029 |
| `workspace_ui_20261022/build_previews.py` | 695 | 725 |
| `ui_cleanup/check_first_paint.js` | 3,616 | 3,652 |
| `ui_optimization/capture.js` | 1,927 | 1,989 |
| `README.md` | 10,890 | 11,531 |
| `docs/index.html` | 10,205,666 | 9,445,727 |

新增：`maintenance/read_html_snapshot.js`及本报告目录内的恢复索引、哈希、校验结果和截图；不属于网站业务代码。

## 验收证据与恢复

- `baseline_tests.json`：清理前33组完整测试。
- `full_tests.json`：清理后32组完整测试。
- `layout_equivalence.json`：四页×三种宽度的计算样式等价与本机导航观测。时间仅为单次本地观测，体积减小和重复计算减少才是本次优化的确定结果。
- `first_paint.json`：慢加载首帧宽度、刷新及无JavaScript检查。
- `protected_hashes.json`、`data_equivalence.json`：研究、账本和净值数据一致性。
- `actions.json`、`archived_html.json`：删除/归档项与逐文件恢复来源。
- `source_before.zip`：修改前源码和正式HTML；按原路径保存，可逐文件恢复。
- `historical_html.zip`：历史UI快照。`ui_cleanup/before.html`从既有 `ui_cleanup/before.zip` 的 `docs/index.html`成员恢复。
- `after_375_today.png`、`after_375_plan.png`、`after_375_review.png`、`after_375_lab.png`：当前375px界面。
