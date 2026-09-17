#!/usr/bin/env python3
"""scheduler/jobs.py — Background scheduler for signal scanning and monitoring."""

import logging
import time
import schedule
import asyncio
import threading

from config import CONFIG
from orchestrator.signals import SignalOrchestrator
from evolution.scanner import EvolutionEngine
from telegram.bot import TelegramBot

logger = logging.getLogger(__name__)


def run_scheduler(
    orchestrator: SignalOrchestrator,
    evolution: EvolutionEngine,
    bot: TelegramBot
) -> None:
    """Run the background scheduler in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_async(coro):
        await coro

    # Scan every 15 minutes
    schedule.every(15).minutes.do(
        lambda: loop.run_until_complete(run_async(orchestrator.scan_all_pairs()))
    )
    # Monitor every 5 minutes
    schedule.every(5).minutes.do(
        lambda: loop.run_until_complete(run_async(orchestrator.monitor_active_signals()))
    )
    # Rebalance weekly (Monday 00:00 UTC)
    schedule.every().monday.at("00:00").do(evolution.rebalance_golden_pairs)
    # Weekly audit report (Friday 16:00 UTC)
    schedule.every().friday.at("16:00").do(
        lambda: loop.run_until_complete(run_async(bot.send_weekly_report()))
    )

    logger.info("Scheduler started: scan every 15m, monitor every 5m, rebalance Mon 00:00, report Fri 16:00")
    while True:
        schedule.run_pending()
        time.sleep(30)