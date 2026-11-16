# Cycle 调度调查与补偿（2026-11-16）

## 已核实的证据

通过已授权的 Git 现有凭据读取 GitHub REST API。凭据仅在内存中使用，不写文件。

| 运行 | 事件 | created_at (UTC) | run_started_at (UTC) | 结果 |
| --- | --- | --- | --- | --- |
| 43058352309 | schedule | 11-11 16:26:28 | 11-11 16:26:28 | failure |
| 43264260668 | schedule | 11-12 16:57:25 | 11-12 16:57:25 | failure |
| 43464778942 | schedule | 11-13 16:38:40 | 11-13 16:38:40 | failure |
| 43725200471 | workflow_dispatch | 11-15 14:35:34 | 11-15 14:35:34 | success |

第 4 次 job 创建于 16:38:41，runner 16:38:44 开始；不是 job 队列等待八小时。
第 5 次 job 创建于 14:35:36，runner 14:35:38 开始。
测试仓库对应 schedule 创建于 11-11 16:28:06、11-12 16:58:09、11-13 16:39:44 UTC，与正式版同样晚创建。
调查时，11-16 尚无新运行。工作流 state=active，Actions enabled=true，默认分支 main，仓库未 archived/disabled。
Pages build_type=legacy，来源 main:/docs，status=built。成功运行日志包含完整 online hash/data 校验，ETF 和四股日期均 11-13。
测试输出中的 `ConnectionError: offline` 来自注入失败的单元测试，不能当作实际抓取失败证据。

## 结论边界

可定位到 schedule 运行记录创建之前的调度/事件交付阶段；不是本仓库 runner 排队或 Pages 发布造成延迟。
GitHub API 没有提供 schedule 内部计划时间及投递记录，无法证明具体平台根因，也不能仅凭约八小时延迟认定时区配置错误。
GitHub 官方说明 schedule 在高负荷时可能延迟或丢失；这是一般机制说明，不是本次平台事故的证明。
来源：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## 改动

- 保留 UTC 08:30（北京时间工作日16:30）主计划。
- 增加 UTC 09:17、11:17、13:17（17:17、19:17、21:17）补跑；仅当线上日期/发布内容落后时生成。
- 记录事件来源、cron、工作流 SHA、API 创建/开始时间、runner UTC 时间，供后续定位。
- `CycleMarketUpdateWatchdog` Windows 计划任务：北京时间工作日16:47、18:47、20:47、22:47及登录时检查。
- 只检查线上状态、调用既有 workflow_dispatch，不生成本机行情、不改策略、不提交本地缓存。
- 使用现有用户 Git Credential Manager 认证，凭据不落盘；当前有运行中的工作流时跳过，每个北京时间自然日最多三次手动/补偿派发。
- 需要本机已开机、该用户已登录、网络与现有 Git 登录可用。电脑关闭时只剩 GitHub 自身的主计划与补跑，不承诺精确准点。

## 运维

安装：`powershell -File install_update_watchdog.ps1`；无管理员权限、无账号密码持久化。
只读检查：`python update_watchdog.py --check-only`。
本机日志：`logs/update_watchdog.log`；任务失败会隔5分钟最多重试两次。
移除独立入口：`Unregister-ScheduledTask -TaskName CycleMarketUpdateWatchdog`。
没有修改交易日历、投资策略或 Actions-Test。

## 云端验证发现的附加问题

独立 Windows 任务成功触发运行 43887573724（2026-11-16 14:36:56 UTC），但行情校验失败：588000 两个来源均失败，旧缓存仍为11-13，严格校验阻止发布。
同一日志证明四只美股响应均含11-16盘中日线，旧代码要求最后日期为最近完整交易日11-13，导致整份有效历史被拒绝。
对此增加生成/校验最多三次重试（间隔45秒，不降低校验标准），以及美股盘中日线裁剪，保持数组对齐、只使用已经完成的交易日。
新增回归测试覆盖盘中行裁剪、原响应不被修改、数组错位拒绝写入。共26项测试通过。

588000 反复失败进一步复现：同一腾讯 qfq 来源，区间2026-11-04至16只返回到13日；精确查询16日返回收盘1.282，加入禁缓存参数仍不能补齐长区间。
因此仅在区间尾部恰好缺最后一个已完成交易日时追加同源同复权的单日查询；超过一个交易日的缺口不直接拼接。日期/价格校验保持不变。
新增两个测试覆盖单日补齐和拒绝跳过中间缺口，合计28项通过；真实只读请求确认修复后末日为11-16，未写本地缓存。
22:47 的 Windows 定时触发也已经实际观察到（运行43889424236）；该旧代码运行随后为切换诊断版本而取消。

## 最终验收

- 修复代码提交 `3bbe8dd` 的正式运行 [43890462130](https://github.com/tammyuuuu/MagicCycle/actions/runs/43890462130) 成功，首次生成尝试即通过。
- 云端诊断运行43889907965确认：东财报Push2RateLimitError，腾讯报DataNotReady；最终运行生成阶段明确记录588000同源qfq单日尾部补查成功。
- 7只ETF均校验至2026-11-16；NVDA/MSFT/GOOGL/BWXT均为最近完整美股交易日2026-11-13，价格分别162.85/523.88/295.77/122.97。未使用11-16盘中价。
- Pages发布及线上校验成功：版本`6eddbdaef41f866b0ae1`，15个发布文件。另在本机独立执行verify_pages_release.py验证线上全部哈希及JSON一致。
- 云端快照提交`cdddb8b`已快进同步本地docs，原有13个未提交缓存文件改动仍保留。
- 成功后Windows任务再次检查输出`all current`并退出0；云端补跑条件检查输出`update_due=False`，不重复生成/派发。
- 已验证真实Windows定时触发、dispatch及云端生成发布；新增GitHub原生cron未来是否准点仍不能提前证明。关闭电脑时，独立本机补偿不可用。
