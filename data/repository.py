#!/usr/bin/env python3
"""data/repository.py — Database protocol and SQLite implementation."""

from abc import ABC, abstractmethod
from typing import Optional, List
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from config import CONFIG
from models.signals import Signal, SignalStatus, SignalDirection

logger = logging.getLogger(__name__)


class SignalRepository(ABC):
    """Abstract signal repository."""

    @abstractmethod
    def save_signal(self, signal: Signal) -> None:
        pass

    @abstractmethod
    def get_signal(self, signal_id: str) -> Optional[Signal]:
        pass

    @abstractmethod
    def update_signal(self, signal_id: str, **kwargs) -> None:
        pass

    @abstractmethod
    def get_active_signals(self) -> List[Signal]:
        pass

    @abstractmethod
    def get_performance_stats(self) -> dict:
        pass

    @abstractmethod
    def save_volatility(self, pair: str, atr_avg: float, vol_score: float, is_golden: bool) -> None:
        pass

    @abstractmethod
    def get_golden_pairs(self) -> List[str]:
        pass

    @abstractmethod
    def expire_old_signals(self, expiry_hours: int) -> int:
        pass


class SQLiteRepository(SignalRepository):
    """SQLite implementation of signal repository."""

    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _init_db(self) -> None:
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

    def save_signal(self, signal: Signal) -> None:
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

    def update_signal(self, signal_id: str, **kwargs) -> None:
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
            rows = conn.execute(
                "SELECT * FROM signals WHERE status IN ('PENDING','ACTIVE','TP1_HIT')"
            ).fetchall()
            return [Signal(
                id=r[0], pair=r[1], direction=SignalDirection(r[2]), entry_price=r[3],
                sl_price=r[4], tp1_price=r[5], tp2_price=r[6], fib_level=r[7],
                htf_bias=r[8], rsi_value=r[9], atr_value=r[10], neural_score=r[11],
                neural_commentary=r[12], news_risk=r[13], status=SignalStatus(r[14]),
                created_at=r[15], updated_at=r[16], result=r[17], net_r=r[18]
            ) for r in rows]

    def get_performance_stats(self) -> dict:
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

    def save_volatility(self, pair: str, atr_avg: float, vol_score: float, is_golden: bool) -> None:
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
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=expiry_hours)).isoformat()
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "UPDATE signals SET status='EXPIRED', updated_at=? WHERE status='PENDING' AND created_at < ?",
                (datetime.now(timezone.utc).isoformat(), cutoff)
            )
            conn.commit()
            return cursor.rowcount