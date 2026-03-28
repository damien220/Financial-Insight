"""Tests for DataAggregatorTool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from tools.data.data_aggregator_tool import (
    DataAggregatorTool,
    _compute_technicals,
    _resolve_ticker,
    _rsi,
)
from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool


@pytest.fixture
def loader():
    ld = ToolLoader()
    ld.register_tool(GoldPriceTool())
    ld.register_tool(StockPriceTool())
    ld.register_tool(FinancialNewsTool())
    return ld


@pytest.fixture
def tool(loader):
    t = DataAggregatorTool(tool_loader=loader)
    return t


# --- Metadata ---

def test_tool_metadata(tool):
    assert tool.get_name() == "data_aggregator"
    schema = tool.get_parameters_schema()
    assert "asset" in schema["required"]


def test_validate_requires_asset(tool):
    ok, err = tool.validate_arguments({})
    assert ok is False


# --- Ticker resolution ---

def test_resolve_ticker_gold():
    assert _resolve_ticker("gold") == "GC=F"
    assert _resolve_ticker("Gold Futures") == "GC=F"


def test_resolve_ticker_stock():
    assert _resolve_ticker("AAPL") == "AAPL"
    assert _resolve_ticker("msft") == "MSFT"


def test_resolve_ticker_sp500():
    assert _resolve_ticker("sp500") == "SPY"
    assert _resolve_ticker("S&P 500") == "SPY"


# --- Technical indicators ---

def test_compute_technicals_sufficient_data():
    # 25 data points: enough for SMA-20 and RSI-14
    closes = [100 + i * 0.5 for i in range(25)]
    t = _compute_technicals(closes)
    assert "sma_20" in t
    assert "rsi_14" in t
    assert "daily_volatility_pct" in t
    assert t["price_vs_sma"] == "above"  # uptrend


def test_compute_technicals_short_data():
    closes = [100, 101, 102]
    t = _compute_technicals(closes)
    assert "sma_20" not in t
    assert "daily_volatility_pct" in t


def test_compute_technicals_empty():
    assert _compute_technicals([]) == {}


def test_rsi_full_gains():
    # Steady uptrend => RSI near 100
    closes = [100 + i for i in range(20)]
    rsi = _rsi(closes, 14)
    assert rsi > 90


def test_rsi_full_losses():
    # Steady downtrend => RSI near 0
    closes = [100 - i for i in range(20)]
    rsi = _rsi(closes, 14)
    assert rsi < 10


# --- Integration (live data) ---

def test_no_loader():
    t = DataAggregatorTool()  # no loader
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(t.execute(asset="AAPL"))
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_stock(tool):
    result = await tool.execute(asset="AAPL", lookback_period="5d", include_news=False)
    assert "error" not in result
    assert result["ticker"] == "AAPL"
    assert "current_price" in result
    assert "technical_indicators" in result
    assert "formatted_prompt" in result
    assert len(result["formatted_prompt"]) > 100


@pytest.mark.asyncio
async def test_execute_gold(tool):
    result = await tool.execute(asset="gold", lookback_period="5d", include_news=False)
    assert "error" not in result
    assert result["ticker"] == "GC=F"
    assert "formatted_prompt" in result


@pytest.mark.asyncio
async def test_execute_with_news(tool):
    result = await tool.execute(asset="AAPL", lookback_period="5d", include_news=True, insight_type="news_impact")
    assert "error" not in result
    assert "recent_news" in result
    assert "news_impact" == result["insight_type"]
    assert "formatted_prompt" in result


@pytest.mark.asyncio
async def test_prompt_types(tool):
    for ptype in ("trend", "news_impact", "full"):
        result = await tool.execute(asset="AAPL", lookback_period="5d", include_news=False, insight_type=ptype)
        assert "formatted_prompt" in result
        assert result["insight_type"] == ptype
