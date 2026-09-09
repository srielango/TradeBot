"""Dual Moving Average & Volatility Filter (The Conservative Trend Follower) strategy.

Strategy Summary
----------------
Pure moving average crossovers can whipsaw in sideways or range-bound markets.
Adding an Average Directional Index (ADX) filter ensures trades are executed only
when a robust trend is present.

Core Checklist Rules:
1. Indicators Needed:
   - 20-day Exponential Moving Average (EMA)
   - 50-day Exponential Moving Average (EMA)
   - 14-day Average Directional Index (ADX)
2. Buy Trigger:
   - 20 EMA crosses above 50 EMA (Bullish Crossover)
   - AND 14-day ADX is above 20 (indicating trend strength)
3. Stop Loss:
   - Placed at the lowest price of recent swing low, or a hard 5% below entry price
     to absorb overnight equity gaps.
4. Sell / Exit Signal:
   - 20 EMA crosses back below 50 EMA (Bearish Crossover)
   - OR price hits a fixed 1:2 risk-to-reward target (2R profit).
5. Position Sizing:
   - Risk 1% of total portfolio capital per trade, sized according to distance
     from entry price to stop loss.
"""

import numpy as np
import pandas as pd

from adx_indicator import calculate_adx
from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class DualMovingAverageAdx(BaseStrategy):
    """Dual Moving Average & Volatility Filter (Conservative Trend Follower)."""

    def __init__(
        self,
        fast_ema: int = 20,
        slow_ema: int = 50,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        hard_stop_pct: float = 0.05,
        risk_reward_ratio: float = 2.0,
        swing_lookback: int = 5,
        stop_loss_mode: str = "swing_low",
    ):
        """Initialize technical strategy parameters.

        Args:
            fast_ema (int): Period for fast Exponential Moving Average (default 20).
            slow_ema (int): Period for slow Exponential Moving Average (default 50).
            adx_period (int): Lookback period for ADX calculation (default 14).
            adx_threshold (float): Minimum ADX level indicating trend presence (default 20.0).
            hard_stop_pct (float): Maximum fractional loss below entry price (default 0.05 / 5%).
            risk_reward_ratio (float): Risk-to-reward multiple for profit target
                (default 2.0 / 1:2).
            swing_lookback (int): Lookback bars for determining recent swing low (default 5).
            stop_loss_mode (str): Mode for stop loss placement:
                - 'swing_low': Recent swing low with 5% fallback and gap cushion.
                - 'hard_5pct': Fixed 5% below entry price.
                - 'absorb_gaps': min(swing_low, entry * 0.95) guaranteeing at least 5% buffer.
        """
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.hard_stop_pct = hard_stop_pct
        self.risk_reward_ratio = risk_reward_ratio
        self.swing_lookback = swing_lookback
        self.stop_loss_mode = stop_loss_mode

    @property
    def name(self) -> str:
        """Return unique strategy identifier."""
        return "Dual_Moving_Average_ADX"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate indicator values, crossover signals, stop loss, and position sizing.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame containing EMA20, EMA50, ADX, Signal, StopLoss,
                TakeProfit, and PositionSize.
        """
        df = df.copy()

        # --- 1. Technical Indicators Calculation ---
        # 20-day Fast EMA & 50-day Slow EMA
        df["EMA20"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["EMA50"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()

        # 14-day ADX Trend Strength Filter
        adx_df = calculate_adx(df, period=self.adx_period)
        df["ADX"] = adx_df["ADX"]

        # --- 2. Signal Generation ---
        # Bullish Crossover: Fast EMA crosses above Slow EMA
        bullish_crossover = (
            (df["EMA20"] > df["EMA50"])
            & (df["EMA20"].shift(1) <= df["EMA50"].shift(1))
        )

        # Volatility / Trend Filter: ADX must be above threshold (20)
        trend_filter = df["ADX"] > self.adx_threshold

        # Buy Trigger: Bullish Crossover AND ADX > 20
        buy_condition = bullish_crossover & trend_filter

        # Bearish Crossover: Fast EMA crosses back below Slow EMA (Exit Signal)
        bearish_crossover = (
            (df["EMA20"] < df["EMA50"])
            & (df["EMA20"].shift(1) >= df["EMA50"].shift(1))
        )

        df["Signal"] = 0
        df.loc[buy_condition, "Signal"] = 1
        df.loc[bearish_crossover, "Signal"] = -1

        # --- 3. Stop Loss, Take Profit Target & Position Sizing ---
        # Lookback swing low computed from previous completed bars
        swing_low = df["low"].shift(1).rolling(
            window=self.swing_lookback, min_periods=1
        ).min()

        df["StopLoss"] = None
        df["TakeProfit"] = None
        df["PositionSize"] = 0

        risk_amount = capital * risk_per_trade

        # Next-day open price estimate for realistic execution sizing
        entry_est = df["open"].shift(-1).fillna(df["close"])
        hard_stop = entry_est * (1.0 - self.hard_stop_pct)

        # Determine effective stop loss according to configured mode
        if self.stop_loss_mode == "hard_5pct":
            effective_stop = hard_stop
        elif self.stop_loss_mode == "absorb_gaps":
            # Guarantees at least 5% distance to absorb overnight gaps
            effective_stop = np.minimum(swing_low, hard_stop)
        else:
            # Default 'swing_low': use swing low, or fallback to hard 5% if
            # swing low is unavailable, higher than entry, or excessively tight
            valid_swing = (swing_low < entry_est) & (swing_low > 0)
            effective_stop = np.where(valid_swing, swing_low, hard_stop)

        # Risk per share based on entry and stop loss
        risk_per_share = entry_est - effective_stop

        # Fixed 1:2 Risk-to-Reward Profit Target: Entry + 2 * (Entry - StopLoss)
        target_price = entry_est + (self.risk_reward_ratio * risk_per_share)

        # Apply position sizing and exit thresholds on valid buy bars
        buy_mask = (df["Signal"] == 1) & (risk_per_share > 0)
        df.loc[buy_mask, "StopLoss"] = effective_stop[buy_mask]
        df.loc[buy_mask, "TakeProfit"] = target_price[buy_mask]
        df.loc[buy_mask, "PositionSize"] = (
            risk_amount / risk_per_share[buy_mask]
        ).astype(int)

        return df
