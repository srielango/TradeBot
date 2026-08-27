"""Market repository module for managing database operations on financial data."""

import os
import sqlite3
import pandas as pd


class MarketRepository:
    """Repository class to interact with SQLite database storing market data."""

    def __init__(self, db_name: str = 'tradebot.db'):
        """Initialize the repository with the path to SQLite database.

        Args:
            db_name (str): The filename or path of the SQLite database.
        """
        self.db_path = os.path.abspath(db_name)

    def get_tickers(self) -> list[str]:
        """Fetch list of all active ticker symbols and asset types from securities table.

        Returns:
            list[str]: Formatted ticker strings with asset types, e.g., 'RELIANCE.NS (STOCK)'.
        """
        query = """
            SELECT ticker, name, asset_type
            FROM securities
            ORDER BY asset_type DESC, ticker ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)
                return [
                    f"{row['ticker']} ({row['asset_type']})"
                    for _, row in df.iterrows()
                ]
        except sqlite3.Error as err:
            print(f"Database error while fetching tickers: {err}")
            return []

    def get_data(self, display_string: str) -> pd.DataFrame:
        """Fetch historical daily price records for a selected ticker.

        Args:
            display_string (str): Formatted ticker string from the UI, e.g. 'RELIANCE.NS (STOCK)'.

        Returns:
            pd.DataFrame: DataFrame containing daily prices (date, open, high, low, close, volume).
        """
        if not display_string:
            return pd.DataFrame()

        ticker = display_string.split(" ")[0]

        query = """
            SELECT p.date, p.open, p.high, p.low, p.close, p.volume
            FROM daily_prices p
            JOIN securities s ON p.security_id = s.id
            WHERE s.ticker = ?
            ORDER BY p.date ASC
        """
        params = [ticker]

        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if df.empty:
                return df

            # Standardize column names to lowercase
            df.columns = df.columns.str.lower()
            return df

        except sqlite3.Error as err:
            print(f"Database error while loading daily prices: {err}")
            return pd.DataFrame()