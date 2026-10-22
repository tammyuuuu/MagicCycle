"""统一提醒参数。旧回测参数与行业参数直接复用，不改变历史回测。"""
from dca import DCA_DEFAULTS
# 行业提醒与均线回测共用此配置；持仓盈亏不参与买卖判断。
SECTOR_PROFILE = {
    "ma_fast": 20, "min_history": 20,
}
# 新增值均为 V1 provisional parameter，需要后续回测确认。
STRATEGY_CONFIG = {
    "broad_etf": {**DCA_DEFAULTS, "normal_amount": DCA_DEFAULTS["amount_b"],
                  "max_position_ratio": .8, "min_history": 250,
                  "price_high_window": 250, "drawdown_medium": .10,
                  "drawdown_large": .20, "valuation_exit_percentile": 90},
    "sector_etf": dict(SECTOR_PROFILE),
    "macro_asset": {"gold": {"min_history": 120, "return_window": 20,
        "ma_window": 60, "heat_threshold": .15, "cooling_threshold": .05}},
}
