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

## 🏗️ Architecture

```
god_mode.py          # Main bot (Telegram + Scheduler + Engine)
forex_dashboard.py   # Streamlit web UI (Equity curve, Heatmap, Logs)
requirements.txt     # Dependencies
Procfile             # Railway/Render deployment
.env.example         # Configuration template
```

## 📦 Data Pipeline (Cascade Redundancy)

1. **Twelve Data** (Primary) — Intraday OHLC
2. **Frankfurter** (Fallback) — Daily FX rates
3. **Synthetic** (Last resort) — Generated for testing

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
| `/update <ID> <WIN\|LOSS>` | Close trade manually |
| `/weekly` | Generate weekly audit |

### Signal UX
- **Sequential delivery** — 3s delay between signals
- **Instant-copy** — All values in MarkdownV2 code blocks
- **Visual structure** — Dividers, emojis, clear sections

## 📊 Streamlit Dashboard

Run: `streamlit run forex_dashboard.py`

Tabs:
1. **Equity Curve** — Cumulative R + Daily P&L bars
2. **AI Bias Heatmap** — Neural score by pair × direction
3. **Signal Log** — Filterable, color-coded table
4. **Performance** — Win rate, profit factor, R-distribution
5. **Volatility** — Evolution engine rankings
6. **AI Commentary** — Expandable reasoning per signal

## 🚀 Deployment (Railway / Render)

```bash
# 1. Push to GitHub
# 2. Connect repo to Railway/Render
# 3. Add env vars from .env.example
# 4. Deploy (Procfile: `web: python god_mode.py`)
```

## 🔧 Local Development

```bash
cd forex-signal-system
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your keys
python god_mode.py
```

## 📈 Weekly Audit Report (Auto)

Every **Friday 16:00 UTC** → Telegram:
- Weekly Win/Loss + Net R
- **MVP Pair** (most profitable)
- Open positions audit (age, status)

## 📝 License

MIT — Build, test, deploy, evolve.