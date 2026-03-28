"""Tests for FinancialNewsTool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from tools.news.financial_news_tool import (
    FinancialNewsTool,
    _clean_html,
    _deduplicate,
    _title_hash,
)


@pytest.fixture
def tool():
    return FinancialNewsTool()


def test_tool_metadata(tool):
    assert tool.get_name() == "financial_news"
    schema = tool.get_parameters_schema()
    assert "query" in schema["required"]
    assert "max_results" in schema["properties"]


def test_validate_requires_query(tool):
    ok, err = tool.validate_arguments({})
    assert ok is False


def test_validate_accepts_valid(tool):
    ok, err = tool.validate_arguments({"query": "AAPL"})
    assert ok is True


@pytest.mark.asyncio
async def test_execute_returns_articles(tool):
    result = await tool.execute(query="AAPL", max_results=5)
    assert "articles" in result
    assert "count" in result
    assert isinstance(result["articles"], list)
    # RSS feeds may occasionally be empty, but structure should be correct
    assert result["query"] == "AAPL"


@pytest.mark.asyncio
async def test_execute_empty_query(tool):
    result = await tool.execute(query="  ")
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_gold_news(tool):
    result = await tool.execute(query="gold", max_results=3)
    assert isinstance(result["articles"], list)


def test_clean_html():
    assert _clean_html("<b>Hello</b> <i>world</i>") == "Hello world"
    assert _clean_html("no tags here") == "no tags here"


def test_deduplicate():
    articles = [
        {"title": "Apple stock rises", "summary": "a"},
        {"title": "Apple Stock Rises!", "summary": "b"},
        {"title": "Gold hits new high", "summary": "c"},
    ]
    result = _deduplicate(articles)
    # The two Apple titles should deduplicate
    assert len(result) == 2


def test_title_hash_consistency():
    assert _title_hash("Hello World!") == _title_hash("hello world")
    assert _title_hash("Apple") != _title_hash("Google")
