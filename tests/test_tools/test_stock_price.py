"""Tests for StockPriceTool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from tools.price.stock_price_tool import StockPriceTool


@pytest.fixture
def tool():
    return StockPriceTool()


def test_tool_metadata(tool):
    assert tool.get_name() == "stock_price"
    schema = tool.get_parameters_schema()
    assert "ticker" in schema["required"]


def test_validate_requires_ticker(tool):
    ok, err = tool.validate_arguments({})
    assert ok is False
    assert "ticker" in err


def test_validate_accepts_valid(tool):
    ok, err = tool.validate_arguments({"ticker": "AAPL"})
    assert ok is True


@pytest.mark.asyncio
async def test_execute_returns_price(tool):
    result = await tool.execute(ticker="AAPL", period="5d", interval="1d")
    assert "ticker" in result
    assert result["ticker"] == "AAPL"
    if "error" not in result:
        assert "current_price" in result
        assert isinstance(result["current_price"], float)
        assert isinstance(result["history"], list)


@pytest.mark.asyncio
async def test_execute_invalid_ticker(tool):
    result = await tool.execute(ticker="ZZZZZZZNOTREAL")
    # Should return error or empty data
    assert "ticker" in result
