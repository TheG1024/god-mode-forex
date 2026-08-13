#!/usr/bin/env python3
"""
god_mode.py — Professional Forex Signal System
Combines SMC Deep OTE strategy with LLM neural analysis.
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import requests
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import schedule
from dotenv import load_dotenv

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# LLM
from openai import AsyncOpenAI

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # API Keys
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    NVIDIA_NIM_API_KEY: str = os.getenv("NVIDIA_NIM_API_KEY", "")
    NVIDIA_NIM_BASE_URL: str = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Database
    DB_PATH: str = os.getenv("DB_PATH", "forex_signals.db")
    
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
    SIGNAL_EXPIRY_HOURS: int = 4  # Auto-expire PENDING signals after this many hours
    
    # Volatility Scanner
    SCAN_PAIRS: List[str] = None  # Will be populated from ALL_PAIRS
    TOP_VOLATILE_COUNT: int = 12
    REBALANCE_INTERVAL_HOURS: int = 168  # Weekly
    
    # News Filter
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
    HIGH_IMPACT_KEYWORDS: List[str] = None
    
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

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=getattr(logging, CONFIG.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("god_mode.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("god_mode")

# ═══════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self, path: str):
        self.path = path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    pair TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    sl_price REAL NOT NULL,
                    tp1_price REAL NOT NULL,
                    tp2_price REAL NOT NULL,
                    fib_level REAL NOT NULL,
                    htf_bias TEXT NOT NULL,
                    rsi_value REAL NOT NULL,
                    atr_value REAL NOT NULL,
                    neural_score REAL NOT NULL,
                    neural_commentary TEXT NOT NULL,
                    news_risk TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT DEFAULT '',
                    net_r REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pair_volatility (
                    pair TEXT PRIMARY KEY,
                    atr_avg REAL NOT NULL,
                    volatility_score REAL NOT NULL,
                    last_updated TEXT NOT NULL,
                    is_golden BOOLEAN DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance (
                    date TEXT PRIMARY KEY,
                    total_signals INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    net_r REAL DEFAULT 0.0,
                    win_rate REAL DEFAULT 0.0
                )
            """)
            conn.commit()
    
    def save_signal(self, signal: Signal):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                signal.id, signal.pair, signal.direction.value, signal.entry_price,
                signal.sl_price, signal.tp1_price, signal.tp2_price, signal.fib_level,
                signal.htf_bias, signal.rsi_value, signal.atr_value, signal.neural_score,
                signal.neural_commentary, signal.news_risk, signal.status.value,
                signal.created_at, signal.updated_at, signal.result, signal.net_r
            ))
            conn.commit()
    
    def get_signal(self, signal_id: str) -> Optional[Signal]:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
            if row:
                return Signal(
                    id=row[0], pair=row[1], direction=SignalDirection(row[2]),
                    entry_price=row[3], sl_price=row[4], tp1_price=row[5], tp2_price=row[6],
                    fib_level=row[7], htf_bias=row[8], rsi_value=row[9], atr_value=row[10],
                    neural_score=row[11], neural_commentary=row[12], news_risk=row[13],
                    status=SignalStatus(row[14]), created_at=row[15], updated_at=row[16],
                    result=row[17], net_r=row[18]
                )
        return None
    
    def update_signal(self, signal_id: str, **kwargs):
        ALLOWED_COLUMNS = {
            "status", "result", "net_r", "updated_at", "neural_score",
            "neural_commentary", "news_risk", "entry_price", "sl_price",
            "tp1_price", "tp2_price"
        }
        fields = []
        values = []
        for k, v in kwargs.items():
            if k not in ALLOWED_COLUMNS:
                raise ValueError(f"Column '{k}' is not in allowed update columns")
            fields.append(f"{k}=?")
            values.append(v)
        values.append(signal_id)
        with sqlite3.connect(self.path) as conn:
            conn.execute(f"UPDATE signals SET {','.join(fields)} WHERE id=?", values)
            conn.commit()
    
    def get_active_signals(self) -> List[Signal]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM signals WHERE status IN ('PENDING','ACTIVE','TP1_HIT')").fetchall()
            return [Signal(
                id=r[0], pair=r[1], direction=SignalDirection(r[2]), entry_price=r[3],
                sl_price=r[4], tp1_price=r[5], tp2_price=r[6], fib_level=r[7],
                htf_bias=r[8], rsi_value=r[9], atr_value=r[10], neural_score=r[11],
                neural_commentary=r[12], news_risk=r[13], status=SignalStatus(r[14]),
                created_at=r[15], updated_at=r[16], result=r[17], net_r=r[18]
            ) for r in rows]
    
    def get_performance_stats(self) -> Dict:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                    SUM(net_r) as net_r
                FROM signals WHERE result IN ('WIN','LOSS')
            """).fetchone()
            total, wins, losses, net_r = row
            return {
                "total": total or 0,
                "wins": wins or 0,
                "losses": losses or 0,
                "net_r": net_r or 0.0,
                "win_rate": (wins / total * 100) if total else 0.0
            }
    
    def save_volatility(self, pair: str, atr_avg: float, vol_score: float, is_golden: bool):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pair_volatility VALUES (?,?,?,?,?)
            """, (pair, atr_avg, vol_score, datetime.now(timezone.utc).isoformat(), int(is_golden)))
            conn.commit()
    
    def get_golden_pairs(self) -> List[str]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT pair FROM pair_volatility WHERE is_golden=1 ORDER BY volatility_score DESC"
            ).fetchall()
            return [r[0] for r in rows]
    
    def expire_old_signals(self, expiry_hours: int) -> int:
        """Expire PENDING signals older than expiry_hours. Returns count of expired signals."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=expiry_hours)).isoformat()
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "UPDATE signals SET status='EXPIRED', updated_at=? WHERE status='PENDING' AND created_at < ?",
                (datetime.now(timezone.utc).isoformat(), cutoff)
            )
            conn.commit()
            return cursor.rowcount

DB = Database(CONFIG.DB_PATH)

# ═══════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS (Pandas/NumPy only, no TA-Lib)
# ═══════════════════════════════════════════════════════════════════════

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def find_swings(high: pd.Series, low: pd.Series, order: int = 5) -> Tuple[List[int], List[int]]:
    high_idx = argrelextrema(high.values, np.greater_equal, order=order)[0]
    low_idx = argrelextrema(low.values, np.less_equal, order=order)[0]
    return high_idx.tolist(), low_idx.tolist()

def calculate_fib_levels(high: float, low: float, direction: SignalDirection) -> Dict[str, float]:
    diff = high - low
    if direction == SignalDirection.LONG:
        return {
            "79%": high - diff * 0.79,
            "88%": high - diff * 0.88,
            "100%": low,
            "0%": high
        }
    else:
        return {
            "79%": low + diff * 0.79,
            "88%": low + diff * 0.88,
            "100%": high,
            "0%": low
        }

# ═══════════════════════════════════════════════════════════════════════
# DATA PIPELINE — CASCADE FETCH
# ═══════════════════════════════════════════════════════════════════════

class DataProvider:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ForexSignalBot/1.0"})
    
    def fetch_twelve_data(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
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
                logger.warning(f"TwelveData: {data.get('message', 'No values')}")
                return None
            df = pd.DataFrame(data["values"])
            df = df.rename(columns={"datetime": "timestamp", "open": "open", "high": "high", "low": "low", "close": "close"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col])
            return df[["open", "high", "low", "close"]]
        except Exception as e:
            logger.error(f"TwelveData error for {pair}: {e}")
            return None
    
    def generate_synthetic(self, pair: str, periods: int = 200) -> pd.DataFrame:
        """Generate synthetic OHLC for testing when all APIs fail."""
        np.random.seed(hash(pair) % 2**32)
        base_price = 1.0 if "JPY" not in pair else 150.0
        returns = np.random.normal(0, 0.0005, periods)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create OHLC from close prices
        noise = np.random.uniform(0.999, 1.001, (periods, 3))
        df = pd.DataFrame({
            "open": prices * noise[:, 0],
            "high": prices * noise[:, 1],
            "low": prices * noise[:, 2],
            "close": prices
        })
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)
        df.index = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq="1h")
        return df[["open", "high", "low", "close"]]
    
    def cascade_fetch(self, pair: str, interval: str = "1h") -> pd.DataFrame:
        """Try Twelve Data → Synthetic fallback."""
        for name, func in [
            ("TwelveData", lambda: self.fetch_twelve_data(pair, interval)),
            ("Synthetic", lambda: self.generate_synthetic(pair))
        ]:
            try:
                df = func()
                if df is not None and len(df) >= 50:
                    logger.info(f"Data for {pair} from {name}: {len(df)} candles")
                    return df
            except Exception as e:
                logger.warning(f"{name} failed for {pair}: {e}")
        raise RuntimeError(f"All data sources failed for {pair}")

DATA_PROVIDER = DataProvider()

# ═══════════════════════════════════════════════════════════════════════
# MARKET ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════

class MarketAnalyzer:
    def analyze(self, pair: str, timeframe: str = "1h") -> Optional[MarketData]:
        df = DATA_PROVIDER.cascade_fetch(pair, timeframe)
        if df is None or len(df) < 50:
            return None
        
        # Indicators
        df["ema_fast"] = ema(df["close"], CONFIG.EMA_FAST)
        df["ema_slow"] = ema(df["close"], CONFIG.EMA_SLOW)
        df["rsi"] = rsi(df["close"], CONFIG.RSI_PERIOD)
        df["atr"] = atr(df["high"], df["low"], df["close"], CONFIG.ATR_PERIOD)
        
        # Swings
        high_idx, low_idx = find_swings(df["high"], df["low"], order=5)
        if not high_idx or not low_idx:
            return None
        
        # Most recent significant swing
        last_high_idx = high_idx[-1]
        last_low_idx = low_idx[-1]
        swing_high = df["high"].iloc[last_high_idx]
        swing_low = df["low"].iloc[last_low_idx]
        
        # Determine displacement direction
        if last_high_idx > last_low_idx:
            displacement = SignalDirection.SHORT  # High after Low = down move
        else:
            displacement = SignalDirection.LONG   # Low after High = up move
        
        # Fib levels
        fibs = calculate_fib_levels(swing_high, swing_low, displacement)
        
        current_price = df["close"].iloc[-1]
        current_rsi = df["rsi"].iloc[-1]
        current_atr = df["atr"].iloc[-1]
        
        # HTF Bias
        htf_bias = "BULLISH" if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1] else "BEARISH"
        
        return MarketData(
            pair=pair, timeframe=timeframe, ohlc=df,
            ema_fast=df["ema_fast"], ema_slow=df["ema_slow"],
            rsi=df["rsi"], atr=df["atr"],
            swing_high=swing_high, swing_low=swing_low,
            displacement_direction=displacement,
            fib_79=fibs["79%"], fib_88=fibs["88%"],
            current_price=current_price
        )

ANALYZER = MarketAnalyzer()

# ═══════════════════════════════════════════════════════════════════════
# DEEP OTE SIGNAL DETECTION
# ═══════════════════════════════════════════════════════════════════════

class SignalDetector:
    def check_deep_ote(self, md: MarketData) -> Optional[Dict]:
        """Check if price is in Deep OTE zone (79%-88% fib retrace)."""
        price = md.current_price
        in_zone = CONFIG.FIB_DEEP_OTE_MIN <= (price - md.fib_88) / (md.fib_79 - md.fib_88) <= 1 if md.fib_79 != md.fib_88 else False
        
        # More precise: check if price between 79% and 88%
        if md.displacement_direction == SignalDirection.LONG:
            in_zone = md.fib_88 <= price <= md.fib_79
            direction = SignalDirection.LONG
        else:
            in_zone = md.fib_79 <= price <= md.fib_88
            direction = SignalDirection.SHORT
        
        if not in_zone:
            return None
        
        # HTF Bias alignment
        bias_aligned = (
            (direction == SignalDirection.LONG and md.ohlc["ema_fast"].iloc[-1] > md.ohlc["ema_slow"].iloc[-1]) or
            (direction == SignalDirection.SHORT and md.ohlc["ema_fast"].iloc[-1] < md.ohlc["ema_slow"].iloc[-1])
        )
        if not bias_aligned:
            return None
        
        # RSI confirmation
        rsi_val = md.rsi.iloc[-1]
        rsi_ok = (
            (direction == SignalDirection.LONG and rsi_val < CONFIG.RSI_OVERBOUGHT) or
            (direction == SignalDirection.SHORT and rsi_val > CONFIG.RSI_OVERSOLD)
        )
        if not rsi_ok:
            return None
        
        # Calculate entry, SL, TP
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
            "fib_level": fib_level, "htf_bias": md.ohlc["ema_fast"].iloc[-1] > md.ohlc["ema_slow"].iloc[-1] and "BULLISH" or "BEARISH",
            "rsi": rsi_val, "atr": atr_val
        }

DETECTOR = SignalDetector()

# ═══════════════════════════════════════════════════════════════════════
# NEURAL BRAIN (NVIDIA NIM / Llama 3.1)
# ═══════════════════════════════════════════════════════════════════════

class NeuralBrain:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=CONFIG.NVIDIA_NIM_API_KEY,
            base_url=CONFIG.NVIDIA_NIM_BASE_URL
        ) if CONFIG.NVIDIA_NIM_API_KEY else None
    
    async def analyze(self, md: MarketData, signal_data: Dict) -> Tuple[float, str]:
        if not self.client:
            return 5.0, "Neural brain not configured (no NVIDIA NIM API key)."
        
        # Prepare context for LLM
        recent_candles = md.ohlc.tail(20)[["open", "high", "low", "close"]].to_string()
        prompt = f"""You are a professional SMC (Smart Money Concepts) forex analyst. Analyze this Deep OTE setup.

PAIR: {md.pair}
TIMEFRAME: {md.timeframe}
DIRECTION: {signal_data['direction'].value}
ENTRY: {signal_data['entry']:.5f}
SL: {signal_data['sl']:.5f}
TP1: {signal_data['tp1']:.5f} (1R)
TP2: {signal_data['tp2']:.5f} (2R)
FIB LEVEL: {signal_data['fib_level']:.1%} (Deep OTE 79-88%)
HTF BIAS: {signal_data['htf_bias']}
RSI: {signal_data['rsi']:.1f}
ATR: {signal_data['atr']:.5f}

RECENT OHLC (last 20 candles):
{recent_candles}

TASK: Provide a Neural Score (0-10) and professional commentary.
- Score 8-10: High conviction, clean structure, strong confluence
- Score 5-7: Moderate, some concerns but valid
- Score 0-4: Low quality, avoid

Respond ONLY in this JSON format:
{{"score": <float>, "commentary": "<string>"}}"""
        
        try:
            resp = await self.client.chat.completions.create(
                model="meta/llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            result = json.loads(resp.choices[0].message.content)
            score = max(0, min(10, float(result.get("score", 5))))
            commentary = result.get("commentary", "No commentary provided.")
            return score, commentary
        except Exception as e:
            logger.error(f"Neural analysis failed: {e}")
            return 5.0, f"Neural analysis error: {str(e)[:100]}"

NEURAL = NeuralBrain()

# ═══════════════════════════════════════════════════════════════════════
# NEWS CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════

class NewsFilter:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour
    
    async def check_high_impact(self, pair: str) -> str:
        """Check for high-impact news in next 24h. Returns 'CLEAR', 'WARNING', 'HIGH_RISK'."""
        if not CONFIG.NEWSAPI_KEY:
            return "UNKNOWN (no API key)"
        
        cache_key = f"news_{pair}_{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        base, quote = pair.split("/")
        currencies = [base, quote]
        
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": " OR ".join(currencies + ["forex", "central bank"]),
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": CONFIG.NEWSAPI_KEY
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            
            risk = "CLEAR"
            for article in data.get("articles", []):
                text = f"{article.get('title', '')} {article.get('description', '')}".lower()
                for kw in CONFIG.HIGH_IMPACT_KEYWORDS:
                    if kw.lower() in text:
                        # Check if article is recent (last 24h)
                        pub = article.get("publishedAt", "")
                        if pub:
                            try:
                                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                if (datetime.now(timezone.utc) - pub_dt).total_seconds() < 86400:
                                    risk = "HIGH_RISK"
                                    break
                            except:
                                pass
                if risk == "HIGH_RISK":
                    break
            
            self.cache[cache_key] = risk
            return risk
        except Exception as e:
            logger.error(f"News check failed: {e}")
            return "ERROR"

NEWS_FILTER = NewsFilter()

# ═══════════════════════════════════════════════════════════════════════
# EVOLUTION ENGINE — VOLATILITY SCANNER
# ═══════════════════════════════════════════════════════════════════════

class EvolutionEngine:
    def __init__(self):
        self.lock = threading.Lock()
    
    def scan_volatility(self, pairs: List[str]) -> List[Tuple[str, float]]:
        """Scan pairs and return (pair, volatility_score) sorted desc."""
        results = []
        for pair in pairs:
            try:
                df = DATA_PROVIDER.cascade_fetch(pair, "1h")
                if df is None or len(df) < 50:
                    continue
                df["atr"] = atr(df["high"], df["low"], df["close"], 14)
                atr_avg = df["atr"].tail(20).mean()
                current_price = df["close"].iloc[-1]
                vol_score = (atr_avg / current_price) * 10000  # Normalized volatility
                results.append((pair, vol_score))
                DB.save_volatility(pair, atr_avg, vol_score, False)
            except Exception as e:
                logger.error(f"Volatility scan failed for {pair}: {e}")
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def rebalance_golden_pairs(self):
        """Run weekly: scan 39 pairs, update top 12 as Golden Pairs."""
        logger.info("Starting weekly volatility rebalance...")
        with self.lock:
            ranked = self.scan_volatility(CONFIG.ALL_PAIRS)
            golden = [p for p, _ in ranked[:CONFIG.TOP_VOLATILE_COUNT]]
            
            # Update DB
            for pair, score in ranked:
                is_golden = pair in golden
                atr_avg = next((s for p, s in ranked if p == pair), 0)
                DB.save_volatility(pair, atr_avg, score, is_golden)
            
            CONFIG.SCAN_PAIRS = golden
            logger.info(f"Golden Pairs updated: {golden}")
    
    def get_golden_pairs(self) -> List[str]:
        golden = DB.get_golden_pairs()
        if golden:
            return golden
        # Fallback: run scan now
        ranked = self.scan_volatility(CONFIG.ALL_PAIRS)
        golden = [p for p, _ in ranked[:CONFIG.TOP_VOLATILE_COUNT]]
        for pair, score in ranked:
            DB.save_volatility(pair, score, score, pair in golden)
        CONFIG.SCAN_PAIRS = golden
        return golden

EVOLUTION = EvolutionEngine()

# ═══════════════════════════════════════════════════════════════════════
# SIGNAL ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════

class SignalOrchestrator:
    def __init__(self):
        self.running = False
    
    async def scan_all_pairs(self) -> List[Signal]:
        signals = []
        pairs = EVOLUTION.get_golden_pairs()
        logger.info(f"Scanning {len(pairs)} golden pairs...")
        
        for pair in pairs:
            try:
                md = ANALYZER.analyze(pair, "1h")
                if not md:
                    continue
                
                sig_data = DETECTOR.check_deep_ote(md)
                if not sig_data:
                    continue
                
                # Neural analysis
                neural_score, neural_commentary = await NEURAL.analyze(md, sig_data)
                if neural_score < 6.0:  # Filter low conviction
                    logger.info(f"{pair}: Neural score {neural_score:.1f} < 6, skipping")
                    continue
                
                # News filter
                news_risk = await NEWS_FILTER.check_high_impact(pair)
                
                # Create signal
                signal_id = uuid.uuid4().hex[:12]
                signal = Signal(
                    id=signal_id,
                    pair=pair,
                    direction=sig_data["direction"],
                    entry_price=sig_data["entry"],
                    sl_price=sig_data["sl"],
                    tp1_price=sig_data["tp1"],
                    tp2_price=sig_data["tp2"],
                    fib_level=sig_data["fib_level"],
                    htf_bias=sig_data["htf_bias"],
                    rsi_value=sig_data["rsi"],
                    atr_value=sig_data["atr"],
                    neural_score=neural_score,
                    neural_commentary=neural_commentary,
                    news_risk=news_risk
                )
                
                DB.save_signal(signal)
                signals.append(signal)
                logger.info(f"Signal generated: {signal_id} | {pair} {signal.direction.value} | Neural: {neural_score:.1f}")
                
            except Exception as e:
                logger.error(f"Scan failed for {pair}: {e}")
        
        # Sequential delivery with 3-second delay
        for signal in signals:
            await TELEGRAM_BOT.send_signal_alert(signal)
            await asyncio.sleep(3)
        
        return signals
    
    async def monitor_active_signals(self):
        """Check active signals against current price for TP/SL hits."""
        # Expire stale PENDING signals first
        expired_count = DB.expire_old_signals(CONFIG.SIGNAL_EXPIRY_HOURS)
        if expired_count:
            logger.info(f"Expired {expired_count} stale PENDING signals")
        
        active = DB.get_active_signals()
        for signal in active:
            try:
                df = DATA_PROVIDER.cascade_fetch(signal.pair, "1h")
                if df is None or len(df) == 0:
                    continue
                current_price = df["close"].iloc[-1]
                
                hit = None
                if signal.direction == SignalDirection.LONG:
                    if current_price <= signal.sl_price:
                        hit = "SL_HIT"
                    elif current_price >= signal.tp2_price:
                        hit = "TP2_HIT"
                    elif current_price >= signal.tp1_price:
                        hit = "TP1_HIT"
                else:
                    if current_price >= signal.sl_price:
                        hit = "SL_HIT"
                    elif current_price <= signal.tp2_price:
                        hit = "TP2_HIT"
                    elif current_price <= signal.tp1_price:
                        hit = "TP1_HIT"
                
                if hit:
                    await self.resolve_signal(signal, hit, current_price)
                    
            except Exception as e:
                logger.error(f"Monitor failed for {signal.id}: {e}")
    
    async def resolve_signal(self, signal: Signal, result: str, exit_price: float):
        """Calculate R and update signal."""
        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
            reward = exit_price - signal.entry_price
        else:
            risk = signal.sl_price - signal.entry_price
            reward = signal.entry_price - exit_price
        
        net_r = reward / risk if risk != 0 else 0
        
        DB.update_signal(signal.id, 
            status=SignalStatus(result),
            result="WIN" if net_r > 0 else "LOSS",
            net_r=net_r,
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        logger.info(f"Signal {signal.id} resolved: {result} | Net R: {net_r:.2f}")

ORCHESTRATOR = SignalOrchestrator()

# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM BOT
# ═══════════════════════════════════════════════════════════════════════

class TelegramBot:
    def __init__(self):
        self.app = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 *God Mode Forex Signal Bot*\n\n"
            "Commands:\n"
            "/scan — Run manual scan\n"
            "/signals — List active signals\n"
            "/performance — Show stats\n"
            "/golden — Show current Golden Pairs\n"
            "/rebalance — Force volatility rebalance\n"
            "/update <ID> <WIN|LOSS> — Manual result update\n"
            "/weekly — Generate weekly audit report\n"
            "/help — This message",
            parse_mode="Markdown"
        )
    
    async def scan_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 Scanning Golden Pairs...")
        signals = await ORCHESTRATOR.scan_all_pairs()
        if not signals:
            await update.message.reply_text("No Deep OTE setups found.")
            return
        await update.message.reply_text(f"✅ {len(signals)} signal(s) generated and sent.")
    
    async def signals_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        active = DB.get_active_signals()
        if not active:
            await update.message.reply_text("No active signals.")
            return
        
        msg = "*Active Signals:*\n\n"
        for s in active:
            msg += (
                f"`{s.id}` {s.pair} {s.direction.value}\n"
                f"Entry: {s.entry_price:.5f} | SL: {s.sl_price:.5f}\n"
                f"TP1: {s.tp1_price:.5f} (1R) | TP2: {s.tp2_price:.5f} (2R)\n"
                f"Neural: {s.neural_score:.1f}/10 | News: {s.news_risk}\n"
                f"Status: {s.status.value}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
    
    async def performance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = DB.get_performance_stats()
        msg = (
            f"📊 *Performance Stats*\n\n"
            f"Total Trades: {stats['total']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Net R: {stats['net_r']:.2f}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    
    async def golden_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        golden = EVOLUTION.get_golden_pairs()
        msg = "*Golden Pairs (Top 12 by Volatility):*\n\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(golden))
        await update.message.reply_text(msg, parse_mode="Markdown")
    
    async def rebalance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⚙️ Running volatility rebalance...")
        EVOLUTION.rebalance_golden_pairs()
        await self.golden_cmd(update, context)
    
    async def update_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /update <ID> <WIN|LOSS>")
            return
        signal_id, result = context.args
        result = result.upper()
        if result not in ("WIN", "LOSS"):
            await update.message.reply_text("Result must be WIN or LOSS")
            return
        
        signal = DB.get_signal(signal_id)
        if not signal:
            await update.message.reply_text(f"Signal {signal_id} not found")
            return
        
        # Calculate R based on result
        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
            reward = risk * (1 if result == "WIN" else -1)
        else:
            risk = signal.sl_price - signal.entry_price
            reward = risk * (1 if result == "WIN" else -1)
        net_r = reward / risk if risk else 0
        
        DB.update_signal(signal_id, 
            status=SignalStatus.TP2_HIT if result == "WIN" else SignalStatus.SL_HIT,
            result=result, net_r=net_r, updated_at=datetime.now(timezone.utc).isoformat()
        )
        await update.message.reply_text(f"✅ Signal {signal_id} updated: {result} | Net R: {net_r:.2f}")

    async def weekly_report_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate and send weekly audit report."""
        await self.send_weekly_report()

    async def send_weekly_report(self):
        """Generate weekly audit report for Friday 16:00 UTC."""
        if not CONFIG.TELEGRAM_CHAT_ID:
            return
        
        # Get signals from last 7 days
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with sqlite3.connect(CONFIG.DB_PATH) as conn:
            # Closed trades this week
            closed = pd.read_sql("""
                SELECT * FROM signals 
                WHERE result IN ('WIN','LOSS') AND updated_at >= ?
                ORDER BY updated_at DESC
            """, conn, params=(week_ago,))
            
            # Open positions
            open_pos = pd.read_sql("""
                SELECT * FROM signals 
                WHERE status IN ('PENDING','ACTIVE','TP1_HIT')
                ORDER BY created_at DESC
            """, conn)
        
        # Weekly stats
        total_closed = len(closed)
        wins = len(closed[closed['result'] == 'WIN']) if total_closed else 0
        losses = len(closed[closed['result'] == 'LOSS']) if total_closed else 0
        win_rate = (wins / total_closed * 100) if total_closed else 0
        net_r = closed['net_r'].sum() if total_closed else 0.0
        
        # MVP Pair
        mvp_pair = "—"
        mvp_r = 0.0
        if total_closed:
            pair_stats = closed.groupby('pair')['net_r'].sum()
            mvp_pair = pair_stats.idxmax()
            mvp_r = pair_stats.max()
        
        # Build report
        msg = f"📋 *WEEKLY AUDIT REPORT* 📋\n"
        msg += f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d')} 16:00 UTC\n\n"
        
        msg += f"📊 *This Week's Closed Trades*\n"
        msg += f"   Total: {total_closed} | Wins: {wins} | Losses: {losses}\n"
        msg += f"   Win Rate: {win_rate:.1f}%\n"
        msg += f"   Net R: {net_r:+.2f}R\n\n"
        
        msg += f"🏆 *MVP Pair*: {mvp_pair} ({mvp_r:+.2f}R)\n\n"
        
        msg += f"📌 *Open Positions Audit* ({len(open_pos)} open)\n"
        if len(open_pos) == 0:
            msg += "   No open positions.\n"
        else:
            for _, row in open_pos.iterrows():
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at'])).days
                msg += f"   `{row['id']}` {row['pair']} {row['direction']} | {row['status']} | {age_days}d old\n"
        
        try:
            await self.app.bot.send_message(
                chat_id=CONFIG.TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown"
            )
            logger.info("Weekly report sent")
        except Exception as e:
            logger.error(f"Weekly report send failed: {e}")

    async def send_signal_alert(self, signal: Signal):
        if not CONFIG.TELEGRAM_CHAT_ID:
            return
        
        emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
        risk_emoji = "🚨" if signal.news_risk == "HIGH_RISK" else "✅"
        
        # Format with MarkdownV2 code blocks for instant copy
        def code(val): return f"`{val}`"
        
        msg = (
            f"{emoji} *NEW DEEP OTE SIGNAL* {emoji}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 *ID:* {code(signal.id)}\n"
            f"💱 *Pair:* {code(signal.pair)} — {code(signal.direction.value)}\n\n"
            f"📊 *BIAS & STRUCTURE*\n"
            f"   HTF Bias: {code(signal.htf_bias)}\n"
            f"   Fib Level: {code(f'{signal.fib_level:.1%}')} (Deep OTE 79-88%)\n"
            f"   RSI: {code(f'{signal.rsi_value:.1f}')}\n"
            f"   ATR: {code(f'{signal.atr_value:.5f}')}\n\n"
            f"🎯 *TARGETS*\n"
            f"   Entry: {code(f'{signal.entry_price:.5f}')}\n"
            f"   SL: {code(f'{signal.sl_price:.5f}')}\n"
            f"   TP1 (1R): {code(f'{signal.tp1_price:.5f}')}\n"
            f"   TP2 (2R): {code(f'{signal.tp2_price:.5f}')}\n\n"
            f"🧠 *NEURAL GRADE:* {code(f'{signal.neural_score:.1f}/10')}\n"
            f"{risk_emoji} *News Risk:* {code(signal.news_risk)}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💬 *AI REASONING*\n{signal.neural_commentary}"
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"win_{signal.id}"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"loss_{signal.id}")
        ]])
        
        try:
            await self.app.bot.send_message(
                chat_id=CONFIG.TELEGRAM_CHAT_ID, text=msg,
                parse_mode="MarkdownV2", reply_markup=keyboard
            )
            logger.info(f"Signal alert sent: {signal.id}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, signal_id = query.data.split("_", 1)
        result = "WIN" if action == "win" else "LOSS"
        
        signal = DB.get_signal(signal_id)
        if not signal:
            await query.edit_message_text("Signal not found")
            return
        
        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
        else:
            risk = signal.sl_price - signal.entry_price
        reward = risk if result == "WIN" else -risk
        net_r = reward / risk if risk else 0
        
        DB.update_signal(signal_id,
            status=SignalStatus.TP2_HIT if result == "WIN" else SignalStatus.SL_HIT,
            result=result, net_r=net_r, updated_at=datetime.now(timezone.utc).isoformat()
        )
        
        await query.edit_message_text(
            f"{query.message.text}\n\n✅ *Updated: {result} | Net R: {net_r:.2f}*",
            parse_mode="Markdown"
        )
    
    def run(self):
        if not CONFIG.TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram bot token not set, skipping")
            return
        
        self.app = Application.builder().token(CONFIG.TELEGRAM_BOT_TOKEN).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("scan", self.scan_cmd))
        self.app.add_handler(CommandHandler("signals", self.signals_cmd))
        self.app.add_handler(CommandHandler("performance", self.performance_cmd))
        self.app.add_handler(CommandHandler("golden", self.golden_cmd))
        self.app.add_handler(CommandHandler("rebalance", self.rebalance_cmd))
        self.app.add_handler(CommandHandler("update", self.update_cmd))
        self.app.add_handler(CommandHandler("weekly", self.weekly_report_cmd))
        self.app.add_handler(CommandHandler("help", self.start))
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        logger.info("Telegram bot started")
        self.app.run_polling()

TELEGRAM_BOT = TelegramBot()

# ═══════════════════════════════════════════════════════════════════════
# HEALTH CHECK SERVER (for Render Web Service)
# ═══════════════════════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # suppress request logs

def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND SCHEDULER
# ═══════════════════════════════════════════════════════════════════════

def run_scheduler():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run_async(coro):
        await coro
    
    # Scan every 15 minutes
    schedule.every(15).minutes.do(lambda: loop.run_until_complete(run_async(ORCHESTRATOR.scan_all_pairs())))
    # Monitor every 5 minutes
    schedule.every(5).minutes.do(lambda: loop.run_until_complete(run_async(ORCHESTRATOR.monitor_active_signals())))
    # Rebalance weekly (Monday 00:00 UTC)
    schedule.every().monday.at("00:00").do(EVOLUTION.rebalance_golden_pairs)
    # Weekly audit report (Friday 16:00 UTC)
    schedule.every().friday.at("16:00").do(lambda: loop.run_until_complete(run_async(TELEGRAM_BOT.send_weekly_report())))
    
    while True:
        schedule.run_pending()
        time.sleep(30)

# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("GOD MODE FOREX SIGNAL SYSTEM — STARTING")
    logger.info("=" * 60)

    # Create and set event loop for Python 3.10+ compatibility
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start health check server (for Render Web Service)
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Initial golden pairs
    EVOLUTION.get_golden_pairs()

    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Run telegram bot (blocking)
    TELEGRAM_BOT.run()

if __name__ == "__main__":
    main()