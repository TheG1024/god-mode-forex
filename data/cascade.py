#!/usr/bin/env python3
"""data/cascade.py — Cascade data provider with fallback chain."""

from typing import Optional
import pandas as pd
import logging

from data.providers import DataProvider, PROVIDERS
from config import CONFIG

logger = logging.getLogger(__name__)


class CascadeProvider:
    """Cascades through data providers until one succeeds."""

    def __init__(self, providers: Optional[list[DataProvider]] = None):
        self.providers = providers or PROVIDERS

    def fetch(self, pair: str, interval: str = "1h", outputsize: int = 200) -> Optional[pd.DataFrame]:
        for provider in self.providers:
            name = provider.__class__.__name__
            try:
                df = provider.fetch(pair, interval, outputsize)
                if df is not None and len(df) >= 50:
                    logger.info(f"Data for {pair} from {name}: {len(df)} candles")
                    return df
            except Exception as e:
                logger.warning(f"{name} failed for {pair}: {e}")
        logger.error(f"All data sources failed for {pair}")
        return None