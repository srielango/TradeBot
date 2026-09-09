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
        """Fetch historical hourly price records for a selected ticker.

        Args:
            display_string (str): Formatted ticker string from UI, e.g. 'RELIANCE.NS (STOCK)'.

        Returns:
            pd.DataFrame: DataFrame containing prices (date, open, high, low, close, volume).
        """
        if not display_string:
            return pd.DataFrame()

        ticker = display_string.split(" ")[0]

        query = """
            SELECT p.date, p.open, p.high, p.low, p.close, p.volume
            FROM hourly_prices p
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
            print(f"Database error while loading hourly prices: {err}")
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

    def get_stock_metadata(self) -> dict[str, str]:
        """Fetch dictionary mapping stock ticker symbols to company names.

        Returns:
            dict[str, str]: Mapping of ticker (e.g. 'RELIANCE.NS') to company name.
        """
        query = """
            SELECT ticker, name
            FROM securities
            WHERE asset_type = 'STOCK'
            ORDER BY ticker ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)
                return dict(zip(df["ticker"], df["name"]))
        except sqlite3.Error as err:
            print(f"Database error while fetching stock metadata: {err}")
            return {}

    def get_all_stocks_data(self) -> dict[str, pd.DataFrame]:
        """Fetch historical hourly price records for all active stocks in a single bulk query.

        Returns:
            dict[str, pd.DataFrame]: Dictionary mapping ticker symbol to OHLCV DataFrame.
        """
        query = """
            SELECT s.ticker, p.date, p.open, p.high, p.low, p.close, p.volume
            FROM hourly_prices p
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

    def get_daily_data(self, display_string: str) -> pd.DataFrame:
        """Fetch historical daily OHLCV price records for a selected ticker.

        Aggregates stored hourly bars into daily candles:
        - open: first hourly bar open
        - high: max hourly bar high
        - low: min hourly bar low
        - close: last hourly bar close
        - volume: sum of hourly volume

        Args:
            display_string (str): Formatted ticker string from UI, e.g. 'RELIANCE.NS (STOCK)'.

        Returns:
            pd.DataFrame: DataFrame containing daily OHLCV records sorted by date.
        """
        hourly_df = self.get_data(display_string)
        if hourly_df.empty:
            return pd.DataFrame()

        hourly_df = hourly_df.copy()
        hourly_df['day'] = hourly_df['date'].str[:10]
        daily_df = (
            hourly_df.groupby('day', as_index=False)
            .agg(
                open=('open', 'first'),
                high=('high', 'max'),
                low=('low', 'min'),
                close=('close', 'last'),
                volume=('volume', 'sum'),
            )
            .rename(columns={'day': 'date'})
        )
        return daily_df

    def get_all_stocks_daily_data(self) -> dict[str, pd.DataFrame]:
        """Fetch daily OHLCV price records for all active stocks.

        Returns:
            dict[str, pd.DataFrame]: Mapping of ticker symbol to daily OHLCV DataFrame.
        """
        stocks_hourly = self.get_all_stocks_data()
        daily_data = {}
        for ticker, df in stocks_hourly.items():
            if df.empty:
                continue
            df_copy = df.copy()
            df_copy['day'] = df_copy['date'].str[:10]
            daily_df = (
                df_copy.groupby('day', as_index=False)
                .agg(
                    open=('open', 'first'),
                    high=('high', 'max'),
                    low=('low', 'min'),
                    close=('close', 'last'),
                    volume=('volume', 'sum'),
                )
                .rename(columns={'day': 'date'})
            )
            daily_data[ticker] = daily_df
        return daily_data
