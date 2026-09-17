#!/usr/bin/env python3
"""main.py — Entry point for God Mode Forex Signal System."""

import logging
import threading
import asyncio
import sys

from config import CONFIG
from data.repository import SQLiteRepository
from data.cascade import CascadeProvider
from data.providers import PROVIDERS
from analysis.market import MarketAnalyzer
from analysis.detector import DETECTOR
from neural.brain import NEURAL
from filters.news import NEWS_FILTER
from evolution.scanner import EvolutionEngine
from orchestrator.signals import SignalOrchestrator
from telegram.bot import TelegramBot
from health.server import start_health_server
from scheduler.jobs import run_scheduler

# Configure logging
logging.basicConfig(
    level=getattr(logging, CONFIG.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("god_mode.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("GOD MODE FOREX SIGNAL SYSTEM — STARTING")
    logger.info("=" * 60)

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize data layer
    repo = SQLiteRepository(CONFIG.DB_PATH)
    cascade = CascadeProvider(PROVIDERS)

    # Initialize analysis layer
    analyzer = MarketAnalyzer(cascade)
    detector = DETECTOR
    neural = NEURAL
    news = NEWS_FILTER
    evolution = EvolutionEngine(repo, cascade)

    # Initialize orchestrator
    orchestrator = SignalOrchestrator(repo, analyzer, evolution)

    # Initialize telegram bot
    bot = TelegramBot(orchestrator, evolution, repo)

    # Global references for telegram bot callbacks
    global ORCHESTRATOR, EVOLUTION
    ORCHESTRATOR = orchestrator
    EVOLUTION = evolution

    # Start health check server
    start_health_server()

    # Initial golden pairs
    evolution.get_golden_pairs()

    # Start scheduler thread
    scheduler_thread = threading.Thread(
        target=run_scheduler, args=(orchestrator, evolution, bot), daemon=True
    )
    scheduler_thread.start()

    # Run telegram bot (blocking)
    bot.run()


if __name__ == "__main__":
    main()