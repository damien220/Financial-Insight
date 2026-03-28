"""End-to-end smoke tests — full pipeline from tools to data store."""

import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
import pytest_asyncio
from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool
from tools.data.data_aggregator_tool import DataAggregatorTool
from tools.llm.llm_insight_tool import LLMInsightTool
from services.data_store import DataStore
from services.events import EventBus
from services.cache import TTLCache
from services.strategy import Signal, Action, TradingStrategy

TEST_DB = os.path.join(tempfile.gettempdir(), "test_e2e.db")


@pytest_asyncio.fixture
async def store():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    s = DataStore(TEST_DB)
    await s.initialize()
    yield s
    await s.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def loader(store):
    ld = ToolLoader()
    ld.register_tool(GoldPriceTool())
    ld.register_tool(StockPriceTool())
    ld.register_tool(FinancialNewsTool())
    agg = DataAggregatorTool(tool_loader=ld)
    ld.register_tool(agg)
    ins = LLMInsightTool(tool_loader=ld, data_store=store)
    ld.register_tool(ins)
    return ld


# --- Full pipeline: price -> store -> retrieve ---

@pytest.mark.asyncio
async def test_price_to_store_roundtrip(loader, store):
    ok, res = await loader.execute_tool("gold_price", {"period": "5d", "interval": "1d"})
    assert ok
    if "error" not in res:
        count = await store.store_prices("GC=F", "Gold Futures", res["history"])
        assert count > 0
        latest = await store.get_latest_price("GC=F")
        assert latest is not None
        assert latest["close"] == res["history"][-1]["close"]


@pytest.mark.asyncio
async def test_stock_to_store_roundtrip(loader, store):
    ok, res = await loader.execute_tool("stock_price", {"ticker": "AAPL", "period": "5d", "interval": "1d"})
    assert ok
    if "error" not in res:
        await store.store_prices("AAPL", res["asset"], res["history"])
        latest = await store.get_latest_price("AAPL")
        assert latest is not None


# --- Full pipeline: aggregate -> prompt ready ---

@pytest.mark.asyncio
async def test_aggregation_produces_prompt(loader, store):
    ok, agg = await loader.execute_tool("data_aggregator", {
        "asset": "AAPL", "lookback_period": "5d", "include_news": False, "insight_type": "full",
    })
    assert ok
    assert "error" not in agg
    assert "formatted_prompt" in agg
    assert len(agg["formatted_prompt"]) > 200
    assert "technical_indicators" in agg
    assert agg["ticker"] == "AAPL"


# --- Full pipeline: insight with mock LLM -> store -> retrieve ---

@pytest.mark.asyncio
async def test_insight_persistence(loader, store):
    # Use a mock provider via the test helper from Phase 3
    from tests.test_tools.test_llm_insight import MockLLMProvider, MOCK_JSON_RESPONSE

    mock = MockLLMProvider(response=MOCK_JSON_RESPONSE)
    insight_tool = loader.get_tool("llm_insight")
    insight_tool._llm = mock

    ok, result = await loader.execute_tool("llm_insight", {"asset": "AAPL", "insight_type": "full"})
    assert ok
    assert "error" not in result
    assert result["trend"] == "bullish"
    assert result["model_used"] == "mock-model"

    # Verify stored
    stored = await store.get_latest_insight("AAPL")
    assert stored is not None
    assert stored["model_used"] == "mock-model"
    meta = stored["metadata"]
    assert meta["trend"] == "bullish"


# --- Event bus integration ---

@pytest.mark.asyncio
async def test_event_bus_with_price_update(loader, store):
    bus = EventBus()
    received = []

    async def on_event(event):
        received.append(event)

    bus.subscribe("price_updated", on_event)

    ok, res = await loader.execute_tool("gold_price", {"period": "5d", "interval": "1d"})
    if ok and "error" not in res:
        await bus.emit("price_updated", {"ticker": "GC=F", "price": res["current_price"]})

    assert len(received) >= 1
    assert received[0]["data"]["ticker"] == "GC=F"


# --- Cache ---

def test_cache_basic():
    cache = TTLCache(default_ttl=60)
    cache.set("key1", {"price": 100})
    assert cache.get("key1") == {"price": 100}
    assert cache.get("missing") is None
    assert cache.size() == 1

    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_cache_ttl_expiry():
    cache = TTLCache(default_ttl=0)  # immediate expiry
    cache.set("key1", "value")
    import time
    time.sleep(0.01)
    assert cache.get("key1") is None


# --- Strategy interfaces ---

def test_signal_creation():
    sig = Signal(
        asset="Apple Inc.",
        ticker="AAPL",
        action=Action.BUY,
        confidence="high",
        reasoning="Strong bullish trend",
    )
    assert sig.action == Action.BUY
    assert sig.ticker == "AAPL"
    assert sig.timestamp  # auto-generated


def test_action_enum():
    assert Action.BUY.value == "buy"
    assert Action.SELL.value == "sell"
    assert Action.HOLD.value == "hold"


@pytest.mark.asyncio
async def test_strategy_interface():
    """Verify the abstract interface can be subclassed."""

    class DummyStrategy(TradingStrategy):
        def get_name(self):
            return "dummy"

        async def evaluate(self, insight):
            hint = insight.get("recommendation_hint", "neutral")
            action = Action.BUY if hint == "bullish" else Action.HOLD
            return Signal(
                asset=insight.get("asset", ""),
                ticker=insight.get("ticker", ""),
                action=action,
                confidence=insight.get("confidence", "low"),
                reasoning="test",
            )

    strat = DummyStrategy()
    assert strat.get_name() == "dummy"

    signal = await strat.evaluate({
        "asset": "AAPL", "ticker": "AAPL",
        "recommendation_hint": "bullish", "confidence": "high",
    })
    assert signal.action == Action.BUY
    assert signal.confidence == "high"

    # Batch
    signals = await strat.evaluate_batch([
        {"asset": "A", "ticker": "A", "recommendation_hint": "bullish", "confidence": "high"},
        {"asset": "B", "ticker": "B", "recommendation_hint": "neutral", "confidence": "low"},
    ])
    assert len(signals) == 2
    assert signals[0].action == Action.BUY
    assert signals[1].action == Action.HOLD


# --- All tools registered ---

def test_all_tools_registered(loader):
    expected = {"gold_price", "stock_price", "financial_news", "data_aggregator", "llm_insight"}
    actual = set(loader.list_tools())
    assert expected == actual


# --- Graceful error handling ---

@pytest.mark.asyncio
async def test_aggregator_handles_bad_ticker(loader, store):
    ok, res = await loader.execute_tool("data_aggregator", {
        "asset": "ZZZNOTREAL", "include_news": False, "lookback_period": "5d",
    })
    # Should either succeed with empty data or return an error — not crash
    assert ok or isinstance(res, (str, dict))
