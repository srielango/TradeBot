"""Backtesting engine module for evaluating trading strategies on historical data."""

import pandas as pd

from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE


class BacktestEngine:
    """Simulates trade execution with stop loss enforcement and performance metrics."""

    def __init__(
        self,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
    ):
        """Initialize the backtest engine with capital and risk parameters.

        Args:
            initial_capital (float): Starting capital in INR. Defaults to DEFAULT_INITIAL_CAPITAL.
            risk_per_trade (float): Fractional risk allocation per trade (e.g. 0.01 for 1%).
        """
        self.initial_capital = initial_capital
        self.risk_amount = initial_capital * risk_per_trade

    def run(self, df: pd.DataFrame) -> dict:
        """Execute backtest over historical dataset using stop loss and next-day open exits.

        Args:
            df (pd.DataFrame): DataFrame with signals, date, open, high, low, close,
                StopLoss, and PositionSize.

        Returns:
            dict: Dictionary containing 'TradeLog' (DataFrame) and 'Metrics' (summary statistics).
        """
        trades = []
        position = None  # Active open trade position
        capital = self.initial_capital

        # Loop until second-to-last row for next-day open price execution
        for i in range(len(df) - 1):
            # --- Check Stop Loss on Active Position (Intraday execution) ---
            if position is not None and position.get("StopLoss") is not None:
                stop_level = position["StopLoss"]
                bar_low = df.loc[i, 'low']
                bar_open = df.loc[i, 'open']

                if bar_low <= stop_level:
                    exit_date = df.loc[i, 'date']
                    # Handle gap-down below stop loss on market open
                    exit_price = min(stop_level, bar_open)

                    pnl = (exit_price - position["EntryPrice"]) * position["Size"]
                    ret_pct = (
                        (exit_price - position["EntryPrice"]) / position["EntryPrice"] * 100
                    )
                    result = "Win" if pnl > 0 else "Loss"

                    trades.append({
                        "EntryDate": position["EntryDate"],
                        "ExitDate": exit_date,
                        "PositionSize": position["Size"],
                        "EntryPrice": position["EntryPrice"],
                        "ExitPrice": exit_price,
                        "PnL": pnl,
                        "ReturnPct": ret_pct,
                        "Result": result,
                        "ExitReason": "Stop Loss",
                    })

                    capital += pnl
                    position = None
                    continue

            signal = df.loc[i, 'Signal']

            # --- Strategy Exit Signal Execution (Next-day open) ---
            if signal == -1 and position is not None:
                exit_date = df.loc[i + 1, 'date']
                exit_price = df.loc[i + 1, 'open']

                pnl = (exit_price - position["EntryPrice"]) * position["Size"]
                ret_pct = (
                    (exit_price - position["EntryPrice"]) / position["EntryPrice"] * 100
                )
                result = "Win" if pnl > 0 else "Loss"

                trades.append({
                    "EntryDate": position["EntryDate"],
                    "ExitDate": exit_date,
                    "PositionSize": position["Size"],
                    "EntryPrice": position["EntryPrice"],
                    "ExitPrice": exit_price,
                    "PnL": pnl,
                    "ReturnPct": ret_pct,
                    "Result": result,
                    "ExitReason": "Signal",
                })

                capital += pnl
                position = None

            # --- Strategy Entry Signal Execution (Next-day open) ---
            elif signal == 1 and position is None:
                entry_date = df.loc[i + 1, 'date']
                entry_price = df.loc[i + 1, 'open']
                stop_loss = df.loc[i, 'StopLoss']
                position_size = df.loc[i, 'PositionSize']

                # Fallback calculation if position_size is unassigned
                if position_size <= 0 and stop_loss is not None and entry_price > stop_loss:
                    risk_per_share = entry_price - stop_loss
                    position_size = int(self.risk_amount / risk_per_share)

                if position_size > 0:
                    position = {
                        "EntryDate": entry_date,
                        "EntryPrice": entry_price,
                        "StopLoss": stop_loss,
                        "Size": position_size,
                    }

        # --- Metrics Calculation ---
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["Result"] == "Win")
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = sum(t["PnL"] for t in trades)

        return {
            "TradeLog": pd.DataFrame(trades),
            "Metrics": {
                "TotalTrades": total_trades,
                "Wins": wins,
                "Losses": losses,
                "TotalPnL": total_pnl,
                "WinRatePct": win_rate,
                "FinalCapital": capital,
            },
        }
