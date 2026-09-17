#!/usr/bin/env python3
"""orchestrator/signals.py — Signal orchestration: scan, monitor, resolve."""

import logging
import uuid
from typing import List
from datetime import datetime, timezone

from config import CONFIG
from models.signals import Signal, SignalStatus, SignalDirection
from data.repository import SignalRepository
from analysis.market import MarketAnalyzer
from analysis.detector import DETECTOR
from neural.brain import NEURAL
from filters.news import NEWS_FILTER
from evolution.scanner import EvolutionEngine

logger = logging.getLogger(__name__)


class SignalOrchestrator:
    def __init__(
        self,
        repo: SignalRepository,
        analyzer: MarketAnalyzer,
        evolution: EvolutionEngine
    ):
        self.repo = repo
        self.analyzer = analyzer
        self.evolution = evolution

    async def scan_all_pairs(self) -> List[Signal]:
        signals = []
        pairs = self.evolution.get_golden_pairs()
        logger.info(f"Scanning {len(pairs)} golden pairs...")

        for pair in pairs:
            try:
                md = self.analyzer.analyze(pair, "1h")
                if not md:
                    continue

                sig_data = DETECTOR.check_deep_ote(md)
                if not sig_data:
                    continue

                neural_score, neural_commentary = await NEURAL.analyze(md, sig_data)
                if neural_score < 6.0:
                    logger.info(f"{pair}: Neural score {neural_score:.1f} < 6, skipping")
                    continue

                news_risk = await NEWS_FILTER.check_high_impact(pair)

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

                self.repo.save_signal(signal)
                signals.append(signal)
                logger.info(f"Signal generated: {signal_id} | {pair} {signal.direction.value} | Neural: {neural_score:.1f}")

            except Exception as e:
                logger.error(f"Scan failed for {pair}: {e}")

        return signals

    async def monitor_active_signals(self):
        expired_count = self.repo.expire_old_signals(CONFIG.SIGNAL_EXPIRY_HOURS)
        if expired_count:
            logger.info(f"Expired {expired_count} stale PENDING signals")

        active = self.repo.get_active_signals()
        for signal in active:
            try:
                df = self.analyzer.cascade.fetch(signal.pair, "1h")
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
        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
            reward = exit_price - signal.entry_price
        else:
            risk = signal.sl_price - signal.entry_price
            reward = signal.entry_price - exit_price

        net_r = reward / risk if risk != 0 else 0

        self.repo.update_signal(signal.id,
            status=SignalStatus(result),
            result="WIN" if net_r > 0 else "LOSS",
            net_r=net_r,
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        logger.info(f"Signal {signal.id} resolved: {result} | Net R: {net_r:.2f}")


ORCHESTRATOR = None  # Will be initialized in main