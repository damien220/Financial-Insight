"""Tests for EventBus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from services.events import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_emit_and_subscribe(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("price_updated", handler)
    await bus.emit("price_updated", {"ticker": "AAPL", "price": 250.0})

    assert len(received) == 1
    assert received[0]["type"] == "price_updated"
    assert received[0]["data"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    results = []

    async def h1(event):
        results.append("h1")

    async def h2(event):
        results.append("h2")

    bus.subscribe("test", h1)
    bus.subscribe("test", h2)
    await bus.emit("test")

    assert results == ["h1", "h2"]


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def handler(event):
        received.append(1)

    bus.subscribe("test", handler)
    await bus.emit("test")
    assert len(received) == 1

    bus.unsubscribe("test", handler)
    await bus.emit("test")
    assert len(received) == 1  # no new events


@pytest.mark.asyncio
async def test_event_isolation(bus):
    a_events = []
    b_events = []

    async def on_a(event):
        a_events.append(event)

    async def on_b(event):
        b_events.append(event)

    bus.subscribe("a", on_a)
    bus.subscribe("b", on_b)
    await bus.emit("a")

    assert len(a_events) == 1
    assert len(b_events) == 0


@pytest.mark.asyncio
async def test_history(bus):
    await bus.emit("x", {"v": 1})
    await bus.emit("x", {"v": 2})
    await bus.emit("y", {"v": 3})

    all_h = bus.get_history()
    assert len(all_h) == 3

    x_h = bus.get_history("x")
    assert len(x_h) == 2

    limited = bus.get_history(limit=1)
    assert len(limited) == 1
    assert limited[0]["data"]["v"] == 3


@pytest.mark.asyncio
async def test_subscriber_error_is_nonfatal(bus):
    called = []

    async def bad_handler(event):
        raise RuntimeError("boom")

    async def good_handler(event):
        called.append(1)

    bus.subscribe("test", bad_handler)
    bus.subscribe("test", good_handler)
    await bus.emit("test")

    assert len(called) == 1  # good_handler still ran


@pytest.mark.asyncio
async def test_clear(bus):
    async def handler(event):
        pass

    bus.subscribe("test", handler)
    await bus.emit("test")
    bus.clear()

    assert bus.get_history() == []
