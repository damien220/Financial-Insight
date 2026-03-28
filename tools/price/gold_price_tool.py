"""Gold Price Tool — fetches gold futures data via yfinance."""

from typing import Any, Dict, List
import yfinance as yf
import pandas as pd
from tools.base import BaseTool

GOLD_TICKER = "GC=F"

VALID_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max")
VALID_INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo")


class GoldPriceTool(BaseTool):

    def get_name(self) -> str:
        return "gold_price"

    def get_description(self) -> str:
        return "Fetch current and historical gold futures (GC=F) price data."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": f"History period. One of: {', '.join(VALID_PERIODS)}",
                },
                "interval": {
                    "type": "string",
                    "description": f"Data interval. One of: {', '.join(VALID_INTERVALS)}",
                },
            },
            "required": [],
        }

    async def execute(self, period: str = "1mo", interval: str = "1d", **kwargs) -> Dict[str, Any]:
        if period not in VALID_PERIODS:
            return {"error": f"Invalid period '{period}'. Must be one of {VALID_PERIODS}"}
        if interval not in VALID_INTERVALS:
            return {"error": f"Invalid interval '{interval}'. Must be one of {VALID_INTERVALS}"}

        try:
            ticker = yf.Ticker(GOLD_TICKER)
            hist: pd.DataFrame = ticker.history(period=period, interval=interval)
        except Exception as e:
            return {"asset": "Gold Futures", "ticker": GOLD_TICKER, "error": f"Network/API error: {e}"}

        if hist.empty:
            return {
                "asset": "Gold Futures",
                "ticker": GOLD_TICKER,
                "error": "No data returned — market may be closed or ticker unavailable.",
            }

        latest = hist.iloc[-1]
        prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else latest["Close"]
        price_change = float(latest["Close"] - prev_close)
        pct_change = (price_change / prev_close * 100) if prev_close else 0.0

        history_records = _dataframe_to_records(hist)

        return {
            "asset": "Gold Futures",
            "ticker": GOLD_TICKER,
            "current_price": round(float(latest["Close"]), 2),
            "price_change": round(price_change, 2),
            "price_change_pct": round(pct_change, 2),
            "day_high": round(float(latest["High"]), 2),
            "day_low": round(float(latest["Low"]), 2),
            "volume": int(latest["Volume"]),
            "period": period,
            "interval": interval,
            "data_points": len(hist),
            "history": history_records,
        }


def _dataframe_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    records = []
    for ts, row in df.iterrows():
        records.append({
            "timestamp": str(ts),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })
    return records
