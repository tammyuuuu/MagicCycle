# 四类资产策略 V1 实施记录

> 以下为早期实施记录。2026-10-03更新：行业588170已启用`sector_ma20_v1`，以收盘价相对20日均线的位置判断买入/观察/退出，移除原行业持仓盈利、RSI、回撤与长期均线条件。投资计划与日记也已实现。当前行为见README和`docs/index.json`；下文旧版本示例保留作历史记录。

本轮只实现策略体系、统一输出和今日提醒的兼容接入。未实现投资计划、投资日记、自动交易、券商接口或基本面分析。

## 原有代码与保留范围

- 宽基：`alerts.py` 生成旧提醒，`dca.py` 负责滚动分位/极值/波动及原定投回测。原回测策略、卖出规则和历史结果计算未改。
- 行业：`industry_strategy.py` 判断回撤、趋势恢复、盈利退出和长期趋势确认。原 8%减仓、15%退出、亏损反弹失败退出规则保留；参数改为从 `strategy_config.py` 引入。
- 传统策略：`strategies.py` 的 ma_cross/rsi_reversal/macd_cross/my_strategy 及注册表保留，新增纯计算入口 `analyze_asset`。
- 行情：保留原 ETF 三源降级、CSV 缓存、联接基金 signal_code 代理。个股的东财/新浪路径改用对应股票接口，腾讯路径可同时支持 ETF 与股票。
- 发布：继续输出单文件 `docs/index.html`，GitHub Pages 的 main/docs 发布方式不变。另输出 `docs/index.json`，可供后续前端读取。

## 修改文件

`strategy_config.py` 新增四类配置；`strategies.py` 新增统一策略入口；`industry_strategy.py` 集中参数并排除未结束周的退出确认；`indicators.py` 修复 RSI 连续上涨和横盘边界；`config.py` 标注四类资产、新增黄金和宇树；`data_fetcher.py` 分流股票数据接口；`app.py` 接入统一结果并保留旧 rep/decision 兼容字段；`main.py` 的 alerts 命令调用统一入口；`export_alerts.py` 导出统一结果及简单卡片；`templates/index.html` 读取 summary；`templates/_asset_guide.html` 新增策略说明；`test_asset_strategies.py` 新增边界和流程测试；`README.md` 补充使用约定；`docs/index.html` 与 `docs/index.json` 为实际生成结果。

用户已有 icon 文件与日志改动未清理或覆盖。

## 资产类型与状态

| 类型 | subtype | 状态与中文 |
|---|---|---|
| broad_etf | null | buy_more 适合增加投入；normal_buy 正常投入；pause 暂时等待；reduce 考虑适度减仓；hold 继续持有 |
| sector_etf | null | wait 暂不追入；watch 进入观察区；small_buy 可以小额尝试；buy 买入条件改善；stop_add 停止继续加仓；reduce 考虑部分减仓；exit 考虑退出 |
| macro_asset | gold | allocate 适合分批配置；normal_hold 正常持有；pause 暂缓追高；reduce 考虑适度减仓；risk 风险上升 |
| stock | null | avoid 暂不关注；watch 进入观察区/高风险观察；starter 可以小仓位尝试；buy 买入条件进一步确认；hold 继续持有；stop_add 停止继续加仓；reduce 考虑减仓；exit 退出条件触发 |

bond/commodity/reit 的类型结构预留，但 V1 仅实现 gold；其他 subtype 会明确报错，不套用黄金规则。

## 统一接口

`analyze_asset(df, item, holding=None, overrides=None, sell_rules=None)` 输出 symbol、name、asset_type、subtype、date、status、action、reason、risk_level、metrics、details。普通输出缺失指标为 null，不使用 NaN/Infinity。发生抓取失败时 JSON 返回 status=error，卡片明确提示数据失败。

持仓输入 holding 为布尔；return_rate 与 position_ratio 使用小数，例如 0.08=8%；兼容 current_return 百分数输入。avg_cost 可用于估算收益，stop_price 可提供个股止损线。fundamental_risk、thesis_invalidated 默认 false，同时标记 fundamental_data_available=false；默认 false 不代表已做基本面审查。

`/api/alerts` 继续返回标的信息、rep、text，新增 summary；`/api/decide` 返回 summary，同时保留旧 rep/decision 兼容字段。新前端以 summary 为准，旧 decision 仅为旧规则接口兼容，不代表新版长期配置结论。

原内部 A–E 条件保留在 details.legacy 中，卡片只展示中文状态与原因。判断依据折叠展示，不直接将条件代号显示给用户。

## 已有指标与修正

复用 MA5/10/20/60/120、RSI14、ATR、滚动价格分位、历史极值，以及现有行业趋势/回撤/反弹失败判断。均线斜率、价格偏离均线、近期回撤、日收益标准差、成交量相对均量均为这些数据的派生计算，没有新增技术指标函数。

RSI 修正：持续上涨且无下跌时输出 100；完全横盘输出 50。长期趋势确认仅使用已结束的完整周，防止周中被当成第二个完整确认周。

## 参数与临时值

沿用：宽基 1260 日历史窗口、低位30/高位70分位、回撤与盈利参考历史最大涨幅的50%；行业15%/25%观察回撤、8%减仓、15%退出、两完整周确认、20/60/120日均线、18%均线偏离与20%近期涨幅过热等。

V1 provisional parameter，需要后续回测确认：

- 宽基：最低60交易日样本、80%仓位上限。
- 行业：统一输出最低120交易日样本、RSI恢复线30。原趋势策略的窗口和阈值保留。
- 黄金：最低120日样本、250日高点窗口、5%配置回调、均线偏离18%/20%、RSI70过热、8%盈利减仓、两周长期趋势确认。
- 个股：最低250交易日与365日上市历史、60日高点窗口、15%观察回撤、RSI30/70、15%单日异常、5%日收益波动、ATR/价格10%、10日跌20%的持续下跌过滤、8%盈利减仓、-8%止损、成交量倍数上限3、10日趋势失效确认。

这些值在一个配置模块维护，不构成已经回测有效的结论。新版提醒与旧回测规则不同，未把旧回测收益当成新版策略证据。

## 真实行情输出（2026-09-30）

| 代码 | 名称 | 类型 | 数据日 | status | action |
|---|---|---|---|---|---|
| 518850 | 华夏黄金ETF | macro_asset | 2026-09-30 | normal_hold | 正常持有 |
| 688836 | 宇树科技 | stock | 2026-09-30 | watch | 高风险观察 |
| 510500 | 中证500ETF | broad_etf | 2026-09-30 | pause | 暂时等待 |
| 588000 | 科创50ETF | broad_etf | 2026-09-30 | pause | 暂时等待 |
| 024418 | 华夏科创半导体材料设备ETF联接C | sector_etf | 2026-09-30 | watch | 进入观察区 |

完整五个标的实际输出见 `docs/index.json`，以下每类给出一个精简 JSON 示例。未提供实际持仓时，不推断已有盈利。

```json
{
  "symbol": "518850",
  "name": "华夏黄金ETF",
  "asset_type": "macro_asset",
  "subtype": "gold",
  "date": "2026-09-30",
  "status": "normal_hold",
  "action": "正常持有",
  "reason": "中长期配置趋势暂未破坏，不必追买。",
  "risk_level": "normal",
  "metrics": {
    "price": 8.726,
    "day_change_pct": 1.38,
    "historical_percentile": null,
    "drawdown": -27.19,
    "rsi14": 39.84,
    "ma5": 8.7732,
    "ma10": 8.889,
    "ma20": 8.9926,
    "ma60": 8.9167,
    "ma120": 9.1616,
    "ma20_slope": -0.16484999999999772,
    "volatility": 0.012686023791642189,
    "atr": 0.1293315237874118,
    "volume_ratio": 0.8342957984366988
  }
}
```

```json
{
  "symbol": "688836",
  "name": "宇树科技",
  "asset_type": "stock",
  "subtype": null,
  "date": "2026-09-30",
  "status": "watch",
  "action": "高风险观察",
  "reason": "上市时间或历史样本不足，不输出强买入。",
  "risk_level": "high",
  "metrics": {
    "price": 450.4,
    "day_change_pct": -0.14,
    "historical_percentile": null,
    "drawdown": -46.7,
    "rsi14": 8.27,
    "ma5": 468.008,
    "ma10": 481.661,
    "ma20": 496.6405,
    "ma60": null,
    "ma120": null,
    "ma20_slope": -29.375999999999976,
    "volatility": 0.04500925986818693,
    "atr": 55.87314945766243,
    "volume_ratio": 0.5041756690285973
  }
}
```

```json
{
  "symbol": "510500",
  "name": "中证500ETF",
  "asset_type": "broad_etf",
  "subtype": null,
  "date": "2026-09-30",
  "status": "pause",
  "action": "暂时等待",
  "reason": "当前价格处于相对较高位置，先不增加投入。",
  "risk_level": "normal",
  "metrics": {
    "price": 7.472,
    "day_change_pct": -0.05,
    "historical_percentile": 86.27,
    "drawdown": -17.39,
    "rsi14": 37.8,
    "ma5": 7.5712,
    "ma10": 7.6799,
    "ma20": 7.694,
    "ma60": 7.8156,
    "ma120": 8.1167,
    "ma20_slope": -0.08384999999999909,
    "volatility": 0.019590693679642654,
    "atr": 0.14811918975481544,
    "volume_ratio": 0.5850781154362605
  }
}
```

```json
{
  "symbol": "024418",
  "name": "华夏科创半导体材料设备ETF联接C",
  "asset_type": "sector_etf",
  "subtype": null,
  "date": "2026-09-30",
  "status": "watch",
  "action": "进入观察区",
  "reason": "已出现明显回撤，但还需要等待趋势企稳。",
  "risk_level": "normal",
  "metrics": {
    "price": 0.91,
    "day_change_pct": -3.29,
    "historical_percentile": null,
    "drawdown": -34.86,
    "rsi14": 41.15,
    "ma5": 0.9546,
    "ma10": 0.9755,
    "ma20": 0.9462,
    "ma60": 1.0041,
    "ma120": 0.9253,
    "ma20_slope": -0.011200000000000099,
    "volatility": 0.050597521850267606,
    "atr": 0.04314837348996357,
    "volume_ratio": 0.9775266902000377
  }
}
```

## 实际验证

1. 执行完整 `python -B export_alerts.py`，联网抓取黄金/宇树并更新行业 ETF，腾讯备用源成功；随后再运行使用最新缓存。
2. 五个标的均输出成功，数据日均为2026-09-30；严格 JSON 序列化通过，无 NaN/Infinity。
3. 11 项自动测试通过：RSI边界、短历史不买入、宽基中性投入与高位盈利减仓、黄金回调配置、个股次新样本和投资逻辑退出、完整周确认、行业/黄金趋势风险、个股异常波动过滤、平价序列导出、缺数据导出、Flask接口与静态流程。
4. Node 检查本地模板渲染和两份静态页 JavaScript 语法，并以 DOM 模拟执行实际静态页初始化、页签和持仓判断。未进行手机真机或真实浏览器视觉验收。
5. `git diff --check` 通过。pandas/NumPy 周重采样存在依赖层弃用提示，当前不影响计算；未升级依赖。

华夏黄金 ETF 518850 的标识来自[华夏基金官方页面](https://fund.chinaamc.com/fund/518850/index.shtml)，宇树688836及上市时间来自[上交所上市公告](https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20260818_10829204.shtml)。卡片数值来自项目行情流程，不来自搜索摘要。
