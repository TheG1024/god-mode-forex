#!/usr/bin/env python3
"""evolution/scanner.py — Volatility scanner and evolution engine."""

import logging
import threading
from typing import List, Tuple

from config import CONFIG
from data.cascade import CascadeProvider
from data.repository import SignalRepository
from analysis.indicators import atr

logger = logging.getLogger(__name__)


class EvolutionEngine:
    def __init__(self, repo: SignalRepository, cascade: CascadeProvider):
        self.repo = repo
        self.cascade = cascade
        self.lock = threading.Lock()

    def scan_volatility(self, pairs: List[str]) -> List[Tuple[str, float]]:
        results = []
        for pair in pairs:
            try:
                df = self.cascade.fetch(pair, "1h")
                if df is None or len(df) < 50:
                    continue
                df["atr"] = atr(df["high"], df["low"], df["close"], 14)
                atr_avg = df["atr"].tail(20).mean()
                current_price = df["close"].iloc[-1]
                vol_score = (atr_avg / current_price) * 10000
                results.append((pair, vol_score))
                self.repo.save_volatility(pair, atr_avg, vol_score, False)
            except Exception as e:
                logger.error(f"Volatility scan failed for {pair}: {e}")
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def rebalance_golden_pairs(self):
        logger.info("Starting weekly volatility rebalance...")
        with self.lock:
            ranked = self.scan_volatility(CONFIG.ALL_PAIRS)
            golden = [p for p, _ in ranked[:CONFIG.TOP_VOLATILE_COUNT]]
            for pair, score in ranked:
                is_golden = pair in golden
                self.repo.save_volatility(pair, score, score, is_golden)
            CONFIG.SCAN_PAIRS = golden
            logger.info(f"Golden Pairs updated: {golden}")

    def get_golden_pairs(self) -> List[str]:
        golden = self.repo.get_golden_pairs()
        if golden:
            return golden
        ranked = self.scan_volatility(CONFIG.ALL_PAIRS)
        golden = [p for p, _ in ranked[:CONFIG.TOP_VOLATILE_COUNT]]
        for pair, score in ranked:
            self.repo.save_volatility(pair, score, score, pair in golden)
        CONFIG.SCAN_PAIRS = golden
        return golden


EVOLUTION = None  # Will be initialized in main