# Au99.99 五年滚动急涨卖出＋六个月动量仓位上限

信号取上海黄金交易所 Au99.99 收盘价（元/克），交易标的为华夏黄金 ETF（518850）。金价回测按每侧 0.10% 扣费，现金无息。站点展示策略模拟仓位。

正式策略在 gold_combination_strategy.py。月末收盘低于六个月前月末收盘时，下个交易日收盘将上限调至 50%，否则上限为 100%。每次急涨卖出清仓，回补时买至届时上限；同日变化按最终目标净额成交一次。交易间仓位随价格漂移。

组合基准来自 CycleTest gold_research/combination 的 cap 账户。combination/daily.csv 为逐日净值、权重和净成交，instructions.csv 为信号与执行日明细。回测以 2011 年末已有的黄金持仓起步。按本次正式规则，月末金价相等时上限为 100%，研究脚本在相等时沿用上期；核对区间内没有相等月份。历史入选的急涨规则均为清仓或继续持有，后续入选的急涨卖出统一执行清仓。

行情与年度选择来自 CycleTest 的 gold_research/early_extension。verified_daily.csv 保留出处，计算从连续报价的 2007 年开始。schedule.csv 为研究锁定的 2012–2026 年选择。account_daily.csv、episodes.csv、summary.csv 是该研究“逐年滚动样本外”账户的核对基准。原 73 个候选及其顺序来自 heat_repurchase/run.py。

新年度使用此前五个完整自然年的日线。每个候选的训练期末资产除以最大单笔正向持金倍数，未回补的交易以训练期末价格估值，得分保留 12 位小数后按原顺序择优。卖出比例与回补条件随原卖单跨年保留。研究期后的新增官方收盘存于 docs/au9999_recent.csv，随正式站发布。

运行 `python -m unittest test_gold_strategy -v` 检查年度入选、每日余额、逐笔信号及网站决策。原五年急涨单策略保留在 gold_rolling_strategy.py，其年度选参和卖出回补信号继续由组合复用。回退时在发布分支还原本次黄金策略提交并重新导出站点。
