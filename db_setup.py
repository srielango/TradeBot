import sqlite3
from sqlite3 import Error
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import time

database_name = "tradebot.db"

TARGET_INDICES = {
    "^CNXIT": "Nifty IT Index",
    "^CNXAUTO": "Nifty Auto Index",
    "^CNXPHARMA": "Nifty Pharma Index",
    "^CNXFMCG": "Nifty FMCG Index",
    "^CNXFIN": "Nifty Financial Services Index",
    "^CNXMETAL": "Nifty Metal Index",
    "^CNXREALTY": "Nifty Realty Index",
    "^CNXENERGY": "Nifty Energy Index",
    "^NSEBANK": "Bank Nifty Index",
}
    
def create_database():
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

    try:
        with sqlite3.connect(database_name) as conn:
            cursor = conn.cursor()

            cursor.execute(sql_create_securities)
            cursor.execute(sql_create_daily_prices)

            for ticker, name in TARGET_INDICES.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO securities (ticker, name, asset_type)
                    VALUES (?,?,'INDEX')
                """,
                    (ticker, name),
                )

            # nifty200_url = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
            # print('Downloading dynamic Nifty 200 structural roster...')
            df_n200 = pd.read_csv('ind_nifty200list.csv')
            print('Reading..')
            for _, row in df_n200.iterrows():
                raw_symbol = row['Symbol'].strip()
                print(f'Symbol: {raw_symbol}')
                company_name = row['Company Name'].strip()
                yf_ticker = f'{raw_symbol}.NS'

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO securities (ticker, name, asset_type)
                    VALUES (?, ?, 'STOCK')
                """,
                    (yf_ticker, company_name),
                )

            conn.commit()
            print(f'Successfully seeded master list with Nifty 200 constituents.')

    except Error as e:
        print(f'An error occurred: {e}')

def process_historical_downloads():
    with sqlite3.connect(database_name) as conn:
        cursor = conn.cursor()
        cursor.execute('select id, ticker, asset_type from securities')
        securities_list = cursor.fetchall()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=10 * 365)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(
        f'Starting mass download for {len(securities_list)} securities...'
    )

    for sec_id, ticker, asset_type in securities_list:
        with sqlite3.connect(database_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE security_id = ?", (sec_id,),
            )
            count = cursor.fetchone()[0]

            if count > 100: #Arbitrary count indicating data is already parsed
                print(f'Skipping {ticker} - Data already exists.')
                continue

            print(f'Syncing {ticker} ({asset_type})...')
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
                    print(f'Empty dataset returned for {ticker}')
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
                        INSERT OR IGNORE INTO daily_prices (security_id, date, open, high, low, close, volume)
                        VALUES (?,?,?,?,?,?,?)
                    """,
                    records,
                )
                conn.commit()
                print(f'Added {insert_cursor.rowcount} records for {ticker}.')

                time.sleep(1) # Cooldown to handle standard Yahoo API rate thresholds

            except Exception as e:
                print(f'Failed processing {ticker}: {e}')


def download_and_store_history(ticker):
    with sqlite3.connect(database_name) as conn:
        cursor = conn.cursor()

        cursor.execute('select id from securities where ticker = ?', (ticker,))
        row = cursor.fetchone()

        if not row:
            print(f'Ticker {ticker} not found in master securities table.')
            return

        security_id = row[0]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=10 * 365)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        print(f'Downloading data for {ticker} from {start_str} to {end_str}...')

        df = yf.download(ticker, start=start_str, end=end_str, interval="1d")

        if df.empty:
            print(f'Failed to fetch data for {ticker}.')
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
            INSERT OR IGNORE INTO daily_prices (security_id, date, open, high, low, close, volume)
            VALUES (?,?,?,?,?,?,?)
        """,
            records_to_insert,
        )

        conn.commit()
        print(f'Successfully inserted {cursor.rowcount} unique records for {ticker}.')

if __name__ == "__main__":
    # create_database()
    # download_and_store_history("^NSEI")
    process_historical_downloads()