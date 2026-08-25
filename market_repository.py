import sqlite3
import pandas as pd
import os

class MarketRepository:
    def __init__(self, db_name='tradebot.db'):
        self.db_path = os.path.abspath(db_name)

    def get_tickers(self):
        query = """
        SELECT ticker, name, asset_type FROM securities ORDER BY asset_type DESC, ticker ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)
                return [
                    f"{row['ticker']} ({row['asset_type']})"
                    for _, row in df.iterrows()
                ]
        except sqlite3.Error:
            return []

    def get_data(self, display_string: str, horizon_months: int = None):
        if not display_string:
            return pd.DataFrame()
            
        ticker = display_string.split(" ")[0]
        
        # 1. Base query: Pull raw dates directly
        query = """
            SELECT p.date, p.open, p.high, p.low, p.close, p.volume
            FROM daily_prices p
            JOIN securities s ON p.security_id = s.id
            WHERE s.ticker = ?
        """
        params = [ticker]
        
        # 2. SQLite exact dynamic math modifier 
        if horizon_months is not None:
            query += """ 
                AND p.date >= date(
                    (SELECT MAX(date) FROM daily_prices pd JOIN securities sd ON pd.security_id = sd.id WHERE sd.ticker = ?), 
                    ?
                )
            """
            params.extend([ticker, f'-{horizon_months} months'])
            
        query += " ORDER BY p.date ASC"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)
                
            if df.empty: return df

            # Standardize names to lowercase
            df.columns = df.columns.str.lower()
            return df
            
        except sqlite3.Error as e:
            print(f"Database error while loading daily prices: {e}")
            return pd.DataFrame()