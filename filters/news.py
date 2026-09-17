#!/usr/bin/env python3
"""filters/news.py — News circuit breaker filter."""

import json
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict

from config import CONFIG

logger = logging.getLogger(__name__)


class NewsFilter:
    def __init__(self):
        self.cache: Dict[str, str] = {}
        self.cache_ttl = 3600

    async def check_high_impact(self, pair: str) -> str:
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
            for article in data.get("articles") or []:
                text = f"{article.get('title', '')} {article.get('description', '')}".lower()
                for kw in CONFIG.HIGH_IMPACT_KEYWORDS:
                    if kw.lower() in text:
                        pub = article.get("publishedAt", "")
                        if pub:
                            try:
                                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                if (datetime.now(timezone.utc) - pub_dt).total_seconds() < 86400:
                                    risk = "HIGH_RISK"
                                    break
                            except Exception:
                                pass
                if risk == "HIGH_RISK":
                    break

            self.cache[cache_key] = risk
            return risk
        except Exception as e:
            logger.error(f"News check failed: {e}")
            return "ERROR"


NEWS_FILTER = NewsFilter()