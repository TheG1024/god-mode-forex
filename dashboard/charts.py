#!/usr/bin/env python3
"""dashboard/charts.py — Plotly chart functions for dashboard."""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def compute_equity_curve(signals_df: pd.DataFrame) -> pd.DataFrame:
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


def equity_curve(signals_df: pd.DataFrame):
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


def ai_bias_heatmap(signals_df: pd.DataFrame):
    st.subheader("🧠 AI Bias Heatmap (Neural Score by Pair × Direction)")

    if signals_df.empty:
        st.info("No signals yet.")
        return

    heatmap_data = signals_df.groupby(['pair', 'direction'])['neural_score'].mean().unstack(fill_value=0)

    if heatmap_data.empty:
        st.info("No data for heatmap.")
        return

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


def volatility_bar(vol_df: pd.DataFrame):
    st.subheader("🌊 Volatility Scanner (Evolution Engine)")

    if vol_df.empty:
        st.info("No volatility data yet. Run a scan or wait for weekly rebalance.")
        return

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


def r_distribution(signals_df: pd.DataFrame):
    closed = signals_df[signals_df['result'].isin(['WIN', 'LOSS'])]
    if closed.empty:
        return

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