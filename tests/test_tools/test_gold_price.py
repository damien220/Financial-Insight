"""Tests for GoldPriceTool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from tools.price.gold_price_tool import GoldPriceTool


@pytest.fixture
def tool():
    return GoldPriceTool()


def test_tool_metadata(tool):
    assert tool.get_name() == "gold_price"
    assert "gold" in tool.get_description().lower()
    schema = tool.get_parameters_schema()
    assert schema["type"] == "object"
    assert "period" in schema["properties"]
    assert "interval" in schema["properties"]


def test_validate_no_required(tool):
    ok, err = tool.validate_arguments({})
    assert ok is True


def test_validate_rejects_unknown(tool):
    ok, err = tool.validate_arguments({"bad_param": 1})
    assert ok is False


@pytest.mark.asyncio
async def test_execute_returns_price(tool):
    result = await tool.execute(period="5d", interval="1d")
    # Either we get price data or a market-closed message
    assert "ticker" in result
    assert result["ticker"] == "GC=F"
    if "error" not in result:
        assert "current_price" in result
        assert isinstance(result["current_price"], float)
        assert isinstance(result["history"], list)
        assert len(result["history"]) > 0


@pytest.mark.asyncio
async def test_execute_invalid_period(tool):
    result = await tool.execute(period="invalid")
    assert "error" in result
