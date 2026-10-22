# 历史归档

本目录不参与正式网站装配。

- `reports/etf_studies/`：根目录旧ETF研究报告，脚本稳定导入关系保持在根目录。
- `legacy_ui/`：已替换的日记、预算、相关性和旧配置UI，保留兼容测试与历史复现。
- `stock/`：已退出运行链路的个股代码、报告和专用缓存，不启用。
- `legacy_checks/`：旧的分散测试入口；当前入口为根目录`run_tests.py`。
- `20261022/`：历史结果、旧研究JSON、一次性补丁与改动前源码ZIP。ZIP内保留原相对路径。

每项归档原路径、SHA256和去向见`maintenance/20261022/actions.json`。使用`python -B maintenance/archive_catalog.py`列出；恢复命令见根README。恢复工具不覆盖内容不同的文件。

V1/V2里仍被引擎或历史分析代码读取的原始数据、费率元数据、清洗面板及输出保留原路径。原有重复数据不按哈希删除。
