"""美股指导入口；保留旧月均线函数，供历史研究复现。"""
import pandas as pd

from us_guidance import VERSION


def monthly_data(close):
    monthly = close.resample('ME').last()
    monthly = monthly[monthly.index <= close.index[-1]]
    average = monthly.rolling(10, min_periods=10).mean()
    return monthly, average


def targets(close):
    monthly, average = monthly_data(close)
    return (monthly > average).astype('boolean').reindex(close.index, method='ffill').fillna(False).astype(bool)


def analyze(data, item, metrics, details):
    # 保留月均线辅助函数供旧研究复现；当前生产策略使用经过追加检验的指导规则。
    from us_guidance import analyze as guidance_analyze
    return guidance_analyze(data, item, metrics, details)

