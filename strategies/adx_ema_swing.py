"""Linda Raschke’s ADX + 20 EMA swing trading strategy (The Holy Grail).

Strategy Summary
----------------
Linda Bradford Raschke and Laurence A. Connors introduced the "Holy Grail"
pattern in their classic book *Street Smarts* (Chapter: The Holy Grail).
The setup identifies pullbacks to the 20-period Exponential Moving Average (EMA)
in strong trending markets measured by the 14-period Average Directional Index (ADX).

Checklist Rules
---------------
1. Trend & Momentum Identification:
   - 14-period ADX must be greater than 30 and rising (ADX[t] > ADX[t-1]).
   - Directional bias:
     * Long: +DMI > -DMI (uptrend).
     * Short: -DMI > +DMI (downtrend).
   - 20-period EMA acts as the dynamic support/resistance baseline.

2. Setup Identification (The Retracement):
   - Long setup: Price retraces from above and touches the 20 EMA (Low <= 20 EMA).
     The touch bar's high becomes the trigger level.
   - Short setup: Price retraces from below and touches the 20 EMA (High >= 20 EMA).
     The touch bar's low becomes the trigger level.

3. Entry Trigger:
   - Long entry: Enter Long on a break above the EMA-touch bar high (Buy Stop).
   - Short entry: Enter Short on a break below the EMA-touch bar low (Sell Stop).

4. Stop-Loss & Position Sizing:
   - Long Stop-Loss: Placed at the recent swing low / touch bar low.
   - Short Stop-Loss: Placed at the recent swing high / touch bar high.
   - Position Sizing: Risk exactly 1% of portfolio capital per trade:
       Shares = floor((Capital * 0.01) / |EntryPrice - StopLoss|)

5. Exit Rules:
   - Initial Stop-Loss hit: Protects against adverse breakout failure.
   - 2R Profit Target: Exit at 2 * R profit (where R = |EntryPrice - StopLoss|).
   - ADX < 30: Fading trend strength signal to exit.
   - 20 EMA Break: Close below 20 EMA for Longs, or close above 20 EMA for Shorts.
"""

import numpy as np
import pandas as pd
import yfinance as yf

from adx_indicator import calculate_adx
from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from market_repository import MarketRepository
from strategies.base_strategy import BaseStrategy


def load_daily_data(
    source: str | pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    repo: MarketRepository | None = None,
) -> pd.DataFrame:
    """Load daily OHLCV dataset from a DataFrame, database, CSV, or Yahoo Finance.

    Args:
        source (str | pd.DataFrame): Ticker symbol (e.g. 'RELIANCE.NS', 'AAPL'),
            CSV filepath, or existing OHLCV pandas DataFrame.
        start (str | None): Optional start date in 'YYYY-MM-DD' format.
        end (str | None): Optional end date in 'YYYY-MM-DD' format.
        repo (MarketRepository | None): Optional MarketRepository instance.

    Returns:
        pd.DataFrame: Clean daily DataFrame containing 'date', 'open', 'high',
            'low', 'close', and 'volume' columns sorted by date.
    """
    # 1. If DataFrame is already provided
    if isinstance(source, pd.DataFrame):
        df = source.copy()
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df['date'] = df.index.strftime('%Y-%m-%d')
        required_cols = {'open', 'high', 'low', 'close', 'volume'}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"DataFrame must contain columns: {required_cols}")
        df['date'] = df['date'].astype(str).str[:10]
        return df.sort_values(by='date').reset_index(drop=True)

    ticker = str(source).strip()

    # 2. Check if source is a CSV file path
    if ticker.lower().endswith('.csv'):
        df = pd.read_csv(ticker)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str).str[:10]
        return df.sort_values(by='date').reset_index(drop=True)

    # 3. Try to load daily data from local SQLite database repository
    if repo is None:
        repo = MarketRepository()

    try:
        db_df = repo.get_daily_data(ticker)
        if not db_df.empty and len(db_df) >= 30:
            if start:
                db_df = db_df[db_df['date'] >= str(start)[:10]]
            if end:
                db_df = db_df[db_df['date'] <= str(end)[:10]]
            if not db_df.empty:
                return db_df.sort_values(by='date').reset_index(drop=True)
    except Exception:
        # Fallback to online fetch if database query fails
        pass

    # 4. Download daily bars from Yahoo Finance
    clean_ticker = ticker.split(' ')[0]
    yf_df = yf.download(
        clean_ticker,
        start=start,
        end=end,
        period="2y" if start is None else None,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if yf_df is None or yf_df.empty:
        return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])

    if isinstance(yf_df.columns, pd.MultiIndex):
        yf_df.columns = yf_df.columns.get_level_values(0)

    yf_df = yf_df.reset_index()
    yf_df.columns = [str(col).lower() for col in yf_df.columns]

    date_col = 'date' if 'date' in yf_df.columns else 'datetime'
    yf_df['date'] = yf_df[date_col].astype(str).str[:10]

    cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    available_cols = [c for c in cols if c in yf_df.columns]
    res_df = yf_df[available_cols].copy()

    for price_col in ['open', 'high', 'low', 'close']:
        if price_col in res_df.columns:
            res_df[price_col] = pd.to_numeric(res_df[price_col], errors='coerce')

    if 'volume' in res_df.columns:
        res_df['volume'] = pd.to_numeric(res_df['volume'], errors='coerce').fillna(0).astype(int)

    return res_df.dropna(subset=['open', 'high', 'low', 'close']).sort_values('date').reset_index(
        drop=True
    )


class AdxEmaSwingStrategy(BaseStrategy):
    """Linda Raschke's ADX + 20 EMA swing trading strategy (The Holy Grail).

    Combines 14-period ADX momentum filtering with 20 EMA pullback entries,
    recent swing low/high stops, and 2R profit targets.
    """

    def __init__(
        self,
        ema_period: int = 20,
        adx_period: int = 14,
        adx_threshold: float = 30.0,
        adx_rising_lookback: int = 5,
        swing_lookback: int = 5,
        target_rr: float = 2.0,
        allow_short: bool = True,
        max_breakout_bars: int = 3,
    ):
        """Initialize strategy hyperparameters.

        Args:
            ema_period (int): EMA smoothing length. Defaults to 20.
            adx_period (int): Wilder's ADX calculation lookback. Defaults to 14.
            adx_threshold (float): Minimum ADX value for a strong trend. Defaults to 30.0.
            adx_rising_lookback (int): Lookback window to check if ADX has been rising into
                the pullback setup. Defaults to 5.
            swing_lookback (int): Lookback bars for identifying swing high/low stop loss.
                Defaults to 5.
            target_rr (float): Risk-to-reward ratio for take profit (e.g. 2.0 for 2R).
                Defaults to 2.0.
            allow_short (bool): Whether to generate Short setups alongside Long setups.
                Defaults to True.
            max_breakout_bars (int): Number of bars to look for a breakout above/below
                the EMA-touch candle. Defaults to 3.
        """
        self.ema_period = ema_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.adx_rising_lookback = adx_rising_lookback
        self.swing_lookback = swing_lookback
        self.target_rr = target_rr
        self.allow_short = allow_short
        self.max_breakout_bars = max_breakout_bars

    @property
    def name(self) -> str:
        """Return unique strategy identifier."""
        return "Linda_Raschke_Holy_Grail"

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute 20 EMA, ADX(14), +DI, -DI, and swing boundaries.

        Args:
            df (pd.DataFrame): OHLCV price DataFrame.

        Returns:
            pd.DataFrame: DataFrame enriched with technical indicator series.
        """
        df = df.copy()

        # 1. 20-period Exponential Moving Average
        df['EMA20'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

        # 2. ADX and Directional Indicators (+DI, -DI)
        adx_data = calculate_adx(df, period=self.adx_period)
        df['ADX'] = adx_data['ADX']
        df['+DI'] = adx_data['+DI']
        df['-DI'] = adx_data['-DI']
        df['ATR'] = adx_data['ATR']

        # 3. ADX Momentum (Rising condition)
        df['ADX_Rising'] = df['ADX'] > df['ADX'].shift(1)
        # Check if ADX was rising within the lookback window
        df['ADX_Rising_Recent'] = (
            df['ADX_Rising']
            .rolling(window=self.adx_rising_lookback, min_periods=1)
            .max()
            .astype(bool)
        )

        # 4. Recent Swing Low & High for dynamic stop placement
        # Shifted by 1 so current bar is excluded from historical swing calculation
        df['SwingLow'] = (
            df['low'].shift(1).rolling(window=self.swing_lookback, min_periods=1).min()
        )
        df['SwingHigh'] = (
            df['high'].shift(1).rolling(window=self.swing_lookback, min_periods=1).max()
        )

        return df

    def generate_signals(
        self,
        df: pd.DataFrame,
        capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        **kwargs,
    ) -> pd.DataFrame:
        """Generate setup flags, breakout signals, stops, and position sizes.

        Args:
            df (pd.DataFrame): Input daily OHLCV records.
            capital (float): Total portfolio capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional risk allocation (e.g. 0.01 for 1%).

        Returns:
            pd.DataFrame: DataFrame enriched with indicators, Setup flags, Signal (1, -1, 0),
                StopLoss, TakeProfit, and PositionSize.
        """
        df = self.compute_indicators(df)

        # Setup Conditions:
        # Long Setup: ADX > 30, ADX was rising into pullback, +DI > -DI, Price touches 20 EMA
        # Short Setup: ADX > 30, ADX was rising into rally, -DI > +DI, Price touches 20 EMA
        long_setup = (
            (df['ADX'] > self.adx_threshold)
            & df['ADX_Rising_Recent']
            & (df['+DI'] > df['-DI'])
            & (df['low'] <= df['EMA20'])
        )

        short_setup = (
            (df['ADX'] > self.adx_threshold)
            & df['ADX_Rising_Recent']
            & (df['-DI'] > df['+DI'])
            & (df['high'] >= df['EMA20'])
        )

        df['Setup_Long'] = long_setup.astype(int)
        df['Setup_Short'] = short_setup.astype(int) if self.allow_short else 0

        # Breakout Entry Signal Logic:
        # Long entry occurs when price breaks above setup bar's high.
        # Short entry occurs when price breaks below setup bar's low.
        n = len(df)
        highs = df['high'].values
        lows = df['low'].values
        opens = df['open'].values
        swing_lows = df['SwingLow'].values
        swing_highs = df['SwingHigh'].values
        setup_long = df['Setup_Long'].values
        setup_short = df['Setup_Short'].values

        signals = np.zeros(n, dtype=int)
        stop_losses = [None] * n
        take_profits = [None] * n
        position_sizes = np.zeros(n, dtype=int)

        risk_amount = capital * risk_per_trade

        for i in range(1, n):
            # Check for Long breakout trigger from preceding setup bars
            triggered_long = False
            for lookback in range(1, self.max_breakout_bars + 1):
                setup_idx = i - lookback
                if setup_idx < 0:
                    break
                if setup_long[setup_idx] == 1:
                    setup_high = highs[setup_idx]
                    setup_low = lows[setup_idx]
                    # Check if today's high broke above setup bar high
                    if highs[i] > setup_high:
                        entry_est = max(opens[i], setup_high)
                        # Stop loss at recent swing low or setup bar low
                        stop_loss = min(setup_low, swing_lows[i])
                        risk_per_share = entry_est - stop_loss
                        if risk_per_share > 0:
                            target = entry_est + (self.target_rr * risk_per_share)
                            pos_size = int(risk_amount / risk_per_share)
                            signals[i] = 1
                            stop_losses[i] = round(stop_loss, 2)
                            take_profits[i] = round(target, 2)
                            position_sizes[i] = pos_size
                            triggered_long = True
                            break

            if triggered_long or not self.allow_short:
                continue

            # Check for Short breakout trigger from preceding setup bars
            for lookback in range(1, self.max_breakout_bars + 1):
                setup_idx = i - lookback
                if setup_idx < 0:
                    break
                if setup_short[setup_idx] == 1:
                    setup_low = lows[setup_idx]
                    setup_high = highs[setup_idx]
                    # Check if today's low broke below setup bar low
                    if lows[i] < setup_low:
                        entry_est = min(opens[i], setup_low)
                        # Stop loss at recent swing high or setup bar high
                        stop_loss = max(setup_high, swing_highs[i])
                        risk_per_share = stop_loss - entry_est
                        if risk_per_share > 0:
                            target = entry_est - (self.target_rr * risk_per_share)
                            pos_size = int(risk_amount / risk_per_share)
                            signals[i] = -1
                            stop_losses[i] = round(stop_loss, 2)
                            take_profits[i] = round(target, 2)
                            position_sizes[i] = pos_size
                            break

        df['Signal'] = signals
        df['StopLoss'] = stop_losses
        df['TakeProfit'] = take_profits
        df['PositionSize'] = position_sizes

        return df


class AdxEmaBacktester:
    """Simulates Long and Short trades according to Linda Raschke's rules.

    Enforces:
    - Stop-loss exit (swing low for longs, swing high for shorts)
    - 2R profit target exit
    - ADX < 30 trend weakness exit
    - 20 EMA break exit (close below EMA for longs, close above EMA for shorts)
    - 1% portfolio risk sizing per trade
    """

    def __init__(
        self,
        strategy: AdxEmaSwingStrategy | None = None,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        max_capital_allocation: float = 0.25,
    ):
        """Initialize the backtester.

        Args:
            strategy (AdxEmaSwingStrategy | None): Strategy instance.
            initial_capital (float): Starting portfolio capital in INR.
            risk_per_trade (float): Portfolio risk per trade fraction (0.01 = 1%).
            max_capital_allocation (float): Maximum capital allowed per single position.
        """
        self.strategy = strategy if strategy is not None else AdxEmaSwingStrategy()
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_capital_allocation = max_capital_allocation

    def run(
        self,
        data: pd.DataFrame | str,
        ticker: str = "Security",
    ) -> dict:
        """Execute single-security backtest simulation.

        Args:
            data (pd.DataFrame | str): OHLCV DataFrame or ticker symbol string.
            ticker (str): Ticker label for trade log.

        Returns:
            dict: Summary containing 'TradeLog' (DataFrame) and 'Metrics' (dict).
        """
        if isinstance(data, str):
            ticker_name = data.split(' ')[0]
            df = load_daily_data(data)
        else:
            ticker_name = ticker
            df = data.copy()

        if df.empty or len(df) < 30:
            empty_trades = pd.DataFrame(columns=[
                "TradeID", "Security", "Type", "EntryDate", "ExitDate",
                "PositionSize", "EntryPrice", "ExitPrice", "StopLoss",
                "TakeProfit", "PnL", "ReturnPct", "RMultiple", "Result", "ExitReason",
            ])
            return {
                "TradeLog": empty_trades,
                "Metrics": self._calculate_metrics(empty_trades, self.initial_capital),
            }

        signals_df = self.strategy.generate_signals(
            df,
            capital=self.initial_capital,
            risk_per_trade=self.risk_per_trade,
        )

        return self._simulate_single_security(signals_df, ticker_name)

    def _simulate_single_security(self, df: pd.DataFrame, ticker: str) -> dict:
        """Simulate trade execution on a single security dataset.

        Args:
            df (pd.DataFrame): DataFrame with signals and indicator values.
            ticker (str): Security symbol identifier.

        Returns:
            dict: Trade log and performance metrics.
        """
        trades = []
        open_pos = None  # None or dict of active trade details
        cash = self.initial_capital
        trade_counter = 0

        dates = df['date'].astype(str).values
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        emas = df['EMA20'].values
        adxs = df['ADX'].values
        signals = df['Signal'].values
        stoplosses = df['StopLoss'].values
        takeprofits = df['TakeProfit'].values

        n = len(df)

        for i in range(n):
            date_str = dates[i][:10]
            bar_open = float(opens[i])
            bar_high = float(highs[i])
            bar_low = float(lows[i])
            bar_close = float(closes[i])
            bar_ema = float(emas[i]) if pd.notna(emas[i]) else bar_close
            bar_adx = float(adxs[i]) if pd.notna(adxs[i]) else 0.0

            # --- 1. Evaluate Active Position for Exits ---
            if open_pos is not None:
                pos_type = open_pos['Type']
                entry_price = open_pos['EntryPrice']
                stop_loss = open_pos['StopLoss']
                take_profit = open_pos['TakeProfit']
                pos_size = open_pos['Size']
                initial_r = open_pos['InitialR']

                exited = False
                exit_price = bar_close
                exit_reason = "Exit"

                if pos_type == "LONG":
                    # Exit Condition 1: Stop-Loss hit (intraday)
                    if bar_low <= stop_loss:
                        exit_price = min(stop_loss, bar_open)
                        exit_reason = "Stop Loss"
                        exited = True
                    # Exit Condition 2: 2R Profit Target hit (intraday)
                    elif bar_high >= take_profit:
                        exit_price = max(take_profit, bar_open)
                        exit_reason = "2R Target"
                        exited = True
                    # EOD Exit Conditions (evaluated on holding days after entry)
                    elif date_str > open_pos["EntryDate"]:
                        if bar_adx < self.strategy.adx_threshold:
                            exit_price = bar_close
                            exit_reason = "ADX < 30"
                            exited = True
                        elif bar_close < bar_ema:
                            exit_price = bar_close
                            exit_reason = "EMA Break"
                            exited = True

                    if exited:
                        pnl = (exit_price - entry_price) * pos_size
                        ret_pct = ((exit_price - entry_price) / entry_price) * 100.0
                        r_mult = (exit_price - entry_price) / initial_r if initial_r > 0 else 0.0

                        trades.append({
                            "TradeID": open_pos["TradeID"],
                            "Security": ticker,
                            "Type": "LONG",
                            "EntryDate": open_pos["EntryDate"],
                            "ExitDate": date_str,
                            "PositionSize": pos_size,
                            "EntryPrice": round(entry_price, 2),
                            "ExitPrice": round(exit_price, 2),
                            "StopLoss": round(stop_loss, 2),
                            "TakeProfit": round(take_profit, 2),
                            "PnL": round(pnl, 2),
                            "ReturnPct": round(ret_pct, 2),
                            "RMultiple": round(r_mult, 2),
                            "Result": "Win" if pnl > 0 else "Loss",
                            "ExitReason": exit_reason,
                        })
                        cash += pnl
                        open_pos = None

                elif pos_type == "SHORT":
                    # Exit Condition 1: Stop-Loss hit (intraday)
                    if bar_high >= stop_loss:
                        exit_price = max(stop_loss, bar_open)
                        exit_reason = "Stop Loss"
                        exited = True
                    # Exit Condition 2: 2R Profit Target hit (intraday)
                    elif bar_low <= take_profit:
                        exit_price = min(take_profit, bar_open)
                        exit_reason = "2R Target"
                        exited = True
                    # EOD Exit Conditions (evaluated on holding days after entry)
                    elif date_str > open_pos["EntryDate"]:
                        if bar_adx < self.strategy.adx_threshold:
                            exit_price = bar_close
                            exit_reason = "ADX < 30"
                            exited = True
                        elif bar_close > bar_ema:
                            exit_price = bar_close
                            exit_reason = "EMA Break"
                            exited = True

                    if exited:
                        pnl = (entry_price - exit_price) * pos_size
                        ret_pct = ((entry_price - exit_price) / entry_price) * 100.0
                        r_mult = (entry_price - exit_price) / initial_r if initial_r > 0 else 0.0

                        trades.append({
                            "TradeID": open_pos["TradeID"],
                            "Security": ticker,
                            "Type": "SHORT",
                            "EntryDate": open_pos["EntryDate"],
                            "ExitDate": date_str,
                            "PositionSize": pos_size,
                            "EntryPrice": round(entry_price, 2),
                            "ExitPrice": round(exit_price, 2),
                            "StopLoss": round(stop_loss, 2),
                            "TakeProfit": round(take_profit, 2),
                            "PnL": round(pnl, 2),
                            "ReturnPct": round(ret_pct, 2),
                            "RMultiple": round(r_mult, 2),
                            "Result": "Win" if pnl > 0 else "Loss",
                            "ExitReason": exit_reason,
                        })
                        cash += pnl
                        open_pos = None

            # --- 2. Evaluate New Entry Signals (if no active position) ---
            if open_pos is None:
                sig = int(signals[i]) if pd.notna(signals[i]) else 0
                sl = float(stoplosses[i]) if pd.notna(stoplosses[i]) else None
                tp = float(takeprofits[i]) if pd.notna(takeprofits[i]) else None

                if sig != 0 and sl is not None and tp is not None:
                    trade_counter += 1
                    risk_amount = cash * self.risk_per_trade

                    if sig == 1:  # Long Signal
                        entry_price = bar_close
                        initial_r = entry_price - sl
                        if initial_r > 0:
                            # 1% risk position sizing
                            raw_size = int(risk_amount / initial_r)
                            # Cap by max capital allocation constraint
                            max_size = int((cash * self.max_capital_allocation) / entry_price)
                            pos_size = max(1, min(raw_size, max_size)) if max_size > 0 else 0

                            if pos_size > 0:
                                open_pos = {
                                    "TradeID": f"TRD-{trade_counter:04d}",
                                    "Type": "LONG",
                                    "EntryDate": date_str,
                                    "EntryPrice": entry_price,
                                    "StopLoss": sl,
                                    "TakeProfit": tp,
                                    "Size": pos_size,
                                    "InitialR": initial_r,
                                }

                    elif sig == -1 and self.strategy.allow_short:  # Short Signal
                        entry_price = bar_close
                        initial_r = sl - entry_price
                        if initial_r > 0:
                            raw_size = int(risk_amount / initial_r)
                            max_size = int((cash * self.max_capital_allocation) / entry_price)
                            pos_size = max(1, min(raw_size, max_size)) if max_size > 0 else 0

                            if pos_size > 0:
                                open_pos = {
                                    "TradeID": f"TRD-{trade_counter:04d}",
                                    "Type": "SHORT",
                                    "EntryDate": date_str,
                                    "EntryPrice": entry_price,
                                    "StopLoss": sl,
                                    "TakeProfit": tp,
                                    "Size": pos_size,
                                    "InitialR": initial_r,
                                }

        # --- Format Trade Log ---
        df_trades = pd.DataFrame(trades)
        if not df_trades.empty:
            df_trades = df_trades.sort_values(
                by=["EntryDate", "ExitDate"]
            ).reset_index(drop=True)
        else:
            df_trades = pd.DataFrame(columns=[
                "TradeID", "Security", "Type", "EntryDate", "ExitDate",
                "PositionSize", "EntryPrice", "ExitPrice", "StopLoss",
                "TakeProfit", "PnL", "ReturnPct", "RMultiple", "Result", "ExitReason",
            ])

        metrics = self._calculate_metrics(df_trades, self.initial_capital)
        return {"TradeLog": df_trades, "Metrics": metrics}

    def run_portfolio(
        self,
        securities_dict: dict[str, pd.DataFrame],
        progress_callback: callable = None,
    ) -> dict:
        """Execute multi-stock portfolio simulation across all securities.

        Args:
            securities_dict (dict[str, pd.DataFrame]): Dictionary mapping ticker
                symbols to daily OHLCV DataFrames.
            progress_callback (callable | None): Optional callback function invoked as
                progress_callback(current_idx, total_count, ticker_name) for progress tracking.

        Returns:
            dict: Aggregated 'TradeLog' and 'Metrics' dictionary.
        """
        all_trades = []
        initial_cap = self.initial_capital
        total_securities = len(securities_dict)

        for idx, (ticker, df) in enumerate(securities_dict.items(), start=1):
            if progress_callback is not None:
                progress_callback(idx, total_securities, ticker)

            if df.empty or len(df) < 30:
                continue
            res = self.run(df, ticker=ticker)
            t_log = res["TradeLog"]
            if not t_log.empty:
                all_trades.append(t_log)

        if all_trades:
            df_all = pd.concat(all_trades, ignore_index=True)
            df_all = df_all.sort_values(
                by=["EntryDate", "ExitDate", "Security"]
            ).reset_index(drop=True)
        else:
            df_all = pd.DataFrame(columns=[
                "TradeID", "Security", "Type", "EntryDate", "ExitDate",
                "PositionSize", "EntryPrice", "ExitPrice", "StopLoss",
                "TakeProfit", "PnL", "ReturnPct", "RMultiple", "Result", "ExitReason",
            ])

        metrics = self._calculate_metrics(df_all, initial_cap)
        return {"TradeLog": df_all, "Metrics": metrics}

    def _calculate_metrics(self, df_trades: pd.DataFrame, initial_capital: float) -> dict:
        """Compute comprehensive trading performance metrics.

        Args:
            df_trades (pd.DataFrame): DataFrame of completed trades.
            initial_capital (float): Initial portfolio capital in INR.

        Returns:
            dict: Computed performance statistics.
        """
        total_trades = len(df_trades)
        if total_trades == 0:
            return {
                "InitialCapital": initial_capital,
                "FinalCapital": initial_capital,
                "TotalPnL": 0.0,
                "TotalReturnPct": 0.0,
                "TotalTrades": 0,
                "LongTrades": 0,
                "ShortTrades": 0,
                "Wins": 0,
                "Losses": 0,
                "WinRatePct": 0.0,
                "GrossProfits": 0.0,
                "GrossLosses": 0.0,
                "ProfitFactor": 0.0,
                "AverageWin": 0.0,
                "AverageLoss": 0.0,
                "WinLossRatio": 0.0,
                "AverageR": 0.0,
                "MaxDrawdown": 0.0,
                "MaxDrawdownPct": 0.0,
                "ExitReasons": {},
            }

        pnls = df_trades["PnL"].values
        win_mask = df_trades["Result"] == "Win"
        loss_mask = df_trades["Result"] == "Loss"

        wins = int(win_mask.sum())
        losses = int(loss_mask.sum())
        win_rate = (wins / total_trades) * 100.0

        long_trades = int((df_trades["Type"] == "LONG").sum())
        short_trades = int((df_trades["Type"] == "SHORT").sum())

        gross_profits = float(df_trades.loc[win_mask, "PnL"].sum())
        gross_losses = float(abs(df_trades.loc[loss_mask, "PnL"].sum()))

        profit_factor = (
            round(gross_profits / gross_losses, 2)
            if gross_losses > 0
            else (999.0 if gross_profits > 0 else 0.0)
        )

        avg_win = float(gross_profits / wins) if wins > 0 else 0.0
        avg_loss = float(gross_losses / losses) if losses > 0 else 0.0
        win_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        avg_r = (
            float(df_trades["RMultiple"].mean())
            if "RMultiple" in df_trades.columns
            else 0.0
        )

        total_pnl = float(df_trades["PnL"].sum())
        final_capital = initial_capital + total_pnl
        total_return_pct = (total_pnl / initial_capital) * 100.0

        # Peak-to-trough Drawdown calculation
        cumulative_pnl = np.cumsum(pnls)
        equity_curve = initial_capital + cumulative_pnl
        running_peak = np.maximum.accumulate(equity_curve)
        drawdowns = running_peak - equity_curve
        drawdown_pcts = (drawdowns / running_peak) * 100.0

        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        max_drawdown_pct = float(np.max(drawdown_pcts)) if len(drawdown_pcts) > 0 else 0.0

        exit_reasons = df_trades["ExitReason"].value_counts().to_dict()

        return {
            "InitialCapital": initial_capital,
            "FinalCapital": final_capital,
            "TotalPnL": total_pnl,
            "TotalReturnPct": total_return_pct,
            "TotalTrades": total_trades,
            "LongTrades": long_trades,
            "ShortTrades": short_trades,
            "Wins": wins,
            "Losses": losses,
            "WinRatePct": win_rate,
            "GrossProfits": gross_profits,
            "GrossLosses": gross_losses,
            "ProfitFactor": profit_factor,
            "AverageWin": avg_win,
            "AverageLoss": avg_loss,
            "WinLossRatio": win_loss_ratio,
            "AverageR": avg_r,
            "MaxDrawdown": max_drawdown,
            "MaxDrawdownPct": max_drawdown_pct,
            "ExitReasons": exit_reasons,
        }
