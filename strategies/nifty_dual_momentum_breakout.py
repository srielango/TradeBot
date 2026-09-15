"""Nifty Dual Momentum Breakout strategy implementation for hourly execution.

Strategy Summary
----------------
Designed specifically for Nifty 50 cash segment equities on the HOURLY timeframe.
Captures high-probability momentum breakouts aligned with higher-timeframe trend
bias while strictly managing risk with an initial 3.5% stop loss, a 1:2 risk-to-reward
7.0% profit target, and an automatic trailing stop to breakeven once price reaches
1:1 RRR (+3.5%).

Core Strategy Rules:
1. Directional Bias & Asset Class:
   - Long-Only Strategy. Cash segment only. No short positions, no leverage.
2. Technical Filters (Daily Equivalent on Hourly Data):
   - Trend Filter: Close price must be above 200-period EMA (calculated on daily
     resampled data, or 200 days * 7 trading hours = 1,400 hourly periods EMA).
   - Breakout Trigger: Current hour's close must break above the highest high of
     the last 20 trading days (20 days * 7 trading hours = 140 hourly periods).
   - Volume Confirmation: Breakout hour volume must be > 1.5x the 20-period
     Volume Moving Average (calculated on daily resampled data, or 140 hourly periods).
3. Execution & Risk Management:
   - Entry: Market order executed at the close of confirming hourly breakout candle.
   - Stop Loss: Placed strictly 3.5% below entry price (0.965 * entry_price).
   - Take Profit: Fixed 1:2 Risk-to-Reward ratio (7.0% target profit from entry).
   - Trailing Stop: When price reaches +3.5% (1:1 RRR), stop loss is moved to the
     exact entry price (breakeven), eliminating downside risk.
4. Standard Interface:
   - Implements `on_candle_close` returning a dictionary with keys:
     'symbol', 'signal' ('BUY' / 'HOLD'), 'entry_price', 'stop_loss', 'take_profit'.
   - Implements `generate_signals` for vectorized enrichment and engine backtesting.
"""

from typing import Any

import numpy as np
import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from strategies.base_strategy import BaseStrategy


class NiftyDualMomentumBreakout(BaseStrategy):
    """Nifty Dual Momentum Breakout strategy for hourly Nifty 50 cash segment data."""

    def __init__(
        self,
        trend_ema_periods: int = 1400,
        breakout_lookback: int = 140,
        volume_ma_periods: int = 140,
        volume_factor: float = 1.5,
        stop_loss_pct: float = 0.035,
        take_profit_pct: float = 0.07,
        breakeven_trigger_pct: float = 0.035,
        use_daily_resample: bool = False,
    ):
        """Initialize technical and risk management parameters.

        Args:
            trend_ema_periods (int): Period for trend filter EMA (default 1400 = 200d * 7h).
            breakout_lookback (int): Lookback bars for highest high (default 140 = 20d * 7h).
            volume_ma_periods (int): Lookback bars for volume moving average
                (default 140 = 20d * 7h).
            volume_factor (float): Multiplier for volume threshold (default 1.5 = 1.5x VMA).
            stop_loss_pct (float): Initial stop loss fraction below entry (default 0.035 = 3.5%).
            take_profit_pct (float): Target profit fraction above entry
                (default 0.07 = 7.0%, 1:2 RRR).
            breakeven_trigger_pct (float): Profit fraction to trigger breakeven trailing stop
                (default 0.035 = 3.5%, 1:1 RRR).
            use_daily_resample (bool): If True, resamples hourly data to daily candles to
                compute daily 200 EMA and 20-day high before projecting back to hourly bars.
        """
        self.trend_ema_periods = trend_ema_periods
        self.breakout_lookback = breakout_lookback
        self.volume_ma_periods = volume_ma_periods
        self.volume_factor = volume_factor
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.breakeven_trigger_pct = breakeven_trigger_pct
        self.use_daily_resample = use_daily_resample

    @property
    def name(self) -> str:
        """Return unique strategy identifier string."""
        return "Nifty_Dual_Momentum_Breakout"

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute trend EMA, 20-day breakout high, and volume moving average.

        Args:
            df (pd.DataFrame): Hourly OHLCV DataFrame with date, open, high, low, close, volume.

        Returns:
            pd.DataFrame: Enriched DataFrame with Trend_EMA, Breakout_High, and Volume_MA columns.
        """
        df = df.copy()

        # Handle daily data fallback if fewer rows than hourly parameters
        is_daily_data = len(df) < 500 or (
            "date" in df.columns and df["date"].astype(str).str.len().max() <= 10
        )

        trend_span = 200 if is_daily_data else self.trend_ema_periods
        breakout_window = 20 if is_daily_data else self.breakout_lookback
        volume_window = 20 if is_daily_data else self.volume_ma_periods

        if self.use_daily_resample and not is_daily_data and "date" in df.columns:
            # Resample daily to compute 200 EMA and 20-day breakout high
            df["_day"] = df["date"].astype(str).str[:10]
            daily_close = df.groupby("_day")["close"].last()
            daily_ema = daily_close.ewm(span=200, adjust=False).mean()

            daily_high = df.groupby("_day")["high"].max()
            daily_breakout_high = (
                daily_high.shift(1).rolling(window=20, min_periods=5).max()
            )

            df["Trend_EMA"] = df["_day"].map(daily_ema)
            df["Breakout_High"] = df["_day"].map(daily_breakout_high)
            df.drop(columns=["_day"], inplace=True)
        else:
            # Vectorized hourly calculation: 1400 EMA and 140 periods lookback
            df["Trend_EMA"] = (
                df["close"]
                .ewm(span=trend_span, adjust=False, min_periods=1)
                .mean()
            )
            # Breakout level: Highest high of previous lookback bars (excluding current bar)
            df["Breakout_High"] = (
                df["high"]
                .shift(1)
                .rolling(window=breakout_window, min_periods=min(20, breakout_window))
                .max()
            )

        # Volume Moving Average (140 hourly periods or 20 daily periods)
        df["Volume_MA"] = (
            df["volume"]
            .rolling(window=volume_window, min_periods=min(20, volume_window))
            .mean()
        )

        return df

    def on_candle_close(
        self,
        symbol: str,
        candle_or_df: pd.Series | pd.DataFrame | dict[str, Any],
        current_position: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process hourly candle close and return standardized signal dictionary.

        Evaluates the 3 core criteria on the completed hourly candle:
        1. Trend Filter: close > Trend_EMA (200 daily EMA / 1400 hourly EMA)
        2. Breakout Trigger: close > Breakout_High (20-day / 140-hour highest high)
        3. Volume Confirmation: volume > 1.5x Volume_MA (20-day / 140-hour VMA)

        Risk Management:
        - If BUY triggers:
            entry_price = candle['close']
            stop_loss   = round(entry_price * (1.0 - 0.035), 2)
            take_profit = round(entry_price * (1.0 + 0.070), 2)
        - If already holding position:
            Checks if price reaches +3.5% (1:1 RRR) to trail stop loss to exact entry price.

        Args:
            symbol (str): Ticker symbol of the Nifty 50 stock (e.g. 'RELIANCE.NS').
            candle_or_df (pd.Series | pd.DataFrame | dict): Completed hourly candle data.
                Can be a Series/dict with indicators, or a DataFrame of historical prices.
            current_position (dict | None): Optional dictionary of an active open trade:
                {'entry_price': float, 'stop_loss': float, 'take_profit': float, 'trailed': bool}

        Returns:
            dict[str, Any]: Explicit dictionary containing:
                - 'symbol': str
                - 'signal': 'BUY' or 'HOLD'
                - 'entry_price': float or None
                - 'stop_loss': float or None
                - 'take_profit': float or None
        """
        # If passed a DataFrame, compute indicators and extract the latest candle
        if isinstance(candle_or_df, pd.DataFrame):
            df_ind = self.compute_indicators(candle_or_df)
            candle = df_ind.iloc[-1].to_dict()
        elif isinstance(candle_or_df, pd.Series):
            candle = candle_or_df.to_dict()
        elif isinstance(candle_or_df, dict):
            candle = dict(candle_or_df)
        else:
            raise TypeError("candle_or_df must be a pd.Series, pd.DataFrame, or dict")

        close_p = float(candle.get("close", 0.0))
        high_p = float(candle.get("high", close_p))
        vol = float(candle.get("volume", 0.0))

        trend_ema = float(candle.get("Trend_EMA", 0.0))
        breakout_high = float(candle.get("Breakout_High", 0.0))
        vol_ma = float(candle.get("Volume_MA", 0.0))

        # -----------------------------------------------------------------
        # 1. Manage Active Position (Trailing Stop to Breakeven)
        # -----------------------------------------------------------------
        if current_position is not None and current_position.get("entry_price"):
            pos_entry = float(current_position["entry_price"])
            pos_sl = float(
                current_position.get("stop_loss")
                or (pos_entry * (1.0 - self.stop_loss_pct))
            )
            pos_tp = float(
                current_position.get("take_profit")
                or (pos_entry * (1.0 + self.take_profit_pct))
            )
            is_trailed = bool(current_position.get("trailed", False))

            # Check 1:1 RRR Trailing Stop (+3.5% trigger -> move stop to exact entry price)
            breakeven_threshold = pos_entry * (1.0 + self.breakeven_trigger_pct)
            if not is_trailed and high_p >= breakeven_threshold:
                pos_sl = max(pos_sl, pos_entry)
                is_trailed = True

            # Position remains active
            return {
                "symbol": symbol,
                "signal": "HOLD",
                "entry_price": round(pos_entry, 2),
                "stop_loss": round(pos_sl, 2),
                "take_profit": round(pos_tp, 2),
                "trailed_to_breakeven": is_trailed,
            }

        # -----------------------------------------------------------------
        # 2. Evaluate New Long-Only Breakout Entry Criteria
        # -----------------------------------------------------------------
        # Criterion 1: Trend Filter (Close > 200 EMA / 1400 Hourly EMA)
        trend_pass = close_p > trend_ema if trend_ema > 0 else False

        # Criterion 2: Breakout Trigger (Close > 20-Day / 140-Hour Highest High)
        breakout_pass = close_p > breakout_high if breakout_high > 0 else False

        # Criterion 3: Volume Confirmation (Hourly Volume > 1.5x Volume Moving Average)
        vol_threshold = self.volume_factor * vol_ma if vol_ma > 0 else 0.0
        volume_pass = vol > vol_threshold if vol_threshold > 0 else False

        # Long-only buy trigger (all 3 filters must align)
        if trend_pass and breakout_pass and volume_pass:
            entry_price = round(close_p, 2)
            stop_loss = round(entry_price * (1.0 - self.stop_loss_pct), 2)
            take_profit = round(entry_price * (1.0 + self.take_profit_pct), 2)

            return {
                "symbol": symbol,
                "signal": "BUY",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }

        # No buy trigger: Maintain HOLD
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
        }

    def run_candle_loop(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """Process an hourly DataFrame row-by-row simulating the on_candle_close loop.

        Tracks open positions, activates the +3.5% breakeven trailing stop,
        and outputs a stream of explicit standard signal dictionaries.

        Args:
            symbol (str): Stock ticker symbol.
            df (pd.DataFrame): Hourly OHLCV price DataFrame.

        Returns:
            list[dict[str, Any]]: Chronological list of signal dictionaries.
        """
        if df.empty:
            return []

        df_ind = self.compute_indicators(df)
        signals_output: list[dict[str, Any]] = []

        active_pos: dict[str, Any] | None = None

        for idx in range(len(df_ind)):
            candle = df_ind.iloc[idx].to_dict()
            bar_high = float(candle.get("high", candle.get("close", 0.0)))
            bar_low = float(candle.get("low", candle.get("close", 0.0)))

            # If currently in position, evaluate exits on this candle
            if active_pos is not None:
                # Check trailing stop condition (+3.5% reached)
                be_target = active_pos["entry_price"] * (1.0 + self.breakeven_trigger_pct)
                if not active_pos["trailed"] and bar_high >= be_target:
                    active_pos["stop_loss"] = active_pos["entry_price"]
                    active_pos["trailed"] = True

                # Check Stop Loss hit (low <= stop loss)
                if bar_low <= active_pos["stop_loss"]:
                    signals_output.append({
                        "symbol": symbol,
                        "signal": "HOLD",
                        "entry_price": round(active_pos["entry_price"], 2),
                        "stop_loss": round(active_pos["stop_loss"], 2),
                        "take_profit": round(active_pos["take_profit"], 2),
                        "action": "STOP_LOSS_EXIT",
                    })
                    active_pos = None
                    continue

                # Check Take Profit hit (high >= take profit)
                if bar_high >= active_pos["take_profit"]:
                    signals_output.append({
                        "symbol": symbol,
                        "signal": "HOLD",
                        "entry_price": round(active_pos["entry_price"], 2),
                        "stop_loss": round(active_pos["stop_loss"], 2),
                        "take_profit": round(active_pos["take_profit"], 2),
                        "action": "TAKE_PROFIT_EXIT",
                    })
                    active_pos = None
                    continue

            # Call on_candle_close
            res = self.on_candle_close(symbol, candle, current_position=active_pos)
            signals_output.append(res)

            # If BUY signal triggered and no position open, enter position
            if res["signal"] == "BUY" and active_pos is None:
                active_pos = {
                    "entry_price": res["entry_price"],
                    "stop_loss": res["stop_loss"],
                    "take_profit": res["take_profit"],
                    "trailed": False,
                }

        return signals_output

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Generate indicator values, signals, stop loss, profit target, and sizing.

        Fully compatible with BacktestEngine, MorningScanner, and desktop UI.
        Implements sequential trade tracking with the +3.5% (1:1 RRR) breakeven
        trailing stop and 7.0% (1:2 RRR) take profit.

        Args:
            df (pd.DataFrame): Hourly OHLCV DataFrame with open, high, low, close, volume.
            capital (float): Portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional risk allocation (default 0.01 = 1%).
            **kwargs: Optional additional arguments.

        Returns:
            pd.DataFrame: Enriched DataFrame with Trend_EMA, Breakout_High, Volume_MA,
                Signal, StopLoss, TakeProfit, StopLossPct, TakeProfitPct, and PositionSize.
        """
        df = self.compute_indicators(df)

        n = len(df)
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values
        trend_emas = df["Trend_EMA"].values
        breakout_highs = df["Breakout_High"].values
        volume_mas = df["Volume_MA"].values

        # Vectorized preliminary buy condition check
        valid_trend = closes > trend_emas
        valid_breakout = closes > breakout_highs
        valid_vol = volumes > (self.volume_factor * volume_mas)
        raw_buy_condition = valid_trend & valid_breakout & valid_vol

        # Sequential position and trailing stop simulation
        signals = np.zeros(n, dtype=int)
        stop_losses = [None] * n
        take_profits = [None] * n
        position_sizes = np.zeros(n, dtype=int)

        risk_amount = capital * risk_per_trade

        in_position = False
        entry_price = 0.0
        current_sl = 0.0
        current_tp = 0.0
        trailed_to_be = False

        for i in range(n):
            if in_position:
                bar_high = float(highs[i])
                bar_low = float(lows[i])

                # Check 1:1 RRR (+3.5%) trailing stop trigger
                be_level = entry_price * (1.0 + self.breakeven_trigger_pct)
                if not trailed_to_be and bar_high >= be_level:
                    current_sl = max(current_sl, entry_price)
                    trailed_to_be = True

                # Check Stop Loss hit (intraday low <= current_sl)
                if bar_low <= current_sl:
                    signals[i] = -1
                    in_position = False
                    continue

                # Check Take Profit hit (intraday high >= current_tp)
                if bar_high >= current_tp:
                    signals[i] = -1
                    in_position = False
                    continue

                continue

            # Check new BUY trigger
            if raw_buy_condition[i]:
                entry_price = float(closes[i])
                current_sl = round(entry_price * (1.0 - self.stop_loss_pct), 2)
                current_tp = round(entry_price * (1.0 + self.take_profit_pct), 2)
                trailed_to_be = False

                signals[i] = 1
                stop_losses[i] = current_sl
                take_profits[i] = current_tp

                risk_per_share = entry_price - current_sl
                if risk_per_share > 0:
                    position_sizes[i] = int(risk_amount / risk_per_share)
                else:
                    position_sizes[i] = 0

                in_position = True

        df["Signal"] = signals
        df["StopLoss"] = stop_losses
        df["TakeProfit"] = take_profits
        df["StopLossPct"] = self.stop_loss_pct
        df["TakeProfitPct"] = self.take_profit_pct
        df["PositionSize"] = position_sizes

        return df

    def backtest(
        self,
        df: pd.DataFrame,
        ticker: str = "NIFTY50",
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        allocation_fraction: float = 0.10,
    ) -> dict[str, Any]:
        """Execute a detailed backtest simulation on hourly data with breakeven trailing stop.

        Args:
            df (pd.DataFrame): Hourly price dataset.
            ticker (str): Stock ticker symbol.
            initial_capital (float): Starting capital in INR.
            allocation_fraction (float): Capital allocated per trade (default 0.10 = 10%).

        Returns:
            dict[str, Any]: Performance metrics summary and trade log.
        """
        if df.empty:
            return {"Metrics": {}, "TradeLog": pd.DataFrame()}

        df_sig = self.generate_signals(df, capital=initial_capital)

        trades = []
        n = len(df_sig)
        dates = df_sig["date"].astype(str).values if "date" in df_sig.columns else list(range(n))
        opens = df_sig["open"].values
        highs = df_sig["high"].values
        lows = df_sig["low"].values
        closes = df_sig["close"].values
        signals = df_sig["Signal"].values

        trade_cap = initial_capital * allocation_fraction
        cash = initial_capital
        in_pos = False
        entry_date = ""
        entry_p = 0.0
        pos_size = 0
        sl_p = 0.0
        tp_p = 0.0
        trailed = False

        for i in range(n):
            b_high = float(highs[i])
            b_low = float(lows[i])
            b_close = float(closes[i])
            b_open = float(opens[i])
            b_date = str(dates[i])

            if in_pos:
                # Trailing stop to breakeven (+3.5% trigger)
                be_target = entry_p * (1.0 + self.breakeven_trigger_pct)
                if not trailed and b_high >= be_target:
                    sl_p = entry_p
                    trailed = True

                # Check Stop Loss
                if b_low <= sl_p:
                    exit_p = min(sl_p, b_open)
                    pnl = (exit_p - entry_p) * pos_size
                    ret_pct = (exit_p - entry_p) / entry_p * 100.0 if entry_p > 0 else 0.0
                    reason = "Trailing Stop (Breakeven)" if trailed else "Stop Loss (-3.5%)"

                    trades.append({
                        "Security": ticker,
                        "EntryDate": entry_date,
                        "ExitDate": b_date,
                        "PositionSize": pos_size,
                        "EntryPrice": entry_p,
                        "ExitPrice": exit_p,
                        "PnL": pnl,
                        "ReturnPct": ret_pct,
                        "Result": "Win" if pnl > 0 else ("Loss" if pnl < 0 else "Breakeven"),
                        "ExitReason": reason,
                        "Trailed": trailed,
                    })
                    cash += (pos_size * exit_p)
                    in_pos = False
                    continue

                # Check Take Profit
                if b_high >= tp_p:
                    exit_p = max(tp_p, b_open)
                    pnl = (exit_p - entry_p) * pos_size
                    ret_pct = (exit_p - entry_p) / entry_p * 100.0 if entry_p > 0 else 0.0

                    trades.append({
                        "Security": ticker,
                        "EntryDate": entry_date,
                        "ExitDate": b_date,
                        "PositionSize": pos_size,
                        "EntryPrice": entry_p,
                        "ExitPrice": exit_p,
                        "PnL": pnl,
                        "ReturnPct": ret_pct,
                        "Result": "Win",
                        "ExitReason": "Take Profit (+7.0%)",
                        "Trailed": trailed,
                    })
                    cash += (pos_size * exit_p)
                    in_pos = False
                    continue

            # Check new entry signal on candle close
            if signals[i] == 1 and not in_pos:
                entry_p = b_close
                pos_size = int(trade_cap / entry_p) if entry_p > 0 else 0
                if pos_size > 0:
                    sl_p = round(entry_p * (1.0 - self.stop_loss_pct), 2)
                    tp_p = round(entry_p * (1.0 + self.take_profit_pct), 2)
                    entry_date = b_date
                    trailed = False
                    cash -= (pos_size * entry_p)
                    in_pos = True

        trade_log = pd.DataFrame(trades)
        total_trades = len(trade_log)

        if total_trades > 0:
            wins = (trade_log["PnL"] > 0).sum()
            losses = (trade_log["PnL"] < 0).sum()
            bes = (trade_log["PnL"] == 0).sum()
            win_rate = (wins / total_trades) * 100.0
            total_pnl = trade_log["PnL"].sum()
            final_cap = initial_capital + total_pnl
            gross_profit = trade_log.loc[trade_log["PnL"] > 0, "PnL"].sum()
            gross_loss = abs(trade_log.loc[trade_log["PnL"] < 0, "PnL"].sum())
            profit_factor = (
                gross_profit / gross_loss if gross_loss > 0 else float("inf")
            )
        else:
            wins = losses = bes = 0
            win_rate = total_pnl = 0.0
            final_cap = initial_capital
            profit_factor = 0.0

        total_return_pct = (
            (total_pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0
        )

        # Compute duration for CAGR calculation
        duration_days = 0
        if not df.empty and "date" in df.columns:
            try:
                s_dt = pd.to_datetime(df["date"].iloc[0])
                e_dt = pd.to_datetime(df["date"].iloc[-1])
                duration_days = max(1, (e_dt - s_dt).days)
            except (ValueError, TypeError):
                duration_days = 0

        if duration_days <= 0 and total_trades > 0:
            try:
                s_dt = pd.to_datetime(trade_log["EntryDate"].min())
                e_dt = pd.to_datetime(trade_log["ExitDate"].max())
                duration_days = max(1, (e_dt - s_dt).days)
            except (ValueError, TypeError):
                duration_days = 365

        duration_years = max(duration_days / 365.25, 1.0 / 365.25)
        if final_cap > 0 and initial_capital > 0:
            cagr = (final_cap / initial_capital) ** (1.0 / duration_years) - 1.0
        elif final_cap <= 0:
            cagr = -1.0
        else:
            cagr = 0.0
        cagr_pct = cagr * 100.0

        metrics = {
            "InitialCapital": initial_capital,
            "FinalCapital": final_cap,
            "TotalPnL": total_pnl,
            "TotalReturnPct": total_return_pct,
            "TotalPnLPct": total_return_pct,
            "CAGR": cagr,
            "CAGRPct": cagr_pct,
            "TotalTrades": total_trades,
            "Wins": int(wins),
            "Losses": int(losses),
            "Breakevens": int(bes),
            "WinRatePct": win_rate,
            "ProfitFactor": profit_factor,
            "DurationDays": duration_days,
            "DurationYears": duration_years,
        }

        return {"Metrics": metrics, "TradeLog": trade_log}
