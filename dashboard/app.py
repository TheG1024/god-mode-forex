#!/usr/bin/env python3
"""dashboard/app.py — Streamlit dashboard entry point."""

import streamlit as st
import pandas as pd

from config import CONFIG
from dashboard.data import load_signals, load_volatility, load_performance
from dashboard.charts import equity_curve, ai_bias_heatmap, volatility_bar, r_distribution
from dashboard.ui import render_sidebar, render_signal_log, render_performance_metrics, render_neural_commentary


def main():
    st.set_page_config(
        page_title="God Mode Forex Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

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
    vol_df = load_volatility()
    perf_df = load_performance()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Equity Curve", "🧠 AI Bias Heatmap", "📋 Signal Log",
        "📊 Performance", "🌊 Volatility", "💬 AI Commentary"
    ])

    with tab1:
        from dashboard.charts import equity_curve
        equity_curve(signals_df)

    with tab2:
        from dashboard.charts import ai_bias_heatmap
        ai_bias_heatmap(signals_df)

    with tab3:
        from dashboard.ui import render_signal_log
        render_signal_log(signals_df)

    with tab4:
        from dashboard.ui import render_performance_metrics
        render_performance_metrics(signals_df)

    with tab5:
        from dashboard.charts import volatility_bar
        volatility_bar(vol_df)

    with tab6:
        from dashboard.ui import render_neural_commentary
        render_neural_commentary(signals_df)

    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30000, key="auto_refresh")


if __name__ == "__main__":
    main()