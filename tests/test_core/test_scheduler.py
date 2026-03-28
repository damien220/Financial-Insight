"""Tests for FinancialScheduler."""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
import pytest_asyncio
from services.scheduler import FinancialScheduler, _load_schedule_config, _get_tracked_assets
from services.events import EventBus
from services.data_store import DataStore
from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool
from tools.data.data_aggregator_tool import DataAggregatorTool
from tools.llm.llm_insight_tool import LLMInsightTool

TEST_DB = os.path.join(tempfile.gettempdir(), "test_scheduler.db")


@pytest.fixture
def loader():
    ld = ToolLoader()
    ld.register_tool(GoldPriceTool())
    ld.register_tool(StockPriceTool())
    ld.register_tool(FinancialNewsTool())
    agg = DataAggregatorTool(tool_loader=ld)
    ld.register_tool(agg)
    ins = LLMInsightTool(tool_loader=ld)
    ld.register_tool(ins)
    return ld


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


# --- Config loading ---

def test_load_config_defaults():
    cfg = _load_schedule_config("/nonexistent/path.yaml")
    assert cfg["price_interval_minutes"] == 5
    assert cfg["market_hours_only"] is True


def test_load_config_from_yaml():
    cfg = _load_schedule_config("config/assets.yaml")
    assert cfg["price_interval_minutes"] == 5
    assert cfg["timezone"] == "US/Eastern"
    # Should have loaded asset data
    assets = _get_tracked_assets(cfg)
    tickers = [a["ticker"] for a in assets]
    assert "GC=F" in tickers
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "SPY" in tickers


def test_get_tracked_assets():
    cfg = _load_schedule_config("config/assets.yaml")
    assets = _get_tracked_assets(cfg)
    assert len(assets) == 4
    gold = next(a for a in assets if a["ticker"] == "GC=F")
    assert gold["name"] == "Gold Futures"
    assert gold["category"] == "commodity"


# --- Scheduler lifecycle ---

@pytest.mark.asyncio
async def test_start_stop(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")

    assert not sched.is_running
    sched.start()
    assert sched.is_running

    jobs = sched.get_jobs_info()
    assert len(jobs) == 3
    job_ids = [j["id"] for j in jobs]
    assert "price_refresh" in job_ids
    assert "news_refresh" in job_ids
    assert "insight_refresh" in job_ids

    sched.stop()
    assert not sched.is_running


# --- Manual triggers ---

@pytest.mark.asyncio
async def test_trigger_price_refresh(loader, store):
    bus = EventBus()
    events_received = []

    async def on_price(event):
        events_received.append(event)

    bus.subscribe("price_updated", on_price)

    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    # Override market hours check so it runs regardless
    sched._config["market_hours_only"] = False

    await sched.trigger_price_refresh()

    # Should have received price events for tracked assets
    assert len(events_received) > 0
    tickers = [e["data"]["ticker"] for e in events_received]
    assert "GC=F" in tickers or "AAPL" in tickers

    # Verify data was stored
    latest = await store.get_latest_price("GC=F")
    assert latest is not None or await store.get_latest_price("AAPL") is not None


@pytest.mark.asyncio
async def test_trigger_news_refresh(loader, store):
    bus = EventBus()
    events_received = []

    async def on_news(event):
        events_received.append(event)

    bus.subscribe("news_updated", on_news)

    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    sched._config["market_hours_only"] = False

    await sched.trigger_news_refresh()
    assert len(events_received) > 0


# --- Change detection ---

def test_change_detection_no_previous(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    # First call: no previous price
    assert sched._check_price_change("AAPL", 250.0) is False


def test_change_detection_small(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    sched._last_prices["AAPL"] = 250.0
    # 0.4% change — below 2% threshold
    assert sched._check_price_change("AAPL", 251.0) is False


def test_change_detection_significant(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    sched._last_prices["AAPL"] = 250.0
    # 4% change — above 2% threshold
    assert sched._check_price_change("AAPL", 260.0) is True


# --- Market hours ---

def test_should_skip_market_hours(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    sched._config["market_hours_only"] = True
    # Result depends on actual time — just verify it returns a bool
    result = sched._should_skip()
    assert isinstance(result, bool)


def test_should_not_skip_when_disabled(loader, store):
    bus = EventBus()
    sched = FinancialScheduler(loader, store, bus, "config/assets.yaml")
    sched._config["market_hours_only"] = False
    assert sched._should_skip() is False
