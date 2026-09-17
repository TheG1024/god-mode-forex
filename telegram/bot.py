#!/usr/bin/env python3
"""telegram/bot.py — Telegram bot for God Mode Forex."""

from typing import Optional
import logging
import uuid
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import CONFIG
from data.repository import SignalRepository
from models.signals import Signal, SignalStatus, SignalDirection
from orchestrator.signals import SignalOrchestrator
from evolution.scanner import EvolutionEngine

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(
        self,
        orchestrator: SignalOrchestrator,
        evolution: EvolutionEngine,
        repo: SignalRepository
    ):
        self.orchestrator = orchestrator
        self.evolution = evolution
        self.repo = repo
        self.app = None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 *God Mode Forex Signal Bot*\n\n"
            "Commands:\n"
            "/scan — Run manual scan\n"
            "/signals — List active signals\n"
            "/performance — Show stats\n"
            "/golden — Show current Golden Pairs\n"
            "/rebalance — Force volatility rebalance\n"
            "/update <ID> <WIN|LOSS> — Manual result update\n"
            "/weekly — Generate weekly audit report\n"
            "/help — This message",
            parse_mode="Markdown"
        )

    async def scan_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 Scanning Golden Pairs...")
        signals = await self.orchestrator.scan_all_pairs()
        if not signals:
            await update.message.reply_text("No Deep OTE setups found.")
            return
        await update.message.reply_text(f"✅ {len(signals)} signal(s) generated and sent.")

    async def signals_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        active = self.repo.get_active_signals()
        if not active:
            await update.message.reply_text("No active signals.")
            return

        msg = "*Active Signals:*\n\n"
        for s in active:
            msg += (
                f"`{s.id}` {s.pair} {s.direction.value}\n"
                f"Entry: {s.entry_price:.5f} | SL: {s.sl_price:.5f}\n"
                f"TP1: {s.tp1_price:.5f} (1R) | TP2: {s.tp2_price:.5f} (2R)\n"
                f"Neural: {s.neural_score:.1f}/10 | News: {s.news_risk}\n"
                f"Status: {s.status.value}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def performance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.repo.get_performance_stats()
        msg = (
            f"📊 *Performance Stats*\n\n"
            f"Total Trades: {stats['total']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Net R: {stats['net_r']:.2f}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def golden_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        golden = self.evolution.get_golden_pairs()
        msg = "*Golden Pairs (Top 12 by Volatility):*\n\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(golden))
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def rebalance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⚙️ Running volatility rebalance...")
        self.evolution.rebalance_golden_pairs()
        await self.golden_cmd(update, context)

    async def update_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /update <ID> <WIN|LOSS>")
            return
        signal_id, result = context.args
        result = result.upper()
        if result not in ("WIN", "LOSS"):
            await update.message.reply_text("Result must be WIN or LOSS")
            return

        signal = self.repo.get_signal(signal_id)
        if not signal:
            await update.message.reply_text(f"Signal {signal_id} not found")
            return

        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
            reward = risk if result == "WIN" else -risk
        else:
            risk = signal.sl_price - signal.entry_price
            reward = risk if result == "WIN" else -risk
        net_r = reward / risk if risk else 0

        self.repo.update_signal(signal_id,
            status=SignalStatus.TP2_HIT if result == "WIN" else SignalStatus.SL_HIT,
            result=result, net_r=net_r, updated_at=datetime.now(timezone.utc).isoformat()
        )
        await update.message.reply_text(f"✅ Signal {signal_id} updated: {result} | Net R: {net_r:.2f}")

    async def weekly_report_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.send_weekly_report()

    async def send_weekly_report(self):
        if not CONFIG.TELEGRAM_CHAT_ID:
            return

        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        import sqlite3
        import pandas as pd

        with sqlite3.connect(CONFIG.DB_PATH) as conn:
            closed = pd.read_sql("""
                SELECT * FROM signals
                WHERE result IN ('WIN','LOSS') AND updated_at >= ?
                ORDER BY updated_at DESC
            """, conn, params=(week_ago,))
            open_pos = pd.read_sql("""
                SELECT * FROM signals
                WHERE status IN ('PENDING','ACTIVE','TP1_HIT')
                ORDER BY created_at DESC
            """, conn)

        total_closed = len(closed)
        wins = len(closed[closed['result'] == 'WIN']) if total_closed else 0
        losses = len(closed[closed['result'] == 'LOSS']) if total_closed else 0
        win_rate = (wins / total_closed * 100) if total_closed else 0
        net_r = closed['net_r'].sum() if total_closed else 0.0

        mvp_pair = "—"
        mvp_r = 0.0
        if total_closed:
            pair_stats = closed.groupby('pair')['net_r'].sum()
            mvp_pair = pair_stats.idxmax()
            mvp_r = pair_stats.max()

        msg = f"📋 *WEEKLY AUDIT REPORT* 📋\n"
        msg += f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d')} 16:00 UTC\n\n"

        msg += f"📊 *This Week's Closed Trades*\n"
        msg += f"   Total: {total_closed} | Wins: {wins} | Losses: {losses}\n"
        msg += f"   Win Rate: {win_rate:.1f}%\n"
        msg += f"   Net R: {net_r:+.2f}R\n\n"

        msg += f"🏆 *MVP Pair*: {mvp_pair} ({mvp_r:+.2f}R)\n\n"

        msg += f"📌 *Open Positions Audit* ({len(open_pos)} open)\n"
        if len(open_pos) == 0:
            msg += "   No open positions.\n"
        else:
            for _, row in open_pos.iterrows():
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at'])).days
                msg += f"   `{row['id']}` {row['pair']} {row['direction']} | {row['status']} | {age_days}d old\n"

        try:
            await self.app.bot.send_message(
                chat_id=CONFIG.TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown"
            )
            logger.info("Weekly report sent")
        except Exception as e:
            logger.error(f"Weekly report send failed: {e}")

    async def send_signal_alert(self, signal: Signal):
        if not CONFIG.TELEGRAM_CHAT_ID:
            return

        emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
        risk_emoji = "🚨" if signal.news_risk == "HIGH_RISK" else "✅"

        def code(val): return f"`{val}`"

        lines = [
            f"{emoji} *NEW DEEP OTE SIGNAL* {emoji}",
            "━━━━━━━━━━━━━━━━━━",
            "",
            f"🆔 *ID:* {code(signal.id)}",
            f"💱 *Pair:* {code(signal.pair)} — {code(signal.direction.value)}",
            "",
            "📊 *BIAS & STRUCTURE*",
            f"   HTF Bias: {code(signal.htf_bias)}",
            f"   Fib Level: {code(f'{signal.fib_level:.1%}')} (Deep OTE 79-88%)",
            f"   RSI: {code(f'{signal.rsi_value:.1f}')}",
            f"   ATR: {code(f'{signal.atr_value:.5f}')}",
            "",
            "🎯 *TARGETS*",
            f"   Entry: {code(f'{signal.entry_price:.5f}')}",
            f"   SL: {code(f'{signal.sl_price:.5f}')}",
            f"   TP1 (1R): {code(f'{signal.tp1_price:.5f}')}",
            f"   TP2 (2R): {code(f'{signal.tp2_price:.5f}')}",
            "",
            f"🧠 *NEURAL GRADE:* {code(f'{signal.neural_score:.1f}/10')}",
            f"{risk_emoji} *News Risk:* {code(signal.news_risk)}",
            "━━━━━━━━━━━━━━━━━━",
            "",
            f"💬 *AI REASONING*",
            signal.neural_commentary
        ]
        msg = "\n".join(lines)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"win_{signal.id}"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"loss_{signal.id}")
        ]])

        try:
            await self.app.bot.send_message(
                chat_id=CONFIG.TELEGRAM_CHAT_ID, text=msg,
                parse_mode="MarkdownV2", reply_markup=keyboard
            )
            logger.info(f"Signal alert sent: {signal.id}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, signal_id = query.data.split("_", 1)
        result = "WIN" if action == "win" else "LOSS"

        signal = self.repo.get_signal(signal_id)
        if not signal:
            await query.edit_message_text("Signal not found")
            return

        if signal.direction == SignalDirection.LONG:
            risk = signal.entry_price - signal.sl_price
        else:
            risk = signal.sl_price - signal.entry_price
        reward = risk if result == "WIN" else -risk
        net_r = reward / risk if risk else 0

        self.repo.update_signal(signal_id,
            status=SignalStatus.TP2_HIT if result == "WIN" else SignalStatus.SL_HIT,
            result=result, net_r=net_r, updated_at=datetime.now(timezone.utc).isoformat()
        )

        await query.edit_message_text(
            f"{query.message.text}\n\n✅ *Updated: {result} | Net R: {net_r:.2f}*",
            parse_mode="Markdown"
        )

    def run(self):
        if not CONFIG.TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram bot token not set, skipping")
            return

        self.app = Application.builder().token(CONFIG.TELEGRAM_BOT_TOKEN).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("scan", self.scan_cmd))
        self.app.add_handler(CommandHandler("signals", self.signals_cmd))
        self.app.add_handler(CommandHandler("performance", self.performance_cmd))
        self.app.add_handler(CommandHandler("golden", self.golden_cmd))
        self.app.add_handler(CommandHandler("rebalance", self.rebalance_cmd))
        self.app.add_handler(CommandHandler("update", self.update_cmd))
        self.app.add_handler(CommandHandler("weekly", self.weekly_report_cmd))
        self.app.add_handler(CommandHandler("help", self.start))
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))

        logger.info("Telegram bot started — deleting any existing webhook")
        self.app.run_polling(drop_pending_updates=True)