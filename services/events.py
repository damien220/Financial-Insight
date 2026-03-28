"""Lightweight pub/sub event system for internal notifications.

Events: price_updated, news_updated, insight_generated.
Foundation for future trading signals in the AI trading platform.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional


EventCallback = Callable[[Dict[str, Any]], Coroutine]


class EventBus:

    def __init__(self):
        self._subscribers: Dict[str, List[EventCallback]] = defaultdict(list)
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        subs = self._subscribers.get(event_type, [])
        if callback in subs:
            subs.remove(callback)

    async def emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        for cb in self._subscribers.get(event_type, []):
            try:
                await cb(event)
            except Exception:
                pass  # subscriber errors are non-fatal

    def get_history(self, event_type: Optional[str] = None, limit: int = 20) -> List[Dict]:
        events = self._history
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]

    def clear(self) -> None:
        self._subscribers.clear()
        self._history.clear()
