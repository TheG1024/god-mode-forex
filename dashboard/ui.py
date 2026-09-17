#!/usr/bin/env python3
"""dashboard/ui.py — UI rendering functions for Streamlit dashboard."""

import streamlit as st
import pandas as pd
import numpy as np

from config import CONFIG
from models.signals import SignalStatus, SignalDirection
from dashboard.charts import (
    equity_curve, ai_bias_heatmap, volatility_bar, r_distribution
)

# Lazy imports for sidebar
def _lazy_imports():
    import sqlite3
    from config import CONFIG
    from evolution.scanner import EvolutionEngine
    from data.repository import SQLiteRepository
    from data.cascade import CascadeProvider
    from data.providers import PROVIDERS
    return sqlite3, CONFIG, EvolutionEngine, SQLiteRepository, CascadeProvider, PROVIDERS


def render_sidebar():
    st.sidebar.title("🤖 God Mode Forex")
    st.sidebar.caption("SMC Deep OTE + Neural Analysis")

    st.sidebar.divider()

    # Quick stats
    import sqlite3
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        signals_df = pd.read_sql("SELECT * FROM signals ORDER BY created_at DESC", conn)

    if not signals_df.empty:
        import sqlite3 as sql
        with sql.connect(CONFIG.DB_PATH) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                    SUM(net_r) as net_r
                FROM signals WHERE result IN ('WIN','LOSS')
            """).fetchone()
        total, wins, losses, net_r = row
        stats = {"total": total or 0, "wins": wins or 0, "losses": losses or 0, "net_r": net_r or 0.0,
                 "win_rate": (wins / total * 100) if total else 0.0}
        st.sidebar.metric("Total Signals", stats['total'])
        st.sidebar.metric("Win Rate", f"{stats['win_rate']:.1f}%")
        st.sidebar.metric("Net R", f"{stats['net_r']:.2f}")

    st.sidebar.divider()

    # Golden pairs
    from evolution.scanner import EvolutionEngine
    from data.repository import SQLiteRepository
    from data.cascade import CascadeProvider
    from config import CONFIG

    repo = SQLiteRepository(CONFIG.DB_PATH)
    from data.cascade import CascadeProvider
    from data.providers import PROVIDERS
    cascade = CascadeProvider(PROVIDERS)
    evolution = EvolutionEngine(repo, cascade)
    golden = evolution.get_golden_pairs()

    st.sidebar.subheader("🏆 Golden Pairs")
    for i, p in enumerate(golden, 1):
        st.sidebar.caption(f"{i}. {p}")

    if st.sidebar.button("🔄 Force Rebalance"):
        evolution.rebalance_golden_pairs()
        st.sidebar.success("Rebalanced!")
        st.rerun()


def render_signal_log(signals_df: pd.DataFrame):
    st.subheader("📋 Signal Log")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_filter = st.multiselect(
            "Status", options=signals_df['status'].unique() if not signals_df.empty else [],
            default=list(signals_df['status'].unique()) if not signals_df.empty else []
        )
    with col2:
        direction_filter = st.multiselect(
            "Direction", options=['LONG', 'SHORT'],
            default=['LONG', 'SHORT']
        )
    with col3:
        pair_filter = st.multiselect(
            "Pair", options=sorted(signals_df['pair'].unique()) if not signals_df.empty else [],
            default=[]
        )
    with col4:
        min_score = st.slider("Min Neural Score", 0.0, 10.0, 0.0, 0.5)

    # Apply filters
    filtered = signals_df.copy()
    if status_filter:
        filtered = filtered[filtered['status'].isin(status_filter)]
    if direction_filter:
        filtered = filtered[filtered['direction'].isin(direction_filter)]
    if pair_filter:
        filtered = filtered[filtered['pair'].isin(pair_filter)]
    filtered = filtered[filtered['neural_score'] >= min_score]

    if filtered.empty:
        st.info("No signals match filters.")
        return

    display_df = filtered[[
        'id', 'pair', 'direction', 'entry_price', 'sl_price', 'tp1_price', 'tp2_price',
        'fib_level', 'htf_bias', 'rsi_value', 'neural_score', 'news_risk', 'status',
        'result', 'net_r', 'created_at'
    ]].copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['fib_level'] = display_df['fib_level'].apply(lambda x: f"{x:.1%}")
    display_df['net_r'] = display_df['net_r'].apply(lambda x: f"{x:.2f}" if x != 0 else "—")

    def style_status(val):
        colors = {
            'PENDING': 'background-color: #ffa500; color: black',
            'ACTIVE': 'background-color: #00bfff; color: white',
            'TP1_HIT': 'background-color: #32cd32; color: white',
            'TP2_HIT': 'background-color: #00ff00; color: black',
            'SL_HIT': 'background-color: #ff4444; color: white',
            'CANCELLED': 'background-color: #888888; color: white',
            'EXPIRED': 'background-color: #888888; color: white'
        }
        return colors.get(val, '')

    def style_result(val):
        if val == 'WIN': return 'background-color: #00ff88; color: black; font-weight: bold'
        if val == 'LOSS': return 'background-color: #ff4444; color: white; font-weight: bold'
        return ''

    styled = display_df.style.applymap(style_status, subset=['status']).applymap(style_result, subset=['result'])
    st.dataframe(styled, use_container_width=True, height=500)


def render_performance_metrics(signals_df: pd.DataFrame):
    st.subheader("📊 Performance Metrics")

    closed = signals_df[signals_df['result'].isin(['WIN', 'LOSS'])]
    if closed.empty:
        st.info("No closed trades for metrics.")
        return

    total = len(closed)
    wins = len(closed[closed['result'] == 'WIN'])
    losses = len(closed[closed['result'] == 'LOSS'])
    win_rate = wins / total * 100 if total else 0
    net_r = closed['net_r'].sum()
    avg_r = closed['net_r'].mean()
    max_dd = (closed['net_r'].cumsum().cummax() - closed['net_r'].cumsum()).max()

    win_r = closed[closed['result'] == 'WIN']['net_r'].mean() if wins else 0
    loss_r = closed[closed['result'] == 'LOSS']['net_r'].mean() if losses else 0
    profit_factor = abs(win_r * wins / (loss_r * losses)) if losses and loss_r != 0 else float('inf')

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Trades", total)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Net R", f"{net_r:.2f}")
    col4.metric("Avg R/Trade", f"{avg_r:.2f}")
    col5.metric("Max Drawdown", f"{max_dd:.2f}R")
    col6.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞")

    # Distribution
    st.subheader("R-Multiple Distribution")
    from dashboard.charts import r_distribution
    r_distribution(signals_df)


def render_neural_commentary(signals_df: pd.DataFrame):
    st.subheader("💬 Recent AI Commentary")

    recent = signals_df.head(10)
    if recent.empty:
        st.info("No signals yet.")
        return

    for _, row in recent.iterrows():
        with st.expander(f"{row['pair']} {row['direction']} | Neural: {row['neural_score']:.1f}/10 | {row['status']} | {row['created_at'][:16]}"):
            st.markdown(f"""
**Entry:** {row['entry_price']:.5f} | **SL:** {row['sl_price']:.5f} | **TP1:** {row['tp1_price']:.5f} | **TP2:** {row['tp2_price']:.5f}
- **Fib Level:** {row['fib_level']:.1%} (Deep OTE)
- **HTF Bias:** {row['htf_bias']}
- **RSI:** {row['rsi_value']:.1f}
- **News Risk:** {row['news_risk']}
- **Result:** {row['result'] or 'Pending'} ({row['net_r']:.2f}R)
---
{row['neural_commentary']}
""")