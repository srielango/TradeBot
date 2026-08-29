"""Base strategy abstraction interface for all algorithmic trading strategies."""

from abc import ABC, abstractmethod

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE


class BaseStrategy(ABC):
    """Abstract base class for all algorithmic trading strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier name of the strategy."""

    @abstractmethod
    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate indicator values, trading signals, stop loss, and position sizing.

        Args:
            df (pd.DataFrame): DataFrame with 'open', 'high', 'low', 'close', and 'volume'.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional risk allocation (e.g. 0.01 for 1%).

        Returns:
            pd.DataFrame: DataFrame with computed indicators, Signal, StopLoss, and PositionSize.
        """
