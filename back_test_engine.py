"""Backtesting engine module for evaluating trading strategies on historical data."""

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE


class BacktestEngine:
    """Simulates trade execution with stop loss enforcement and performance metrics."""

    def __init__(
        self,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        allocation_fraction: float = 0.10,
    ):
        """Initialize the backtest engine with capital and risk parameters.

        Args:
            initial_capital (float): Starting capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional risk allocation per trade (e.g. 0.01 for 1%).
            allocation_fraction (float): Capital allocation fraction per security
                (e.g. 0.10 for 10%).
        """
        self.initial_capital = initial_capital
        self.risk_amount = initial_capital * risk_per_trade
        self.allocation_fraction = allocation_fraction

    def run(
        self,
        data: pd.DataFrame | dict[str, pd.DataFrame],
        ticker: str = "Security",
    ) -> dict:
        """Execute backtest over historical dataset or multi-asset dictionary.

        Args:
            data (pd.DataFrame | dict[str, pd.DataFrame]): Single DataFrame or dictionary of
                DataFrames with signals, date, open, high, low, close, and StopLoss.
            ticker (str): Security name to label trades when a single DataFrame is passed.

        Returns:
            dict: Dictionary containing 'TradeLog' (DataFrame) and 'Metrics' (summary statistics).
        """
        if isinstance(data, dict):
            return self.run_portfolio(data)

        ticker_name = ticker or "Security"
        return self.run_portfolio({ticker_name: data})

    def run_portfolio(
        self,
        securities_data: dict[str, pd.DataFrame],
        progress_callback: callable = None,
    ) -> dict:
        """Execute chronological multi-asset portfolio simulation across all securities.

        Allocates a fixed fraction of initial capital (10%) for each stock buy signal,
        handles intraday stop losses, and executes next-day open entries/exits.

        Args:
            securities_data (dict[str, pd.DataFrame]): Dictionary mapping security ticker
                symbols to DataFrames containing price and indicator data.
            progress_callback (callable | None): Optional callback function invoked as
                progress_callback(current_idx, total_count, current_date) for progress tracking.

        Returns:
            dict: Dictionary containing 'TradeLog' (DataFrame) and 'Metrics' (summary statistics).
        """
        trades = []
        positions = {}  # ticker -> dict of open trade details
        cash = self.initial_capital
        trade_capital_target = self.initial_capital * self.allocation_fraction

        # Build fast date-indexed lookup structures for simulation performance
        ticker_date_data: dict[
            str, dict[str, tuple[float, float, float, int, float | None, float | None]]
        ] = {}
        all_dates_set = set()

        for ticker, df in securities_data.items():
            if df.empty or 'date' not in df.columns:
                continue

            dates = df['date'].values
            opens = df['open'].values
            highs = df['high'].values if 'high' in df.columns else df['open'].values
            lows = df['low'].values if 'low' in df.columns else df['open'].values
            signals = df['Signal'].values if 'Signal' in df.columns else [0] * len(df)
            stoplosses = df['StopLoss'].values if 'StopLoss' in df.columns else [None] * len(df)
            takeprofits = (
                df['TakeProfit'].values if 'TakeProfit' in df.columns else [None] * len(df)
            )

            ticker_dict = {}
            for d, o, h, l, s, sl, tp in zip(
                dates, opens, highs, lows, signals, stoplosses, takeprofits
            ):
                d_str = str(d)[:10]
                ticker_dict[d_str] = (
                    float(o),
                    float(h),
                    float(l),
                    int(s) if pd.notna(s) else 0,
                    float(sl) if pd.notna(sl) else None,
                    float(tp) if pd.notna(tp) else None,
                )
                all_dates_set.add(d_str)

            ticker_date_data[ticker] = ticker_dict

        all_dates = sorted(all_dates_set)
        total_dates = len(all_dates)
        pending_exits = set()
        pending_entries: dict[str, tuple[float | None, float | None]] = {}

        for date_idx, date in enumerate(all_dates, start=1):
            if progress_callback is not None and (date_idx % 25 == 0 or date_idx == total_dates):
                progress_callback(date_idx, total_dates, date)

            exited_today = set()

            # --- 1. Check Intraday Stop Loss & Take Profit on Active Positions ---
            for ticker, pos in list(positions.items()):
                t_data = ticker_date_data.get(ticker, {}).get(date)
                if t_data is not None:
                    bar_open, bar_high, bar_low, _, _, _ = t_data
                    stop_level = pos.get('StopLoss')
                    target_level = pos.get('TakeProfit')

                    # Check Stop Loss
                    if stop_level is not None and bar_low <= stop_level:
                        exit_price = min(stop_level, bar_open)
                        pnl = (exit_price - pos['EntryPrice']) * pos['Size']
                        ret_pct = (
                            (exit_price - pos['EntryPrice']) / pos['EntryPrice'] * 100
                        ) if pos['EntryPrice'] > 0 else 0.0

                        trades.append({
                            "Security": ticker,
                            "EntryDate": pos["EntryDate"],
                            "ExitDate": date,
                            "PositionSize": pos["Size"],
                            "EntryPrice": pos["EntryPrice"],
                            "ExitPrice": exit_price,
                            "PnL": pnl,
                            "ReturnPct": ret_pct,
                            "Result": "Win" if pnl > 0 else "Loss",
                            "ExitReason": "Stop Loss",
                        })

                        cash += pos['Size'] * exit_price
                        exited_today.add(ticker)
                        del positions[ticker]

                    # Check Take Profit Target
                    elif target_level is not None and bar_high >= target_level:
                        exit_price = max(target_level, bar_open)
                        pnl = (exit_price - pos['EntryPrice']) * pos['Size']
                        ret_pct = (
                            (exit_price - pos['EntryPrice']) / pos['EntryPrice'] * 100
                        ) if pos['EntryPrice'] > 0 else 0.0

                        target_pct = (
                            (target_level - pos['EntryPrice']) / pos['EntryPrice'] * 100
                        ) if pos['EntryPrice'] > 0 else 0.0

                        trades.append({
                            "Security": ticker,
                            "EntryDate": pos["EntryDate"],
                            "ExitDate": date,
                            "PositionSize": pos["Size"],
                            "EntryPrice": pos["EntryPrice"],
                            "ExitPrice": exit_price,
                            "PnL": pnl,
                            "ReturnPct": ret_pct,
                            "Result": "Win" if pnl > 0 else "Loss",
                            "ExitReason": f"Profit Target ({target_pct:.1f}%)",
                        })

                        cash += pos['Size'] * exit_price
                        exited_today.add(ticker)
                        del positions[ticker]

            # --- 2. Execute Pending Strategy Exits (Next-Day Open) ---
            for ticker in list(pending_exits):
                if ticker in positions and ticker not in exited_today:
                    t_data = ticker_date_data.get(ticker, {}).get(date)
                    if t_data is not None:
                        bar_open, _, _, _, _, _ = t_data
                        pos = positions[ticker]
                        exit_price = bar_open
                        pnl = (exit_price - pos['EntryPrice']) * pos['Size']
                        ret_pct = (
                            (exit_price - pos['EntryPrice']) / pos['EntryPrice'] * 100
                        ) if pos['EntryPrice'] > 0 else 0.0

                        trades.append({
                            "Security": ticker,
                            "EntryDate": pos["EntryDate"],
                            "ExitDate": date,
                            "PositionSize": pos["Size"],
                            "EntryPrice": pos["EntryPrice"],
                            "ExitPrice": exit_price,
                            "PnL": pnl,
                            "ReturnPct": ret_pct,
                            "Result": "Win" if pnl > 0 else "Loss",
                            "ExitReason": "Signal",
                        })

                        cash += pos['Size'] * exit_price
                        del positions[ticker]

            pending_exits.clear()

            # --- 3. Execute Pending Strategy Entries (Next-Day Open) ---
            for ticker, (sl, tp) in list(pending_entries.items()):
                if ticker not in positions:
                    t_data = ticker_date_data.get(ticker, {}).get(date)
                    if t_data is not None:
                        bar_open, _, _, _, _, _ = t_data
                        alloc = min(trade_capital_target, cash)
                        if bar_open > 0:
                            size = int(alloc / bar_open)
                            if size > 0 and cash >= size * bar_open:
                                cost = size * bar_open
                                cash -= cost
                                positions[ticker] = {
                                    "Security": ticker,
                                    "EntryDate": date,
                                    "EntryPrice": bar_open,
                                    "StopLoss": sl,
                                    "TakeProfit": tp,
                                    "Size": size,
                                }

            pending_entries.clear()

            # --- 4. Evaluate End-of-Day Signals on Day t ---
            for ticker, t_dict in ticker_date_data.items():
                t_data = t_dict.get(date)
                if t_data is not None:
                    _, _, _, sig, sl, tp = t_data
                    if sig == -1 and ticker in positions:
                        pending_exits.add(ticker)
                    elif sig == 1 and ticker not in positions:
                        pending_entries[ticker] = (sl, tp)

        # --- Sort & Format Completed Trades ---
        df_trades = pd.DataFrame(trades)
        if not df_trades.empty:
            df_trades = df_trades.sort_values(
                by=["EntryDate", "ExitDate", "Security"]
            ).reset_index(drop=True)
        else:
            df_trades = pd.DataFrame(columns=[
                "Security",
                "EntryDate",
                "ExitDate",
                "PositionSize",
                "EntryPrice",
                "ExitPrice",
                "PnL",
                "ReturnPct",
                "Result",
                "ExitReason",
            ])

        # --- Metrics Calculation ---
        total_trades = len(df_trades)
        wins = int((df_trades["Result"] == "Win").sum()) if total_trades > 0 else 0
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = float(df_trades["PnL"].sum()) if total_trades > 0 else 0.0
        final_capital = self.initial_capital + total_pnl

        return {
            "TradeLog": df_trades,
            "Metrics": {
                "TotalTrades": total_trades,
                "Wins": wins,
                "Losses": losses,
                "TotalPnL": total_pnl,
                "WinRatePct": win_rate,
                "FinalCapital": final_capital,
            },
        }
