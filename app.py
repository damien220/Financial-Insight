"""
Financial Insight — main entry point.

Initializes the MCP tool system, loads financial tools, starts the scheduler,
and runs the server.
"""

import sys
import asyncio
import signal
import argparse
from pathlib import Path

# Ensure project root is on sys.path so local tools/ is importable
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_config
from core.logger import MCPLogger
from tools.loader import ToolLoader
from tools.price.gold_price_tool import GoldPriceTool
from tools.price.stock_price_tool import StockPriceTool
from tools.news.financial_news_tool import FinancialNewsTool
from tools.data.data_aggregator_tool import DataAggregatorTool
from tools.llm.llm_insight_tool import LLMInsightTool
from services.data_store import DataStore
from services.events import EventBus
from services.scheduler import FinancialScheduler


def build_tools(loader: ToolLoader, store: DataStore) -> None:
    """Register all tools with the loader."""
    loader.register_tool(GoldPriceTool())
    loader.register_tool(StockPriceTool())
    loader.register_tool(FinancialNewsTool())
    aggregator = DataAggregatorTool(tool_loader=loader)
    loader.register_tool(aggregator)
    insight_tool = LLMInsightTool(tool_loader=loader, data_store=store)
    loader.register_tool(insight_tool)


async def run_demo(loader: ToolLoader, store: DataStore) -> None:
    """Quick self-test: fetch prices, news, aggregation, LLM insight."""
    # Prices
    ok, res = await loader.execute_tool("gold_price", {"period": "5d", "interval": "1d"})
    if ok and "error" not in res:
        print(f"  Gold price       : ${res['current_price']}  ({res['price_change_pct']:+.2f}%)")
        await store.store_prices("GC=F", "Gold Futures", res["history"])

    ok, res = await loader.execute_tool("stock_price", {"ticker": "AAPL", "period": "5d", "interval": "1d"})
    if ok and "error" not in res:
        print(f"  AAPL price       : ${res['current_price']}  ({res['price_change_pct']:+.2f}%)")
        await store.store_prices("AAPL", res["asset"], res["history"])

    # Aggregation
    ok, agg = await loader.execute_tool("data_aggregator", {
        "asset": "AAPL", "lookback_period": "5d", "include_news": True, "insight_type": "full",
    })
    if ok and "error" not in agg:
        print(f"  Aggregator       : {agg['data_points']} pts, {len(agg['recent_news'])} news, {len(agg['formatted_prompt'])} char prompt")

    # LLM insight
    ok, ins = await loader.execute_tool("llm_insight", {"asset": "AAPL", "insight_type": "full", "llm_mode": "auto"})
    if ok and "error" not in ins:
        print(f"  LLM insight      : {ins['trend']} ({ins['confidence']}) via {ins['model_used']}")
    else:
        err = ins.get("error", ins) if isinstance(ins, dict) else ins
        print(f"  LLM insight      : {err}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Financial Insight")
    parser.add_argument("--schedule", action="store_true", help="Run with periodic scheduler")
    parser.add_argument("--demo", action="store_true", help="Run demo self-test then exit")
    args = parser.parse_args()

    config = get_config()
    logger = MCPLogger.get_logger("financial_insight")

    # --- Initialize data store ---
    db_path = config.get("DATABASE_PATH", "data/prices.db")
    store = DataStore(db_path)
    await store.initialize()

    # --- Load tools ---
    loader = ToolLoader()
    build_tools(loader, store)

    event_bus = EventBus()

    print("[Financial Insight] Starting up …")
    print(f"  Tools registered : {loader.list_tools()}")
    print(f"  Database         : {db_path}")

    # --- Demo mode (default if no flags) ---
    if args.demo or not args.schedule:
        await run_demo(loader, store)

    # --- Scheduler mode ---
    if args.schedule:
        scheduler = FinancialScheduler(
            tool_loader=loader,
            data_store=store,
            event_bus=event_bus,
            config_path=config.get("ASSETS_CONFIG", "config/assets.yaml"),
        )

        # Log events to console
        async def on_price(event):
            d = event["data"]
            sig = " *** SIGNIFICANT" if d.get("significant_change") else ""
            print(f"  [event] price_updated: {d['ticker']} ${d['price']}{sig}")

        async def on_insight(event):
            d = event["data"]
            print(f"  [event] insight_generated: {d['ticker']} trend={d.get('trend')} via {d.get('model')}")

        event_bus.subscribe("price_updated", on_price)
        event_bus.subscribe("insight_generated", on_insight)

        scheduler.start()
        jobs = scheduler.get_jobs_info()
        for j in jobs:
            print(f"  Job: {j['name']:20s} next_run={j['next_run']}")

        # Run initial refresh immediately
        print("\n  Running initial price refresh …")
        await scheduler.trigger_price_refresh()

        print("\n  Scheduler running. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await stop_event.wait()
        scheduler.stop()
        print("\n  Scheduler stopped.")

    print("[Financial Insight] OK")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
