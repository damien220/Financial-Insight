"""Tests for LLMInsightTool and LLM providers."""

import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from tools.llm.llm_insight_tool import LLMInsightTool, _parse_llm_response
from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool
from tools.data.data_aggregator_tool import DataAggregatorTool
from services.llm_provider import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    get_llm_provider,
)
from services.data_store import DataStore


# ---- Fixtures ----

@pytest.fixture
def loader():
    ld = ToolLoader()
    ld.register_tool(GoldPriceTool())
    ld.register_tool(StockPriceTool())
    ld.register_tool(FinancialNewsTool())
    agg = DataAggregatorTool(tool_loader=ld)
    ld.register_tool(agg)
    return ld


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for testing."""

    def __init__(self, response: str = ""):
        self._response = response

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        return self._response

    def get_model_name(self) -> str:
        return "mock-model"

    async def is_available(self) -> bool:
        return True


MOCK_JSON_RESPONSE = json.dumps({
    "trend": "bullish",
    "confidence": "medium",
    "key_factors": ["Strong earnings", "Positive market sentiment"],
    "short_term_outlook": "Price likely to test resistance at $260.",
    "medium_term_outlook": "Continued uptrend expected if earnings hold.",
    "recommendation_hint": "bullish",
    "summary": "AAPL shows bullish momentum supported by strong earnings and positive sentiment.",
})


# ---- Tool metadata ----

def test_tool_metadata(loader):
    tool = LLMInsightTool(tool_loader=loader)
    assert tool.get_name() == "llm_insight"
    schema = tool.get_parameters_schema()
    assert "asset" in schema["required"]
    assert "insight_type" in schema["properties"]
    assert "llm_mode" in schema["properties"]


def test_validate_requires_asset(loader):
    tool = LLMInsightTool(tool_loader=loader)
    ok, err = tool.validate_arguments({})
    assert ok is False


# ---- Response parsing ----

def test_parse_clean_json():
    parsed = _parse_llm_response(MOCK_JSON_RESPONSE)
    assert parsed["trend"] == "bullish"
    assert parsed["confidence"] == "medium"
    assert len(parsed["key_factors"]) == 2


def test_parse_json_in_markdown_fences():
    raw = '```json\n{"trend": "bearish", "confidence": "high", "summary": "Down."}\n```'
    parsed = _parse_llm_response(raw)
    assert parsed["trend"] == "bearish"


def test_parse_json_embedded_in_text():
    raw = 'Here is my analysis:\n{"trend": "sideways", "confidence": "low", "summary": "Flat."}\nEnd.'
    parsed = _parse_llm_response(raw)
    assert parsed["trend"] == "sideways"


def test_parse_regex_fallback():
    raw = "The trend is bearish with high confidence. Recommendation: neutral."
    parsed = _parse_llm_response(raw)
    assert parsed["trend"] == "bearish"
    assert parsed["confidence"] == "high"
    assert parsed["recommendation_hint"] == "neutral"
    assert "summary" in parsed


def test_parse_garbage_returns_summary():
    raw = "Some random text with no structure."
    parsed = _parse_llm_response(raw)
    assert "summary" in parsed
    assert parsed["summary"] == raw


# ---- LLM provider factory ----

def test_get_provider_offline():
    provider = get_llm_provider("offline")
    assert isinstance(provider, OllamaProvider)


def test_get_provider_online_openai():
    with patch.dict("os.environ", {"LLM_ONLINE_PROVIDER": "openai", "LLM_API_KEY": "test"}):
        provider = get_llm_provider("online")
        assert isinstance(provider, OpenAIProvider)


def test_get_provider_online_anthropic():
    with patch.dict("os.environ", {"LLM_ONLINE_PROVIDER": "anthropic", "LLM_API_KEY": "test"}):
        provider = get_llm_provider("online")
        assert isinstance(provider, AnthropicProvider)


def test_get_provider_invalid():
    with pytest.raises(ValueError):
        get_llm_provider("invalid_mode")


# ---- End-to-end with mock LLM ----

@pytest.mark.asyncio
async def test_execute_with_mock_llm(loader):
    mock_provider = MockLLMProvider(response=MOCK_JSON_RESPONSE)
    tool = LLMInsightTool(tool_loader=loader, llm_provider=mock_provider)
    loader.register_tool(tool)

    result = await tool.execute(asset="AAPL", insight_type="full", llm_mode="auto")

    assert "error" not in result
    assert result["ticker"] == "AAPL"
    assert result["trend"] == "bullish"
    assert result["confidence"] == "medium"
    assert result["model_used"] == "mock-model"
    assert result["recommendation_hint"] == "bullish"
    assert len(result["key_factors"]) == 2
    assert result["insight_type"] == "full"


@pytest.mark.asyncio
async def test_execute_gold_with_mock_llm(loader):
    mock_provider = MockLLMProvider(response=json.dumps({
        "trend": "bullish", "confidence": "high",
        "key_factors": ["Safe haven demand"], "short_term_outlook": "Up.",
        "medium_term_outlook": "Strong.", "recommendation_hint": "bullish",
        "summary": "Gold is bullish.",
    }))
    tool = LLMInsightTool(tool_loader=loader, llm_provider=mock_provider)
    loader.register_tool(tool)

    result = await tool.execute(asset="gold", insight_type="trend")
    assert "error" not in result
    assert result["ticker"] == "GC=F"
    assert result["trend"] == "bullish"


@pytest.mark.asyncio
async def test_execute_with_data_store(loader):
    import tempfile, os, aiosqlite
    db_path = os.path.join(tempfile.gettempdir(), "test_insight.db")
    store = DataStore(db_path)
    await store.initialize()

    try:
        mock_provider = MockLLMProvider(response=MOCK_JSON_RESPONSE)
        tool = LLMInsightTool(tool_loader=loader, data_store=store, llm_provider=mock_provider)
        loader.register_tool(tool)

        result = await tool.execute(asset="AAPL")
        assert "error" not in result

        # Verify insight was persisted
        insight = await store.get_latest_insight("AAPL")
        assert insight is not None
        assert "bullish" in insight["insight_text"].lower() or "AAPL" in insight["insight_text"]
        assert insight["model_used"] == "mock-model"
    finally:
        await store.close()
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_execute_no_provider_available(loader):
    tool = LLMInsightTool(tool_loader=loader, llm_provider=None)
    # With no env vars set and no Ollama running, auto mode should return error with data
    result = await tool.execute(asset="AAPL", llm_mode="auto")
    assert "error" in result
    # Should still have aggregated data and prompt
    assert "formatted_prompt" in result or "aggregated_data" in result


@pytest.mark.asyncio
async def test_execute_no_loader():
    tool = LLMInsightTool()
    result = await tool.execute(asset="AAPL")
    assert "error" in result


# ---- Provider availability ----

@pytest.mark.asyncio
async def test_openai_not_available_without_key():
    provider = OpenAIProvider(api_key="")
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_anthropic_not_available_without_key():
    provider = AnthropicProvider(api_key="")
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_ollama_availability():
    # Ollama may or may not be running in test env
    provider = OllamaProvider()
    result = await provider.is_available()
    assert isinstance(result, bool)
