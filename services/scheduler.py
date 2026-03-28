"""Scheduler module — periodic refresh for prices, news, and LLM insights.

Wraps APScheduler's AsyncIOScheduler with market-hours awareness,
change-detection triggers, and event bus integration.
"""

import os
import asyncio
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional

import yaml
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.logger import MCPLogger
from tools.loader import ToolLoader
from services.data_store import DataStore
from services.events import EventBus

logger = MCPLogger.get_logger("scheduler")

# Default schedule config (overridden by assets.yaml)
_DEFAULTS = {
    "price_interval_minutes": 5,
    "news_interval_minutes": 15,
    "insight_interval_minutes": 60,
    "market_hours_only": True,
    "market_open": "09:30",
    "market_close": "16:00",
    "timezone": "US/Eastern",
    "price_change_threshold_pct": 2.0,
}


class FinancialScheduler:

    def __init__(
        self,
        tool_loader: ToolLoader,
        data_store: DataStore,
        event_bus: Optional[EventBus] = None,
        config_path: Optional[str] = None,
    ):
        self._loader = tool_loader
        self._store = data_store
        self._events = event_bus or EventBus()
        self._scheduler = AsyncIOScheduler()
        self._config = _load_schedule_config(config_path)
        self._running = False
        # Track last known prices for change detection
        self._last_prices: Dict[str, float] = {}

    @property
    def event_bus(self) -> EventBus:
        return self._events

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        cfg = self._config
        tz = pytz.timezone(cfg["timezone"])

        self._scheduler.add_job(
            self._refresh_prices,
            IntervalTrigger(minutes=cfg["price_interval_minutes"], timezone=tz),
            id="price_refresh",
            name="Price refresh",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._refresh_news,
            IntervalTrigger(minutes=cfg["news_interval_minutes"], timezone=tz),
            id="news_refresh",
            name="News refresh",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._refresh_insights,
            IntervalTrigger(minutes=cfg["insight_interval_minutes"], timezone=tz),
            id="insight_refresh",
            name="Insight refresh",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        logger.info(
            f"Scheduler started  price={cfg['price_interval_minutes']}m  "
            f"news={cfg['news_interval_minutes']}m  insight={cfg['insight_interval_minutes']}m  "
            f"market_hours_only={cfg['market_hours_only']}"
        )

    def stop(self) -> None:
        if self._running:
            self._scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Scheduler stopped")

    def get_jobs_info(self) -> List[Dict[str, Any]]:
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return jobs

    # ------------------------------------------------------------------
    # Refresh jobs
    # ------------------------------------------------------------------

    async def _refresh_prices(self) -> None:
        if self._should_skip():
            logger.info("Price refresh skipped — outside market hours")
            return

        assets = _get_tracked_assets(self._config)
        logger.info(f"Price refresh started for {len(assets)} assets")

        for asset in assets:
            ticker = asset["ticker"]
            try:
                if ticker == "GC=F":
                    ok, result = await self._loader.execute_tool(
                        "gold_price", {"period": "5d", "interval": "1d"}
                    )
                else:
                    ok, result = await self._loader.execute_tool(
                        "stock_price", {"ticker": ticker, "period": "5d", "interval": "1d"}
                    )

                if ok and "error" not in result:
                    await self._store.store_prices(ticker, asset["name"], result["history"])
                    current = result["current_price"]

                    # Change detection
                    significant = self._check_price_change(ticker, current)

                    await self._events.emit("price_updated", {
                        "ticker": ticker,
                        "price": current,
                        "change_pct": result.get("price_change_pct", 0),
                        "significant_change": significant,
                    })
                    logger.info(f"Price updated: {ticker} ${current}")

                    if significant:
                        logger.info(f"Significant price change for {ticker} — triggering insight refresh")
                        await self._refresh_insight_for(asset)
                else:
                    logger.warning(f"Price fetch failed for {ticker}: {result}")

            except Exception as e:
                logger.error(f"Price refresh error for {ticker}: {e}")

    async def _refresh_news(self) -> None:
        if self._should_skip():
            return

        assets = _get_tracked_assets(self._config)
        logger.info(f"News refresh started for {len(assets)} assets")

        for asset in assets:
            try:
                query = asset["name"] if asset["ticker"] == "GC=F" else asset["ticker"]
                ok, result = await self._loader.execute_tool(
                    "financial_news", {"query": query, "max_results": 5}
                )
                if ok:
                    await self._events.emit("news_updated", {
                        "ticker": asset["ticker"],
                        "count": result.get("count", 0),
                    })
                    logger.info(f"News updated: {asset['ticker']} ({result.get('count', 0)} articles)")
            except Exception as e:
                logger.error(f"News refresh error for {asset['ticker']}: {e}")

    async def _refresh_insights(self) -> None:
        assets = _get_tracked_assets(self._config)
        logger.info(f"Insight refresh started for {len(assets)} assets")

        for asset in assets:
            await self._refresh_insight_for(asset)

    async def _refresh_insight_for(self, asset: Dict[str, str]) -> None:
        ticker = asset["ticker"]
        try:
            ok, result = await self._loader.execute_tool(
                "llm_insight", {"asset": ticker, "insight_type": "full", "llm_mode": "auto"}
            )
            if ok and "error" not in result:
                await self._events.emit("insight_generated", {
                    "ticker": ticker,
                    "trend": result.get("trend"),
                    "confidence": result.get("confidence"),
                    "model": result.get("model_used"),
                })
                logger.info(f"Insight generated: {ticker} trend={result.get('trend')}")
            else:
                err = result.get("error", result) if isinstance(result, dict) else result
                logger.warning(f"Insight generation skipped for {ticker}: {err}")
        except Exception as e:
            logger.error(f"Insight refresh error for {ticker}: {e}")

    # ------------------------------------------------------------------
    # Market hours & change detection
    # ------------------------------------------------------------------

    def _should_skip(self) -> bool:
        if not self._config.get("market_hours_only", True):
            return False
        tz = pytz.timezone(self._config["timezone"])
        now = datetime.now(tz)
        # Skip weekends
        if now.weekday() >= 5:
            return True
        open_h, open_m = map(int, self._config["market_open"].split(":"))
        close_h, close_m = map(int, self._config["market_close"].split(":"))
        market_open = time(open_h, open_m)
        market_close = time(close_h, close_m)
        return not (market_open <= now.time() <= market_close)

    def _check_price_change(self, ticker: str, current_price: float) -> bool:
        threshold = self._config.get("price_change_threshold_pct", 2.0)
        last = self._last_prices.get(ticker)
        self._last_prices[ticker] = current_price
        if last is None or last == 0:
            return False
        pct = abs((current_price - last) / last * 100)
        return pct >= threshold

    # ------------------------------------------------------------------
    # Manual triggers (for dashboard / testing)
    # ------------------------------------------------------------------

    async def trigger_price_refresh(self) -> None:
        await self._refresh_prices()

    async def trigger_news_refresh(self) -> None:
        await self._refresh_news()

    async def trigger_insight_refresh(self) -> None:
        await self._refresh_insights()


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_schedule_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("ASSETS_CONFIG", "config/assets.yaml")
    cfg = dict(_DEFAULTS)
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        refresh = data.get("refresh", {})
        cfg.update({k: v for k, v in refresh.items() if v is not None})
        # Also keep full yaml data for asset list
        cfg["_yaml"] = data
    except FileNotFoundError:
        cfg["_yaml"] = {}
    return cfg


def _get_tracked_assets(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    data = cfg.get("_yaml", {})
    assets_cfg = data.get("assets", {})
    result = []
    for category in assets_cfg.values():
        if isinstance(category, dict):
            for key, info in category.items():
                if isinstance(info, dict) and "ticker" in info:
                    result.append({
                        "ticker": info["ticker"],
                        "name": info.get("name", key),
                        "category": info.get("category", "unknown"),
                    })
    return result
