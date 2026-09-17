#!/usr/bin/env python3
"""models/signals.py — Signal and MarketData dataclasses."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import pandas as pd


class SignalStatus(Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    SL_HIT = "SL_HIT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SignalDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Signal:
    id: str
    pair: str
    direction: SignalDirection
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    fib_level: float
    htf_bias: str
    rsi_value: float
    atr_value: float
    neural_score: float
    neural_commentary: str
    news_risk: str
    status: SignalStatus = SignalStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    result: str = ""
    net_r: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class MarketData:
    pair: str
    timeframe: str
    ohlc: pd.DataFrame
    ema_fast: pd.Series
    ema_slow: pd.Series
    rsi: pd.Series
    atr: pd.Series
    swing_high: float
    swing_low: float
    displacement_direction: SignalDirection
    fib_79: float
    fib_88: float
    current_price: float