"""LLM Insight Tool — generates financial insights via online or offline LLM."""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from tools.base import BaseTool
from tools.loader import ToolLoader
from services.llm_provider import LLMProvider, get_llm_provider
from services.data_store import DataStore

_SYSTEM_PROMPT = (
    "You are an expert financial analyst. Respond in valid JSON with these fields:\n"
    '{\n'
    '  "trend": "bullish" | "bearish" | "sideways",\n'
    '  "confidence": "low" | "medium" | "high",\n'
    '  "key_factors": ["factor1", "factor2", ...],\n'
    '  "short_term_outlook": "1-2 sentence outlook for 1-5 days",\n'
    '  "medium_term_outlook": "1-2 sentence outlook for 1-4 weeks",\n'
    '  "recommendation_hint": "bullish" | "bearish" | "neutral",\n'
    '  "summary": "2-4 sentence overall analysis"\n'
    '}\n'
    "Respond ONLY with the JSON object, no markdown fences or extra text."
)


class LLMInsightTool(BaseTool):

    def __init__(
        self,
        tool_loader: Optional[ToolLoader] = None,
        data_store: Optional[DataStore] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        super().__init__()
        self._loader = tool_loader
        self._store = data_store
        self._llm = llm_provider

    def set_dependencies(
        self,
        tool_loader: ToolLoader,
        data_store: Optional[DataStore] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._loader = tool_loader
        if data_store is not None:
            self._store = data_store
        if llm_provider is not None:
            self._llm = llm_provider

    def get_name(self) -> str:
        return "llm_insight"

    def get_description(self) -> str:
        return "Generate an AI-powered financial insight for an asset using online or offline LLM."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "Ticker symbol or asset name (e.g. 'AAPL', 'gold').",
                },
                "insight_type": {
                    "type": "string",
                    "description": "Type of analysis: 'trend', 'news_impact', or 'full' (default 'full').",
                },
                "llm_mode": {
                    "type": "string",
                    "description": "LLM mode: 'online', 'offline', or 'auto' (default 'auto').",
                },
                "include_news": {
                    "type": "boolean",
                    "description": "Whether to include news in the analysis (default true).",
                },
            },
            "required": ["asset"],
        }

    async def execute(
        self,
        asset: str,
        insight_type: str = "full",
        llm_mode: str = "auto",
        include_news: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self._loader:
            return {"error": "LLMInsightTool requires a ToolLoader (call set_dependencies)."}

        # --- 1. Get aggregated data ---
        ok, agg_data = await self._loader.execute_tool("data_aggregator", {
            "asset": asset,
            "include_news": include_news,
            "lookback_period": "1mo",
            "insight_type": insight_type,
        })
        if not ok or "error" in (agg_data if isinstance(agg_data, dict) else {}):
            return {"error": f"Data aggregation failed: {agg_data}"}

        formatted_prompt = agg_data.get("formatted_prompt", "")
        if not formatted_prompt:
            return {"error": "No formatted prompt produced by aggregator."}

        # --- 2. Resolve LLM provider ---
        provider = self._llm
        if provider is None or llm_mode != "auto":
            provider = await _resolve_provider(llm_mode)
        if provider is None:
            return {
                "error": "No LLM provider available. Set LLM_API_KEY for online or start Ollama for offline.",
                "aggregated_data": agg_data,
                "formatted_prompt": formatted_prompt,
            }

        # --- 3. Call LLM ---
        try:
            raw_response = await provider.generate(
                prompt=formatted_prompt,
                system=_SYSTEM_PROMPT,
            )
        except Exception as e:
            return {
                "error": f"LLM call failed: {e}",
                "model_used": provider.get_model_name(),
                "aggregated_data": agg_data,
                "formatted_prompt": formatted_prompt,
            }

        # --- 4. Parse response ---
        parsed = _parse_llm_response(raw_response)
        model_name = provider.get_model_name()
        now = datetime.now(timezone.utc).isoformat()

        result = {
            "asset": agg_data.get("asset", asset),
            "ticker": agg_data.get("ticker", asset),
            "current_price": agg_data.get("current_price"),
            "price_change_pct": agg_data.get("price_change_pct"),
            "insight": parsed.get("summary", raw_response[:500]),
            "trend": parsed.get("trend", "unknown"),
            "confidence": parsed.get("confidence", "unknown"),
            "key_factors": parsed.get("key_factors", []),
            "short_term_outlook": parsed.get("short_term_outlook", ""),
            "medium_term_outlook": parsed.get("medium_term_outlook", ""),
            "recommendation_hint": parsed.get("recommendation_hint", "neutral"),
            "model_used": model_name,
            "insight_type": insight_type,
            "timestamp": now,
            "raw_response": raw_response,
        }

        # --- 5. Persist insight ---
        if self._store:
            try:
                await self._store.store_insight(
                    ticker=result["ticker"],
                    asset=result["asset"],
                    insight_text=result["insight"],
                    model_used=model_name,
                    insight_type=insight_type,
                    metadata={
                        "trend": result["trend"],
                        "confidence": result["confidence"],
                        "recommendation_hint": result["recommendation_hint"],
                        "key_factors": result["key_factors"],
                    },
                )
            except Exception:
                pass  # storage failure is non-critical

        return result


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

async def _resolve_provider(mode: str) -> Optional[LLMProvider]:
    """Resolve provider by mode, with 'auto' trying online then offline."""
    if mode == "auto":
        # Try online first
        try:
            provider = get_llm_provider("online")
            if await provider.is_available():
                return provider
        except Exception:
            pass
        # Fall back to offline
        try:
            provider = get_llm_provider("offline")
            if await provider.is_available():
                return provider
        except Exception:
            pass
        return None

    try:
        provider = get_llm_provider(mode)
        return provider
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> Dict[str, Any]:
    """Parse LLM response as JSON with regex fallback."""
    # Try direct JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding any JSON object in the text
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Regex fallback: extract key fields
    result = {}
    trend_match = re.search(r"(?:trend|direction)\s*(?:is|:)\s*(bullish|bearish|sideways)", raw, re.IGNORECASE)
    if trend_match:
        result["trend"] = trend_match.group(1).lower()

    conf_match = re.search(r"(?:(low|medium|high)\s+confidence|confidence\s*(?:is|:)?\s*(low|medium|high))", raw, re.IGNORECASE)
    if conf_match:
        result["confidence"] = (conf_match.group(1) or conf_match.group(2)).lower()

    rec_match = re.search(r"recommendation\s*(?:is|:)?\s*(bullish|bearish|neutral)", raw, re.IGNORECASE)
    if rec_match:
        result["recommendation_hint"] = rec_match.group(1).lower()

    result["summary"] = raw[:500]
    return result
