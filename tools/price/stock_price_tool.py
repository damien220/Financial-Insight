"""Stock Price Tool — fetches stock/ETF data via yfinance."""

from typing import Any, Dict, List, Optional
import yfinance as yf
import pandas as pd
from tools.base import BaseTool

VALID_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max")
VALID_INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo")


class StockPriceTool(BaseTool):

    def get_name(self) -> str:
        return "stock_price"

    def get_description(self) -> str:
        return "Fetch current and historical price data for a stock or ETF by ticker symbol."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock/ETF ticker symbol (e.g. AAPL, MSFT, SPY).",
                },
                "period": {
                    "type": "string",
                    "description": f"History period. One of: {', '.join(VALID_PERIODS)}",
                },
                "interval": {
                    "type": "string",
                    "description": f"Data interval. One of: {', '.join(VALID_INTERVALS)}",
                },
            },
            "required": ["ticker"],
        }

    async def execute(self, ticker: str, period: str = "1mo", interval: str = "1d", **kwargs) -> Dict[str, Any]:
        ticker = ticker.upper().strip()
        if not ticker:
            return {"error": "Ticker symbol is required."}
        if period not in VALID_PERIODS:
            return {"error": f"Invalid period '{period}'. Must be one of {VALID_PERIODS}"}
        if interval not in VALID_INTERVALS:
            return {"error": f"Invalid interval '{interval}'. Must be one of {VALID_INTERVALS}"}

        try:
            stock = yf.Ticker(ticker)
            hist: pd.DataFrame = stock.history(period=period, interval=interval)
        except Exception as e:
            return {"asset": ticker, "ticker": ticker, "error": f"Network/API error: {e}"}

        if hist.empty:
            return {
                "asset": ticker,
                "ticker": ticker,
                "error": f"No data returned for '{ticker}' — check ticker or market hours.",
            }

        info = _safe_info(stock)
        latest = hist.iloc[-1]
        prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else latest["Close"]
        price_change = float(latest["Close"] - prev_close)
        pct_change = (price_change / prev_close * 100) if prev_close else 0.0

        history_records = _dataframe_to_records(hist)

        return {
            "asset": info.get("shortName", ticker),
            "ticker": ticker,
            "current_price": round(float(latest["Close"]), 2),
            "price_change": round(price_change, 2),
            "price_change_pct": round(pct_change, 2),
            "day_high": round(float(latest["High"]), 2),
            "day_low": round(float(latest["Low"]), 2),
            "volume": int(latest["Volume"]),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "USD"),
            "period": period,
            "interval": interval,
            "data_points": len(hist),
            "history": history_records,
        }


def _safe_info(stock: yf.Ticker) -> Dict[str, Any]:
    try:
        return stock.info
    except Exception:
        return {}


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
