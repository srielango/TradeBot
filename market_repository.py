"""Market repository module for managing database operations on financial data."""

import os
import sqlite3
from pathlib import Path

import pandas as pd

from config import DB_PATH


class MarketRepository:
    """Repository class to interact with SQLite database storing market data."""

    def __init__(self, db_name: str | Path = DB_PATH):
        """Initialize repository with path to SQLite database.

        Args:
            db_name (str | Path): Path of the SQLite database. Defaults to DB_PATH.
        """
        self.db_path = str(os.path.abspath(db_name))

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
            display_string (str): Formatted ticker string from UI, e.g. 'RELIANCE.NS (STOCK)'.

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

    def get_fundamentals(self, display_string: str) -> dict | None:
        """Fetch cached fundamental metrics for a selected security.

        Args:
            display_string (str): Formatted ticker string from UI, e.g. 'INFY.NS (STOCK)'.

        Returns:
            dict | None: Dictionary of fundamental attributes or None if unpopulated.
        """
        if not display_string:
            return None

        ticker = display_string.split(" ")[0]
        query = """
            SELECT market_cap_cr, debt_to_equity, peg_ratio, beta_nsei,
                   beta_yf, avg_volume_252, roe, institutional_ownership,
                   is_passing, updated_at
            FROM security_fundamentals
            WHERE ticker = ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=[ticker])
            if df.empty:
                return None
            return df.iloc[0].to_dict()
        except sqlite3.Error as err:
            print(f"Database error while fetching fundamentals for {ticker}: {err}")
            return None

    def get_stock_tickers(self) -> list[str]:
        """Fetch list of all active equity stock tickers (asset_type = 'STOCK').

        Returns:
            list[str]: Formatted ticker strings with asset type, e.g. 'RELIANCE.NS (STOCK)'.
        """
        query = """
            SELECT ticker, name, asset_type
            FROM securities
            WHERE asset_type = 'STOCK'
            ORDER BY ticker ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)
                return [
                    f"{row['ticker']} ({row['asset_type']})"
                    for _, row in df.iterrows()
                ]
        except sqlite3.Error as err:
            print(f"Database error while fetching stock tickers: {err}")
            return []

    def get_all_stocks_data(self) -> dict[str, pd.DataFrame]:
        """Fetch historical daily price records for all active stocks in a single bulk query.

        Returns:
            dict[str, pd.DataFrame]: Dictionary mapping ticker symbol to OHLCV DataFrame.
        """
        query = """
            SELECT s.ticker, p.date, p.open, p.high, p.low, p.close, p.volume
            FROM daily_prices p
            JOIN securities s ON p.security_id = s.id
            WHERE s.asset_type = 'STOCK'
            ORDER BY s.ticker ASC, p.date ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)

            if df.empty:
                return {}

            df.columns = df.columns.str.lower()
            stocks_data = {}
            for ticker, group in df.groupby("ticker"):
                group_clean = group.drop(columns=["ticker"]).reset_index(drop=True)
                stocks_data[str(ticker)] = group_clean
            return stocks_data

        except sqlite3.Error as err:
            print(f"Database error while loading all stock prices: {err}")
            return {}
