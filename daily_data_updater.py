"""Daily data synchronization module for updating database records from Yahoo Finance."""

import sqlite3
import time
from datetime import datetime, timedelta, timezone

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


def run_daily_sync() -> None:
    """Synchronize latest hourly price bars for all registered securities."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, ticker FROM securities")
    securities_list = cursor.fetchall()

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Starting hourly data sync batch for date: {today_str}")
    print(f"Tracking {len(securities_list)} total securities.\n" + "=" * 50)

    for sec_id, ticker in securities_list:
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

        print(f"{ticker:<12} | Syncing missing hourly window from {start_str}")

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
                time.sleep(0.2)
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
                print(f"{ticker:<12} | Added {len(records_to_insert)} new hourly bars.")
            else:
                print(f"{ticker:<12} | Data up to date inside database.")

            time.sleep(0.6)

        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            print(f"Error processing {ticker}: {err}")
            conn.rollback()

    # Aggregate constituent volume for index securities
    aggregate_index_volumes(conn)
    conn.close()


def update_daily_fundamentals(limit: int | None = None) -> None:
    """Refresh fundamental analysis metrics for securities after daily price updates.

    Args:
        limit (int | None): Optional limit on number of securities to sync per run.
    """
    from fundamental_screener import FundamentalScreener

    screener = FundamentalScreener()

    with sqlite3.connect(DB_PATH) as conn:
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

    for idx, ticker in enumerate(tickers, start=1):
        try:
            metrics = screener.analyze_ticker(ticker, force_refresh=True)
            status_text = "PASS" if metrics.is_passing else "FAIL"
            print(f"[{idx}/{len(tickers)}] {ticker:<12} -> Fundamentals synced ({status_text})")
            time.sleep(0.3)
        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            print(f"Failed updating fundamentals for {ticker}: {err}")


def run_full_daily_update() -> None:
    """Execute complete daily pipeline: price bars sync followed by fundamental metrics update."""
    run_daily_sync()
    update_daily_fundamentals()


if __name__ == "__main__":
    run_full_daily_update()
