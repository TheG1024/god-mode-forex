#!/usr/bin/env python3
"""analysis/market.py — Market analysis using indicators and cascade data."""

from typing import Optional
from typing import Optional
import pandas as pd

from config import CONFIG
from data.cascade import CascadeProvider
from data.providers import PROVIDERS
from analysis.indicators import ema, rsi, atr, find_swings, calculate_fib_levels
from analysis.detector import DETECTOR
from models.signals import SignalDirection, MarketData


class MarketAnalyzer:
    def __init__(self, cascade: Optional[CascadeProvider] = None):
        self.cascade = cascade or CascadeProvider()

    def analyze(self, pair: str, timeframe: str = "1h") -> Optional[MarketData]:
        df = self.cascade.fetch(pair, timeframe)
        if df is None or len(df) < 50:
            return None

        df["ema_fast"] = ema(df["close"], CONFIG.EMA_FAST)
        df["ema_slow"] = ema(df["close"], CONFIG.EMA_SLOW)
        df["rsi"] = rsi(df["close"], CONFIG.RSI_PERIOD)
        df["atr"] = atr(df["high"], df["low"], df["close"], CONFIG.ATR_PERIOD)

        high_idx, low_idx = find_swings(df["high"], df["low"], order=5)
        if not high_idx or not low_idx:
            return None

        last_high_idx = high_idx[-1]
        last_low_idx = low_idx[-1]
        swing_high = df["high"].iloc[last_high_idx]
        swing_low = df["low"].iloc[last_low_idx]

        if last_high_idx > last_low_idx:
            displacement = SignalDirection.SHORT
        else:
            displacement = SignalDirection.LONG

        fibs = calculate_fib_levels(swing_high, swing_low, displacement.value)

        return MarketData(
            pair=pair, timeframe=timeframe, ohlc=df,
            ema_fast=df["ema_fast"], ema_slow=df["ema_slow"],
            rsi=df["rsi"], atr=df["atr"],
            swing_high=swing_high, swing_low=swing_low,
            displacement_direction=displacement,
            fib_79=fibs["79%"], fib_88=fibs["88%"],
            current_price=df["close"].iloc[-1]
        )


ANALYZER = MarketAnalyzer()