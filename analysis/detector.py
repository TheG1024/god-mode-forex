#!/usr/bin/env python3
"""analysis/detector.py — Deep OTE signal detection."""

from typing import Optional
import pandas as pd

from config import CONFIG
from models.signals import SignalDirection, MarketData


class SignalDetector:
    def check_deep_ote(self, md: MarketData) -> Optional[dict]:
        price = md.current_price
        if md.displacement_direction == SignalDirection.LONG:
            in_zone = md.fib_88 <= price <= md.fib_79
            direction = SignalDirection.LONG
        else:
            in_zone = md.fib_79 <= price <= md.fib_88
            direction = SignalDirection.SHORT

        if not in_zone:
            return None

        bias_aligned = (
            (direction == SignalDirection.LONG and md.ohlc["ema_fast"].iloc[-1] > md.ohlc["ema_slow"].iloc[-1]) or
            (direction == SignalDirection.SHORT and md.ohlc["ema_fast"].iloc[-1] < md.ohlc["ema_slow"].iloc[-1])
        )
        if not bias_aligned:
            return None

        rsi_val = md.rsi.iloc[-1]
        rsi_ok = (
            (direction == SignalDirection.LONG and rsi_val < CONFIG.RSI_OVERBOUGHT) or
            (direction == SignalDirection.SHORT and rsi_val > CONFIG.RSI_OVERSOLD)
        )
        if not rsi_ok:
            return None

        atr_val = md.atr.iloc[-1]
        if direction == SignalDirection.LONG:
            entry = price
            sl = md.swing_low - atr_val * CONFIG.ATR_SL_MULTIPLIER
            risk = entry - sl
            tp1 = entry + risk * CONFIG.RISK_REWARD_TP1
            tp2 = entry + risk * CONFIG.RISK_REWARD_TP2
            fib_level = (md.swing_high - price) / (md.swing_high - md.swing_low)
        else:
            entry = price
            sl = md.swing_high + atr_val * CONFIG.ATR_SL_MULTIPLIER
            risk = sl - entry
            tp1 = entry - risk * CONFIG.RISK_REWARD_TP1
            tp2 = entry - risk * CONFIG.RISK_REWARD_TP2
            fib_level = (price - md.swing_low) / (md.swing_high - md.swing_low)

        return {
            "direction": direction,
            "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
            "fib_level": fib_level,
            "htf_bias": "BULLISH" if md.ohlc["ema_fast"].iloc[-1] > md.ohlc["ema_slow"].iloc[-1] else "BEARISH",
            "rsi": rsi_val, "atr": atr_val
        }


DETECTOR = SignalDetector()