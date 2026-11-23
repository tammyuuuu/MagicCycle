# Au99.99 五年滚动规则

信号取上海黄金交易所 Au99.99 收盘价（元/克），交易标的为华夏黄金 ETF（518850）。金价回测按每侧 0.10% 扣费，现金无息。站点展示策略模拟仓位。

行情与年度选择来自 CycleTest 的 gold_research/early_extension。verified_daily.csv 保留出处，计算从连续报价的 2007 年开始。schedule.csv 为研究锁定的 2012–2026 年选择。account_daily.csv、episodes.csv、summary.csv 是该研究“逐年滚动样本外”账户的核对基准。原 73 个候选及其顺序来自 heat_repurchase/run.py。

新年度使用此前五个完整自然年的日线。每个候选的训练期末资产除以最大单笔正向持金倍数，未回补的交易以训练期末价格估值，得分保留 12 位小数后按原顺序择优。卖出比例与回补条件随原卖单跨年保留。研究期后的新增官方收盘存于 docs/au9999_recent.csv，随正式站发布。

运行 `python -m unittest test_gold_strategy -v` 检查年度入选、每日余额、逐笔信号及网站决策。原过热策略保留在 gold_strategy.py。回退时在发布分支还原本次黄金策略提交并重新导出站点。
