#!/usr/bin/env python3
"""analysis/indicators.py — Pure technical indicator functions."""

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=1).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period, min_periods=1).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def find_swings(high: pd.Series, low: pd.Series, order: int = 5) -> tuple[list[int], list[int]]:
    high_idx = argrelextrema(high.values, np.greater_equal, order=order)[0]
    low_idx = argrelextrema(low.values, np.less_equal, order=order)[0]
    return high_idx.tolist(), low_idx.tolist()


def calculate_fib_levels(high: float, low: float, direction: str) -> dict[str, float]:
    diff = high - low
    if direction == "LONG":
        return {"79%": high - diff * 0.79, "88%": high - diff * 0.88, "100%": low, "0%": high}
    else:
        return {"79%": low + diff * 0.79, "88%": low + diff * 0.88, "100%": high, "0%": low}