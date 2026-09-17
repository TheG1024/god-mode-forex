#!/usr/bin/env python3
"""tests/test_indicators.py — Tests for technical indicators."""

import pytest
import pandas as pd
import numpy as np

from analysis.indicators import ema, rsi, atr, find_swings, calculate_fib_levels


def test_ema():
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    result = ema(series, 3)
    assert len(result) == len(series)
    assert not result.isna().all()


def test_rsi():
    # Rising series should have high RSI
    series = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24])
    result = rsi(series, 14)
    assert len(result) == len(series)
    # Last RSI should be high (overbought)
    assert result.iloc[-1] > 70


def test_atr():
    high = pd.Series([10, 11, 12, 11, 10])
    low = pd.Series([9, 10, 11, 10, 9])
    close = pd.Series([9.5, 10.5, 11.5, 10.5, 9.5])
    result = atr(high, low, close, 3)
    assert len(result) == len(high)
    assert (result >= 0).all()


def test_find_swings():
    high = pd.Series([1, 2, 3, 2, 1, 2, 3, 2, 1])
    low = pd.Series([0, 1, 2, 1, 0, 1, 2, 1, 0])
    high_idx, low_idx = find_swings(high, low, order=1)
    assert len(high_idx) > 0
    assert len(low_idx) > 0


def test_calculate_fib_levels_long():
    fibs = calculate_fib_levels(100, 90, "LONG")
    assert fibs["79%"] == 92.1  # 100 - 10*0.79
    assert fibs["88%"] == 91.2  # 100 - 10*0.88
    assert fibs["100%"] == 90
    assert fibs["0%"] == 100


def test_calculate_fib_levels_short():
    fibs = calculate_fib_levels(100, 90, "SHORT")
    assert fibs["79%"] == 97.9  # 90 + 10*0.79
    assert fibs["88%"] == 98.8  # 90 + 10*0.88
    assert fibs["100%"] == 100
    assert fibs["0%"] == 90


if __name__ == "__main__":
    pytest.main([__file__, "-v"])