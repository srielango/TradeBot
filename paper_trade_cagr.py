"""Paper trade CAGR and performance evaluation module.

Calculates holding periods, annualized returns, and Compound Annual Growth Rate
(CAGR) for individual paper trades and the overall virtual portfolio in TradeBot.
"""

from datetime import date, datetime, timezone
from typing import Any

from paper_trading_engine import PaperTradingEngine


def calculate_trade_cagr(
    entry_price: float,
    exit_price: float,
    entry_date: str,
    exit_date: str | None = None,
    min_days: float = 1.0,
) -> dict[str, Any]:
    """Calculate the holding duration and Compound Annual Growth Rate (CAGR) for a trade.

    Formula:
        Holding Days = max(0, (Exit Date - Entry Date).days)
        Duration in Years = max(Holding Days, min_days) / 365.25
        CAGR = (Exit Price / Entry Price) ** (1.0 / Duration in Years) - 1.0

    Args:
        entry_price (float): Buy execution entry price (> 0).
        exit_price (float): Exit or current market price.
        entry_date (str): Entry date formatted as 'YYYY-MM-DD'.
        exit_date (str | None): Exit date formatted as 'YYYY-MM-DD'. Defaults to today.
        min_days (float): Minimum days floor to avoid zero division and extreme annualized values
            for intraday executions. Defaults to 1.0.

    Returns:
        dict[str, Any]: Dictionary containing:
            - entry_date: Sanitized entry date string.
            - exit_date: Sanitized exit date string.
            - holding_days: Exact calendar days between entry and exit.
            - duration_years: Duration expressed in fractional years.
            - return_pct: Absolute percentage price change.
            - cagr: Fractional CAGR (e.g. 0.15 for 15%).
            - cagr_pct: Percentage CAGR (e.g. 15.0%).
    """
    if entry_price <= 0:
        return {
            "entry_date": entry_date,
            "exit_date": exit_date or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"),
            "holding_days": 0,
            "duration_years": 0.0,
            "return_pct": 0.0,
            "cagr": 0.0,
            "cagr_pct": 0.0,
        }

    # Resolve date strings to date objects
    today_dt = datetime.now(timezone.utc).astimezone().date()
    try:
        e_date = date.fromisoformat(str(entry_date)[:10])
    except (ValueError, TypeError):
        e_date = today_dt

    if exit_date:
        try:
            x_date = date.fromisoformat(str(exit_date)[:10])
        except (ValueError, TypeError):
            x_date = today_dt
    else:
        x_date = today_dt

    holding_days = max(0, (x_date - e_date).days)
    effective_days = max(float(holding_days), float(min_days))
    duration_years = effective_days / 365.25

    abs_return = (exit_price - entry_price) / entry_price
    return_pct = abs_return * 100.0

    if exit_price <= 0:
        cagr = -1.0
    elif duration_years <= 0:
        cagr = abs_return
    else:
        try:
            cagr = (exit_price / entry_price) ** (1.0 / duration_years) - 1.0
        except (ZeroDivisionError, OverflowError):
            cagr = abs_return

    cagr_pct = cagr * 100.0

    return {
        "entry_date": e_date.strftime("%Y-%m-%d"),
        "exit_date": x_date.strftime("%Y-%m-%d"),
        "holding_days": holding_days,
        "duration_years": round(duration_years, 4),
        "return_pct": round(return_pct, 2),
        "cagr": round(cagr, 4),
        "cagr_pct": round(cagr_pct, 2),
    }


def calculate_portfolio_cagr(
    engine: PaperTradingEngine | None = None,
) -> dict[str, Any]:
    """Calculate comprehensive performance metrics and overall portfolio CAGR.

    Assesses the virtual portfolio from its initial seed capital and inception date
    to the current total net portfolio value (cash balance + open positions value).

    Args:
        engine (PaperTradingEngine | None): Engine instance. Creates new instance if None.

    Returns:
        dict[str, Any]: Detailed performance breakdown including:
            - initial_capital: Seed capital in INR.
            - cash_balance: Liquid unallocated cash in INR.
            - open_positions_value: Market value of active trades.
            - total_portfolio_value: Net worth (cash + open positions).
            - net_profit_loss: Overall profit or loss in INR.
            - total_return_pct: Percentage gain on initial capital.
            - portfolio_inception_date: Earliest trade or portfolio date.
            - evaluation_date: Today's date.
            - portfolio_duration_days: Days since portfolio inception.
            - portfolio_duration_years: Inception duration in fractional years.
            - portfolio_cagr_pct: Annualized growth rate of the portfolio.
            - open_trades: List of active trades with individual CAGR metrics.
            - closed_trades: List of closed trades with individual CAGR metrics.
    """
    if engine is None:
        engine = PaperTradingEngine()

    summary = engine.get_portfolio_summary()
    initial_cap = float(summary.get("initial_capital", 500_000.0))
    cash = float(summary.get("cash_balance", 500_000.0))
    open_val = float(summary.get("open_positions_value", 0.0))
    total_worth = float(summary.get("total_portfolio_value", initial_cap))
    realized_pnl = float(summary.get("total_realized_pnl", 0.0))
    unrealized_pnl = float(summary.get("open_unrealized_pnl", 0.0))
    net_pnl = (total_worth - initial_cap)
    total_return_pct = (net_pnl / initial_cap * 100.0) if initial_cap > 0 else 0.0

    today_dt = datetime.now(timezone.utc).astimezone().date()
    today_str = today_dt.strftime("%Y-%m-%d")

    # Determine earliest inception date from database
    inception_date: date = today_dt
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MIN(entry_date) as min_entry
            FROM paper_trades
            WHERE entry_date IS NOT NULL AND entry_date != ''
            """
        )
        row = cursor.fetchone()
        if row and row["min_entry"]:
            try:
                inception_date = date.fromisoformat(str(row["min_entry"])[:10])
            except (ValueError, TypeError):
                inception_date = today_dt

        # Fallback to portfolio updated_at if no trade date found
        cursor.execute("SELECT updated_at FROM paper_portfolio WHERE id = 1")
        p_row = cursor.fetchone()
        if p_row and p_row["updated_at"]:
            try:
                p_date = date.fromisoformat(str(p_row["updated_at"])[:10])
                inception_date = min(inception_date, p_date)
            except (ValueError, TypeError):
                pass

    portfolio_days = max(0, (today_dt - inception_date).days)
    effective_portfolio_days = max(float(portfolio_days), 1.0)
    portfolio_years = effective_portfolio_days / 365.25

    if total_worth <= 0:
        port_cagr = -1.0
    else:
        try:
            port_cagr = (total_worth / initial_cap) ** (1.0 / portfolio_years) - 1.0
        except (ZeroDivisionError, OverflowError):
            port_cagr = net_pnl / initial_cap if initial_cap > 0 else 0.0

    portfolio_cagr_pct = port_cagr * 100.0

    # Enrich open trades with trade-level CAGR
    open_trades = engine.get_open_trades()
    for trade in open_trades:
        e_price = float(trade["entry_price"])
        c_price = float(trade["current_price"])
        e_date = trade.get("entry_date") or today_str
        cagr_info = calculate_trade_cagr(
            entry_price=e_price,
            exit_price=c_price,
            entry_date=e_date,
            exit_date=today_str,
        )
        trade["trade_cagr_pct"] = cagr_info["cagr_pct"]
        trade["holding_days"] = cagr_info["holding_days"]

    # Enrich closed trades with trade-level CAGR
    closed_trades = engine.get_trade_history()
    for trade in closed_trades:
        e_price = float(trade["entry_price"])
        x_price = float(trade.get("exit_price") or e_price)
        e_date = trade.get("entry_date") or today_str
        x_date = trade.get("exit_date") or today_str
        cagr_info = calculate_trade_cagr(
            entry_price=e_price,
            exit_price=x_price,
            entry_date=e_date,
            exit_date=x_date,
        )
        trade["trade_cagr_pct"] = cagr_info["cagr_pct"]
        trade["holding_days"] = cagr_info["holding_days"]

    return {
        "initial_capital": initial_cap,
        "cash_balance": cash,
        "open_positions_value": open_val,
        "total_portfolio_value": total_worth,
        "total_realized_pnl": realized_pnl,
        "open_unrealized_pnl": unrealized_pnl,
        "net_profit_loss": net_pnl,
        "total_return_pct": round(total_return_pct, 2),
        "portfolio_inception_date": inception_date.strftime("%Y-%m-%d"),
        "evaluation_date": today_str,
        "portfolio_duration_days": portfolio_days,
        "portfolio_duration_years": round(portfolio_years, 4),
        "portfolio_cagr_pct": round(portfolio_cagr_pct, 2),
        "open_trades": open_trades,
        "closed_trades": closed_trades,
    }


def generate_cagr_report(engine: PaperTradingEngine | None = None) -> str:
    """Generate a formatted ASCII string report summarizing paper trading performance and CAGR.

    Args:
        engine (PaperTradingEngine | None): Engine instance.

    Returns:
        str: Formatted human-readable performance report.
    """
    data = calculate_portfolio_cagr(engine=engine)
    lines: list[str] = []

    lines.append("=" * 90)
    lines.append("PAPER TRADING PORTFOLIO - PERFORMANCE & CAGR REPORT")
    lines.append("=" * 90)
    lines.append(f"Inception Date          : {data['portfolio_inception_date']}")
    lines.append(f"Evaluation Date         : {data['evaluation_date']}")
    lines.append(f"Portfolio Duration      : {data['portfolio_duration_days']} calendar day(s) "
                 f"({data['portfolio_duration_years']:.2f} yrs)")
    lines.append("-" * 90)
    lines.append(f"Initial Starting Capital: INR {data['initial_capital']:>14,.2f}")
    lines.append(f"Available Cash Balance  : INR {data['cash_balance']:>14,.2f}")
    lines.append(f"Active Positions Value  : INR {data['open_positions_value']:>14,.2f}")
    lines.append(f"Total Net Portfolio Worth: INR {data['total_portfolio_value']:>13,.2f}")
    lines.append(f"Realized PnL (Closed)   : INR {data['total_realized_pnl']:>14,.2f}")
    lines.append(f"Unrealized PnL (Open)   : INR {data['open_unrealized_pnl']:>14,.2f}")
    lines.append(f"Net Profit / Loss       : INR {data['net_profit_loss']:>14,.2f}")
    lines.append(f"Total Portfolio Return  : {data['total_return_pct']:>17.2f} %")
    lines.append(f"PORTFOLIO CAGR          : {data['portfolio_cagr_pct']:>17.2f} %")
    lines.append("=" * 90)

    # Active open positions breakdown
    open_trades = data["open_trades"]
    lines.append(f"\n[ACTIVE OPEN POSITIONS] ({len(open_trades)} monitored)")
    if open_trades:
        hdr = (
            f"{'ID':<4} | {'Ticker':<13} | {'Entry Date':<10} | {'Days':<4} | "
            f"{'Qty':<4} | {'Entry (INR)':<11} | {'CMP (INR)':<11} | {'PnL (INR)':<12} | "
            f"{'Return %':<8} | {'CAGR %':<10}"
        )
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for t in open_trades:
            pnl = t["unrealized_pnl"]
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:,.2f}"
            ret_str = f"{'+' if t['pnl_pct'] >= 0 else ''}{t['pnl_pct']:.2f}%"
            cagr_str = f"{'+' if t['trade_cagr_pct'] >= 0 else ''}{t['trade_cagr_pct']:.2f}%"
            lines.append(
                f"#{t['trade_id']:<3} | {t['ticker']:<13} | {t['entry_date']:<10} | "
                f"{t['holding_days']:<4} | {t['quantity']:<4} | {t['entry_price']:<10,.2f} | "
                f"{t['current_price']:<10,.2f} | {pnl_str:<11} | {ret_str:<8} | {cagr_str:<10}"
            )
        lines.append("-" * len(hdr))
    else:
        lines.append("  No open positions active.")

    # Closed trades breakdown
    closed_trades = data["closed_trades"]
    lines.append(f"\n[TRADE HISTORY JOURNAL] ({len(closed_trades)} closed)")
    if closed_trades:
        hdr = (
            f"{'ID':<4} | {'Ticker':<13} | {'Entry Date':<10} | {'Exit Date':<10} | "
            f"{'Days':<4} | {'Qty':<4} | {'Entry (INR)':<11} | {'Exit (INR)':<11} | "
            f"{'Realized (INR)':<14} | {'Return %':<8} | {'CAGR %':<10}"
        )
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for t in closed_trades:
            pnl = float(t["realized_pnl"])
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:,.2f}"
            ret_str = f"{'+' if t['return_pct'] >= 0 else ''}{t['return_pct']:.2f}%"
            cagr_str = f"{'+' if t['trade_cagr_pct'] >= 0 else ''}{t['trade_cagr_pct']:.2f}%"
            lines.append(
                f"#{t['trade_id']:<3} | {t['ticker']:<13} | {t['entry_date']:<10} | "
                f"{t['exit_date']:<10} | {t['holding_days']:<4} | {t['quantity']:<4} | "
                f"{t['entry_price']:<10,.2f} | {t['exit_price']:<10,.2f} | {pnl_str:<12} | "
                f"{ret_str:<8} | {cagr_str:<10}"
            )
        lines.append("-" * len(hdr))
    else:
        lines.append("  No closed trades in history journal yet.")

    lines.append("=" * 90)
    return "\n".join(lines)
