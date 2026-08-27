"""Moving Average combined with Stochastic Oscillator strategy implementation."""

import pandas as pd

try:
    from .base_strategy import BaseStrategy
except ImportError:
    from base_strategy import BaseStrategy


class MovingAverageStochastic(BaseStrategy):
    """Strategy combining 200-day Trend Following Moving Average with Stochastic Oscillator reversals."""

    @property
    def name(self) -> str:
        """Return unique strategy name."""
        return "MovingAverage_Stochastic"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate trend-filtered Stochastic oversold/overbought signals with position sizing.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close.

        Returns:
            pd.DataFrame: Augmented DataFrame containing calculated indicators, Signal, StopLoss, and PositionSize.
        """
        df = df.copy()

        # --- 200-day Moving Average ---
        df['MA200'] = df['close'].rolling(window=200).mean()

        # --- Stochastic Oscillator (8, 3, 3) ---
        k_period, k_smooth, d_smooth = 8, 3, 3
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        df['%K_raw'] = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['%K'] = df['%K_raw'].rolling(window=k_smooth).mean()
        df['%D'] = df['%K'].rolling(window=d_smooth).mean()

        # --- Signal Logic ---
        df['Signal'] = 0

        # Conservative Entry: Bullish trend filter + stochastic crossover below oversold threshold 20
        buy_condition = (
            (df['close'] > df['MA200']) &
            (df['%K'].shift(1) < df['%D'].shift(1)) &
            (df['%K'] > df['%D']) &
            (df['%K'] < 20)
        )

        # Exit: Price breaks below 200 MA or stochastic bearish cross
        sell_condition = (
            (df['close'] < df['MA200']) |
            ((df['%K'].shift(1) > df['%D'].shift(1)) & (df['%K'] < df['%D']))
        )

        # Apply signals
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1

        # --- Stop Loss & Position Sizing ---
        df['StopLoss'] = None
        df['PositionSize'] = 0

        capital = 1_000_000
        risk_per_trade = capital * 0.01  # 1% risk = 10,000 INR

        for i in range(len(df)):
            if df.loc[i, 'Signal'] == 1:
                # Look back 5 days for recent swing low
                lookback = df.iloc[max(0, i - 5):i]
                if not lookback.empty:
                    stop = lookback['low'].min()
                    entry = df.loc[i + 1, 'open'] if i + 1 < len(df) else df.loc[i, 'close']
                    risk_per_share = entry - stop
                    if risk_per_share > 0:
                        position_size = int(risk_per_trade / risk_per_share)
                        df.loc[i, 'StopLoss'] = stop
                        df.loc[i, 'PositionSize'] = position_size

        return df
