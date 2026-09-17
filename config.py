#!/usr/bin/env python3
"""config.py — Configuration dataclass for Forex Signal System."""

import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # API Keys
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
    NVIDIA_NIM_API_KEY: str = os.getenv("NVIDIA_NIM_API_KEY", "")
    NVIDIA_NIM_BASE_URL: str = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "forex_signals.db")

    # Health server
    HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "8080"))

    # Strategy Parameters
    FIB_DEEP_OTE_MIN: float = 0.79
    FIB_DEEP_OTE_MAX: float = 0.88
    EMA_FAST: int = 20
    EMA_SLOW: int = 50
    RSI_PERIOD: int = 14
    RSI_OVERBOUGHT: float = 70
    RSI_OVERSOLD: float = 30
    ATR_PERIOD: int = 14
    ATR_SL_MULTIPLIER: float = 1.5
    RISK_REWARD_TP1: float = 1.0
    RISK_REWARD_TP2: float = 2.0
    SIGNAL_EXPIRY_HOURS: int = 4

    # Volatility Scanner
    SCAN_PAIRS: Optional[List[str]] = None
    TOP_VOLATILE_COUNT: int = 12
    REBALANCE_INTERVAL_HOURS: int = 168

    # Backup data sources
    FCS_API_KEY: str = os.getenv("FCS_API_KEY", "")
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "DEMO_KEY")
    COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
    HIGH_IMPACT_KEYWORDS: Optional[List[str]] = None

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        if self.SCAN_PAIRS is None:
            self.SCAN_PAIRS = self.ALL_PAIRS[:39]
        if self.HIGH_IMPACT_KEYWORDS is None:
            self.HIGH_IMPACT_KEYWORDS = [
                "NFP", "Non-Farm Payroll", "CPI", "Inflation", "FOMC", "Federal Reserve",
                "ECB", "Interest Rate", "GDP", "Unemployment", "Retail Sales",
                "PMI", "Manufacturing", "Services", "Central Bank", "Rate Decision",
                "Powell", "Lagarde", "Bailey", "Ueda", "Macklem"
            ]

    # All major/minor/exotic pairs for scanning
    ALL_PAIRS = [
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD",
        "EUR/GBP", "EUR/JPY", "GBP/JPY", "AUD/JPY", "CAD/JPY", "CHF/JPY",
        "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/NZD", "GBP/AUD", "GBP/CAD", "GBP/CHF",
        "GBP/NZD", "AUD/CAD", "AUD/CHF", "AUD/NZD", "CAD/CHF", "NZD/CAD", "NZD/CHF",
        "USD/SGD", "USD/HKD", "USD/SEK", "USD/NOK", "USD/MXN", "USD/ZAR", "USD/TRY",
        "EUR/SEK", "EUR/NOK", "EUR/PLN", "GBP/SEK", "GBP/NOK"
    ]


CONFIG = Config()