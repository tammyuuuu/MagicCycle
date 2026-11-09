# MSFT 月度估值监测

策略版本 MSFT-PIT-PE-v1，来源为 `cycle-actions-test/stock_research/timing_backtest_20261107.py`、`rules.json` 和 `metrics.csv`，研究日 2026-11-07，回测数据截至 2026-11-06。`engine/backtest.py` 仅修改数据根目录；`engine/metrics.csv` 为原研究数据。运行时使用 Yahoo chart 和 SEC companyfacts，独立重建历史模拟仓位，实时快照存 `engine/snapshot.json`，不访问个人持仓。

Flask 的 `/api/msft-monitor` 在刷新今日提醒后请求数据；静态页在 `export_alerts.py` 运行时更新。网络、行情不完整、财报无效或日历超界时保留上次快照，并禁止产生新信号。静态页在下一完整美股交易日的数据应可用之后自动标记过期。离线导出明确标记未联网核验。

SEC 请求建议设置环境变量 `MSFT_SEC_USER_AGENT`，值包含应用名称及真实联系邮箱，符合 SEC 公平访问要求。自动日历目前只覆盖 2026—2027，特殊休市需要维护；超范围时拒绝生成信号。当前数据源为 Yahoo Finance 和 SEC，成本假设不含税、汇率和实际滑点；财报加权股数近似每日流通股本。

验证：`python -X utf8 -m unittest test_msft_monitor -v`；离线预览：`python export_alerts.py --offline --out research_msft_strategy/preview/index.html`。原研究 11 项测试保留在原研究目录；此处的测试另外核对原策略五笔历史股票交易。
