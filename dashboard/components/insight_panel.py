"""LLM Insight panel component."""

import streamlit as st
from typing import Any, Dict, Optional

_TREND_ICONS = {"bullish": "📈", "bearish": "📉", "sideways": "➡️", "unknown": "❓"}
_CONF_COLORS = {"high": "green", "medium": "orange", "low": "red", "unknown": "gray"}


def render_insight_panel(
    insight_data: Optional[Dict[str, Any]] = None,
    stored_insight: Optional[Dict[str, Any]] = None,
) -> None:
    """Render the LLM insight panel.

    Args:
        insight_data: Fresh insight from LLMInsightTool (if just generated).
        stored_insight: Latest insight from DataStore (fallback).
    """
    st.subheader("AI Insight")

    # Use fresh data if available, else stored
    data = insight_data or stored_insight
    if not data:
        st.info("No insight available yet. Click 'Generate Insight' to create one.")
        return

    # Check if this is a stored insight (different field names)
    if "trend" not in data and "metadata" in data and data["metadata"]:
        # Stored insight format
        meta = data["metadata"] if isinstance(data["metadata"], dict) else {}
        trend = meta.get("trend", "unknown")
        confidence = meta.get("confidence", "unknown")
        key_factors = meta.get("key_factors", [])
        recommendation = meta.get("recommendation_hint", "neutral")
        summary = data.get("insight_text", "")
        model = data.get("model_used", "")
        timestamp = data.get("created_at", "")
    else:
        # Fresh insight format
        trend = data.get("trend", "unknown")
        confidence = data.get("confidence", "unknown")
        key_factors = data.get("key_factors", [])
        recommendation = data.get("recommendation_hint", "neutral")
        summary = data.get("insight", "") or data.get("insight_text", "")
        model = data.get("model_used", "")
        timestamp = data.get("timestamp", "") or data.get("created_at", "")

    # Error state
    if isinstance(data, dict) and "error" in data:
        st.warning(data["error"])
        if "formatted_prompt" in data:
            with st.expander("View generated prompt"):
                st.code(data["formatted_prompt"][:2000], language="markdown")
        return

    # Trend + confidence header
    icon = _TREND_ICONS.get(trend, "❓")
    conf_color = _CONF_COLORS.get(confidence, "gray")

    col1, col2, col3 = st.columns(3)
    col1.metric("Trend", f"{icon} {trend.title()}")
    col2.metric("Confidence", confidence.title())
    col3.metric("Signal", recommendation.title())

    # Summary
    if summary:
        st.markdown(f"**Analysis:** {summary}")

    # Key factors
    if key_factors:
        st.markdown("**Key Factors:**")
        for f in key_factors:
            st.markdown(f"- {f}")

    # Short/medium term outlook
    short = data.get("short_term_outlook", "")
    medium = data.get("medium_term_outlook", "")
    if short or medium:
        c1, c2 = st.columns(2)
        if short:
            c1.markdown(f"**Short-term (1-5d):** {short}")
        if medium:
            c2.markdown(f"**Medium-term (1-4w):** {medium}")

    # Metadata footer
    if model or timestamp:
        footer = []
        if model:
            footer.append(f"Model: `{model}`")
        if timestamp:
            footer.append(f"Generated: `{timestamp[:19]}`")
        st.caption(" | ".join(footer))


def render_insight_controls(ticker: str) -> Dict[str, Any]:
    """Render insight generation controls. Returns config dict."""
    col1, col2, col3 = st.columns([2, 2, 1])

    insight_type = col1.selectbox(
        "Insight type",
        ["full", "trend", "news_impact"],
        index=0,
        key=f"insight_type_{ticker}",
    )

    llm_mode = col2.selectbox(
        "LLM mode",
        ["auto", "online", "offline"],
        index=0,
        key=f"llm_mode_{ticker}",
    )

    generate = col3.button("Generate Insight", key=f"gen_{ticker}", type="primary")

    return {
        "insight_type": insight_type,
        "llm_mode": llm_mode,
        "generate": generate,
    }
