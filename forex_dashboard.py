#!/usr/bin/env python3
"""
forex_dashboard.py — Streamlit Dashboard for God Mode Forex System
Equity curve, AI-bias heatmap, signal log, performance metrics.
"""

import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import sys

sys.path.append(os.path.dirname(__file__))
from god_mode import CONFIG, DB, SignalStatus, SignalDirection, EVOLUTION

st.set_page_config(
    page_title="God Mode Forex Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_signals():
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM signals ORDER BY created_at DESC", conn)
    return df

@st.cache_data(ttl=30)
def load_volatility():
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM pair_volatility ORDER BY volatility_score DESC", conn)
    return df

@st.cache_data(ttl=30)
def load_performance():
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM performance ORDER BY date", conn)
    return df

# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def compute_equity_curve(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Build equity curve from closed trades."""
    closed = signals_df[signals_df['result'].isin(['WIN', 'LOSS'])].copy()
    if closed.empty:
        return pd.DataFrame(columns=['date', 'cumulative_r', 'trade_r', 'pair'])
    
    closed['created_at'] = pd.to_datetime(closed['created_at'])
    closed = closed.sort_values('created_at')
    closed['cumulative_r'] = closed['net_r'].cumsum()
    return closed[['created_at', 'cumulative_r', 'net_r', 'pair', 'direction']].rename(
        columns={'created_at': 'date', 'net_r': 'trade_r'}
    )

def compute_daily_pnl(signals_df: pd.DataFrame) -> pd.DataFrame:
    closed = signals_df[signals_df['result'].isin(['WIN', 'LOSS'])].copy()
    if closed.empty:
        return pd.DataFrame(columns=['date', 'daily_r', 'trades'])
    closed['created_at'] = pd.to_datetime(closed['created_at'])
    closed['date'] = closed['created_at'].dt.date
    daily = closed.groupby('date').agg(
        daily_r=('net_r', 'sum'),
        trades=('net_r', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum())
    ).reset_index()
    daily['win_rate'] = daily['wins'] / daily['trades'] * 100
    return daily

# ═══════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════

def render_sidebar():
    st.sidebar.title("🤖 God Mode Forex")
    st.sidebar.caption("SMC Deep OTE + Neural Analysis")
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
    if auto_refresh:
        st.rerun()
    
    st.sidebar.divider()
    
    # Quick stats
    signals_df = load_signals()
    if not signals_df.empty:
        stats = DB.get_performance_stats()
        st.sidebar.metric("Total Signals", stats['total'])
        st.sidebar.metric("Win Rate", f"{stats['win_rate']:.1f}%")
        st.sidebar.metric("Net R", f"{stats['net_r']:.2f}")
    
    st.sidebar.divider()
    
    # Golden pairs
    golden = EVOLUTION.get_golden_pairs()
    st.sidebar.subheader("🏆 Golden Pairs")
    for i, p in enumerate(golden, 1):
        st.sidebar.caption(f"{i}. {p}")
    
    if st.sidebar.button("🔄 Force Rebalance"):
        EVOLUTION.rebalance_golden_pairs()
        st.sidebar.success("Rebalanced!")
        st.rerun()

def render_equity_curve(signals_df: pd.DataFrame):
    st.subheader("📈 Equity Curve (Cumulative R)")
    
    equity = compute_equity_curve(signals_df)
    if equity.empty:
        st.info("No closed trades yet. Equity curve will appear after first resolved signal.")
        return
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity['date'], y=equity['cumulative_r'],
        mode='lines+markers', name='Cumulative R',
        line=dict(color='#00ff88', width=2),
        marker=dict(size=6, color=np.where(equity['trade_r'] > 0, '#00ff88', '#ff4444')),
        hovertemplate='%{x}<br>Cumulative R: %{y:.2f}<br>Trade R: %{customdata:.2f}<extra></extra>',
        customdata=equity['trade_r']
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    fig.update_layout(
        template="plotly_dark",
        height=400,
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis_title="Date",
        yaxis_title="Cumulative R",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Daily P&L bar chart
    daily = compute_daily_pnl(signals_df)
    if not daily.empty:
        fig2 = go.Figure()
        colors = ['#00ff88' if r >= 0 else '#ff4444' for r in daily['daily_r']]
        fig2.add_trace(go.Bar(
            x=daily['date'], y=daily['daily_r'],
            marker_color=colors, name='Daily R',
            hovertemplate='%{x}<br>Daily R: %{y:.2f}<br>Trades: %{customdata}<extra></extra>',
            customdata=daily['trades']
        ))
        fig2.update_layout(
            template="plotly_dark", height=250,
            margin=dict(l=40, r=20, t=20, b=40),
            xaxis_title="Date", yaxis_title="Daily R",
            showlegend=False
        )
        st.plotly_chart(fig2, use_container_width=True)

def render_ai_bias_heatmap(signals_df: pd.DataFrame):
    st.subheader("🧠 AI Bias Heatmap (Neural Score by Pair × Direction)")
    
    if signals_df.empty:
        st.info("No signals yet.")
        return
    
    # Pivot table: pair × direction, avg neural score
    heatmap_data = signals_df.groupby(['pair', 'direction'])['neural_score'].mean().unstack(fill_value=0)
    
    if heatmap_data.empty:
        st.info("No data for heatmap.")
        return
    
    # Ensure both columns exist
    for d in ['LONG', 'SHORT']:
        if d not in heatmap_data.columns:
            heatmap_data[d] = 0
    
    heatmap_data = heatmap_data[['LONG', 'SHORT']].sort_values('LONG', ascending=False)
    
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=['LONG 📈', 'SHORT 📉'],
        y=heatmap_data.index,
        colorscale='RdYlGn',
        zmin=0, zmax=10,
        text=np.round(heatmap_data.values, 1),
        texttemplate="%{text}",
        textfont={"size": 12},
        hovertemplate='Pair: %{y}<br>Direction: %{x}<br>Avg Neural Score: %{z:.1f}<extra></extra>',
        colorbar=dict(title="Neural Score")
    ))
    
    fig.update_layout(
        template="plotly_dark",
        height=max(400, len(heatmap_data) * 25 + 100),
        margin=dict(l=100, r=40, t=40, b=40),
        xaxis_title="Direction",
        yaxis_title="Pair"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary stats
    col1, col2, col3 = st.columns(3)
    with col1:
        avg_long = heatmap_data['LONG'].mean()
        st.metric("Avg LONG Score", f"{avg_long:.1f}" if not np.isnan(avg_long) else "N/A")
    with col2:
        avg_short = heatmap_data['SHORT'].mean()
        st.metric("Avg SHORT Score", f"{avg_short:.1f}" if not np.isnan(avg_short) else "N/A")
    with col3:
        best_pair = heatmap_data.max(axis=1).idxmax()
        best_score = heatmap_data.max(axis=1).max()
        st.metric("Best Pair", f"{best_pair} ({best_score:.1f})")

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
    
    # Display
    if filtered.empty:
        st.info("No signals match filters.")
        return
    
    # Format for display
    display_df = filtered[[
        'id', 'pair', 'direction', 'entry_price', 'sl_price', 'tp1_price', 'tp2_price',
        'fib_level', 'htf_bias', 'rsi_value', 'neural_score', 'news_risk', 'status',
        'result', 'net_r', 'created_at'
    ]].copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['fib_level'] = display_df['fib_level'].apply(lambda x: f"{x:.1%}")
    display_df['net_r'] = display_df['net_r'].apply(lambda x: f"{x:.2f}" if x != 0 else "—")
    
    # Color coding
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
    
    # Risk-adjusted metrics
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
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=closed['net_r'], nbinsx=20,
        marker_color='#00bfff', opacity=0.7,
        name='All Trades'
    ))
    fig.add_trace(go.Histogram(
        x=closed[closed['result'] == 'WIN']['net_r'], nbinsx=20,
        marker_color='#00ff88', opacity=0.7, name='Wins'
    ))
    fig.add_trace(go.Histogram(
        x=closed[closed['result'] == 'LOSS']['net_r'], nbinsx=20,
        marker_color='#ff4444', opacity=0.7, name='Losses'
    ))
    fig.update_layout(
        template="plotly_dark", barmode='overlay',
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        xaxis_title="Net R", yaxis_title="Count"
    )
    st.plotly_chart(fig, use_container_width=True)

def render_volatility_scanner():
    st.subheader("🌊 Volatility Scanner (Evolution Engine)")
    
    vol_df = load_volatility()
    if vol_df.empty:
        st.info("No volatility data yet. Run a scan or wait for weekly rebalance.")
        return
    
    # Golden pairs highlight
    vol_df['is_golden'] = vol_df['is_golden'].astype(bool)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=vol_df['pair'], y=vol_df['volatility_score'],
        marker_color=['#ffd700' if g else '#00bfff' for g in vol_df['is_golden']],
        text=np.round(vol_df['volatility_score'], 2),
        textposition='outside',
        hovertemplate='%{x}<br>Vol Score: %{y:.2f}<br>ATR Avg: %{customdata:.5f}<extra></extra>',
        customdata=vol_df['atr_avg']
    ))
    
    fig.update_layout(
        template="plotly_dark", height=400,
        margin=dict(l=40, r=20, t=40, b=80),
        xaxis_title="Pair", yaxis_title="Volatility Score (Normalized)",
        xaxis_tickangle=-45
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.caption("🟡 Gold = Top 12 Golden Pairs (actively scanned) | 🔵 Blue = Other tracked pairs")

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

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    # Custom CSS
    st.markdown("""
    <style>
    .stMetric { background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; }
    .stDataFrame { font-size: 12px; }
    h1 { color: #00ff88; }
    h2 { color: #00bfff; }
    h3 { color: #ffd700; }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🤖 God Mode Forex Dashboard")
    st.caption("SMC Deep OTE Signals • Neural Analysis (Llama 3.1) • Evolution Engine")
    
    render_sidebar()
    
    signals_df = load_signals()
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Equity Curve", "🧠 AI Bias Heatmap", "📋 Signal Log", 
        "📊 Performance", "🌊 Volatility", "💬 AI Commentary"
    ])
    
    with tab1:
        render_equity_curve(signals_df)
    
    with tab2:
        render_ai_bias_heatmap(signals_df)
    
    with tab3:
        render_signal_log(signals_df)
    
    with tab4:
        render_performance_metrics(signals_df)
    
    with tab5:
        render_volatility_scanner()
    
    with tab6:
        render_neural_commentary(signals_df)

if __name__ == "__main__":
    main()