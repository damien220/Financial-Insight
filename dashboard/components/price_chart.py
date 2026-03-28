"""Price chart component — candlestick + SMA overlay via Plotly."""

import streamlit as st
import plotly.graph_objects as go
from typing import Any, Dict, List


PERIOD_OPTIONS = ["1d", "5d", "1mo", "3mo", "6mo", "1y"]


def render_price_header(price_data: Dict[str, Any]) -> None:
    """Render price summary metrics."""
    if "error" in price_data:
        st.warning(price_data["error"])
        return

    cols = st.columns(4)
    price = price_data.get("current_price", 0)
    change = price_data.get("price_change", 0)
    pct = price_data.get("price_change_pct", 0)
    volume = price_data.get("volume", 0)

    cols[0].metric("Price", f"${price:,.2f}", f"{pct:+.2f}%")
    cols[1].metric("Day High", f"${price_data.get('day_high', 0):,.2f}")
    cols[2].metric("Day Low", f"${price_data.get('day_low', 0):,.2f}")
    cols[3].metric("Volume", f"{volume:,}")


def render_period_selector() -> str:
    """Render time period selector. Returns selected period."""
    cols = st.columns(len(PERIOD_OPTIONS))
    if "chart_period" not in st.session_state:
        st.session_state.chart_period = "1mo"

    for i, period in enumerate(PERIOD_OPTIONS):
        if cols[i].button(period, key=f"period_{period}",
                          type="primary" if st.session_state.chart_period == period else "secondary"):
            st.session_state.chart_period = period

    return st.session_state.chart_period


def render_candlestick_chart(history: List[Dict[str, Any]], asset_name: str = "") -> None:
    """Render Plotly candlestick chart with SMA overlay."""
    if not history:
        st.info("No price history available.")
        return

    timestamps = [r["timestamp"][:16] for r in history]
    opens = [r["open"] for r in history]
    highs = [r["high"] for r in history]
    lows = [r["low"] for r in history]
    closes = [r["close"] for r in history]
    volumes = [r["volume"] for r in history]

    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=timestamps, open=opens, high=highs, low=lows, close=closes,
        name="OHLC",
        increasing_line_color="#00c853",
        decreasing_line_color="#ff1744",
    ))

    # SMA overlay (if enough data)
    if len(closes) >= 5:
        window = min(20, len(closes))
        sma = []
        for i in range(len(closes)):
            if i < window - 1:
                sma.append(None)
            else:
                sma.append(sum(closes[i - window + 1:i + 1]) / window)
        fig.add_trace(go.Scatter(
            x=timestamps, y=sma,
            mode="lines", name=f"SMA-{window}",
            line=dict(color="#ffc107", width=1.5, dash="dot"),
        ))

    fig.update_layout(
        title=f"{asset_name} Price" if asset_name else "Price Chart",
        yaxis_title="Price (USD)",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=450,
        margin=dict(l=40, r=20, t=40, b=30),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Volume bar chart below
    if any(v > 0 for v in volumes):
        colors = ["#00c853" if c >= o else "#ff1744" for o, c in zip(opens, closes)]
        vol_fig = go.Figure(go.Bar(
            x=timestamps, y=volumes, marker_color=colors, name="Volume",
        ))
        vol_fig.update_layout(
            height=150,
            template="plotly_dark",
            margin=dict(l=40, r=20, t=10, b=30),
            yaxis_title="Volume",
        )
        st.plotly_chart(vol_fig, use_container_width=True)
