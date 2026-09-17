#!/usr/bin/env python3
"""dashboard/data.py — Data loaders for Streamlit dashboard."""

import streamlit as st
import sqlite3
import pandas as pd

from config import CONFIG


@st.cache_data(ttl=30)
def load_signals() -> pd.DataFrame:
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        return pd.read_sql("SELECT * FROM signals ORDER BY created_at DESC", conn)


@st.cache_data(ttl=30)
def load_volatility() -> pd.DataFrame:
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        return pd.read_sql("SELECT * FROM pair_volatility ORDER BY volatility_score DESC", conn)


@st.cache_data(ttl=30)
def load_performance() -> pd.DataFrame:
    with sqlite3.connect(CONFIG.DB_PATH) as conn:
        return pd.read_sql("SELECT * FROM performance ORDER BY date", conn)