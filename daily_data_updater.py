"""Daily data synchronization module for updating database records from Yahoo Finance."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import sqlite3
import time

import yfinance as yf

from config import DB_PATH
from historical_data_loader import aggregate_index_volumes


def get_latest_stored_date(cursor: sqlite3.Cursor, security_id: int) -> str | None:
    """Retrieve the latest recorded price timestamp for a specific security.

    Args:
        cursor (sqlite3.Cursor): Active database cursor.
        security_id (int): Primary key ID of the security.

    Returns:
        str | None: Date string in 'YYYY-MM-DD HH:MM:SS' format if found, otherwise None.
    """
    cursor.execute(
        """
        SELECT MAX(date)
        FROM hourly_prices
        WHERE security_id = ?
        """,
        (security_id,),
    )
    result = cursor.fetchone()
    return result[0] if result and result[0] else None


def get_latest_database_bar_date() -> str | None:
    """Retrieve the newest bar timestamp across all securities in the database.

    Returns:
        str | None: Latest recorded timestamp string or None if table is empty.
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(date) FROM hourly_prices")
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    except sqlite3.Error as err:
        print(f"Error checking latest database date: {err}")
        return None


def run_daily_sync(
    progress_callback: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Synchronize latest hourly price bars for all registered securities.

    Args:
        progress_callback: Optional callable receiving (current_step, total_steps, message).
        is_cancelled: Optional callable returning True if synchronization should abort.

    Returns:
        int: Total number of newly inserted price bars across all securities.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # Enable Write-Ahead Logging to prevent lock contention with background readers
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.Error:
        pass

    cursor = conn.cursor()

    cursor.execute("SELECT id, ticker FROM securities")
    securities_list = cursor.fetchall()

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Starting hourly data sync batch for date: {today_str}")
    print(f"Tracking {len(securities_list)} total securities.\n" + "=" * 50)

    total_securities = len(securities_list)
    total_bars_inserted = 0

    for idx, (sec_id, ticker) in enumerate(securities_list, start=1):
        if is_cancelled and is_cancelled():
            print("Sync cancelled by user.")
            break

        last_date_str = get_latest_stored_date(cursor, sec_id)

        if last_date_str:
            # Extract date portion and download from that start date
            last_date_date_str = last_date_str[:10]
            start_date_obj = datetime.strptime(
                last_date_date_str, "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc)
        else:
            start_date_obj = datetime.now(timezone.utc) - timedelta(days=30)

        start_str = start_date_obj.strftime("%Y-%m-%d")

        status_msg = f"[{idx}/{total_securities}] Syncing {ticker} from {start_str}..."
        print(f"{ticker:<12} | Syncing missing hourly window from {start_str}")
        if progress_callback:
            progress_callback(idx, total_securities, status_msg)

        try:
            df = yf.download(
                ticker,
                start=start_str,
                end=None,
                interval="1h",
                progress=False,
                auto_adjust=True,
                multi_level_index=False,
            )

            if df is None or df.empty or len(df) == 0:
                print(f"{ticker:<12} | No new trading bars found online.")
                time.sleep(0.1)
                continue

            df = df.reset_index()
            df.columns = [str(col).lower() for col in df.columns]

            records_to_insert = []
            for _, row in df.iterrows():
                date_val = row.get("datetime", row.get("date"))
                if isinstance(date_val, str):
                    date_str = date_val[:19]
                elif hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    date_str = str(date_val)

                if last_date_str and date_str <= last_date_str:
                    continue

                records_to_insert.append(
                    (
                        sec_id,
                        date_str,
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume']),
                    )
                )

            if records_to_insert:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO hourly_prices (
                        security_id, date, open, high, low, close, volume
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    records_to_insert,
                )
                conn.commit()
                inserted_count = len(records_to_insert)
                total_bars_inserted += inserted_count
                print(f"{ticker:<12} | Added {inserted_count} new hourly bars.")
                if progress_callback:
                    detail_msg = f"[{idx}/{total_securities}] {ticker}: +{inserted_count} bars"
                    progress_callback(idx, total_securities, detail_msg)
            else:
                print(f"{ticker:<12} | Data up to date inside database.")

            time.sleep(0.4)

        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            print(f"Error processing {ticker}: {err}")
            conn.rollback()

    # Aggregate constituent volume for index securities if not cancelled
    if not (is_cancelled and is_cancelled()):
        if progress_callback:
            progress_callback(
                total_securities,
                total_securities,
                "Aggregating constituent index volumes...",
            )
        aggregate_index_volumes(conn)

    conn.close()
    return total_bars_inserted


def update_daily_fundamentals(
    limit: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Refresh fundamental analysis metrics for securities after daily price updates.

    Args:
        limit (int | None): Optional limit on number of securities to sync per run.
        progress_callback: Optional callable receiving (current_step, total_steps, message).
        is_cancelled: Optional callable returning True if synchronization should abort.

    Returns:
        int: Number of stocks successfully updated with fresh fundamentals.
    """
    from fundamental_screener import FundamentalScreener

    screener = FundamentalScreener()

    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cursor = conn.cursor()
        query = (
            "SELECT ticker FROM securities "
            "WHERE asset_type = 'STOCK' ORDER BY ticker ASC"
        )
        if limit:
            query += f" LIMIT {limit}"
        cursor.execute(query)
        tickers = [r[0] for r in cursor.fetchall()]

    print(f"\nStarting daily fundamental refresh for {len(tickers)} stocks...")
    total_stocks = len(tickers)
    updated_count = 0

    for idx, ticker in enumerate(tickers, start=1):
        if is_cancelled and is_cancelled():
            print("Fundamentals update cancelled by user.")
            break

        status_msg = f"[{idx}/{total_stocks}] Syncing fundamentals for {ticker}..."
        print(f"[{idx}/{total_stocks}] {ticker:<12} -> Fundamentals synced")
        if progress_callback:
            progress_callback(idx, total_stocks, status_msg)

        try:
            screener.analyze_ticker(ticker, force_refresh=True)
            updated_count += 1
            time.sleep(0.25)
        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            print(f"Failed updating fundamentals for {ticker}: {err}")

    return updated_count


def run_full_daily_update(
    progress_callback: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    sync_fundamentals: bool = False,
) -> tuple[int, int]:
    """Execute daily market data pipeline: price bars sync, and optional fundamentals.

    Args:
        progress_callback: Optional callable receiving (current_step, total_steps, message).
        is_cancelled: Optional callable returning True if synchronization should abort.
        sync_fundamentals (bool): Whether to also update fundamentals. Defaults to False.

    Returns:
        tuple[int, int]: (new_price_bars_count, updated_fundamentals_count).
    """
    if not sync_fundamentals:
        # Market data sync only (no fundamentals sync)
        bars_added = run_daily_sync(
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
        )
        return bars_added, 0

    # Count total steps to scale progress smoothly when syncing both
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM securities")
        securities_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM securities WHERE asset_type = 'STOCK'")
        stocks_count = cursor.fetchone()[0]

    # Phase 1: securities_count + 1 (volume aggregation); Phase 2: stocks_count
    total_steps = securities_count + 1 + stocks_count

    def phase1_callback(cur: int, tot: int, msg: str) -> None:
        if progress_callback:
            # Step in phase 1 ranges from 1 to securities_count + 1
            progress_callback(cur, total_steps, f"Phase 1/2 Price Bars: {msg}")

    bars_added = run_daily_sync(
        progress_callback=phase1_callback if progress_callback else None,
        is_cancelled=is_cancelled,
    )

    if is_cancelled and is_cancelled():
        return bars_added, 0

    def phase2_callback(cur: int, tot: int, msg: str) -> None:
        if progress_callback:
            # Step in phase 2 starts after Phase 1 finishes
            combined_cur = securities_count + 1 + cur
            progress_callback(combined_cur, total_steps, f"Phase 2/2 Fundamentals: {msg}")

    fundamentals_updated = update_daily_fundamentals(
        progress_callback=phase2_callback if progress_callback else None,
        is_cancelled=is_cancelled,
    )

    if progress_callback and not (is_cancelled and is_cancelled()):
        progress_callback(
            total_steps,
            total_steps,
            f"Daily sync completed! ({bars_added} bars, {fundamentals_updated} fundamentals)",
        )

    return bars_added, fundamentals_updated


if __name__ == "__main__":
    run_daily_sync()
