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

        # Determine trading signals based on MACD signal line crossovers
        # 1: Bullish crossover (MACD crosses above Signal Line)
        # -1: Bearish crossover (MACD crosses below Signal Line)
        # 0: Hold / Neutral
        bullish_crossover = (df['MACD'] > df['Signal_Line']) & (
            df['MACD'].shift(1) <= df['Signal_Line'].shift(1)
        )
        bearish_crossover = (df['MACD'] < df['Signal_Line']) & (
            df['MACD'].shift(1) >= df['Signal_Line'].shift(1)
        )

        df['Signal'] = 0
        df.loc[bullish_crossover, 'Signal'] = 1
        df.loc[bearish_crossover, 'Signal'] = -1

        # Stop loss and position sizing
        swing_low = df['low'].shift(1).rolling(window=5, min_periods=1).min()
        df['StopLoss'] = None
        df['PositionSize'] = 0

        risk_amount = capital * risk_per_trade

        # Next-day open price estimate for entry sizing
        entry_est = df['open'].shift(-1).fillna(df['close'])
        risk_per_share = entry_est - swing_low

        buy_mask = (df['Signal'] == 1) & (risk_per_share > 0)
        df.loc[buy_mask, 'StopLoss'] = swing_low[buy_mask]
        df.loc[buy_mask, 'PositionSize'] = (risk_amount / risk_per_share[buy_mask]).astype(int)

        return df
