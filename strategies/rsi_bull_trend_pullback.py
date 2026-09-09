"""Relative Strength Index (RSI) Pullback in a Bull Trend strategy.

Strategy Summary
----------------
This strategy boasts a high win rate in large-cap stocks (such as the Nifty 50)
because it buys the dip only after structural trend confirmation.

Core Checklist Rules:
1. Indicators Needed:
   - 200-day Simple Moving Average (SMA) for structural trend.
   - 14-period Relative Strength Index (RSI) for momentum.
2. Buy Trigger:
   - Closing price must be completely above the 200 SMA (Structural Bull Market).
   - The 14-day RSI drops below 40 (Oversold pullback within a structural uptrend).
   - Buy on the next candle's open as soon as the RSI crosses back above 40.
3. Stop Loss:
   - Placed at the lower of the last 5 days' price low, or the 200 SMA.
   - A close below the 200 SMA also serves as an immediate structural exit.
4. Sell / Exit Signal:
   - Exit when the RSI reaches the overbought zone of 70 (RSI >= 70).
   - OR after a maximum holding period of 15 trading days.
   - OR if the price closes below the 200 SMA.
5. Position Sizing:
   - Risk 1% of total portfolio capital per trade, sized according to distance
     from entry price to stop loss.
"""

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from rsi_indicator import calculate_rsi
from strategies.base_strategy import BaseStrategy


class RsiBullTrendPullback(BaseStrategy):
    """Relative Strength Index (RSI) Pullback in a Bull Trend strategy."""

    def __init__(
        self,
        sma_period: int = 200,
        rsi_period: int = 14,
        oversold_threshold: float = 40.0,
        overbought_threshold: float = 70.0,
        max_holding_days: int = 15,
        swing_lookback: int = 5,
    ):
        """Initialize strategy technical parameters.

        Args:
            sma_period (int): Lookback period for structural trend moving average (default 200).
            rsi_period (int): Lookback smoothing window for RSI (default 14).
            oversold_threshold (float): RSI pullback oversold threshold (default 40.0).
            overbought_threshold (float): RSI overbought exit threshold (default 70.0).
            max_holding_days (int): Maximum holding period in trading days (default 15).
            swing_lookback (int): Lookback bars for determining recent swing low (default 5).
        """
        self.sma_period = sma_period
        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.max_holding_days = max_holding_days
        self.swing_lookback = swing_lookback

    @property
    def name(self) -> str:
        """Return unique strategy identifier."""
        return "RSI_Bull_Trend_Pullback"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate trend-confirmed RSI pullback signals, dynamic stop loss, and exits.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame containing SMA200, RSI, Signal, StopLoss, and PositionSize.
        """
        df = df.copy()

        # --- 1. Compute Indicators ---
        df["SMA200"] = df["close"].rolling(
            window=self.sma_period, min_periods=self.sma_period // 2
        ).mean()
        df["RSI"] = calculate_rsi(df["close"], period=self.rsi_period)

        # 5-day swing low calculated from previous completed bars
        swing_low_series = df["low"].shift(1).rolling(
            window=self.swing_lookback, min_periods=1
        ).min()

        df["Signal"] = 0
        df["StopLoss"] = None
        df["TakeProfit"] = None
        df["PositionSize"] = 0

        risk_amount = capital * risk_per_trade
        n = len(df)
        if n < self.rsi_period + 1:
            return df

        closes = df["close"].values
        opens = df["open"].values
        lows = df["low"].values
        smas = df["SMA200"].values
        rsis = df["RSI"].values
        swing_lows = swing_low_series.values

        in_position = False
        entry_idx = -1
        current_stop_loss = 0.0

        # --- 2. Sequential Bar-by-Bar State Machine ---
        for i in range(1, n):
            # Check active position for exit conditions
            if in_position:
                days_held = i - entry_idx
                bar_low = lows[i]
                bar_close = closes[i]
                bar_rsi = rsis[i]
                bar_sma = smas[i]

                # Condition A: Intraday Stop Loss hit
                stopped_out = current_stop_loss > 0 and bar_low <= current_stop_loss

                # Condition B: Overbought exit (RSI >= 70)
                overbought_exit = pd.notna(bar_rsi) and bar_rsi >= self.overbought_threshold

                # Condition C: Maximum holding period reached (15 trading days)
                time_exit = days_held >= self.max_holding_days

                # Condition D: Structural breakdown below 200 SMA
                sma_breakdown = pd.notna(bar_sma) and bar_close < bar_sma

                if stopped_out:
                    in_position = False
                    entry_idx = -1
                    current_stop_loss = 0.0
                elif overbought_exit or time_exit or sma_breakdown:
                    # Signal exit to be executed on the next bar open
                    df.iloc[i, df.columns.get_loc("Signal")] = -1
                    in_position = False
                    entry_idx = -1
                    current_stop_loss = 0.0
                continue

            # Check for new buy setup
            # 1. Structural Bull Market: Closing price strictly above 200 SMA
            above_sma = pd.notna(smas[i]) and closes[i] > smas[i]

            # 2. RSI Pullback: Previous bar RSI < 40 and current bar crosses back above 40
            rsi_prev = rsis[i - 1]
            rsi_curr = rsis[i]
            rsi_cross_back = (
                pd.notna(rsi_prev)
                and pd.notna(rsi_curr)
                and rsi_prev < self.oversold_threshold
                and rsi_curr >= self.oversold_threshold
            )

            if above_sma and rsi_cross_back:
                # Next bar open estimate for realistic position sizing
                entry_est = opens[i + 1] if i + 1 < n else closes[i]

                # Stop Loss: Lower of the last 5 days' low, or the 200 SMA
                s_low = swing_lows[i] if pd.notna(swing_lows[i]) else closes[i] * 0.95
                sma_val = smas[i] if pd.notna(smas[i]) else s_low

                # Use the lower of 5-day swing low or 200 SMA
                calculated_stop = min(s_low, sma_val)

                # Ensure stop loss is below entry price with a safety fallback
                if calculated_stop >= entry_est or calculated_stop <= 0:
                    calculated_stop = entry_est * 0.95

                risk_per_share = entry_est - calculated_stop
                if risk_per_share > 0:
                    pos_size = int(risk_amount / risk_per_share)
                    if pos_size > 0:
                        df.iloc[i, df.columns.get_loc("Signal")] = 1
                        df.iloc[i, df.columns.get_loc("StopLoss")] = calculated_stop
                        df.iloc[i, df.columns.get_loc("PositionSize")] = pos_size

                        in_position = True
                        entry_idx = i
                        current_stop_loss = calculated_stop

        return df
