"""SQLite-backed data store for price history and insights."""

import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ticker TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ticker TEXT NOT NULL,
    insight_text TEXT NOT NULL,
    model_used TEXT,
    insight_type TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_price_ticker_ts ON price_history(ticker, timestamp);
CREATE INDEX IF NOT EXISTS idx_insights_ticker ON insights(ticker, created_at);
"""


class DataStore:

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or os.environ.get("DATABASE_PATH", "data/prices.db")
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ---- Price History ----

    async def store_prices(self, ticker: str, asset: str, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        rows = [
            (asset, ticker, r["timestamp"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume"))
            for r in records
        ]
        await self._db.executemany(
            """INSERT OR REPLACE INTO price_history
               (asset, ticker, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()
        return len(rows)

    async def get_price_history(
        self, ticker: str, limit: int = 100, since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT timestamp, open, high, low, close, volume FROM price_history WHERE ticker = ?"
        params: list = [ticker]
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {"timestamp": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in rows
        ]

    async def get_latest_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        rows = await self.get_price_history(ticker, limit=1)
        return rows[0] if rows else None

    # ---- Insights ----

    async def store_insight(
        self, ticker: str, asset: str, insight_text: str,
        model_used: str = "", insight_type: str = "general",
        metadata: Optional[Dict] = None,
    ) -> int:
        meta_json = json.dumps(metadata) if metadata else None
        async with self._db.execute(
            """INSERT INTO insights (asset, ticker, insight_text, model_used, insight_type, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (asset, ticker, insight_text, model_used, insight_type, meta_json),
        ) as cursor:
            row_id = cursor.lastrowid
        await self._db.commit()
        return row_id

    async def get_latest_insight(self, ticker: str, insight_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        query = "SELECT id, asset, insight_text, model_used, insight_type, metadata, created_at FROM insights WHERE ticker = ?"
        params: list = [ticker]
        if insight_type:
            query += " AND insight_type = ?"
            params.append(insight_type)
        query += " ORDER BY created_at DESC LIMIT 1"

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "asset": row[1], "insight_text": row[2],
            "model_used": row[3], "insight_type": row[4],
            "metadata": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
        }

    async def get_insights(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with self._db.execute(
            """SELECT id, asset, insight_text, model_used, insight_type, metadata, created_at
               FROM insights WHERE ticker = ? ORDER BY created_at DESC LIMIT ?""",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"id": r[0], "asset": r[1], "insight_text": r[2], "model_used": r[3],
             "insight_type": r[4], "metadata": json.loads(r[5]) if r[5] else None, "created_at": r[6]}
            for r in rows
        ]
