"""Momentum Sniper Streamlit launcher with market selector."""
from __future__ import annotations

import os
import runpy
from pathlib import Path

import streamlit as st

# app_ui.py already contains the proven Momentum Sniper UI and calls
# set_page_config itself. Configure once here, then suppress its duplicate call.
_real_set_page_config = st.set_page_config
_real_set_page_config(page_title="Momentum Sniper", page_icon="🎯", layout="wide")
st.set_page_config = lambda *args, **kwargs: None

try:
    with st.sidebar:
        st.markdown("### 🌍 Kalodata market")
        market_label = st.selectbox(
            "Market",
            ["United States (US)", "United Kingdom (UK)"],
            index=1,
            key="momentum_market_v23",
            help=(
                "Changes the actual Kalodata region and currency. UK uses GB / GBP / en-GB; "
                "it does not convert US results into pounds."
            ),
        )
        market_code = "GB" if market_label.startswith("United Kingdom") else "US"
        symbol = "£" if market_code == "GB" else "$"
        st.caption(
            f"Active: **{market_label}**. Vetting remains {symbol}8+ average price, "
            f"{symbol}3+ commission per sale, and 7/10+ ads."
        )

    # subprocess.Popen in app_ui.py inherits this environment variable, so both
    # Product and Creator scans use the selected market without changing the UI engine.
    os.environ["SNIPER_MARKET"] = market_code
    runpy.run_path(str(Path(__file__).with_name("app_ui.py")), run_name="__main__")
finally:
    st.set_page_config = _real_set_page_config
