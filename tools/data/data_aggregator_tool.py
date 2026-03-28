"""Data Aggregator Tool — combines price + news + technicals into LLM-ready format."""

from typing import Any, Dict, List, Optional
import math
from tools.base import BaseTool
from tools.loader import ToolLoader

# Ticker alias map (friendly name -> yfinance ticker)
_ALIASES = {
    "gold": "GC=F",
    "gold futures": "GC=F",
    "sp500": "SPY",
    "s&p500": "SPY",
    "s&p 500": "SPY",
}

_PROMPT_TEMPLATES = {
    "trend": (
        "You are a financial analyst. Analyze the price trend for {asset} ({ticker}).\n\n"
        "## Current Data\n"
        "- Current price: ${current_price}\n"
        "- Price change: {price_change_pct:+.2f}% over the lookback period\n"
        "- Day range: ${day_low} – ${day_high}\n\n"
        "## Technical Indicators\n{technicals_text}\n\n"
        "## Price History ({data_points} data points)\n{history_summary}\n\n"
        "Provide:\n"
        "1. Current trend direction (bullish / bearish / sideways)\n"
        "2. Key support and resistance levels\n"
        "3. Short-term outlook (1–5 days)\n"
        "4. Confidence level (low / medium / high)\n"
    ),
    "news_impact": (
        "You are a financial analyst. Assess the impact of recent news on {asset} ({ticker}).\n\n"
        "## Current Price\n"
        "- Price: ${current_price} ({price_change_pct:+.2f}%)\n\n"
        "## Recent News\n{news_text}\n\n"
        "Provide:\n"
        "1. Overall sentiment of the news (positive / negative / mixed)\n"
        "2. Which news items are most likely to move the price\n"
        "3. Expected impact direction and magnitude\n"
        "4. Confidence level (low / medium / high)\n"
    ),
    "full": (
        "You are a senior financial analyst. Provide a comprehensive analysis of {asset} ({ticker}).\n\n"
        "## Current Data\n"
        "- Current price: ${current_price}\n"
        "- Price change: {price_change_pct:+.2f}% over the lookback period\n"
        "- Day range: ${day_low} – ${day_high}\n\n"
        "## Technical Indicators\n{technicals_text}\n\n"
        "## Price History ({data_points} data points)\n{history_summary}\n\n"
        "## Recent News\n{news_text}\n\n"
        "## Market Context\n{market_context}\n\n"
        "Provide:\n"
        "1. Trend analysis (direction, strength, duration)\n"
        "2. Key technical levels (support, resistance)\n"
        "3. News sentiment and likely price impact\n"
        "4. Short-term outlook (1–5 days) and medium-term outlook (1–4 weeks)\n"
        "5. Key risks and catalysts\n"
        "6. Overall recommendation hint (bullish / bearish / neutral) with confidence\n"
    ),
}


class DataAggregatorTool(BaseTool):

    def __init__(self, tool_loader: Optional[ToolLoader] = None):
        super().__init__()
        self._loader = tool_loader

    def set_tool_loader(self, loader: ToolLoader) -> None:
        self._loader = loader

    def get_name(self) -> str:
        return "data_aggregator"

    def get_description(self) -> str:
        return "Aggregate price data, news, and technical indicators into a structured LLM-ready format."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "Ticker symbol or asset name (e.g. 'AAPL', 'gold').",
                },
                "include_news": {
                    "type": "boolean",
                    "description": "Whether to include news articles (default true).",
                },
                "lookback_period": {
                    "type": "string",
                    "description": "Price history lookback period (default '1mo').",
                },
                "insight_type": {
                    "type": "string",
                    "description": "Prompt type: 'trend', 'news_impact', or 'full' (default 'full').",
                },
            },
            "required": ["asset"],
        }

    async def execute(
        self,
        asset: str,
        include_news: bool = True,
        lookback_period: str = "1mo",
        insight_type: str = "full",
        **kwargs,
    ) -> Dict[str, Any]:
        if not self._loader:
            return {"error": "DataAggregatorTool requires a ToolLoader instance (call set_tool_loader)."}

        ticker = _resolve_ticker(asset)
        is_gold = ticker == "GC=F"

        # --- Fetch price data ---
        if is_gold:
            ok, price_data = await self._loader.execute_tool("gold_price", {
                "period": lookback_period, "interval": "1d",
            })
        else:
            ok, price_data = await self._loader.execute_tool("stock_price", {
                "ticker": ticker, "period": lookback_period, "interval": "1d",
            })

        if not ok or "error" in (price_data if isinstance(price_data, dict) else {}):
            return {"error": f"Price fetch failed for '{asset}': {price_data}"}

        # --- Compute technical indicators ---
        history = price_data.get("history", [])
        closes = [r["close"] for r in history]
        technicals = _compute_technicals(closes)

        # --- Fetch news (optional) ---
        news_articles: List[Dict] = []
        if include_news:
            query = asset if is_gold else ticker
            ok_n, news_data = await self._loader.execute_tool("financial_news", {
                "query": query, "max_results": 8,
            })
            if ok_n and isinstance(news_data, dict):
                news_articles = news_data.get("articles", [])

        # --- Fetch market context (SPY) ---
        market_context = ""
        if ticker != "SPY":
            ok_m, spy_data = await self._loader.execute_tool("stock_price", {
                "ticker": "SPY", "period": "5d", "interval": "1d",
            })
            if ok_m and "error" not in spy_data:
                market_context = (
                    f"S&P 500 (SPY): ${spy_data['current_price']} "
                    f"({spy_data['price_change_pct']:+.2f}% last session)"
                )

        # --- Build LLM-ready output ---
        asset_name = price_data.get("asset", asset)
        history_summary = _summarize_history(history)
        technicals_text = _format_technicals(technicals)
        news_text = _format_news(news_articles) if news_articles else "No recent news available."

        template = _PROMPT_TEMPLATES.get(insight_type, _PROMPT_TEMPLATES["full"])
        formatted_prompt = template.format(
            asset=asset_name,
            ticker=ticker,
            current_price=price_data.get("current_price", "N/A"),
            price_change_pct=price_data.get("price_change_pct", 0),
            day_high=price_data.get("day_high", "N/A"),
            day_low=price_data.get("day_low", "N/A"),
            data_points=price_data.get("data_points", 0),
            technicals_text=technicals_text,
            history_summary=history_summary,
            news_text=news_text,
            market_context=market_context or "Not available.",
        )

        return {
            "asset": asset_name,
            "ticker": ticker,
            "current_price": price_data.get("current_price"),
            "price_change_pct": price_data.get("price_change_pct"),
            "day_high": price_data.get("day_high"),
            "day_low": price_data.get("day_low"),
            "volume": price_data.get("volume"),
            "technical_indicators": technicals,
            "price_history_summary": history_summary,
            "data_points": price_data.get("data_points", 0),
            "recent_news": news_articles,
            "market_context": market_context,
            "insight_type": insight_type,
            "formatted_prompt": formatted_prompt,
        }


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def _compute_technicals(closes: List[float]) -> Dict[str, Any]:
    if not closes:
        return {}
    result: Dict[str, Any] = {}

    # SMA-20
    if len(closes) >= 20:
        result["sma_20"] = round(sum(closes[-20:]) / 20, 2)
    elif len(closes) >= 5:
        n = len(closes)
        result[f"sma_{n}"] = round(sum(closes) / n, 2)

    # RSI-14
    if len(closes) >= 15:
        result["rsi_14"] = round(_rsi(closes, 14), 2)

    # Daily volatility (std dev of daily returns)
    if len(closes) >= 3:
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
        if returns:
            mean_r = sum(returns) / len(returns)
            var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            result["daily_volatility_pct"] = round(math.sqrt(var) * 100, 3)

    # Price vs SMA signal
    sma_key = "sma_20" if "sma_20" in result else next((k for k in result if k.startswith("sma_")), None)
    if sma_key and closes:
        result["price_vs_sma"] = "above" if closes[-1] > result[sma_key] else "below"

    return result


def _rsi(closes: List[float], period: int = 14) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _resolve_ticker(asset: str) -> str:
    lower = asset.lower().strip()
    if lower in _ALIASES:
        return _ALIASES[lower]
    return asset.upper().strip()


def _summarize_history(history: List[Dict]) -> str:
    if not history:
        return "No history available."
    lines = []
    for r in history[-10:]:  # last 10 data points
        lines.append(f"  {r['timestamp'][:16]}  O:{r['open']}  H:{r['high']}  L:{r['low']}  C:{r['close']}  V:{r['volume']}")
    return "\n".join(lines)


def _format_technicals(technicals: Dict[str, Any]) -> str:
    if not technicals:
        return "Insufficient data for technical indicators."
    lines = []
    for k, v in technicals.items():
        label = k.upper().replace("_", " ")
        lines.append(f"- {label}: {v}")
    return "\n".join(lines)


def _format_news(articles: List[Dict]) -> str:
    if not articles:
        return "No recent news available."
    lines = []
    for i, a in enumerate(articles[:8], 1):
        lines.append(f"{i}. [{a.get('source', '?')}] {a['title']}")
        if a.get("summary"):
            lines.append(f"   {a['summary'][:200]}")
    return "\n".join(lines)
