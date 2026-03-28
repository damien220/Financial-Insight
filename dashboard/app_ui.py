"""
Financial Insight Dashboard — Streamlit main application.

Run with:  streamlit run dashboard/app_ui.py
"""

import sys
import asyncio
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool
from tools.data.data_aggregator_tool import DataAggregatorTool
from tools.llm.llm_insight_tool import LLMInsightTool
from services.data_store import DataStore
from dashboard.components.asset_selector import render_asset_selector
from dashboard.components.price_chart import (
    render_price_header,
    render_period_selector,
    render_candlestick_chart,
)
from dashboard.components.insight_panel import render_insight_panel, render_insight_controls
from dashboard.components.news_feed import render_news_feed


# ---------------------------------------------------------------------------
# Async helper — run coroutines from Streamlit (sync) context
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine from Streamlit's sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Initialization (cached across reruns)
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Initialize tools, data store (once per Streamlit session)."""
    loader = ToolLoader()
    loader.register_tool(GoldPriceTool())
    loader.register_tool(StockPriceTool())
    loader.register_tool(FinancialNewsTool())
    agg = DataAggregatorTool(tool_loader=loader)
    loader.register_tool(agg)

    store = run_async(_init_store())
    insight_tool = LLMInsightTool(tool_loader=loader, data_store=store)
    loader.register_tool(insight_tool)

    return loader, store


async def _init_store():
    store = DataStore("data/prices.db")
    await store.initialize()
    return store


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_price(loader: ToolLoader, ticker: str, period: str):
    """Fetch price data for a ticker."""
    async def _fetch():
        if ticker == "GC=F":
            ok, data = await loader.execute_tool("gold_price", {"period": period, "interval": "1d"})
        else:
            ok, data = await loader.execute_tool("stock_price", {"ticker": ticker, "period": period, "interval": "1d"})
        return data if ok else {"error": str(data)}
    return run_async(_fetch())


def fetch_news(loader: ToolLoader, query: str):
    async def _fetch():
        ok, data = await loader.execute_tool("financial_news", {"query": query, "max_results": 10})
        return data if ok else {"articles": []}
    return run_async(_fetch())


def fetch_aggregated(loader: ToolLoader, ticker: str, period: str, insight_type: str):
    async def _fetch():
        ok, data = await loader.execute_tool("data_aggregator", {
            "asset": ticker, "lookback_period": period, "include_news": True, "insight_type": insight_type,
        })
        return data if ok else {"error": str(data)}
    return run_async(_fetch())


def generate_insight(loader: ToolLoader, ticker: str, insight_type: str, llm_mode: str):
    async def _fetch():
        ok, data = await loader.execute_tool("llm_insight", {
            "asset": ticker, "insight_type": insight_type, "llm_mode": llm_mode,
        })
        return data if ok else data  # return even on failure for error display
    return run_async(_fetch())


def get_stored_insight(store: DataStore, ticker: str):
    async def _fetch():
        return await store.get_latest_insight(ticker)
    return run_async(_fetch())


def store_prices(store: DataStore, ticker: str, asset_name: str, history):
    async def _store():
        await store.store_prices(ticker, asset_name, history)
    run_async(_store())


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

def load_css():
    css_path = Path(__file__).parent / "styles" / "custom.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_title="Financial Insight",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    load_css()

    loader, store = init_services()

    # --- Sidebar ---
    st.sidebar.title("📊 Financial Insight")
    ticker = render_asset_selector()

    if not ticker:
        st.warning("Select an asset to begin.")
        return

    # Auto-refresh toggle
    st.sidebar.divider()
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
    if auto_refresh:
        st.sidebar.caption("Dashboard will refresh every 30 seconds.")

    # --- Main area: tabs ---
    tab_overview, tab_insight, tab_news, tab_settings = st.tabs(
        ["Overview", "AI Insight", "News", "Settings"]
    )

    # === Overview tab ===
    with tab_overview:
        st.header(f"{ticker}")

        period = render_period_selector()

        with st.spinner("Fetching price data…"):
            price_data = fetch_price(loader, ticker, period)

        render_price_header(price_data)

        if "error" not in price_data:
            history = price_data.get("history", [])
            asset_name = price_data.get("asset", ticker)
            render_candlestick_chart(history, asset_name)

            # Store prices in background
            store_prices(store, ticker, asset_name, history)

            # Technical indicators summary
            agg_data = fetch_aggregated(loader, ticker, period, "trend")
            if "error" not in agg_data:
                ti = agg_data.get("technical_indicators", {})
                if ti:
                    st.subheader("Technical Indicators")
                    cols = st.columns(len(ti))
                    for i, (k, v) in enumerate(ti.items()):
                        label = k.upper().replace("_", " ")
                        cols[i].metric(label, v)

    # === AI Insight tab ===
    with tab_insight:
        st.header(f"AI Insight — {ticker}")

        controls = render_insight_controls(ticker)

        insight_data = None
        if controls["generate"]:
            with st.spinner("Generating insight…"):
                insight_data = generate_insight(
                    loader, ticker, controls["insight_type"], controls["llm_mode"]
                )

        # Show fresh insight or fall back to stored
        stored = get_stored_insight(store, ticker)
        render_insight_panel(insight_data=insight_data, stored_insight=stored)

        # Insight history
        if stored:
            with st.expander("Insight History"):
                async def _get_history():
                    return await store.get_insights(ticker, limit=5)
                history = run_async(_get_history())
                for h in history:
                    meta = h.get("metadata", {}) or {}
                    trend = meta.get("trend", "?")
                    st.markdown(
                        f"**{h.get('created_at', '?')[:19]}** — "
                        f"{trend} | {h.get('model_used', '?')} | "
                        f"{h.get('insight_text', '')[:100]}…"
                    )

    # === News tab ===
    with tab_news:
        st.header(f"News — {ticker}")
        query = ticker if ticker != "GC=F" else "gold"
        with st.spinner("Fetching news…"):
            news_data = fetch_news(loader, query)
        render_news_feed(news_data)

    # === Settings tab ===
    with tab_settings:
        st.header("Settings")

        st.subheader("LLM Configuration")
        col1, col2 = st.columns(2)
        col1.text_input("LLM API Key", type="password", key="settings_api_key",
                         help="Set LLM_API_KEY environment variable for persistent config.")
        col2.selectbox("Default LLM Mode", ["auto", "online", "offline"], key="settings_llm_mode")
        col2.selectbox("Online Provider", ["openai", "anthropic"], key="settings_provider")

        st.subheader("Refresh Intervals")
        c1, c2, c3 = st.columns(3)
        c1.number_input("Price refresh (min)", value=5, min_value=1, key="settings_price_int")
        c2.number_input("News refresh (min)", value=15, min_value=1, key="settings_news_int")
        c3.number_input("Insight refresh (min)", value=60, min_value=5, key="settings_insight_int")

        st.subheader("Tracked Assets")
        st.json({
            "commodities": {"gold": "GC=F"},
            "stocks": {"AAPL": "AAPL", "MSFT": "MSFT"},
            "ETFs": {"SPY": "SPY"},
        })
        st.caption("Edit `config/assets.yaml` to add or remove tracked assets.")

    # Auto-refresh
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()


if __name__ == "__main__":
    main()
