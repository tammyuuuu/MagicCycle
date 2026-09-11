# 宽基 ETF 监测与策略回测工具

一个面向**宽基指数 ETF** 的小工具：用 AkShare 拉行情 → 跑你的买卖策略 → 做**历史回测**并输出收益/回撤/胜率等指标，同时提供**每日信号监测**。

- 数据源：东财（前复权）→ 腾讯（前复权）→ 新浪（不复权）三级自动降级，并有本地 CSV 缓存
- 回测规则：信号按当日收盘产生、次日开盘成交（避免未来函数），含佣金/最低佣金/滑点，按 100 份一手满仓
- 内置对照基准：同期「买入持有（Buy & Hold）」

## 项目结构

```
cycle/
├── config.py          # 配置：监测标的 / 手续费 / 回测资金 / 缓存参数
├── data_fetcher.py    # AkShare/腾讯行情获取 + 多源自动降级 + CSV 缓存
├── indicators.py      # 技术指标库：MA/EMA/RSI/MACD/BOLL/ATR/区间高低
├── strategies.py      # 传统策略定义（你的买卖规则也可填这里）
├── backtest.py        # 传统全仓进出式回测引擎 + 绩效 + 绘图
├── dca.py             # ⭐条件定投(估值/回撤)回测引擎 —— 网页版主引擎
├── alerts.py          # 今日买卖点提醒 / 结合持仓的精确决策
├── monitor.py         # CLI 每日信号监测（传统策略）
├── main.py            # 命令行入口（fetch/backtest/monitor/dca/alerts/list）
├── app.py             # 网页版（Flask）：规则录入 + 回测 + 今日提醒
├── templates/index.html
├── rules.json         # 网页里“保存规则”的落盘文件（自动生成）
├── requirements.txt
└── data_cache/        # 本地行情缓存（自动生成）
```

## 安装

```bash
pip install -r requirements.txt
```

## 快速上手

### 1) 拉取 / 刷新数据（可选，程序会自动缓存）

```bash
python main.py fetch                      # 拉取所有目标 ETF
python main.py fetch --etf 588000 --force # 强制全量刷新单只
```

### 2) 历史回测

```bash
# 对全部标的跑默认示例策略（ma_cross 双均线 20/60）
python main.py backtest

# 指定标的、区间、策略，并保存图表与交易明细
python main.py backtest --etf 510500 --strategy rsi_reversal --start 20200101 --save --plot

# 覆盖策略参数
python main.py backtest --etf 588000 --strategy ma_cross --params "fast=20,slow=120"
```

回测输出指标：总收益 / 年化收益 / 最大回撤 / 夏普 / 卡玛 / 胜率 / 盈亏比 / 平均持有天数，
并自动与「买入持有」对照；`--save` 会把图表和逐笔交易明细写入 `results/`。

### 3) 每日监测

```bash
# 收盘后运行，输出每只 ETF 当前的持仓建议
python main.py monitor
python main.py monitor --etf 588000 --strategy ma_cross
```

监测基于**当日收盘**计算信号，买/卖需按提示在**次日开盘**执行。

### 4) 查看内置策略

```bash
python main.py list
```

## ⭐ 填入你自己的买卖规则

策略都在 `strategies.py` 里。把你自己的规则写进 `my_strategy` 函数即可：

```python
def my_strategy(df, params):
    # df: 日线（open/high/low/close/volume...）
    # 可用 indicators 里的 ma/ema/rsi/macd/bollinger/atr/cross_up...
    buy  = ...   # 买入条件（布尔 Series，True 处发买入信号）
    sell = ...   # 卖出条件（布尔 Series，True 处发卖出信号）
    return buy.astype(int) - sell.astype(int)   # +1 买入 / -1 卖出 / 0 无操作
```

改完后运行：

```bash
python main.py backtest --etf all --strategy my_strategy --save --plot
```

需要新增参数时：把默认值加到 `strategies.py` 的 `DEFAULT_PARAMS["my_strategy"]`，
命令行可用 `--params "xxx=值"` 覆盖。

## 更换 / 增加监测标的

编辑 `config.py` 的 `TARGET_ETFS`，每行一个字典：

```python
TARGET_ETFS = [
    {"code": "510500", "name": "中证500ETF", "index": "中证500"},
    {"code": "588000", "name": "科创50ETF",  "index": "科创50"},
    # {"code": "510300", "name": "沪深300ETF", "index": "沪深300"},
    # {"code": "159915", "name": "创业板ETF",  "index": "创业板指"},
]
```

`config.py` 里还能改：初始资金、佣金费率（默认万 1）、单笔最低佣金、滑点等。

## 数据与网络说明

- 首次使用某只 ETF 需要联网拉取；之后只要缓存已包含**最近一个应已收盘的交易日**就直接复用，
  否则从缓存末尾增量拉取（判据是数据日期，不是文件时间）。
- 东财源被屏蔽/限流时会打印 `[提示]`，先降级到**腾讯**（同为前复权，价格与东财一致），
  再不行才用新浪（不复权，对 ETF 分红影响很小）。
- 若网络长期不可用，可先用 `fetch` 把数据缓存好，之后回测/监测可在离线状态复用缓存。
- 监测页里显示的“实时价格”来自腾讯行情接口（单次快速请求）。

## 免责声明

本项目仅用于**策略研究、回测与个人学习**，不构成任何投资建议。回测结果不代表未来表现；
实盘前请自行核对手续费、滑点、分红、停牌等细节。

---

## 🌐 网页版（推荐）：录入规则 → 看收益 → 看今日买卖点

```bash
python app.py
# 浏览器打开 http://127.0.0.1:5000
```

三个页签：

1. **规则编辑**
   - ① 策略参数：历史极值/最大涨幅窗口、分位点窗口、日均波动窗口、A/B/C/D/E 阈值、定投金额档、资金池等，全部可改。
   - ② 卖出/仓位管理规则：每一行 =「满足【条件】→ 执行【操作】」，勾选条件、选操作，从上到下优先级判断、首个命中生效。
   - 可「💾 保存为默认规则」（落到 `rules.json`）或「载入已保存」。
2. **定投回测**：选标的 + 起始日 → 开始回测 → 同时给出**条件定投 vs 无脑定投基准**两张指标表、资金曲线图和动作日志。
3. **今日提醒**：打开即显示每只 ETF 今天能不能投（A/B/D 状态 + 建议金额）、是否过热暂停；点开「填我的实际持仓（是否持有/平均成本/持仓最高价）」可得到精确的**该买 / 该卖 / 该减仓 / 继续持有**判断。

命令行等价用法：

```bash
python main.py dca --etf all --start 20160101 --save --plot   # 条件定投回测
python main.py alerts                                         # 今日买卖点提醒
```

### 定投/提醒的引擎约定（务必了解，参数均可调）

- **成交模型**：条件用当日收盘数据计算，按当日收盘价成交；每周第一个交易日定投（周一休市自动顺延到当周首个交易日）。
- **历史最高/最低价与最大涨幅** = 过去 `hist_window`(默认5年=1260交易日)的滚动极值，用「截至昨日」的数据（避免当日未来信息）；数据不足时退化为自上市以来。
- **分位点** = 当日收盘在过去 `percentile_window`(默认5年) 收盘价中的百分位（含当日）。
- **C 涨幅** 相对「持仓摊薄成本(含费用)」；**E 高位回撤** 指持仓期间收盘最高点回撤 ≥ 日均波动×倍数（日均波动=过去 `vol_window` 日 |涨跌幅| 均值，截至昨日）。
- **减仓类动作**(卖50%)同一持仓周期内只触发一次，避免反复减半；E 保护清仓会把持仓周期重置。
- **金额档 30/20/10 元** 默认按「1 份」粒度买入，用于**信号与收益比率的验证**（小额也可买）。⚠️ 实盘场内 ETF 需按一手 100 份并放大金额，佣金/滑点请按你券商实际调整（参数 `lot`、`fee_rate`、`min_fee` 可改）。
- 已实现盈亏按“摊薄成本法”后算；基准「无脑定投」= 每期固定投档1金额、不择时、不减仓。

### 提醒的触发临界参考价

卖出提醒中若你还没填持仓，工具会给出“什么价位会触发”：

- E 回撤保护：需 **持仓期最高价 ≥ 现价 × (1 + 日均波动×倍数)** 才可能触发；
- C 涨幅：需你的 **摊薄平均成本 ≤ 现价 / (1 + 最大涨幅×C阈值)** 才满足；
- D 过热：分位点 > 阈值即触发暂停定投。

填上你的实际持仓（成本/最高价）后，网页会直接告诉你今天该怎么做。

## 📱 手机看今日提醒（GitHub Pages，免费）

本地网页只有电脑能访问；想「手机上随时看今天能不能投」，可把今日提醒导出成静态页发布到 GitHub Pages：

```bash
python export_alerts.py        # 生成 docs/index.html（手机友好、可填持仓精判断）
```

然后：

1. 提交推送 `docs/`：`git add . && git commit -m "update alerts" && git push`
2. 在 GitHub 仓库 **Settings → Pages** → Source 选 **Deploy from a branch: main / docs** → Save
3. 手机访问 `https://<你的用户名>.github.io/<仓库名>/`（本仓库即 `https://tammyuuuu.github.io/MagicCycle/`）

说明：

- 规则来源：优先用网页「保存为默认规则」生成的 `rules.json`；没有则用内置默认规则。想在网页改好规则再导出，先去网页保存一次再跑导出。
- 这是**定时快照**：每次 `python export_alerts.py` 生成当天数据，可配合 Windows 任务计划程序在每天收盘后自动跑（用 AkShare 本地缓存，无需实时接口）。
- 若 GitHub 在你网络下访问不畅，把 `docs/index.html` 这个单文件同样可推到 Gitee Pages 等国内静态托管，效果相同。

