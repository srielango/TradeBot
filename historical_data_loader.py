"""Database initialization and historical data ingestion module for TradeBot."""

import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from config import DB_PATH, NIFTY50_CSV_PATH, TARGET_INDICES


def create_database():
    """Create sqlite tables for securities and daily prices, and seed initial securities list."""
    sql_create_securities = """
    CREATE TABLE IF NOT EXISTS securities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        asset_type TEXT CHECK(asset_type IN ('INDEX', 'STOCK')) NOT NULL
    );
    """

    sql_create_daily_prices = """
    CREATE TABLE IF NOT EXISTS daily_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        security_id INTEGER,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL,
        FOREIGN KEY (security_id) REFERENCES securities(id),
        UNIQUE(security_id, date) -- Prevents duplicate entries per day
    );
    """

    sql_create_fundamentals = """
    CREATE TABLE IF NOT EXISTS security_fundamentals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        security_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        market_cap REAL,
        market_cap_cr REAL,
        debt_to_equity REAL,
        peg_ratio REAL,
        beta_nsei REAL,
        beta_yf REAL,
        avg_volume_252 REAL,
        roe REAL,
        institutional_ownership REAL,
        is_passing INTEGER NOT NULL DEFAULT 0,
        filter_details TEXT,
        FOREIGN KEY (security_id) REFERENCES securities(id),
        UNIQUE(security_id)
    );
    """

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute(sql_create_securities)
            cursor.execute(sql_create_daily_prices)
            cursor.execute(sql_create_fundamentals)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker "
                "ON security_fundamentals(ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_passing "
                "ON security_fundamentals(is_passing);"
            )

            # Seed target benchmark indices
            for ticker, name in TARGET_INDICES.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO securities (ticker, name, asset_type)
                    VALUES (?, ?, 'INDEX')
                    """,
                    (ticker, name),
                )

            # Seed constituents from Nifty 50 list
            df_n50 = pd.read_csv(NIFTY50_CSV_PATH)
            print("Reading Nifty 50 list...")
            for _, row in df_n50.iterrows():
                raw_symbol = row['Symbol'].strip()
                company_name = row['Company Name'].strip()
                yf_ticker = f"{raw_symbol}.NS"

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO securities (ticker, name, asset_type)
                    VALUES (?, ?, 'STOCK')
                    """,
                    (yf_ticker, company_name),
                )

            conn.commit()
            print("Successfully seeded master list with Nifty 50 constituents.")

    except sqlite3.Error as err:
        print(f"An error occurred during database creation: {err}")


def process_historical_downloads():
    """Download 10-year historical daily price bars for all registered securities."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, asset_type FROM securities")
        securities_list = cursor.fetchall()

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=10 * 365)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"Starting mass download for {len(securities_list)} securities...")

    for sec_id, ticker, asset_type in securities_list:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE security_id = ?",
                (sec_id,),
            )
            count = cursor.fetchone()[0]

            if count > 100:  # Count indicating data is already populated
                print(f"Skipping {ticker} - Data already exists ({count} records).")
                continue

            print(f"Syncing {ticker} ({asset_type})...")
            try:
                df = yf.download(
                    ticker,
                    start=start_str,
                    end=end_str,
                    interval='1d',
                    progress=False,
                    auto_adjust=True,
                    multi_level_index=False,
                )

                if df is None or df.empty or len(df) == 0:
                    print(f"Empty dataset returned for {ticker}")
                    time.sleep(0.5)
                    continue

                df = df.reset_index()
                df.columns = [col.lower() for col in df.columns]

                records = []
                for _, row in df.iterrows():
                    date_val = row['date']
                    if isinstance(date_val, str):
                        date_str = date_val[:10]
                    else:
                        date_str = date_val.strftime("%Y-%m-%d")

                    records.append(
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

                insert_cursor = conn.cursor()
                insert_cursor.executemany(
                    """
                    INSERT OR IGNORE INTO daily_prices (
                        security_id, date, open, high, low, close, volume
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    records,
                )
                conn.commit()
                print(f"Added {insert_cursor.rowcount} records for {ticker}.")

                # Cooldown to handle standard Yahoo API rate thresholds
                time.sleep(1)

            except (sqlite3.Error, OSError, ValueError, KeyError) as err:
                print(f"Failed processing {ticker}: {err}")


def download_and_store_history(ticker: str):
    """Download and store 10-year historical daily bars for a single specified ticker.

    Args:
        ticker (str): Yahoo finance ticker symbol (e.g. '^NSEI' or 'INFY.NS').
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM securities WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()

        if not row:
            print(f"Ticker {ticker} not found in master securities table.")
            return

        security_id = row[0]
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=10 * 365)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        print(f"Downloading data for {ticker} from {start_str} to {end_str}...")
        df = yf.download(ticker, start=start_str, end=end_str, interval="1d")

        if df.empty:
            print(f"Failed to fetch data for {ticker}.")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()

        records_to_insert = []
        for _, row_data in df.iterrows():
            date_str = row_data["Date"].strftime("%Y-%m-%d")
            records_to_insert.append(
                (
                    security_id,
                    date_str,
                    float(row_data['Open']),
                    float(row_data['High']),
                    float(row_data['Low']),
                    float(row_data['Close']),
                    int(row_data['Volume']),
                )
            )

        cursor.executemany(
            """
            INSERT OR IGNORE INTO daily_prices (
                security_id, date, open, high, low, close, volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            records_to_insert,
        )
        conn.commit()
        print(f"Successfully inserted {cursor.rowcount} unique records for {ticker}.")


def process_fundamentals_downloads(force_refresh: bool = False) -> None:
    """Ingest and compute fundamental analysis and benchmark metrics for all stock securities.

    Args:
        force_refresh (bool): When True, re-downloads and overwrites existing fundamental records.
    """
    from fundamental_screener import FundamentalScreener

    screener = FundamentalScreener()

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, ticker FROM securities WHERE asset_type = 'STOCK' ORDER BY ticker ASC"
        )
        stock_list = cursor.fetchall()

    print(f"Starting fundamental ingestion for {len(stock_list)} stock securities...")

    for idx, (_, ticker) in enumerate(stock_list, start=1):
        try:
            print(f"[{idx}/{len(stock_list)}] Analyzing fundamentals for {ticker}...")
            metrics = screener.analyze_ticker(ticker, force_refresh=force_refresh)
            status_text = "PASS" if metrics.is_passing else "FAIL"
            print(f"    -> Status: {status_text} | MCap: {metrics.market_cap_cr} Cr")
            time.sleep(0.3)
        except (sqlite3.Error, OSError, ValueError, KeyError) as err:
            print(f"    -> Failed analyzing {ticker}: {err}")


if __name__ == "__main__":
    create_database()
    process_historical_downloads()
    process_fundamentals_downloads()
