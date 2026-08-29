"""Moving Average combined with Stochastic Oscillator strategy implementation."""

import numpy as np
import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class MovingAverageStochastic(BaseStrategy):
    """Strategy combining 200-day Trend Following Moving Average with Stochastic Oscillator."""

    def __init__(
        self,
        k_period: int = 8,
        k_smooth: int = 3,
        d_smooth: int = 3,
        ma_window: int = 200,
        oversold_threshold: float = 20.0,
    ):
        """Initialize technical strategy parameters.

        Args:
            k_period (int): Lookback window for Stochastic %K (default 8).
            k_smooth (int): Smoothing factor for %K (default 3).
            d_smooth (int): Smoothing factor for %D (default 3).
            ma_window (int): Moving average trend filter period (default 200).
            oversold_threshold (float): Oversold threshold for %K entry trigger (default 20).
        """
        self.k_period = k_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.ma_window = ma_window
        self.oversold_threshold = oversold_threshold

    @property
    def name(self) -> str:
        """Return unique strategy name."""
        return "MovingAverage_Stochastic"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate trend-filtered Stochastic oversold/overbought signals with position sizing.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame containing indicators, Signal, StopLoss, and PositionSize.
        """
        df = df.copy()

        # --- 1. 200-day Moving Average Trend Filter ---
        df['MA200'] = df['close'].rolling(window=self.ma_window).mean()

        # --- 2. Stochastic Oscillator (8, 3, 3) ---
        low_min = df['low'].rolling(window=self.k_period).min()
        high_max = df['high'].rolling(window=self.k_period).max()

        price_spread = high_max - low_min
        price_spread = price_spread.replace(0, np.nan)

        df['%K_raw'] = 100 * (df['close'] - low_min) / price_spread
        df['%K'] = df['%K_raw'].rolling(window=self.k_smooth).mean()
        df['%D'] = df['%K'].rolling(window=self.d_smooth).mean()

        # --- 3. Signal Logic ---
        df['Signal'] = 0

        # Bullish Trend + Oversold Stochastic Crossover
        buy_condition = (
            (df['close'] > df['MA200'])
            & (df['%K'].shift(1) < df['%D'].shift(1))
            & (df['%K'] > df['%D'])
            & (df['%K'] < self.oversold_threshold)
        )

        # Exit: Price breaks below MA200 or Stochastic bearish cross
        sell_condition = (
            (df['close'] < df['MA200'])
            | ((df['%K'].shift(1) > df['%D'].shift(1)) & (df['%K'] < df['%D']))
        )

        # Apply signals
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1

        # --- 4. Stop Loss & Position Sizing ---
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
