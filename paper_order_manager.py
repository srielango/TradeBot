"""Paper trading order manager module for TradeBot.

Handles queued, pending, and limit orders for paper trading:
1. Supports placing orders with a specific buy price (limit order: buy on or below price).
2. Supports market orders where buy price defaults to Current Market Price (CMP) or is left blank.
3. Automatically queues orders placed outside the trading window (pre-market, post-market, weekend),
   waiting until the NSE opens.
4. When NSE opens:
   - If the order has no buy price: executes at the opening CMP.
   - If the order has a buy price: executes only if the CMP is <= the buy price.
5. Manages order cancellation and database lifecycle for the 'paper_orders' table.
"""

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DB_PATH, is_market_open_ist


class PaperOrderManager:
    """Manages order placement, pending queues, and limit trigger evaluations."""

    def __init__(self, engine: Any, db_path: str | Path = DB_PATH):
        """Initialize order manager with paper trading engine and database.

        Args:
            engine (Any): PaperTradingEngine instance.
            db_path (str | Path): SQLite database path. Defaults to DB_PATH.
        """
        self.engine = engine
        self.db_path = str(os.path.abspath(db_path))
        self.init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection with row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        """Create paper_orders table and indexes if not already present."""
        create_orders_table = """
        CREATE TABLE IF NOT EXISTS paper_orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            order_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT CHECK(side IN ('BUY', 'SELL')) NOT NULL DEFAULT 'BUY',
            buy_price REAL,
            stop_loss REAL NOT NULL,
            sell_target REAL,
            requested_quantity INTEGER NOT NULL,
            status TEXT CHECK(status IN ('PENDING', 'EXECUTED', 'CANCELLED', 'REJECTED'))
                NOT NULL DEFAULT 'PENDING',
            status_reason TEXT,
            executed_price REAL,
            executed_quantity INTEGER,
            executed_at TEXT,
            executed_trade_id INTEGER,
            FOREIGN KEY(executed_trade_id) REFERENCES paper_trades(trade_id)
        );
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_orders_table)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status);"
            )
            conn.commit()

    def submit_order(
        self,
        ticker: str,
        buy_price: float | None = None,
        stop_loss: float = 0.0,
        sell_target: float | None = None,
        side: str = "BUY",
        override_quantity: int | None = None,
        current_cmp: float | None = None,
        market_open_override: bool | None = None,
    ) -> dict[str, Any]:
        """Submit a paper trade order, executing immediately or queueing as pending.

        Rules:
        - If outside NSE trading window: queue as PENDING until NSE opens.
        - If inside NSE trading window:
          - If no buy_price is entered: execute immediately at CMP.
          - If buy_price is entered: execute only if CMP <= buy_price; otherwise queue as PENDING.

        Args:
            ticker (str): Security ticker symbol (e.g. 'RELIANCE.NS').
            buy_price (float | None): Target limit price (buy on or below), or None for CMP.
            stop_loss (float): Mandatory stop loss price level.
            sell_target (float | None): Optional profit target level.
            side (str): Order side ('BUY'). Defaults to 'BUY'.
            override_quantity (int | None): Explicit quantity override if specified.
            current_cmp (float | None): Known current market price if already fetched.
            market_open_override (bool | None): Explicit flag for testing or simulation.

        Returns:
            dict[str, Any]: Order submission outcome details including status and trade_id.

        Raises:
            ValueError: If ticker or pricing parameters violate risk rules.
        """
        clean_ticker = ticker.split(" ")[0].strip().upper()
        if not clean_ticker:
            raise ValueError("A valid ticker symbol is required.")

        if side != "BUY":
            raise ValueError("Only BUY swing orders are supported on equity stocks.")

        # Fetch live CMP if not supplied
        if current_cmp is None or current_cmp <= 0:
            current_cmp = self.engine.fetch_live_quote(clean_ticker)

        # Determine effective entry price for position sizing calculations
        if buy_price is not None and buy_price > 0:
            effective_entry = float(buy_price)
        elif current_cmp is not None and current_cmp > 0:
            effective_entry = float(current_cmp)
        else:
            raise ValueError(
                f"Unable to determine price for {clean_ticker}. "
                "Please enter a buy price or check network connection."
            )

        # Validate stop loss and profit target levels
        if stop_loss <= 0:
            raise ValueError("Stop loss must be strictly positive.")
        if stop_loss >= effective_entry:
            raise ValueError(
                f"Stop loss (INR {stop_loss:,.2f}) must be strictly below entry/buy price "
                f"(INR {effective_entry:,.2f}) for BUY trades."
            )
        if sell_target is not None and sell_target <= effective_entry:
            raise ValueError(
                f"Sell target (INR {sell_target:,.2f}) must be strictly above entry/buy price "
                f"(INR {effective_entry:,.2f}) for BUY trades."
            )

        # Compute position sizing based on 1% risk framework
        current_cash = self.engine.get_cash_balance()
        sizing = self.engine.calculate_position_size(
            entry_price=effective_entry,
            stop_loss=stop_loss,
            available_cash=current_cash,
        )
        quantity = (
            override_quantity
            if override_quantity is not None
            else sizing["allowed_quantity"]
        )
        if quantity <= 0:
            raise ValueError(
                "Calculated allowed quantity is 0 shares. Verify price levels and available cash."
            )

        # Check market operating window
        if market_open_override is not None:
            is_open = market_open_override
            desc = "Market Open (Override)" if is_open else "Market Closed (Override)"
        else:
            is_open, desc = is_market_open_ist()

        now_dt = datetime.now(timezone.utc).astimezone()
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        today_date = now_dt.strftime("%Y-%m-%d")

        # Scenario 1: Outside trading window -> Wait until NSE opens
        if not is_open:
            reason = (
                f"Outside trading window ({desc}) - Waiting for NSE open at 09:15 AM IST"
            )
            order_id = self._insert_order(
                created_at=now_ts,
                order_date=today_date,
                ticker=clean_ticker,
                side=side,
                buy_price=buy_price,
                stop_loss=stop_loss,
                sell_target=sell_target,
                requested_quantity=quantity,
                status="PENDING",
                status_reason=reason,
            )
            return {
                "order_id": order_id,
                "status": "PENDING",
                "ticker": clean_ticker,
                "side": side,
                "buy_price": buy_price,
                "stop_loss": stop_loss,
                "sell_target": sell_target,
                "quantity": quantity,
                "estimated_capital": quantity * effective_entry,
                "status_reason": reason,
                "created_at": now_ts,
                "trade_id": None,
            }

        # Scenario 2: Inside trading window
        # If CMP is unavailable or invalid, queue as PENDING
        if current_cmp is None or current_cmp <= 0:
            reason = "Waiting for live market quote confirmation"
            order_id = self._insert_order(
                created_at=now_ts,
                order_date=today_date,
                ticker=clean_ticker,
                side=side,
                buy_price=buy_price,
                stop_loss=stop_loss,
                sell_target=sell_target,
                requested_quantity=quantity,
                status="PENDING",
                status_reason=reason,
            )
            return {
                "order_id": order_id,
                "status": "PENDING",
                "ticker": clean_ticker,
                "side": side,
                "buy_price": buy_price,
                "stop_loss": stop_loss,
                "sell_target": sell_target,
                "quantity": quantity,
                "estimated_capital": quantity * effective_entry,
                "status_reason": reason,
                "created_at": now_ts,
                "trade_id": None,
            }

        # Sub-scenario 2A: Order has a buy price (limit order)
        if buy_price is not None:
            if current_cmp <= buy_price:
                # Limit condition met: execute immediately at current CMP
                trade = self.engine.place_order(
                    ticker=clean_ticker,
                    entry_price=current_cmp,
                    stop_loss=stop_loss,
                    sell_target=sell_target,
                    side=side,
                    override_quantity=quantity,
                )
                exec_reason = (
                    f"Executed at CMP INR {current_cmp:,.2f} (<= Limit INR {buy_price:,.2f})"
                )
                order_id = self._insert_order(
                    created_at=now_ts,
                    order_date=today_date,
                    ticker=clean_ticker,
                    side=side,
                    buy_price=buy_price,
                    stop_loss=stop_loss,
                    sell_target=sell_target,
                    requested_quantity=quantity,
                    status="EXECUTED",
                    status_reason=exec_reason,
                    executed_price=current_cmp,
                    executed_quantity=trade["quantity"],
                    executed_at=now_ts,
                    executed_trade_id=trade["trade_id"],
                )
                return {
                    "order_id": order_id,
                    "status": "EXECUTED",
                    "trade_id": trade["trade_id"],
                    "ticker": clean_ticker,
                    "entry_price": current_cmp,
                    "quantity": trade["quantity"],
                    "total_cost": trade["total_cost"],
                    "stop_loss": stop_loss,
                    "sell_target": sell_target,
                    "status_reason": exec_reason,
                }
            else:
                # CMP > buy_price: Queue as PENDING waiting for CMP to drop on/below limit
                reason = (
                    f"Waiting for CMP (INR {current_cmp:,.2f}) <= Buy Price (INR {buy_price:,.2f})"
                )
                order_id = self._insert_order(
                    created_at=now_ts,
                    order_date=today_date,
                    ticker=clean_ticker,
                    side=side,
                    buy_price=buy_price,
                    stop_loss=stop_loss,
                    sell_target=sell_target,
                    requested_quantity=quantity,
                    status="PENDING",
                    status_reason=reason,
                )
                return {
                    "order_id": order_id,
                    "status": "PENDING",
                    "ticker": clean_ticker,
                    "side": side,
                    "buy_price": buy_price,
                    "stop_loss": stop_loss,
                    "sell_target": sell_target,
                    "quantity": quantity,
                    "estimated_capital": quantity * effective_entry,
                    "status_reason": reason,
                    "created_at": now_ts,
                    "trade_id": None,
                }

        # Sub-scenario 2B: Order doesn't have a buy price (market order) -> use CMP
        trade = self.engine.place_order(
            ticker=clean_ticker,
            entry_price=current_cmp,
            stop_loss=stop_loss,
            sell_target=sell_target,
            side=side,
            override_quantity=quantity,
        )
        exec_reason = f"Executed at CMP INR {current_cmp:,.2f} (Market Order)"
        order_id = self._insert_order(
            created_at=now_ts,
            order_date=today_date,
            ticker=clean_ticker,
            side=side,
            buy_price=None,
            stop_loss=stop_loss,
            sell_target=sell_target,
            requested_quantity=quantity,
            status="EXECUTED",
            status_reason=exec_reason,
            executed_price=current_cmp,
            executed_quantity=trade["quantity"],
            executed_at=now_ts,
            executed_trade_id=trade["trade_id"],
        )
        return {
            "order_id": order_id,
            "status": "EXECUTED",
            "trade_id": trade["trade_id"],
            "ticker": clean_ticker,
            "entry_price": current_cmp,
            "quantity": trade["quantity"],
            "total_cost": trade["total_cost"],
            "stop_loss": stop_loss,
            "sell_target": sell_target,
            "status_reason": exec_reason,
        }

    def process_pending_orders(
        self,
        price_map: dict[str, float] | None = None,
        market_open_override: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate pending orders and execute any meeting market hours and price limits.

        Args:
            price_map (dict[str, float] | None): Dictionary mapping ticker to live CMP.
            market_open_override (bool | None): Explicit market open flag for simulation.

        Returns:
            list[dict[str, Any]]: List of executed order trade confirmations.
        """
        # 1. Market operating window check
        if market_open_override is not None:
            is_open = market_open_override
            desc = "Market Open (Override)" if is_open else "Market Closed (Override)"
        else:
            is_open, desc = is_market_open_ist()

        if not is_open:
            # Market is still closed; update status description and return
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE paper_orders SET status_reason = ? WHERE status = 'PENDING'",
                    (f"Waiting for NSE market open ({desc})",),
                )
                conn.commit()
            return []

        # 2. Retrieve pending orders
        pending_orders = self.get_pending_orders()
        if not pending_orders:
            return []

        tickers = list({o["ticker"] for o in pending_orders})
        if price_map is None:
            price_map = self.engine.fetch_live_quotes_batch(tickers)

        executed_reports: list[dict[str, Any]] = []
        now_dt = datetime.now(timezone.utc).astimezone()
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        for order in pending_orders:
            order_id = int(order["order_id"])
            ticker = str(order["ticker"])
            cmp = price_map.get(ticker)
            if cmp is None or cmp <= 0:
                cmp = self.engine.fetch_live_quote(ticker)
            if cmp is None or cmp <= 0:
                continue

            buy_price = (
                float(order["buy_price"]) if order["buy_price"] is not None else None
            )
            should_execute = False

            if buy_price is None:
                # Order doesn't have a buy price -> "use the CMP"
                should_execute = True
            else:
                # Order has a buy price -> "place the order only if the CMP is <= the buy price"
                if cmp <= buy_price:
                    should_execute = True
                else:
                    reason = (
                        f"Waiting for CMP (INR {cmp:,.2f}) <= Buy Price (INR {buy_price:,.2f})"
                    )
                    self._update_order_reason(order_id, reason)

            if not should_execute:
                continue

            # Verify Stop Loss safety
            sl = float(order["stop_loss"])
            if cmp <= sl:
                # Protect trader: Do not enter if CMP gapped down on/below Stop Loss
                rej_msg = (
                    f"Rejected: CMP (INR {cmp:,.2f}) opened at or below Stop Loss (INR {sl:,.2f})"
                )
                self._set_order_status(order_id, "REJECTED", rej_msg)
                continue

            # Calculate allowed quantity at actual execution CMP
            avail_cash = self.engine.get_cash_balance()
            try:
                sizing = self.engine.calculate_position_size(
                    entry_price=cmp,
                    stop_loss=sl,
                    available_cash=avail_cash,
                )
                allowed_qty = sizing["allowed_quantity"]
            except Exception as err:
                self._set_order_status(
                    order_id, "REJECTED", f"Position sizing calculation failed: {err}"
                )
                continue

            requested_qty = int(order["requested_quantity"])
            final_qty = min(requested_qty, allowed_qty)

            # Ensure cash is adequate for at least 1 share
            if final_qty * cmp > avail_cash:
                final_qty = math.floor(avail_cash / cmp)

            if final_qty <= 0:
                self._set_order_status(
                    order_id, "REJECTED", "Insufficient cash balance at market execution"
                )
                continue

            # Execute the order in paper trading engine
            try:
                trade = self.engine.place_order(
                    ticker=ticker,
                    entry_price=cmp,
                    stop_loss=sl,
                    sell_target=order.get("sell_target"),
                    side=order.get("side", "BUY"),
                    override_quantity=final_qty,
                )
                success_reason = (
                    f"Executed at CMP INR {cmp:,.2f}"
                    + (
                        f" (<= Limit INR {buy_price:,.2f})"
                        if buy_price is not None
                        else " (Market Order)"
                    )
                )
                self._mark_order_executed(
                    order_id=order_id,
                    trade_id=trade["trade_id"],
                    executed_price=cmp,
                    executed_qty=final_qty,
                    executed_at=now_ts,
                    reason=success_reason,
                )
                executed_reports.append(
                    {
                        "order_id": order_id,
                        "trade_id": trade["trade_id"],
                        "ticker": ticker,
                        "entry_price": cmp,
                        "quantity": final_qty,
                        "total_cost": trade["total_cost"],
                        "buy_price": buy_price,
                        "stop_loss": sl,
                        "sell_target": order.get("sell_target"),
                        "status_reason": success_reason,
                    }
                )
            except Exception as exc:
                self._set_order_status(order_id, "REJECTED", f"Execution error: {exc}")

        return executed_reports

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending order before execution.

        Args:
            order_id (int): Order identifier to cancel.

        Returns:
            bool: True if order was successfully cancelled, False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM paper_orders WHERE order_id = ?", (order_id,)
            )
            row = cursor.fetchone()
            if not row or row["status"] != "PENDING":
                return False

            cursor.execute(
                """
                UPDATE paper_orders
                SET status = 'CANCELLED', status_reason = 'Cancelled by trader'
                WHERE order_id = ?
                """,
                (order_id,),
            )
            conn.commit()
            return True

    def get_pending_orders(self) -> list[dict[str, Any]]:
        """Retrieve all currently pending orders awaiting market open or limit trigger.

        Returns:
            list[dict[str, Any]]: List of pending order dictionaries.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM paper_orders WHERE status = 'PENDING' ORDER BY order_id ASC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_orders(self) -> list[dict[str, Any]]:
        """Retrieve complete order book history across all statuses.

        Returns:
            list[dict[str, Any]]: List of order records ordered by most recent.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_orders ORDER BY order_id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def reset_orders(self) -> None:
        """Clear all order records from database upon portfolio reset."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM paper_orders")
            conn.commit()

    def _insert_order(
        self,
        created_at: str,
        order_date: str,
        ticker: str,
        side: str,
        buy_price: float | None,
        stop_loss: float,
        sell_target: float | None,
        requested_quantity: int,
        status: str,
        status_reason: str,
        executed_price: float | None = None,
        executed_quantity: int | None = None,
        executed_at: str | None = None,
        executed_trade_id: int | None = None,
    ) -> int:
        """Insert a new order entry into the database table."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO paper_orders (
                    created_at, order_date, ticker, side, buy_price, stop_loss,
                    sell_target, requested_quantity, status, status_reason,
                    executed_price, executed_quantity, executed_at, executed_trade_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    order_date,
                    ticker,
                    side,
                    buy_price,
                    stop_loss,
                    sell_target,
                    requested_quantity,
                    status,
                    status_reason,
                    executed_price,
                    executed_quantity,
                    executed_at,
                    executed_trade_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def _update_order_reason(self, order_id: int, reason: str) -> None:
        """Update status reason text for an active order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE paper_orders SET status_reason = ? WHERE order_id = ?",
                (reason, order_id),
            )
            conn.commit()

    def _set_order_status(self, order_id: int, status: str, reason: str) -> None:
        """Update status and reason for an order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE paper_orders SET status = ?, status_reason = ? WHERE order_id = ?",
                (status, reason, order_id),
            )
            conn.commit()

    def _mark_order_executed(
        self,
        order_id: int,
        trade_id: int,
        executed_price: float,
        executed_qty: int,
        executed_at: str,
        reason: str,
    ) -> None:
        """Mark an order as successfully executed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE paper_orders
                SET status = 'EXECUTED',
                    executed_trade_id = ?,
                    executed_price = ?,
                    executed_quantity = ?,
                    executed_at = ?,
                    status_reason = ?
                WHERE order_id = ?
                """,
                (
                    trade_id,
                    executed_price,
                    executed_qty,
                    executed_at,
                    reason,
                    order_id,
                ),
            )
            conn.commit()
