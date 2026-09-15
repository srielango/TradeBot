"""Bullish Outside Bar (Engulfing) candlestick pattern strategy implementation.

Strategy Summary
----------------
A two-candle bullish reversal setup where the second (reversal) candle completely
engulfs the first candle's high-low range after a prior downtrend of at least 6-10%.
Best applied on weekly charts for reliability.

Checklist Rules
---------------
1. Spotting the Setup:
   - Prior downtrend of at least 6-10% over the lookback window.
   - Reversal candle (bar 2) engulfs bar 1 completely:
       High[2] > High[1] AND Low[2] < Low[1]
   - Bar 1 is a bearish candle (Close[1] < Open[1]).

2. Validating Strength:
   - Reversal candle is large and decisive (body >= min_body_ratio of its range).
   - Bullish close: Close[2] > Open[2].
   - Reversal candle closes near its high (close near high adds conviction).
   - Optional volume spike: Volume[2] >= vol_factor * 20-period SMA volume.

3. Entry:
   - Enter at the close of the reversal candle (same bar).
   - Stop loss = Low of the reversal candle.

4. Exit:
   - Fixed profit target percentage above entry price.

5. Position Sizing:
   - Risk no more than 1% of portfolio capital per trade.
"""

import numpy as np
import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class BullishOutsideBar(BaseStrategy):
    """Bullish Outside Bar (engulfing) candlestick reversal strategy.

    Applies on any timeframe but is most reliable on weekly charts.
    Requires a prior bearish trend, full engulfment of the previous bar,
    and a decisive bullish close on the reversal candle.
    """

    def __init__(
        self,
        prior_trend_pct: float = 0.06,
        trend_lookback: int = 10,
        min_body_ratio: float = 0.40,
        close_near_high_ratio: float = 0.60,
        volume_factor: float = 1.0,
        target_profit_pct: float = 0.20,
        max_holding_days: int = 15,
    ):
        """Initialize Bullish Outside Bar strategy parameters.

        Args:
            prior_trend_pct (float): Minimum prior downtrend decline required as a
                fraction (default 0.06 = 6%). Measures peak-to-bar-1 decline over
                the lookback window.
            trend_lookback (int): Number of bars to look back when measuring the
                prior trend magnitude (default 10).
            min_body_ratio (float): Minimum ratio of candle body to high-low range
                for the reversal candle to be considered decisive (default 0.40).
            close_near_high_ratio (float): Minimum ratio of (Close - Low) / Range
                for the reversal candle, ensuring the close is near the high
                (default 0.60 = top 40% of candle range).
            volume_factor (float): Minimum volume multiplier relative to 20-bar
                volume SMA for the reversal candle (default 1.0).
            target_profit_pct (float): Profit target percentage above entry price
                (default 0.20 = 20%).
            max_holding_days (int): Maximum holding period in trading days
                (default 15 = 2 to 3 weeks).
        """
        self.prior_trend_pct = prior_trend_pct
        self.trend_lookback = trend_lookback
        self.min_body_ratio = min_body_ratio
        self.close_near_high_ratio = close_near_high_ratio
        self.volume_factor = volume_factor
        self.target_profit_pct = target_profit_pct
        self.max_holding_days = max_holding_days

    @property
    def name(self) -> str:
        """Return unique strategy name."""
        return "Bullish_Outside_Bar"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate Bullish Outside Bar signals, stop loss, profit target, and position sizing.

        Strategy Rules:
            1. Prior Trend:
               - The high over the past `trend_lookback` bars must be at least
                 `prior_trend_pct` above the previous bar close, confirming a
                 meaningful prior decline into the reversal.
            2. Bar 1 (t-1) - Setup Bar:
               - Must be a bearish candle: Close[t-1] < Open[t-1].
            3. Bar 2 (t) - Reversal Bar:
               - Engulfs Bar 1 completely: High[t] > High[t-1] AND Low[t] < Low[t-1].
               - Bullish close: Close[t] > Open[t].
               - Decisive body: (Close - Open) / (High - Low) >= min_body_ratio.
               - Close near the high: (Close - Low) / (High - Low) >= close_near_high_ratio.
            4. Volume Confirmation (adds conviction):
               - Volume[t] >= volume_factor * 20-bar rolling mean volume.
            5. Stop Loss:
               - Set at the low of the reversal candle (Bar 2 low).
            6. Entry:
               - At the close of the reversal candle.
            7. Profit Target:
               - target_profit_pct above the entry price.
            8. Position Sizing:
               - Risk 1% of capital per trade; size = risk_amount / risk_per_share.

        Args:
            df (pd.DataFrame): Historical price DataFrame with columns:
                open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to
                DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk per trade
                (default 0.01 = 1%).
            **kwargs: Additional optional arguments (unused).

        Returns:
            pd.DataFrame: Input DataFrame enriched with Signal, StopLoss,
                TakeProfit, and PositionSize columns.
        """
        df = df.copy()

        # --- Bar 1 (t-1) reference values ---
        prev_open = df['open'].shift(1)
        prev_close = df['close'].shift(1)
        prev_high = df['high'].shift(1)
        prev_low = df['low'].shift(1)

        # --- Prior downtrend condition ---
        # Rolling peak of high over the lookback window (lagged by 1 to exclude current bar)
        rolling_peak = df['high'].shift(1).rolling(window=self.trend_lookback, min_periods=1).max()

        # Decline from peak to Bar 1 close must be >= prior_trend_pct
        prior_downtrend = (
            (rolling_peak - prev_close) / (rolling_peak + 1e-9) >= self.prior_trend_pct
        )

        # --- Bar 1 bearish condition ---
        bar1_bearish = prev_close < prev_open

        # --- Bar 2 (t) - current reversal bar ---
        curr_open = df['open']
        curr_close = df['close']
        curr_high = df['high']
        curr_low = df['low']
        curr_volume = df['volume']

        # Full engulfment: current bar range completely contains Bar 1 range
        engulfs_high = curr_high > prev_high
        engulfs_low = curr_low < prev_low

        # Bullish close on the reversal candle
        bar2_bullish = curr_close > curr_open

        # Decisive body: body-to-range ratio >= min_body_ratio
        bar2_body = curr_close - curr_open
        bar2_range = curr_high - curr_low
        bar2_decisive = (bar2_body / (bar2_range + 1e-9)) >= self.min_body_ratio

        # Close near high: strongest bullish setups close near the top of the candle
        bar2_close_near_high = (
            (curr_close - curr_low) / (bar2_range + 1e-9)
        ) >= self.close_near_high_ratio

        # --- Volume spike confirmation ---
        vol_sma20 = df['volume'].rolling(window=20, min_periods=1).mean()
        volume_confirmed = curr_volume >= (vol_sma20 * self.volume_factor)

        # --- Combined bullish outside bar buy condition ---
        buy_condition = (
            prior_downtrend
            & bar1_bearish
            & engulfs_high
            & engulfs_low
            & bar2_bullish
            & bar2_decisive
            & bar2_close_near_high
            & volume_confirmed
        )

        # --- Signal Generation & Sequential Holding Tracking ---
        # Outside Bar targets 20% within 2 to 3 weeks (max_holding_days = 15 bars)
        n = len(df)
        signals = np.zeros(n, dtype=int)
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        opens = df['open'].values

        in_position = False
        entry_idx = -1
        current_stop_loss = 0.0
        current_take_profit = 0.0

        for i in range(n):
            if in_position:
                days_held = i - entry_idx
                bar_low = lows[i]
                bar_high = highs[i]

                # Condition A: Intraday Stop Loss hit
                stopped_out = current_stop_loss > 0 and bar_low <= current_stop_loss
                # Condition B: Intraday 20%+ Profit Target achieved
                profit_target_hit = current_take_profit > 0 and bar_high >= current_take_profit
                # Condition C: Maximum holding period reached (2 to 3 weeks / 15 trading days)
                time_exit = days_held >= self.max_holding_days

                if stopped_out or profit_target_hit:
                    in_position = False
                    entry_idx = -1
                elif time_exit:
                    # Signal exit to be executed on the next bar open
                    signals[i] = -1
                    in_position = False
                    entry_idx = -1
                continue

            if buy_condition.iloc[i]:
                signals[i] = 1
                in_position = True
                entry_idx = i
                entry_est = opens[i + 1] if i + 1 < n else closes[i]
                current_stop_loss = lows[i]
                current_take_profit = entry_est * (1.0 + self.target_profit_pct)

        df['Signal'] = signals

        # --- Stop Loss, Profit Target, and Position Sizing ---
        entry_est = curr_close
        stop_loss_series = curr_low

        df['StopLoss'] = None
        df['TakeProfit'] = None
        df['TakeProfitPct'] = self.target_profit_pct
        df['PositionSize'] = 0

        risk_amount = capital * risk_per_trade
        risk_per_share = entry_est - stop_loss_series

        buy_mask = (df['Signal'] == 1) & (risk_per_share > 0)

        df.loc[buy_mask, 'StopLoss'] = stop_loss_series[buy_mask]
        df.loc[buy_mask, 'TakeProfit'] = entry_est[buy_mask] * (1.0 + self.target_profit_pct)
        df.loc[buy_mask, 'PositionSize'] = (
            risk_amount / risk_per_share[buy_mask]
        ).astype(int)

        return df
