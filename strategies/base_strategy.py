"""Base strategy abstraction and reference strategy implementations."""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for all algorithmic trading strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier name of the strategy."""
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate indicator values and trading signals on the input OHLCV DataFrame.

        Args:
            df (pd.DataFrame): DataFrame containing 'open', 'high', 'low', 'close', and 'volume'.

        Returns:
            pd.DataFrame: DataFrame with added technical indicators and a 'Signal' column (1, 0, -1).
        """
        pass


class MacdRsiSwing(BaseStrategy):
    """Example strategy implementation using MACD signal line crossovers."""

    @property
    def name(self) -> str:
        """Return strategy name."""
        return "MACD_RSI_Swing"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate MACD crossover signals.

        Args:
            df (pd.DataFrame): Input price DataFrame.

        Returns:
            pd.DataFrame: DataFrame with computed MACD and Signal columns.
        """
        df = df.copy()

        # Compute Fast & Slow Exponential Moving Averages
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Determine trading signals (1: Buy, -1: Sell, 0: Hold)
        df['Signal'] = 0
        df.loc[(df['MACD'] > df['Signal_Line']), 'Signal'] = 1   # Buy signal
        df.loc[(df['MACD'] < df['Signal_Line']), 'Signal'] = -1  # Sell signal

        return df