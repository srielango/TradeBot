"""MACD Trend and Momentum Swing strategy implementation."""

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class MacdRsiSwing(BaseStrategy):
    """Strategy utilizing MACD signal line crossovers with swing-low stop-loss protection."""

    @property
    def name(self) -> str:
        """Return unique strategy name."""
        return "MACD_RSI_Swing"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate MACD crossover signals with risk-based position sizing and stop loss.

        Args:
            df (pd.DataFrame): Input OHLCV price DataFrame.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.

        Returns:
            pd.DataFrame: Augmented DataFrame with MACD, Signal, StopLoss, and PositionSize.
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

        # Stop loss and position sizing
        df['StopLoss'] = None
        df['PositionSize'] = 0

        risk_amount = capital * risk_per_trade

        for i in range(len(df)):
            if df.loc[i, 'Signal'] == 1:
                # Look back 5 days for recent swing low
                lookback = df.iloc[max(0, i - 5):i]
                if not lookback.empty:
                    stop = lookback['low'].min()
                    entry = df.loc[i + 1, 'open'] if i + 1 < len(df) else df.loc[i, 'close']
                    risk_per_share = entry - stop
                    if risk_per_share > 0:
                        position_size = int(risk_amount / risk_per_share)
                        df.loc[i, 'StopLoss'] = stop
                        df.loc[i, 'PositionSize'] = position_size

        return df
