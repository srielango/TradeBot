
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import time

DB_NAME = "tradebot.db"

def get_latest_stored_date(cursor, security_id):
    cursor.execute(
        """
            SELECT MAX(date) FROM daily_prices
            WHERE security_id = ?
        """, (security_id,),
    )

    result = cursor.fetchone()
    return result[0] if result[0] else None

def run_daily_sync():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id, ticker FROM securities")
    securities_list = cursor.fetchall()

    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f'Starting daily sync batch for date: {today_str}')
    print(f'Tracking {len(securities_list)} total securities. \n' + '=' * 50)

    for sec_id, ticker in securities_list:
        last_date_str = get_latest_stored_date(cursor, sec_id)

        if last_date_str:
            last_date_obj = datetime.strptime(last_date_str, "%Y-%m-%d")
            start_date_obj = last_date_obj + timedelta(days=1)
        else:
            start_date_obj = datetime.now() - timedelta(days=30)

        start_str = start_date_obj.strftime("%Y-%m-%d")

        if start_str > today_str:
            print(f'{ticker:<12} | Up-to-date (Last record: {last_date_str})')
            continue

        print(f'{ticker:<12} | Syncing missing window: {start_str} to {today_str}')

        try:
            df = yf.download(
                ticker,
                start = start_str,
                end = None,
                interval = "1d",
                progress = False,
                auto_adjust = True,
                multi_level_index = False
            )

            if df is None or df.empty or len(df) == 0:
                print(f'No new trading bars found online.')
                time.sleep(0.2)
                continue

            df = df.reset_index()
            df.columns = [col.lower() for col in df.columns]

            records_to_insert = []

            for _, row in df.iterrows():
                date_val = row["date"]
                date_str = (
                    date_val[:10]
                    if isinstance(date_val, str)
                    else date_val.strftime("%Y-%m-%d")
                )

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
                        INSERT OR IGNORE INTO daily_prices (security_id, date, open, high, low, close, volume)
                        VALUES (?,?,?,?,?,?,?)
                    """,
                    records_to_insert,
                )
                conn.commit()
                print(f'Added {len(records_to_insert)} new daily bars.')
            else:
                print(f'Data up to date inside database.')

                time.sleep(0.6)

        except Exception as e:
            print(f'Network/Processing error for {ticker}: {e}')
            conn.rollback()

    conn.close()       

if __name__ == "__main__":
    run_daily_sync()