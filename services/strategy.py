"""Trading strategy interfaces — future AI trading platform hooks.

These are abstract interfaces only. The future trading platform will provide
concrete implementations that consume LLM insights and produce trading signals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """Trading signal produced by a strategy.

    This is the bridge between the insight engine (Phase 3) and
    a future execution engine. The `recommendation_hint` field from
    LLMInsightTool maps directly to the `action` field here.
    """
    asset: str
    ticker: str
    action: Action
    confidence: str          # low / medium / high
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class TradingStrategy(ABC):
    """Abstract base for trading strategies.

    Subclass and implement `evaluate()` to create a strategy that
    converts LLM insights into actionable signals.

    Example future implementation::

        class MomentumStrategy(TradingStrategy):
            def get_name(self):
                return "momentum"

            async def evaluate(self, insight):
                hint = insight.get("recommendation_hint", "neutral")
                if hint == "bullish" and insight.get("confidence") == "high":
                    return Signal(
                        asset=insight["asset"],
                        ticker=insight["ticker"],
                        action=Action.BUY,
                        confidence="high",
                        reasoning="Strong bullish signal with high confidence",
                    )
                return Signal(...)
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the strategy name."""
        ...

    @abstractmethod
    async def evaluate(self, insight: Dict[str, Any]) -> Signal:
        """Evaluate an LLM insight and produce a trading signal.

        Args:
            insight: Output from LLMInsightTool.execute(), containing:
                - ticker, asset, current_price, price_change_pct
                - trend, confidence, key_factors
                - recommendation_hint (bullish/bearish/neutral)
                - short_term_outlook, medium_term_outlook

        Returns:
            Signal with action, confidence, and reasoning.
        """
        ...

    async def evaluate_batch(self, insights: List[Dict[str, Any]]) -> List[Signal]:
        """Evaluate multiple insights. Default: sequential evaluation."""
        return [await self.evaluate(i) for i in insights]


class PortfolioManager(ABC):
    """Abstract portfolio manager interface.

    Future implementations will track positions, execute signals,
    manage risk, and report P&L.
    """

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Return current portfolio positions."""
        ...

    @abstractmethod
    async def execute_signal(self, signal: Signal) -> Dict[str, Any]:
        """Execute a trading signal. Returns execution result."""
        ...

    @abstractmethod
    async def get_portfolio_value(self) -> float:
        """Return total portfolio value in USD."""
        ...
