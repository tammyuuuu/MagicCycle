# 统一测试覆盖说明

当前自动入口为根目录run_tests.py，遇到失败停止。日志保留实际输出；acceptance_summary.json注明PWA沙箱权限失败及放行后通过情况。

## Python发现范围

根目录全部test_*.py自动发现，包含接口、ETF信号、因果性、数据版本、账本关联和归档完整性；V1四个测试脚本另外执行，覆盖unittest无法发现的函数式测试。

- `test_asset_strategies.py`
- `test_broad_individual_research.py`
- `test_broad_individual_strategy.py`
- `test_broad_valuation_research.py`
- `test_csi300_entry_windows.py`
- `test_csi300_search.py`
- `test_csi500_search.py`
- `test_decide_api.py`
- `test_def_research.py`
- `test_gold_heat.py`
- `test_gold_rebound.py`
- `test_gold_research.py`
- `test_gold_strategy.py`
- `test_maintenance.py`
- `test_monthly_execution.py`
- `test_purchase_monitor.py`
- `test_research_causality.py`
- `test_sector_add.py`
- `test_sector_partial_exit.py`
- `test_sector_research.py`
- `test_sector_strategy.py`
- `test_sector_valuation_research.py`
- `test_star50_robustness.py`
- `test_star50_search.py`
- `test_star50_verification.py`
- `test_stock_watch.py`
- `test_strategy_hold_audit.py`
- `test_us_etf_research.py`
- `test_us_etf_strategy.py`
- `test_valuation_data.py`
- `test_workspace_data.py`

## Node发现范围

- `test_correlation_tools.js`
- `test_investment_planner.js`
- `test_journal_integration.js`
- `test_monthly_budget.js`
- `test_portfolio_ledger.js`
- `test_portfolio_valuation.js`
- `test_purchase_monitor.js`
- `test_purchase_monitor_policy.js`
- `test_strategy_preferences.js`

## 浏览器与历史探测

- browser_acceptance：四页、交易确认/到账、真实盈亏分离、JSON恢复、策略场景、布局。
- browser_simple_plan：首次空仓和简化申购/赎回流程。
- browser_def_monitor：两类美股监测、10策略、区间缺失和指数代理、公平配对、曲线。
- test_pwa：localhost服务工作线程安装、缓存和断网导航。
- 归档results/check_scripts.js是旧双导航VM手工探测。它对已移除guide导航的假DOM假设不适用于四页；其脚本装载/初始化职责由真实浏览器套件覆盖，原文件保留在historical_results.zip。
- 归档results/check_investment_tools.js是旧日记UI探测，包含已损坏的中文夹具。旧逻辑继续由test_journal_integration/test_strategy_preferences/test_monthly_budget覆盖；新流程由browser_acceptance覆盖，原探测保留不删除。
- 这些历史探测不作为可运行的现行测试入口；未通过删掉失败回归测试来获得通过结果。
