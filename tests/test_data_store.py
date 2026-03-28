"""Tests for DataStore."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pytest_asyncio
from services.data_store import DataStore

TEST_DB = "/tmp/test_financial_insight.db"


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


@pytest.mark.asyncio
async def test_store_and_retrieve_prices(store):
    records = [
        {"timestamp": "2025-01-01 10:00:00", "open": 100.0, "high": 105.0,
         "low": 99.0, "close": 103.0, "volume": 1000},
        {"timestamp": "2025-01-02 10:00:00", "open": 103.0, "high": 107.0,
         "low": 101.0, "close": 106.0, "volume": 1200},
    ]
    count = await store.store_prices("GC=F", "Gold Futures", records)
    assert count == 2

    history = await store.get_price_history("GC=F", limit=10)
    assert len(history) == 2
    assert history[0]["close"] == 106.0  # Most recent first


@pytest.mark.asyncio
async def test_upsert_prices(store):
    records = [{"timestamp": "2025-01-01", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000}]
    await store.store_prices("GC=F", "Gold", records)

    records[0]["close"] = 104
    await store.store_prices("GC=F", "Gold", records)

    history = await store.get_price_history("GC=F")
    assert len(history) == 1
    assert history[0]["close"] == 104


@pytest.mark.asyncio
async def test_get_latest_price(store):
    records = [
        {"timestamp": "2025-01-01", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
        {"timestamp": "2025-01-02", "open": 103, "high": 107, "low": 101, "close": 106, "volume": 1200},
    ]
    await store.store_prices("AAPL", "Apple", records)
    latest = await store.get_latest_price("AAPL")
    assert latest is not None
    assert latest["close"] == 106


@pytest.mark.asyncio
async def test_store_and_retrieve_insight(store):
    row_id = await store.store_insight(
        ticker="AAPL", asset="Apple", insight_text="Bullish trend detected.",
        model_used="gpt-4o-mini", insight_type="trend",
    )
    assert row_id > 0

    insight = await store.get_latest_insight("AAPL")
    assert insight is not None
    assert "Bullish" in insight["insight_text"]
    assert insight["model_used"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_no_data_returns_none(store):
    assert await store.get_latest_price("NONEXIST") is None
    assert await store.get_latest_insight("NONEXIST") is None
