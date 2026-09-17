#!/usr/bin/env python3
"""data/providers.py — Data provider protocols and implementations."""

from abc import ABC, abstractmethod
from typing import Optional
import os
import requests
import pandas as pd
import yfinance as yf
import time

from config import CONFIG


class DataProvider(ABC):
    """Abstract base for OHLC data providers."""

    @abstractmethod
    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        pass


class TwelveDataProvider(DataProvider):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ForexSignalBot/1.0"})

    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        if not CONFIG.TWELVE_DATA_API_KEY:
            return None
        symbol = pair.replace("/", "")
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol, "interval": interval, "outputsize": outputsize,
            "apikey": CONFIG.TWELVE_DATA_API_KEY, "format": "JSON"
        }
        try:
            r = self.session.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if "values" not in data:
                return None
            df = pd.DataFrame(data["values"])
            df = df.rename(columns={"datetime": "timestamp", "open": "open", "high": "high", "low": "low", "close": "close"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col])
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


class QuotientProvider(DataProvider):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ForexSignalBot/1.0"})

    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        api_key = os.environ.get("RAPIDAPI_KEY", "")
        if not api_key:
            return None

        clean = pair.replace("/", "").upper()
        interval_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240"}
        q_interval = interval_map.get(interval, "60")

        try:
            from datetime import timedelta, datetime
            end = datetime.now()
            start = end - timedelta(days=min(outputsize // 24 + 1, 30))

            r = self.session.get(
                "https://quotient.p.rapidapi.com/forex/intraday",
                headers={"x-rapidapi-key": api_key, "x-rapidapi-host": "quotient.p.rapidapi.com"},
                params={"symbol": clean, "interval": q_interval, "from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d %H:%M")},
                timeout=15
            )

            if r.status_code == 429:
                return None
            r.raise_for_status()
            data = r.json()

            if isinstance(data, dict) and "message" in data:
                return None
            if not isinstance(data, list) or len(data) == 0:
                return None

            df = pd.DataFrame(data)
            df = df.dropna(subset=["Date", "Close"])
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


class YFinanceProvider(DataProvider):
    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        symbol = pair.replace("/", "") + "=X"
        try:
            yf_interval = interval.replace("h", "h").replace("d", "d")
            period = "60d" if yf_interval in ["1h", "2h", "4h"] else "1y"
            time.sleep(1)
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=yf_interval)
            if df is None or len(df) < 50:
                return None
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
            df.index.name = "timestamp"
            if len(df) > outputsize:
                df = df.tail(outputsize)
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


class FCSProvider(DataProvider):
    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        if not CONFIG.FCS_API_KEY:
            return None
        symbol = pair.replace("/", "")
        url = "https://fcsapi.com/v3/forex/history"
        params = {"symbol": symbol, "period": interval, "key": CONFIG.FCS_API_KEY}
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("status") != 1 or "response" not in data:
                return None
            records = data["response"]
            if not records:
                return None
            df = pd.DataFrame(records)
            df = df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna()
            if len(df) > outputsize:
                df = df.tail(outputsize)
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


class AlphaVantageProvider(DataProvider):
    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        if not CONFIG.ALPHA_VANTAGE_API_KEY:
            return None
        symbol = pair.replace("/", "")
        url = "https://www.alphavantage.co/query"
        av_interval = interval.replace("1h", "60min").replace("4h", "240min").replace("1d", "Daily")
        params = {
            "function": "FX_INTRADAY" if "min" in av_interval else "FX_DAILY",
            "from_symbol": symbol[:3], "to_symbol": symbol[3:],
            "interval": av_interval if "min" in av_interval else None,
            "outputsize": "full", "apikey": CONFIG.ALPHA_VANTAGE_API_KEY
        }
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            ts_key = next((k for k in data if "Time Series" in k or "time series" in k.lower()), None)
            if not ts_key:
                return None
            records = data[ts_key]
            rows = []
            for ts, vals in records.items():
                rows.append({"timestamp": pd.to_datetime(ts), "open": float(vals.get("1. open", 0)),
                            "high": float(vals.get("2. high", 0)), "low": float(vals.get("3. low", 0)),
                            "close": float(vals.get("4. close", 0))})
            df = pd.DataFrame(rows).set_index("timestamp").sort_index()
            df = df[(df > 0).all(axis=1)]
            if len(df) > outputsize:
                df = df.tail(outputsize)
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


class FrankfurterProvider(DataProvider):
    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        clean = pair.replace("/", "")
        base, quote = clean[:3].upper(), clean[3:].upper()
        try:
            from datetime import timedelta, datetime
            end = datetime.now()
            start = end - timedelta(days=outputsize)
            url = f"https://api.frankfurter.dev/v1/{start.strftime('%Y-%m-%d')}..{end.strftime('%Y-%m-%d')}?base={base}&symbols={quote}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates", {})
            if not rates:
                return None
            rows = []
            for date_str, rate_dict in sorted(rates.items()):
                rate = rate_dict.get(quote)
                if rate:
                    rows.append({"date": pd.to_datetime(date_str), "close": float(rate)})
            if len(rows) < 20:
                return None
            df = pd.DataFrame(rows).set_index("date")
            df["open"] = df["close"].shift(1).fillna(df["close"])
            df["high"] = df[["open", "close"]].max(axis=1) * 1.001
            df["low"] = df[["open", "close"]].min(axis=1) * 0.999
            df.index = pd.date_range(end=datetime.now(), periods=len(df), freq="1D")
            return df[["open", "high", "low", "close"]]
        except Exception:
            return None


PROVIDERS = [
    TwelveDataProvider(),
    QuotientProvider(),
    YFinanceProvider(),
    FCSProvider(),
    AlphaVantageProvider(),
    FrankfurterProvider(),
]