#!/usr/bin/env python3
"""neural/brain.py — Neural analysis via NVIDIA NIM (Llama 3.1)."""

import json
import logging
from typing import Tuple

from openai import AsyncOpenAI

from config import CONFIG
from models.signals import MarketData

logger = logging.getLogger(__name__)


class NeuralBrain:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=CONFIG.NVIDIA_NIM_API_KEY,
            base_url=CONFIG.NVIDIA_NIM_BASE_URL
        ) if CONFIG.NVIDIA_NIM_API_KEY else None

    async def analyze(self, md: MarketData, signal_data: dict) -> Tuple[float, str]:
        if not self.client:
            return 5.0, "Neural brain not configured (no NVIDIA NIM API key)."

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
            result = json.loads(resp.choices[0].message.content or "{}")
            score = max(0, min(10, float(result.get("score", 5))))
            commentary = result.get("commentary", "No commentary provided.")
            return score, commentary
        except Exception as e:
            logger.error(f"Neural analysis failed: {e}")
            return 5.0, f"Neural analysis error: {str(e)[:100]}"


NEURAL = NeuralBrain()