"""Moving Average combined with Stochastic Oscillator strategy implementation."""

import numpy as np
import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class MovingAverageStochastic(BaseStrategy):
    """Strategy combining 200-day Trend Following Moving Average with Stochastic Oscillator.

    ### 1. Market & Sector Scan
    - Confirm Nifty above 200-day MA (trend filter).
    - Identify strong sectors (e.g., banking, IT).
    - Eliminate sectors failing beta/liquidity criteria.

    ### 2. Stock Selection
    - Apply fundamental filters: PEG > 2, Debt/Equity < 0.5, Market Cap > 5,000 Cr, Beta > 1.2.
    - Ensure good liquidity and institutional ownership.

    ### 3. Technical Setup
    - Price above 200-day MA (uptrend).
    - Stochastic (8,3,3 D & 8,3 K) dips below 20 -> watchlist candidate.

    ### 4. Entry Strategy
    - Wait for stochastic crossover (%K crosses above %D below 20).
    - Define stop loss based on recent swing low.

    ### 5. Exit Plan
    - Target 10% returns (TakeProfit >= 10%).
    - Exit occurs strictly on Stop Loss or upon achieving the 10%+ Profit Target.
    - No intermediate sell/loss signals are emitted.

    ### 6. Risk Management
    - Risk <= 1% of capital per trade.
    - Position size based on stop loss distance.
    - Maintain discipline and consistency.
    """

    def __init__(
        self,
        k_period: int = 8,
        k_smooth: int = 3,
        d_smooth: int = 3,
        ma_window: int = 200,
        oversold_threshold: float = 20.0,
        target_profit_pct: float = 0.10,
    ):
        """Initialize technical strategy parameters.

        Args:
            k_period (int): Lookback window for Stochastic %K (default 8).
            k_smooth (int): Smoothing factor for %K (default 3).
            d_smooth (int): Smoothing factor for %D (default 3).
            ma_window (int): Moving average trend filter period (default 200).
            oversold_threshold (float): Oversold threshold for %K entry trigger (default 20).
            target_profit_pct (float): Profit target percentage from entry price
                (default 0.10 / 10%).
        """
        self.k_period = k_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.ma_window = ma_window
        self.oversold_threshold = oversold_threshold
        self.target_profit_pct = target_profit_pct

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
        """Generate trend-filtered Stochastic oversold signals with 10% profit target.

        Exit occurs strictly on Stop Loss or when 10%+ profit target is achieved.
        No intermediate sell/loss signals are generated.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame containing indicators, Signal, StopLoss, TakeProfit,
                and PositionSize.
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

        # Apply buy signals only (exits occur strictly on Stop Loss or 10%+ Profit Target)
        df.loc[buy_condition, 'Signal'] = 1

        # --- 4. Stop Loss, Profit Target & Position Sizing ---
        # 5-day swing low calculated from the previous 5 bars
        swing_low = df['low'].shift(1).rolling(window=5, min_periods=1).min()
        df['StopLoss'] = None
        df['TakeProfit'] = None
        df['TakeProfitPct'] = self.target_profit_pct
        df['PositionSize'] = 0

        risk_amount = capital * risk_per_trade

        # Next-day open price estimate for entry sizing
        entry_est = df['open'].shift(-1).fillna(df['close'])
        risk_per_share = entry_est - swing_low

        buy_mask = (df['Signal'] == 1) & (risk_per_share > 0)
        df.loc[buy_mask, 'StopLoss'] = swing_low[buy_mask]
        df.loc[buy_mask, 'TakeProfit'] = entry_est[buy_mask] * (1.0 + self.target_profit_pct)
        df.loc[buy_mask, 'PositionSize'] = (risk_amount / risk_per_share[buy_mask]).astype(int)

        return df
