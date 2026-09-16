"""Paper trading engine for TradeBot.

Manages virtual portfolio tracking, position sizing based on 1% risk rules,
order placement, live price evaluation against stop loss and profit targets,
and trade history journal logging for Nifty 50 securities.
"""

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from config import DB_PATH

# Fixed risk management framework parameters
STARTING_PORTFOLIO_BALANCE = 500_000.0  # INR 5 Lakhs virtual capital
MAX_TRADE_ALLOCATION = 100_000.0        # INR 1 Lakh deployment cap per trade
BASELINE_RISK_PER_TRADE = 1_000.0       # 1% risk of 1 Lakh baseline capital


class PositionSizingError(ValueError):
    """Exception raised for invalid parameters during position sizing."""


class PaperTradingEngine:
    """Engine handling SQLite persistence, risk sizing, and trade executions."""

    def __init__(self, db_path: str | Path = DB_PATH):
        """Initialize engine and ensure database schema exists.

        Args:
            db_path (str | Path): Path to SQLite database file.
        """
        self.db_path = str(os.path.abspath(db_path))
        self.init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection with row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        """Create required tables for paper portfolio and trades if not present.

        Seeds paper_portfolio with INR 5,00,000 starting cash balance if empty.
        """
        create_portfolio_table = """
        CREATE TABLE IF NOT EXISTS paper_portfolio (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash_balance REAL NOT NULL,
            initial_capital REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        create_trades_table = """
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT CHECK(side IN ('BUY', 'SELL')) NOT NULL DEFAULT 'BUY',
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            exit_price REAL,
            quantity INTEGER NOT NULL,
            stop_loss REAL NOT NULL,
            sell_target REAL,
            status TEXT CHECK(status IN ('OPEN', 'CLOSED')) NOT NULL DEFAULT 'OPEN',
            realized_pnl REAL DEFAULT 0.0,
            exit_timestamp TEXT,
            exit_reason TEXT
        );
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_portfolio_table)
            cursor.execute(create_trades_table)

            # Seed starting balance if record does not exist
            cursor.execute("SELECT cash_balance FROM paper_portfolio WHERE id = 1")
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO paper_portfolio (id, cash_balance, initial_capital, updated_at)
                    VALUES (1, ?, ?, ?)
                    """,
                    (
                        STARTING_PORTFOLIO_BALANCE,
                        STARTING_PORTFOLIO_BALANCE,
                        datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            conn.commit()

    def get_cash_balance(self) -> float:
        """Retrieve current available cash balance from virtual portfolio.

        Returns:
            float: Available cash balance in INR.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cash_balance FROM paper_portfolio WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return float(row["cash_balance"])
            return STARTING_PORTFOLIO_BALANCE

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        available_cash: float | None = None,
    ) -> dict[str, Any]:
        """Calculate allowed trade quantity according to strict 1% risk and capital limits.

        Rules:
            1. Risk framework: Fixed INR 1,000 risk (1% of INR 1,00,000 baseline).
            2. Exact formula: Position Size = (Risk) / (Entry - Stop Loss).
            3. Deployment limit: Maximum INR 1,00,000 per trade, or remaining cash if < 1 Lakh.
            4. Final quantity: min(Risk Quantity, Capital Allowed Quantity).

        Args:
            entry_price (float): Intended entry price (> 0).
            stop_loss (float): Mandatory stop loss price (must be < entry_price for BUY).
            available_cash (float | None): Available cash to consider. Defaults to current balance.

        Returns:
            dict[str, Any]: Calculation breakdown including quantity, capital required,
                            actual risk amount, and constraints applied.

        Raises:
            PositionSizingError: If prices are invalid or stop loss is equal/greater than entry.
        """
        if entry_price <= 0:
            raise PositionSizingError("Entry price must be strictly positive.")
        if stop_loss <= 0:
            raise PositionSizingError("Stop loss must be strictly positive.")
        if stop_loss >= entry_price:
            raise PositionSizingError(
                f"Stop loss ({stop_loss:.2f}) must be strictly less than entry price "
                f"({entry_price:.2f}) for BUY swing trades."
            )

        if available_cash is None:
            available_cash = self.get_cash_balance()

        risk_per_share = entry_price - stop_loss
        raw_risk_quantity = math.floor(BASELINE_RISK_PER_TRADE / risk_per_share)

        # Deployment limit: max 1 Lakh, or whatever cash remains
        max_capital_for_trade = min(MAX_TRADE_ALLOCATION, max(0.0, available_cash))
        max_capital_quantity = (
            math.floor(max_capital_for_trade / entry_price) if entry_price > 0 else 0
        )

        final_quantity = max(0, min(raw_risk_quantity, max_capital_quantity))
        capital_required = final_quantity * entry_price
        actual_risk = final_quantity * risk_per_share

        capped_by = "none"
        if final_quantity == 0:
            capped_by = "insufficient_capital_or_risk"
        elif final_quantity < raw_risk_quantity:
            capped_by = "capital_limit"
        else:
            capped_by = "risk_rule"

        return {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "risk_per_share": risk_per_share,
            "baseline_risk": BASELINE_RISK_PER_TRADE,
            "raw_risk_quantity": raw_risk_quantity,
            "max_capital_for_trade": max_capital_for_trade,
            "max_capital_quantity": max_capital_quantity,
            "allowed_quantity": final_quantity,
            "capital_required": capital_required,
            "actual_risk": actual_risk,
            "available_cash": available_cash,
            "capped_by": capped_by,
        }

    def place_order(
        self,
        ticker: str,
        entry_price: float,
        stop_loss: float,
        sell_target: float | None = None,
        side: str = "BUY",
        override_quantity: int | None = None,
    ) -> dict[str, Any]:
        """Validate, size, and execute an order in the paper trading system.

        Args:
            ticker (str): Security ticker symbol (e.g., 'RELIANCE.NS').
            entry_price (float): Trade execution entry price.
            stop_loss (float): Mandatory stop loss level.
            sell_target (float | None): Optional profit target level.
            side (str): Order side, defaults to 'BUY'.
            override_quantity (int | None): Explicit quantity override if permitted.

        Returns:
            dict[str, Any]: Trade confirmation details.

        Raises:
            PositionSizingError: If order validation fails or cash is insufficient.
        """
        clean_ticker = ticker.split(" ")[0].strip().upper()
        if not clean_ticker:
            raise PositionSizingError("A valid ticker symbol is required.")

        if side != "BUY":
            raise PositionSizingError("Only BUY (long) swing orders are supported on equity stocks.")

        if sell_target is not None and sell_target <= entry_price:
            raise PositionSizingError(
                f"Sell target ({sell_target:.2f}) must be strictly higher than entry price "
                f"({entry_price:.2f}) for BUY trades."
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cash_balance FROM paper_portfolio WHERE id = 1")
            row = cursor.fetchone()
            current_cash = float(row["cash_balance"]) if row else 0.0

            sizing = self.calculate_position_size(
                entry_price=entry_price,
                stop_loss=stop_loss,
                available_cash=current_cash,
            )

            quantity = (
                override_quantity
                if override_quantity is not None
                else sizing["allowed_quantity"]
            )

            if quantity <= 0:
                raise PositionSizingError(
                    "Calculated allowed quantity is 0 shares. Verify price levels and available cash."
                )

            total_cost = quantity * entry_price
            if total_cost > current_cash:
                raise PositionSizingError(
                    f"Insufficient cash balance (INR {current_cash:,.2f}) for required "
                    f"trade cost (INR {total_cost:,.2f})."
                )

            timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                """
                INSERT INTO paper_trades (
                    timestamp, ticker, side, entry_price, current_price,
                    exit_price, quantity, stop_loss, sell_target,
                    status, realized_pnl, exit_timestamp, exit_reason
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, 'OPEN', 0.0, NULL, NULL)
                """,
                (
                    timestamp,
                    clean_ticker,
                    side,
                    entry_price,
                    entry_price,
                    quantity,
                    stop_loss,
                    sell_target,
                ),
            )
            trade_id = cursor.lastrowid

            # Deduct capital deployed from available cash
            new_cash = current_cash - total_cost
            cursor.execute(
                "UPDATE paper_portfolio SET cash_balance = ?, updated_at = ? WHERE id = 1",
                (new_cash, timestamp),
            )
            conn.commit()

        return {
            "trade_id": trade_id,
            "timestamp": timestamp,
            "ticker": clean_ticker,
            "side": side,
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "sell_target": sell_target,
            "total_cost": total_cost,
            "remaining_cash": new_cash,
            "status": "OPEN",
        }

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_reason: str = "MANUAL_EXIT",
    ) -> dict[str, Any]:
        """Close an active paper trade, compute realized PnL, and credit capital.

        Args:
            trade_id (int): Identifier of the trade to close.
            exit_price (float): Final execution exit price.
            exit_reason (str): Reason for closure ('STOP_LOSS', 'SELL_TARGET', 'MANUAL_EXIT').

        Returns:
            dict[str, Any]: Closed trade summary and updated cash balance.

        Raises:
            ValueError: If trade_id is not found or already closed.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,))
            trade = cursor.fetchone()

            if trade is None:
                raise ValueError(f"Trade ID #{trade_id} does not exist.")
            if trade["status"] != "OPEN":
                raise ValueError(f"Trade ID #{trade_id} is already CLOSED.")

            quantity = int(trade["quantity"])
            entry_price = float(trade["entry_price"])
            ticker = str(trade["ticker"])
            side = str(trade["side"])

            # Compute realized PnL
            if side == "BUY":
                realized_pnl = quantity * (exit_price - entry_price)
                capital_returned = quantity * exit_price
            else:
                realized_pnl = quantity * (entry_price - exit_price)
                capital_returned = (quantity * entry_price) + realized_pnl

            exit_timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

            # Update trade record
            cursor.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED',
                    exit_price = ?,
                    current_price = ?,
                    realized_pnl = ?,
                    exit_timestamp = ?,
                    exit_reason = ?
                WHERE trade_id = ?
                """,
                (
                    exit_price,
                    exit_price,
                    realized_pnl,
                    exit_timestamp,
                    exit_reason,
                    trade_id,
                ),
            )

            # Credit capital returned to paper_portfolio
            cursor.execute("SELECT cash_balance FROM paper_portfolio WHERE id = 1")
            current_cash = float(cursor.fetchone()["cash_balance"])
            new_cash = current_cash + capital_returned

            cursor.execute(
                "UPDATE paper_portfolio SET cash_balance = ?, updated_at = ? WHERE id = 1",
                (new_cash, exit_timestamp),
            )
            conn.commit()

        return {
            "trade_id": trade_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "realized_pnl": realized_pnl,
            "return_pct": (
                (exit_price - entry_price) / entry_price * 100.0 if entry_price > 0 else 0.0
            ),
            "exit_timestamp": exit_timestamp,
            "exit_reason": exit_reason,
            "updated_cash": new_cash,
        }

    def update_trade_sl_and_target(
        self,
        trade_id: int,
        stop_loss: float,
        sell_target: float | None = None,
    ) -> dict[str, Any]:
        """Update stop loss and optional profit target for an active open trade.

        Args:
            trade_id (int): Identifier of the active trade.
            stop_loss (float): New stop loss price level (must be strictly positive).
            sell_target (float | None): New sell target price level, or None to clear target.

        Returns:
            dict[str, Any]: Updated trade record information.

        Raises:
            ValueError: If trade does not exist, is closed, or prices violate trading logic.
        """
        if stop_loss <= 0:
            raise ValueError("Stop loss must be strictly positive.")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,))
            trade = cursor.fetchone()

            if trade is None:
                raise ValueError(f"Trade ID #{trade_id} does not exist.")
            if trade["status"] != "OPEN":
                raise ValueError(f"Trade ID #{trade_id} is already CLOSED.")

            curr_price = float(trade["current_price"])
            side = str(trade["side"])

            if side == "BUY":
                if stop_loss >= curr_price:
                    raise ValueError(
                        f"Stop loss (₹{stop_loss:,.2f}) must be strictly below current "
                        f"market price (₹{curr_price:,.2f}) for BUY trade."
                    )
                if sell_target is not None:
                    if sell_target <= curr_price:
                        raise ValueError(
                            f"Sell target (₹{sell_target:,.2f}) must be strictly above current "
                            f"market price (₹{curr_price:,.2f}) for BUY trade."
                        )
                    if sell_target <= stop_loss:
                        raise ValueError(
                            f"Sell target (₹{sell_target:,.2f}) must be strictly greater than "
                            f"stop loss (₹{stop_loss:,.2f})."
                        )

            cursor.execute(
                """
                UPDATE paper_trades
                SET stop_loss = ?, sell_target = ?
                WHERE trade_id = ?
                """,
                (stop_loss, sell_target, trade_id),
            )
            conn.commit()

        return {
            "trade_id": trade_id,
            "ticker": str(trade["ticker"]),
            "stop_loss": stop_loss,
            "sell_target": sell_target,
            "current_price": curr_price,
            "quantity": int(trade["quantity"]),
        }

    def partial_close_trade(
        self,
        trade_id: int,
        sell_quantity: int,
        exit_price: float | None = None,
        exit_reason: str = "PARTIAL_EXIT",
    ) -> dict[str, Any]:
        """Sell a partial quantity of an active open trade, realizing PnL and crediting capital.

        If sell_quantity equals total open quantity, executes a full trade closure.

        Args:
            trade_id (int): Identifier of the trade to partially exit.
            sell_quantity (int): Number of shares to sell (must be >= 1 and <= open quantity).
            exit_price (float | None): Exit execution price (defaults to current_price if None).
            exit_reason (str): Reason for partial exit (defaults to 'PARTIAL_EXIT').

        Returns:
            dict[str, Any]: Summary of partial exit execution and remaining position state.

        Raises:
            ValueError: If trade is invalid, closed, or sell_quantity exceeds open quantity.
        """
        if sell_quantity <= 0:
            raise ValueError("Sell quantity must be strictly greater than 0.")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,))
            trade = cursor.fetchone()

            if trade is None:
                raise ValueError(f"Trade ID #{trade_id} does not exist.")
            if trade["status"] != "OPEN":
                raise ValueError(f"Trade ID #{trade_id} is already CLOSED.")

            open_qty = int(trade["quantity"])
            if sell_quantity > open_qty:
                raise ValueError(
                    f"Requested sell quantity ({sell_quantity}) exceeds available "
                    f"position quantity ({open_qty}) for Trade #{trade_id}."
                )

        # If selling the entire remaining quantity, delegate to full close_trade
        if sell_quantity == open_qty:
            resolved_exit = (
                exit_price
                if exit_price is not None and exit_price > 0
                else float(trade["current_price"])
            )
            return self.close_trade(
                trade_id=trade_id,
                exit_price=resolved_exit,
                exit_reason=exit_reason,
            )

        # Otherwise perform partial sale
        with self._get_connection() as conn:
            cursor = conn.cursor()
            entry_price = float(trade["entry_price"])
            ticker = str(trade["ticker"])
            side = str(trade["side"])
            stop_loss = float(trade["stop_loss"])
            sell_target = (
                float(trade["sell_target"]) if trade["sell_target"] is not None else None
            )

            resolved_exit = (
                exit_price
                if exit_price is not None and exit_price > 0
                else float(trade["current_price"])
            )

            if side == "BUY":
                realized_pnl = sell_quantity * (resolved_exit - entry_price)
                capital_returned = sell_quantity * resolved_exit
            else:
                realized_pnl = sell_quantity * (entry_price - resolved_exit)
                capital_returned = (sell_quantity * entry_price) + realized_pnl

            remaining_qty = open_qty - sell_quantity
            exit_timestamp = (
                datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            )
            formatted_reason = f"{exit_reason} (Trade #{trade_id})"

            # 1. Insert closed tranche into journal
            cursor.execute(
                """
                INSERT INTO paper_trades (
                    timestamp, ticker, side, entry_price, current_price,
                    exit_price, quantity, stop_loss, sell_target,
                    status, realized_pnl, exit_timestamp, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CLOSED', ?, ?, ?)
                """,
                (
                    trade["timestamp"],
                    ticker,
                    side,
                    entry_price,
                    resolved_exit,
                    resolved_exit,
                    sell_quantity,
                    stop_loss,
                    sell_target,
                    realized_pnl,
                    exit_timestamp,
                    formatted_reason,
                ),
            )
            closed_trade_id = cursor.lastrowid

            # 2. Update remaining active trade
            cursor.execute(
                """
                UPDATE paper_trades
                SET quantity = ?, current_price = ?
                WHERE trade_id = ?
                """,
                (remaining_qty, resolved_exit, trade_id),
            )

            # 3. Credit capital returned to available cash balance
            cursor.execute("SELECT cash_balance FROM paper_portfolio WHERE id = 1")
            current_cash = float(cursor.fetchone()["cash_balance"])
            new_cash = current_cash + capital_returned

            cursor.execute(
                "UPDATE paper_portfolio SET cash_balance = ?, updated_at = ? WHERE id = 1",
                (new_cash, exit_timestamp),
            )
            conn.commit()

        return {
            "trade_id": trade_id,
            "closed_trade_id": closed_trade_id,
            "ticker": ticker,
            "side": side,
            "sold_quantity": sell_quantity,
            "remaining_quantity": remaining_qty,
            "entry_price": entry_price,
            "exit_price": resolved_exit,
            "realized_pnl": realized_pnl,
            "return_pct": (
                (resolved_exit - entry_price) / entry_price * 100.0 if entry_price > 0 else 0.0
            ),
            "capital_returned": capital_returned,
            "exit_timestamp": exit_timestamp,
            "exit_reason": formatted_reason,
            "updated_cash": new_cash,
        }

    def evaluate_open_trades(self, price_map: dict[str, float]) -> list[dict[str, Any]]:
        """Evaluate all open trades against the latest market prices for exit triggers.

        Triggers automatic closure if:
        1. Current price <= stop_loss (for BUY)
        2. Current price >= sell_target (for BUY with target specified)

        Args:
            price_map (dict[str, float]): Dictionary mapping ticker to current market price.

        Returns:
            list[dict[str, Any]]: List of trade exit reports executed during this evaluation.
        """
        closed_reports: list[dict[str, Any]] = []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_trades WHERE status = 'OPEN'")
            open_trades = cursor.fetchall()

        for trade in open_trades:
            ticker = trade["ticker"]
            if ticker not in price_map:
                continue

            current_price = price_map[ticker]
            if current_price <= 0:
                continue

            trade_id = trade["trade_id"]
            stop_loss = float(trade["stop_loss"])
            sell_target = (
                float(trade["sell_target"]) if trade["sell_target"] is not None else None
            )

            # Check stop loss hit
            if current_price <= stop_loss:
                report = self.close_trade(
                    trade_id=trade_id,
                    exit_price=current_price,
                    exit_reason="STOP_LOSS",
                )
                closed_reports.append(report)
            # Check target hit
            elif sell_target is not None and current_price >= sell_target:
                report = self.close_trade(
                    trade_id=trade_id,
                    exit_price=current_price,
                    exit_reason="SELL_TARGET",
                )
                closed_reports.append(report)
            else:
                # Update current price in DB for open trade
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE paper_trades SET current_price = ? WHERE trade_id = ?",
                        (current_price, trade_id),
                    )
                    conn.commit()

        return closed_reports

    def get_open_trades(self) -> list[dict[str, Any]]:
        """Retrieve all currently active open trades.

        Returns:
            list[dict[str, Any]]: List of active trade dictionaries.
        """
        query = "SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY trade_id DESC"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                item = dict(row)
                qty = item["quantity"]
                entry = item["entry_price"]
                curr = item["current_price"]
                item["invested_value"] = qty * entry
                item["current_value"] = qty * curr
                item["unrealized_pnl"] = qty * (curr - entry)
                item["pnl_pct"] = (
                    ((curr - entry) / entry * 100.0) if entry > 0 else 0.0
                )
                trades.append(item)
            return trades

    def get_trade_history(self) -> list[dict[str, Any]]:
        """Retrieve all closed historical trades.

        Returns:
            list[dict[str, Any]]: List of closed trade dictionaries.
        """
        query = "SELECT * FROM paper_trades WHERE status = 'CLOSED' ORDER BY trade_id DESC"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            history = []
            for row in rows:
                item = dict(row)
                entry = item["entry_price"]
                exit_p = item["exit_price"] or entry
                item["return_pct"] = (
                    ((exit_p - entry) / entry * 100.0) if entry > 0 else 0.0
                )
                history.append(item)
            return history

    def get_portfolio_summary(self) -> dict[str, float]:
        """Compute portfolio balance, open positions value, and total net worth.

        Returns:
            dict[str, float]: Summary metrics:
                - cash_balance: Unallocated liquid cash.
                - open_positions_value: Current market value of active trades.
                - open_unrealized_pnl: Floating profit/loss on active trades.
                - total_realized_pnl: Accumulated realized profit/loss on closed trades.
                - total_portfolio_value: Cash + open positions value.
                - initial_capital: Starting seed balance (5 Lakhs).
        """
        cash = self.get_cash_balance()
        open_trades = self.get_open_trades()

        open_positions_value = sum(t["current_value"] for t in open_trades)
        open_unrealized_pnl = sum(t["unrealized_pnl"] for t in open_trades)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(realized_pnl), 0.0) as total_pnl FROM paper_trades WHERE status = 'CLOSED'"
            )
            realized_row = cursor.fetchone()
            total_realized_pnl = float(realized_row["total_pnl"]) if realized_row else 0.0

            cursor.execute("SELECT initial_capital FROM paper_portfolio WHERE id = 1")
            init_row = cursor.fetchone()
            initial_capital = (
                float(init_row["initial_capital"]) if init_row else STARTING_PORTFOLIO_BALANCE
            )

        total_portfolio_value = cash + open_positions_value

        return {
            "cash_balance": cash,
            "open_positions_value": open_positions_value,
            "open_unrealized_pnl": open_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "total_portfolio_value": total_portfolio_value,
            "initial_capital": initial_capital,
            "total_pnl": (total_portfolio_value - initial_capital),
            "total_return_pct": (
                ((total_portfolio_value - initial_capital) / initial_capital * 100.0)
                if initial_capital > 0
                else 0.0
            ),
            "open_count": len(open_trades),
        }

    def reset_portfolio(self, starting_cash: float = STARTING_PORTFOLIO_BALANCE) -> None:
        """Reset virtual portfolio to initial starting balance and clear paper trades.

        Args:
            starting_cash (float): Virtual cash balance to reset to. Defaults to 5,00,000.
        """
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM paper_trades")
            cursor.execute(
                """
                UPDATE paper_portfolio
                SET cash_balance = ?, initial_capital = ?, updated_at = ?
                WHERE id = 1
                """,
                (starting_cash, starting_cash, now),
            )
            conn.commit()

    def get_nifty50_tickers(self) -> list[dict[str, str]]:
        """Fetch list of active Nifty 50 equity stock symbols and company names from database.

        Returns:
            list[dict[str, str]]: List of dicts with 'ticker' and 'name'.
        """
        query = """
            SELECT ticker, name
            FROM securities
            WHERE asset_type = 'STOCK'
            ORDER BY ticker ASC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [{"ticker": row["ticker"], "name": row["name"]} for row in cursor.fetchall()]
        except sqlite3.Error as err:
            print(f"Error fetching Nifty 50 stocks: {err}")
            return []

    @staticmethod
    def fetch_live_quote(ticker: str) -> float | None:
        """Fetch the latest price for a single ticker via yfinance.

        Args:
            ticker (str): Ticker symbol (e.g. 'RELIANCE.NS').

        Returns:
            float | None: Latest market price or None if unavailable.
        """
        clean_ticker = ticker.split(" ")[0].strip().upper()
        try:
            t = yf.Ticker(clean_ticker)
            fast_price = getattr(t.fast_info, "last_price", None)
            if fast_price is not None and not math.isnan(fast_price) and fast_price > 0:
                return float(fast_price)

            hist = t.history(period="1d")
            if not hist.empty and "Close" in hist.columns:
                last_close = hist["Close"].iloc[-1]
                if not pd.isna(last_close) and last_close > 0:
                    return float(last_close)
        except (ValueError, KeyError, IndexError, AttributeError) as err:
            print(f"Live quote fetch error for {clean_ticker}: {err}")
        return None

    @staticmethod
    def fetch_live_quotes_batch(tickers: list[str]) -> dict[str, float]:
        """Fetch latest quotes for multiple tickers efficiently.

        Args:
            tickers (list[str]): List of ticker symbols.

        Returns:
            dict[str, float]: Mapping from ticker to current market price.
        """
        if not tickers:
            return {}

        unique_tickers = list({t.split(" ")[0].strip().upper() for t in tickers if t})
        price_map: dict[str, float] = {}

        # First attempt fast_info loop (very fast in modern yfinance)
        missing: list[str] = []
        for sym in unique_tickers:
            try:
                t = yf.Ticker(sym)
                p = getattr(t.fast_info, "last_price", None)
                if p is not None and not math.isnan(p) and p > 0:
                    price_map[sym] = float(p)
                else:
                    missing.append(sym)
            except (ValueError, KeyError, AttributeError):
                missing.append(sym)

        # Batch download fallback for any remaining missing tickers
        if missing:
            try:
                batch_df = yf.download(missing, period="1d", progress=False)
                if not batch_df.empty and "Close" in batch_df.columns:
                    close_data = batch_df["Close"]
                    if isinstance(close_data, pd.DataFrame):
                        for sym in missing:
                            if sym in close_data.columns:
                                val = close_data[sym].dropna().iloc[-1]
                                if not pd.isna(val) and val > 0:
                                    price_map[sym] = float(val)
                    elif isinstance(close_data, pd.Series) and len(missing) == 1:
                        val = close_data.dropna().iloc[-1]
                        if not pd.isna(val) and val > 0:
                            price_map[missing[0]] = float(val)
            except (ValueError, KeyError, IndexError) as err:
                print(f"Batch quote download error: {err}")

        return price_map
