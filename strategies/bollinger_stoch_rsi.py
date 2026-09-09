"""Mean Reversion via Bollinger Bands & Stochastic RSI strategy module.

Strategy Summary
----------------
This strategy captures temporary momentum exhaustion and subsequent sharp bounces
back to the mean value.

Core Checklist Rules:
1. Indicators Needed:
   - Bollinger Bands (20 period, 2 Standard Deviations).
   - Stochastic RSI (14, 14, 3, 3).
   - 14-period Average True Range (ATR) for volatility stop loss.
2. Buy Trigger:
   - The stock price touches or closes below the Lower Bollinger Band.
   - AND Stochastic RSI %K crosses above %D below the 20 level (Oversold territory).
3. Stop Loss:
   - Set at exactly 1.5 ATR below the entry setup candle's low.
4. Sell / Exit Signal:
   - Price crosses the Middle Bollinger Band (20 SMA mean).
   - OR Stochastic RSI %K crosses below %D above the 80 level (Overbought exhaustion).
   - OR stop loss breach.
5. Position Sizing:
   - Risk 1% of total portfolio capital per trade, sized according to distance
     from entry price to stop loss.
"""

import pandas as pd

from bollinger_bands import calculate_bollinger_bands
from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from stoch_rsi_indicator import calculate_stoch_rsi
from strategies.base_strategy import BaseStrategy


class BollingerStochRsi(BaseStrategy):
    """Mean Reversion via Bollinger Bands & Stochastic RSI strategy."""

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_period: int = 3,
        d_period: int = 3,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        oversold_threshold: float = 20.0,
        overbought_threshold: float = 80.0,
    ):
        """Initialize technical strategy parameters.

        Args:
            bb_period (int): Lookback period for Bollinger Bands SMA (default 20).
            bb_std (float): Standard deviations for Bollinger Bands (default 2.0).
            rsi_period (int): Lookback period for RSI component (default 14).
            stoch_period (int): Lookback window for StochRSI min/max (default 14).
            k_period (int): Smoothing factor for %K line (default 3).
            d_period (int): Smoothing factor for %D signal line (default 3).
            atr_period (int): Lookback smoothing for ATR calculation (default 14).
            atr_multiplier (float): Multiplier for ATR below setup low (default 1.5).
            oversold_threshold (float): StochRSI oversold entry level (default 20.0).
            overbought_threshold (float): StochRSI overbought exit level (default 80.0).
        """
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_period = k_period
        self.d_period = d_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold

    @property
    def name(self) -> str:
        """Return unique strategy identifier."""
        return "Bollinger_Stoch_RSI"

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate mean reversion signals, dynamic ATR stop loss, and exit signals.

        Args:
            df (pd.DataFrame): Historical price DataFrame with open, high, low, close, volume.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional portfolio risk allocation per trade.
            **kwargs: Additional optional strategy arguments.

        Returns:
            pd.DataFrame: DataFrame enriched with BB, StochRSI, ATR, Signal, StopLoss,
                TakeProfit, and PositionSize.
        """
        df = df.copy()

        # --- 1. Bollinger Bands (20, 2) ---
        bb_df = calculate_bollinger_bands(
            df["close"], period=self.bb_period, num_std=self.bb_std
        )
        df["BB_Middle"] = bb_df["BB_Middle"]
        df["BB_Upper"] = bb_df["BB_Upper"]
        df["BB_Lower"] = bb_df["BB_Lower"]

        # --- 2. Stochastic RSI (14, 14, 3, 3) ---
        stoch_df = calculate_stoch_rsi(
            df["close"],
            rsi_period=self.rsi_period,
            stoch_period=self.stoch_period,
            k_period=self.k_period,
            d_period=self.d_period,
        )
        df["StochRSI_K"] = stoch_df["StochRSI_K"]
        df["StochRSI_D"] = stoch_df["StochRSI_D"]

        # --- 3. Average True Range (ATR 14) ---
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["ATR"] = tr.ewm(
            alpha=1.0 / self.atr_period, min_periods=self.atr_period, adjust=False
        ).mean()

        df["Signal"] = 0
        df["StopLoss"] = None
        df["TakeProfit"] = None
        df["PositionSize"] = 0

        risk_amount = capital * risk_per_trade
        n = len(df)
        min_bars = max(self.bb_period, self.rsi_period + self.stoch_period + self.k_period)
        if n < min_bars:
            return df

        closes = df["close"].values
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        bb_lowers = df["BB_Lower"].values
        bb_middles = df["BB_Middle"].values
        stoch_ks = df["StochRSI_K"].values
        stoch_ds = df["StochRSI_D"].values
        atrs = df["ATR"].values

        in_position = False
        current_stop_loss = 0.0

        # --- 4. Sequential Simulation State Machine ---
        for i in range(1, n):
            # Check active position for exit conditions
            if in_position:
                bar_low = lows[i]
                bar_high = highs[i]
                bar_close = closes[i]
                mid_val = bb_middles[i]
                k_curr = stoch_ks[i]
                d_curr = stoch_ds[i]
                k_prev = stoch_ks[i - 1]
                d_prev = stoch_ds[i - 1]

                # Exit 1: Intraday Stop Loss breach
                stopped_out = current_stop_loss > 0 and bar_low <= current_stop_loss

                # Exit 2: Price reaches or crosses Middle Bollinger Band (20 SMA mean)
                mean_reached = pd.notna(mid_val) and (bar_high >= mid_val or bar_close >= mid_val)

                # Exit 3: StochRSI %K crosses below %D above the 80 level
                overbought_cross = (
                    pd.notna(k_curr)
                    and pd.notna(d_curr)
                    and pd.notna(k_prev)
                    and pd.notna(d_prev)
                    and k_curr > self.overbought_threshold
                    and k_prev >= d_prev
                    and k_curr < d_curr
                )

                if stopped_out:
                    in_position = False
                    current_stop_loss = 0.0
                elif mean_reached or overbought_cross:
                    df.iloc[i, df.columns.get_loc("Signal")] = -1
                    in_position = False
                    current_stop_loss = 0.0
                continue

            # Check for new buy setup
            # Condition 1: Price touches or closes below Lower Bollinger Band
            lower_val = bb_lowers[i]
            touch_lower = (
                pd.notna(lower_val)
                and (lows[i] <= lower_val or closes[i] <= lower_val)
            )

            # Condition 2: StochRSI %K crosses above %D below the 20 level
            k_curr = stoch_ks[i]
            d_curr = stoch_ds[i]
            k_prev = stoch_ks[i - 1]
            d_prev = stoch_ds[i - 1]
            oversold_cross = (
                pd.notna(k_curr)
                and pd.notna(d_curr)
                and pd.notna(k_prev)
                and pd.notna(d_prev)
                and k_curr < self.oversold_threshold
                and k_prev <= d_prev
                and k_curr > d_curr
            )

            if touch_lower and oversold_cross:
                entry_est = opens[i + 1] if i + 1 < n else closes[i]
                atr_val = atrs[i] if pd.notna(atrs[i]) else (entry_est * 0.02)

                # Strict stop loss: 1.5 ATR below entry candle low
                setup_low = lows[i]
                stop_loss = setup_low - (self.atr_multiplier * atr_val)

                # Safety check: stop loss must be positive and below entry price
                if stop_loss >= entry_est or stop_loss <= 0:
                    stop_loss = entry_est * 0.95

                risk_per_share = entry_est - stop_loss
                if risk_per_share > 0:
                    pos_size = int(risk_amount / risk_per_share)
                    if pos_size > 0:
                        df.iloc[i, df.columns.get_loc("Signal")] = 1
                        df.iloc[i, df.columns.get_loc("StopLoss")] = stop_loss
                        # Profit target is the current Middle Band estimate
                        if pd.notna(bb_middles[i]) and bb_middles[i] > entry_est:
                            df.iloc[i, df.columns.get_loc("TakeProfit")] = bb_middles[i]
                        df.iloc[i, df.columns.get_loc("PositionSize")] = pos_size

                        in_position = True
                        current_stop_loss = stop_loss

        return df
