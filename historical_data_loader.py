"""Database initialization and historical data ingestion module for TradeBot."""

import sqlite3
import time

import pandas as pd
import yfinance as yf

from config import DB_PATH, NIFTY50_CSV_PATH, TARGET_INDICES


def create_database() -> None:
    """Create sqlite tables for securities and hourly prices, and seed initial securities list."""
    sql_create_securities = """
    CREATE TABLE IF NOT EXISTS securities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        asset_type TEXT CHECK(asset_type IN ('INDEX', 'STOCK')) NOT NULL
    );
    """

    sql_create_hourly_prices = """
    CREATE TABLE IF NOT EXISTS hourly_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        security_id INTEGER,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL,
        FOREIGN KEY (security_id) REFERENCES securities(id),
        UNIQUE(security_id, date) -- Prevents duplicate entries per hourly timestamp
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
            cursor.execute(sql_create_hourly_prices)
            cursor.execute(sql_create_fundamentals)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker "
                "ON security_fundamentals(ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_passing "
                "ON security_fundamentals(is_passing);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_hourly_prices_sec_date "
                "ON hourly_prices(security_id, date);"
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


def aggregate_index_volumes(conn: sqlite3.Connection | None = None) -> None:
    """Compute and update hourly volumes for benchmark and sectoral indices.

    Aggregates the volume of underlying constituent stocks for each index.

    Args:
        conn (sqlite3.Connection | None): Optional active SQLite connection.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        should_close = True

    cursor = conn.cursor()

    # Get index securities
    cursor.execute("SELECT id, ticker FROM securities WHERE asset_type = 'INDEX'")
    indices = cursor.fetchall()
    if not indices:
        if should_close:
            conn.close()
        return

    # Map stock ticker to security_id
    cursor.execute("SELECT ticker, id FROM securities WHERE asset_type = 'STOCK'")
    stock_ticker_to_id = {row[0]: row[1] for row in cursor.fetchall()}

    # Sector & benchmark constituent mappings based on Nifty 50 constituents
    index_constituents_map = {
        "^NSEI": list(stock_ticker_to_id.values()),  # All 50 Nifty stocks
        "^NSEBANK": [
            stock_ticker_to_id[t]
            for t in [
                "AXISBANK.NS", "HDFCBANK.NS", "ICICIBANK.NS",
                "INDUSINDBK.NS", "KOTAKBANK.NS", "SBIN.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXIT": [
            stock_ticker_to_id[t]
            for t in [
                "HCLTECH.NS", "INFY.NS", "TCS.NS", "TECHM.NS", "WIPRO.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXAUTO": [
            stock_ticker_to_id[t]
            for t in [
                "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS",
                "M&M.NS", "MARUTI.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXPHARMA": [
            stock_ticker_to_id[t]
            for t in [
                "APOLLOHOSP.NS", "CIPLA.NS", "DIVISLAB.NS",
                "DRREDDY.NS", "SUNPHARMA.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXFMCG": [
            stock_ticker_to_id[t]
            for t in [
                "BRITANNIA.NS", "HINDUNILVR.NS", "ITC.NS",
                "NESTLEIND.NS", "TATACONSUM.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXFIN": [
            stock_ticker_to_id[t]
            for t in [
                "AXISBANK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS",
                "HDFCBANK.NS", "HDFCLIFE.NS", "ICICIBANK.NS",
                "INDUSINDBK.NS", "KOTAKBANK.NS", "SBILIFE.NS",
                "SHRIRAMFIN.NS", "SBIN.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXMETAL": [
            stock_ticker_to_id[t]
            for t in [
                "ADANIENT.NS", "HINDALCO.NS", "JSWSTEEL.NS", "TATASTEEL.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXENERGY": [
            stock_ticker_to_id[t]
            for t in [
                "BPCL.NS", "COALINDIA.NS", "ONGC.NS",
                "RELIANCE.NS", "NTPC.NS", "POWERGRID.NS",
            ]
            if t in stock_ticker_to_id
        ],
        "^CNXREALTY": [
            stock_ticker_to_id[t]
            for t in ["LT.NS", "GRASIM.NS", "ULTRACEMCO.NS"]
            if t in stock_ticker_to_id
        ],
    }

    print("\nAggregating constituent volumes for index benchmarks...")
    for idx_id, idx_ticker in indices:
        constituent_ids = index_constituents_map.get(idx_ticker)
        if not constituent_ids:
            constituent_ids = list(stock_ticker_to_id.values())

        placeholders = ",".join(["?"] * len(constituent_ids))
        query = f"""
            SELECT p.date, SUM(p.volume) as total_volume
            FROM hourly_prices p
            WHERE p.security_id IN ({placeholders})
            GROUP BY p.date
        """
        cursor.execute(query, constituent_ids)
        aggregated_rows = cursor.fetchall()

        if aggregated_rows:
            update_data = [
                (int(total_vol), idx_id, date_str)
                for date_str, total_vol in aggregated_rows
            ]
            cursor.executemany(
                """
                UPDATE hourly_prices
                SET volume = ?
                WHERE security_id = ? AND date = ?
                """,
                update_data,
            )
            conn.commit()
            print(
                f"Updated constituent volume for {idx_ticker:<12} "
                f"across {len(update_data)} hourly bars."
            )

    if should_close:
        conn.close()


def process_historical_downloads() -> None:
    """Download up to 730-day historical hourly price bars for all registered securities."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, asset_type FROM securities")
        securities_list = cursor.fetchall()

    print(f"Starting mass hourly download for {len(securities_list)} securities...")

    for sec_id, ticker, asset_type in securities_list:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM hourly_prices WHERE security_id = ?",
                (sec_id,),
            )
            count = cursor.fetchone()[0]

            if count > 100:  # Count indicating data is already populated
                print(f"Skipping {ticker} - Data already exists ({count} records).")
                continue

            print(f"Syncing hourly data for {ticker} ({asset_type})...")
            try:
                df = yf.download(
                    ticker,
                    period="730d",
                    interval="1h",
                    progress=False,
                    auto_adjust=True,
                    multi_level_index=False,
                )

                if df is None or df.empty or len(df) == 0:
                    print(f"Empty dataset returned for {ticker}")
                    time.sleep(0.5)
                    continue

                df = df.reset_index()
                df.columns = [str(col).lower() for col in df.columns]

                records = []
                for _, row in df.iterrows():
                    date_val = row.get("datetime", row.get("date"))
                    if isinstance(date_val, str):
                        date_str = date_val[:19]
                    elif hasattr(date_val, "strftime"):
                        date_str = date_val.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        date_str = str(date_val)

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
                    INSERT OR IGNORE INTO hourly_prices (
                        security_id, date, open, high, low, close, volume
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    records,
                )
                conn.commit()
                print(f"Added {insert_cursor.rowcount} hourly records for {ticker}.")

                # Cooldown to handle standard Yahoo API rate thresholds
                time.sleep(1)

            except (sqlite3.Error, OSError, ValueError, KeyError) as err:
                print(f"Failed processing {ticker}: {err}")

    # Aggregate constituent volume for index securities
    aggregate_index_volumes()


def download_and_store_history(ticker: str) -> None:
    """Download and store historical hourly bars for a single specified ticker.

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
        print(f"Downloading hourly data for {ticker} (730d)...")
        df = yf.download(ticker, period="730d", interval="1h", progress=False)

        if df.empty:
            print(f"Failed to fetch data for {ticker}.")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df.columns = [str(col).lower() for col in df.columns]

        records_to_insert = []
        for _, row_data in df.iterrows():
            date_val = row_data.get("datetime", row_data.get("date"))
            if isinstance(date_val, str):
                date_str = date_val[:19]
            elif hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%Y-%m-%d %H:%M:%S")
            else:
                date_str = str(date_val)

            records_to_insert.append(
                (
                    security_id,
                    date_str,
                    float(row_data['open']),
                    float(row_data['high']),
                    float(row_data['low']),
                    float(row_data['close']),
                    int(row_data['volume']),
                )
            )

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
        print(f"Successfully inserted {cursor.rowcount} unique hourly records for {ticker}.")


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
