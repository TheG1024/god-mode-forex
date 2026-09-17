# 🤖 God Mode Forex Signal System

Professional-grade automated Forex signal system combining **SMC Deep OTE strategy** with **LLM neural analysis** (NVIDIA NIM / Llama 3.1 70B).

## 🎯 Strategy: Deep OTE (Optimal Trade Entry)

| Component | Logic |
|-----------|-------|
| **Core** | Strong displacement (Swing High → Low) |
| **Entry Zone** | 79%–88% Fibonacci retracement (Deep OTE) |
| **HTF Bias** | EMA 20/50 alignment |
| **RSI** | Confirmation (not overbought/oversold) |
| **SL** | Beyond 100% fib + 0.5 ATR |
| **TP1** | 1R |
| **TP2** | 2R |

## 🏗️ Architecture (Modular, DI-Wired)

```
forex-signal-system/
├── config.py                 # Config dataclass (single source of truth)
├── main.py                   # Entry: DI wire-up, health + scheduler + bot
├── models/
│   └── signals.py            # Signal, SignalStatus, SignalDirection, MarketData
├── data/
│   ├── providers.py          # 6 data provider implementations
│   ├── cascade.py            # Fallback chain: TwelveData → Quotient → yfinance → FCS → AlphaVantage → Frankfurter
│   └── repository.py         # SignalRepository protocol + SQLite impl
├── analysis/
│   ├── indicators.py         # Pure: ema, rsi, atr, swings, fib
│   ├── detector.py           # Deep OTE detection only
│   └── market.py             # MarketAnalyzer using indicators + detector
├── neural/
│   └── brain.py              # NVIDIA NIM client (Llama 3.1 70B)
├── filters/
│   └── news.py               # NewsAPI circuit breaker
├── evolution/
│   └── scanner.py            # Weekly volatility scan 39→12 pairs
├── orchestrator/
│   └── signals.py            # SignalOrchestrator: scan → neural → news → monitor → resolve
├── telegram/
│   └── bot.py                # Commands + inline WIN/LOSS buttons + weekly report
├── health/
│   └── server.py             # /health endpoint for Render
├── scheduler/
│   └── jobs.py               # 15m scan, 5m monitor, Mon rebalance, Fri 16:00 report
├── dashboard/
│   ├── app.py                # Streamlit entry
│   ├── data.py               # load_signals, load_volatility, load_performance
│   ├── charts.py             # equity_curve, ai_bias_heatmap, volatility_bar, r_distribution
│   └── ui.py                 # render_sidebar, render_signal_log, render_performance_metrics, render_neural_commentary
├── tests/
│   └── test_indicators.py    # Pure function tests
├── requirements.txt
├── Procfile                  # web: python main.py
├── render.yaml               # Render deployment
├── .env.example              # Config template
└── README.md
```

## 📦 Data Pipeline (Cascade Redundancy)

1. **Twelve Data** (Primary) — Intraday OHLC
2. **Quotient** (RapidAPI) — Real OHLC + volume
3. **yfinance** (Free) — Yahoo Finance backup
4. **FCS API** — 500 calls/month free
5. **Alpha Vantage** — 500 calls/day free
6. **Frankfurter** (Free, no key) — Daily FX rates

## 🧠 Neural Brain

- **Provider:** NVIDIA NIM (`meta/llama-3.1-70b-instruct`)
- **Output:** Neural Score (0–10) + Professional commentary
- **Input:** Raw OHLC, EMA, RSI, Fib levels, structure

## ⚠️ Guardrails

- **News Circuit Breaker** — NewsAPI scans for Red Folder events (NFP, CPI, FOMC, etc.)
- **Evolution Engine** — Weekly rebalance: scans 39 pairs → rotates top 12 by volatility

## 💾 Persistence

- **SQLite** — Signals, volatility history, performance
- **Unique ID** — Every signal tracked
- **Commands:** `/update <ID> <WIN|LOSS>` → auto-calculates Net R

## 📱 Telegram Bot

| Command | Description |
|---------|-------------|
| `/scan` | Manual Deep OTE scan |
| `/signals` | Active positions |
| `/performance` | Win rate, Net R |
| `/golden` | Current 12 Golden Pairs |
| `/rebalance` | Force volatility scan |
| `/update <ID> <WIN|LOSS>` | Close trade manually |
| `/weekly` | Generate weekly audit |

### Signal UX
- **Sequential delivery** — 3s delay between signals
- **Instant-copy** — All values in MarkdownV2 code blocks
- **Visual structure** — Dividers, emojis, clear sections
- **Inline WIN/LOSS buttons** — One-tap resolution

## 📊 Streamlit Dashboard

Run: `streamlit run dashboard/app.py`

Tabs:
1. **Equity Curve** — Cumulative R + Daily P&L bars
2. **AI Bias Heatmap** — Neural score by pair × direction
3. **Signal Log** — Filterable, color-coded table
4. **Performance** — Win rate, profit factor, R-distribution
5. **Volatility** — Evolution engine rankings
6. **AI Commentary** — Expandable reasoning per signal

## 🧪 Tests

```bash
cd forex-signal-system
pytest tests/test_indicators.py -v
```

## 🚀 Deployment (Railway / Render)

```bash
# 1. Push to GitHub
# 2. Connect repo to Railway/Render
# 3. Add env vars from .env.example
# 4. Deploy (Procfile: `web: python main.py`)
```

## 🔧 Local Development

```bash
cd forex-signal-system
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your keys
python main.py
```

## 📈 Weekly Audit Report (Auto)

Every **Friday 16:00 UTC** → Telegram:
- Weekly Win/Loss + Net R
- **MVP Pair** (most profitable)
- Open positions audit (age, status)

## 📝 License

MIT — Build, test, deploy, evolve.

---

*Last updated: 2026-09-17*