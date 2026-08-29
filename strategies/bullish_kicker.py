"""Bullish Kicker Candlestick Pattern strategy implementation."""

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class BullishKicker(BaseStrategy):
    """Bullish Kicker candlestick pattern trading strategy with fixed profit target exit."""

    def __init__(
        self,
        target_profit_pct: float = 0.09,
        min_body_ratio: float = 0.40,
        volume_factor: float = 1.0,
    ):
        """Initialize Bullish Kicker strategy parameters.

        Args:
            target_profit_pct (float): Profit target percentage from entry price
                (default 0.09 / 9%).
            min_body_ratio (float): Minimum ratio of candle body to high-low range (default 0.40).
            volume_factor (float): Minimum volume multiplier relative to 20-day SMA (default 1.0).
        """
        self.target_profit_pct = target_profit_pct
        self.min_body_ratio = min_body_ratio
        self.volume_factor = volume_factor

    @property
    def name(self) -> str:
        """Return unique strategy name."""
        return "Bullish_Kicker"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate Bullish Kicker signals, stop loss, profit target, and position sizing.

        Strategy Rules:
            1. Setup Identification:
               - Candle 1 (Day t-1): Decisive bearish candle (Close < Open).
               - Candle 2 (Day t): Gap-up open at or near Day 1 Open and decisive bullish close.
            2. Strength Validation:
               - Elevated volume (Volume > Day 1 Volume OR Volume >= 20-day SMA Volume).
            3. Stop Loss:
               - Set at the low of Candle 1 (Day t-1 low).
            4. Profit Target:
               - Set at 9% above the estimated entry price.
            5. Risk & Position Sizing:
               - Risk 1% of total portfolio capital per trade.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade (default 0.01).
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame with Signal, StopLoss, TakeProfit, and PositionSize columns.
        """
        df = df.copy()

        # --- 1. Candle 1 (Day t-1): Bearish and Decisive ---
        prev_open = df['open'].shift(1)
        prev_close = df['close'].shift(1)
        prev_high = df['high'].shift(1)
        prev_low = df['low'].shift(1)
        prev_volume = df['volume'].shift(1)

        c1_bearish = prev_close < prev_open
        c1_body = prev_open - prev_close
        c1_range = prev_high - prev_low
        c1_decisive = (c1_body / (c1_range + 1e-9)) >= self.min_body_ratio

        # --- 2. Candle 2 (Day t): Bullish Gap-Up Reversal ---
        curr_open = df['open']
        curr_close = df['close']
        curr_high = df['high']
        curr_low = df['low']
        curr_volume = df['volume']

        # Gap open: opens at or above previous day's open (with 0.2% tolerance for close opens)
        c2_gap = curr_open >= (prev_open * 0.998)
        c2_bullish = curr_close > curr_open
        c2_body = curr_close - curr_open
        c2_range = curr_high - curr_low
        c2_decisive = (c2_body / (c2_range + 1e-9)) >= self.min_body_ratio

        # --- 3. Strength & Volume Validation ---
        vol_sma20 = df['volume'].rolling(window=20, min_periods=1).mean()
        c2_volume_confirmed = (curr_volume > prev_volume) | (
            curr_volume >= vol_sma20 * self.volume_factor
        )

        # Bullish Kicker entry condition
        buy_condition = (
            c1_bearish
            & c1_decisive
            & c2_gap
            & c2_bullish
            & c2_decisive
            & c2_volume_confirmed
        )

        # --- 4. Signal Generation ---
        df['Signal'] = 0
        df.loc[buy_condition, 'Signal'] = 1

        # --- 5. Stop Loss, Profit Target, and Position Sizing ---
        # Stop loss is placed strictly below the low of the first candle (Day t-1)
        stop_loss_series = prev_low

        df['StopLoss'] = None
        df['TakeProfit'] = None
        df['PositionSize'] = 0

        risk_amount = capital * risk_per_trade

        # Entry occurs at the next day's market open
        entry_est = df['open'].shift(-1).fillna(df['close'])
        risk_per_share = entry_est - stop_loss_series

        buy_mask = (df['Signal'] == 1) & (risk_per_share > 0)
        df.loc[buy_mask, 'StopLoss'] = stop_loss_series[buy_mask]
        df.loc[buy_mask, 'TakeProfit'] = entry_est[buy_mask] * (1.0 + self.target_profit_pct)
        df.loc[buy_mask, 'PositionSize'] = (risk_amount / risk_per_share[buy_mask]).astype(int)

        return df
