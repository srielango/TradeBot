"""Fundamental analysis and screening module for TradeBot.

Fetches fundamental metrics from Yahoo Finance, computes benchmark-relative Beta
against Nifty 50 (^NSEI) and 252-day average trading volume, evaluates criteria,
and caches results in the SQLite database.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from config import DB_PATH
from screener_data_fetcher import ScreenerCompanyFundamentals, ScreenerDataFetcher


@dataclass
class FundamentalMetrics:
    """Dataclass encapsulating fundamental and technical screening parameters."""

    ticker: str
    updated_at: str
    market_cap: Optional[float] = None
    market_cap_cr: Optional[float] = None
    debt_to_equity: Optional[float] = None  # Normalized ratio (e.g. 0.10 for 10%)
    peg_ratio: Optional[float] = None
    beta_nsei: Optional[float] = None       # Beta calculated against Nifty 50 (^NSEI)
    beta_yf: Optional[float] = None         # Built-in beta from Yahoo Finance
    avg_volume_252: Optional[float] = None  # 252-day historical average volume
    roe: Optional[float] = None             # Return on Equity (e.g. 0.25 for 25%)
    institutional_ownership: Optional[float] = None  # Held by institutions (e.g. 0.45 for 45%)
    is_passing: bool = False
    filter_details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass instance to standard dictionary."""
        return asdict(self)


class FundamentalScreener:
    """Screener engine to fetch, compute, filter, and store fundamental stock data."""

    def __init__(self, db_path: str = str(DB_PATH)):
        """Initialize screener with database connection path.

        Args:
            db_path (str): Filepath to the SQLite database. Defaults to DB_PATH.
        """
        self.db_path = str(db_path)
        self.screener_fetcher = ScreenerDataFetcher()
        self.init_database()

    def init_database(self) -> None:
        """Create the security_fundamentals table and associated indices if absent."""
        create_table_sql = """
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
        create_idx_sql1 = (
            "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker "
            "ON security_fundamentals(ticker);"
        )
        create_idx_sql2 = (
            "CREATE INDEX IF NOT EXISTS idx_fundamentals_passing "
            "ON security_fundamentals(is_passing);"
        )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            cursor.execute(create_idx_sql1)
            cursor.execute(create_idx_sql2)
            conn.commit()

    def get_nsei_returns(self, lookback_bars: int = 300) -> pd.Series:
        """Fetch historical close return series for Nifty 50 (^NSEI) from database.

        Args:
            lookback_bars (int): Number of most recent daily bars to fetch. Defaults to 300.

        Returns:
            pd.Series: Daily percentage return series indexed by date.
        """
        query = """
            SELECT p.date, p.close
            FROM hourly_prices p
            JOIN securities s ON p.security_id = s.id
            WHERE s.ticker = '^NSEI'
            ORDER BY p.date DESC
            LIMIT ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=[lookback_bars])

            if df.empty or len(df) < 30:
                # Fallback to yfinance if database does not contain ^NSEI
                bench_hist = yf.Ticker("^NSEI").history(period="2y")
                if bench_hist.empty:
                    return pd.Series(dtype=float)
                bench_hist.index = pd.to_datetime(bench_hist.index).tz_localize(None)
                return bench_hist['Close'].pct_change().dropna()

            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').set_index('date')
            return df['close'].pct_change().dropna()

        except sqlite3.Error as err:
            print(f"Database error while fetching ^NSEI benchmark returns: {err}")
            return pd.Series(dtype=float)

    def calculate_beta_nsei(
        self,
        stock_series: pd.Series,
        nsei_returns: Optional[pd.Series] = None,
        period: int = 252,
    ) -> Optional[float]:
        """Calculate stock Beta relative to Nifty 50 (^NSEI) over a specified period.

        Formula: Beta = Cov(R_stock, R_nsei) / Var(R_nsei)

        Args:
            stock_series (pd.Series): Daily close prices or returns of the stock.
            nsei_returns (Optional[pd.Series]): Benchmark return series. If None, fetched.
            period (int): Lookback trading days (default 252 for 1 financial year).

        Returns:
            Optional[float]: Calculated Beta coefficient or None if insufficient data.
        """
        if stock_series.empty or len(stock_series) < 30:
            return None

        # Convert price series to return series if values are prices
        if (stock_series > 0).all() and (stock_series > 2).any():
            stock_ret = stock_series.pct_change().dropna()
        else:
            stock_ret = stock_series.dropna()

        if nsei_returns is None or nsei_returns.empty:
            nsei_returns = self.get_nsei_returns(lookback_bars=period + 50)

        # Align stock and benchmark returns on matching dates (ensure tz compatibility)
        if hasattr(stock_ret.index, "tz") and stock_ret.index.tz is not None:
            stock_ret.index = stock_ret.index.tz_localize(None)
        if hasattr(nsei_returns.index, "tz") and nsei_returns.index.tz is not None:
            nsei_returns.index = nsei_returns.index.tz_localize(None)

        aligned = pd.DataFrame({'stock': stock_ret, 'nsei': nsei_returns}).dropna().tail(period)

        if len(aligned) < 30:
            return None

        nsei_var = float(np.var(aligned['nsei']))
        if nsei_var <= 1e-12:
            return None

        cov_matrix = np.cov(aligned['stock'], aligned['nsei'])
        covariance = float(cov_matrix[0][1])

        beta_val = covariance / nsei_var
        return round(float(beta_val), 3)

    def calculate_avg_volume(
        self,
        volume_series: pd.Series,
        period: int = 252,
    ) -> Optional[float]:
        """Compute the average daily traded volume over the last 252 trading days.

        Args:
            volume_series (pd.Series): Historical daily trading volume series.
            period (int): Trading period window in days (default 252).

        Returns:
            Optional[float]: Average daily volume or None.
        """
        if volume_series.empty:
            return None
        tail_vol = volume_series.dropna().tail(period)
        if tail_vol.empty:
            return None
        return round(float(tail_vol.mean()), 2)

    def fetch_yahoo_info(self, ticker: str) -> dict[str, Any]:
        """Retrieve the fundamental info dictionary from Yahoo Finance with error protection.

        Args:
            ticker (str): Yahoo finance ticker symbol, e.g. 'INFY.NS'.

        Returns:
            dict[str, Any]: Parsed metadata dictionary.
        """
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info
            if not isinstance(info, dict):
                return {}
            return info
        except (KeyError, ValueError, OSError, ConnectionError) as err:
            print(f"Yahoo Finance API fetch error for {ticker}: {err}")
            return {}

    def analyze_ticker(
        self,
        ticker: str,
        df: Optional[pd.DataFrame] = None,
        force_refresh: bool = False,
        criteria: Optional[dict[str, Any]] = None,
    ) -> FundamentalMetrics:
        """Analyze a single security against fundamental and historical criteria.

        Args:
            ticker (str): Security ticker symbol (e.g. 'INFY.NS' or 'INFY.NS (STOCK)').
            df (Optional[pd.DataFrame]): Optional existing price DataFrame with close and volume.
            force_refresh (bool): When True, ignores cached database records and fetches live.
            criteria (Optional[dict]): Override screening thresholds if provided.

        Returns:
            FundamentalMetrics: Complete fundamental and technical evaluation.
        """
        clean_ticker = ticker.split(" ")[0].strip()

        # Check existing cached metrics in SQLite if not force refreshed
        if not force_refresh:
            cached = self.load_from_db(clean_ticker)
            if cached is not None:
                # Re-evaluate with current criteria if criteria specified
                if criteria is not None:
                    is_passing, details = self.evaluate_criteria(cached, criteria)
                    cached.is_passing = is_passing
                    cached.filter_details = details
                return cached

        # Fetch historical price and volume if not provided
        if df is None or df.empty:
            query = """
                SELECT p.date, p.close, p.volume
                FROM hourly_prices p
                JOIN securities s ON p.security_id = s.id
                WHERE s.ticker = ?
                ORDER BY p.date ASC
            """
            try:
                with sqlite3.connect(self.db_path) as conn:
                    df = pd.read_sql_query(query, conn, params=[clean_ticker])
            except sqlite3.Error:
                df = pd.DataFrame()

        # Fallback to yfinance historical prices if database is empty
        if df.empty or len(df) < 30:
            try:
                hist = yf.Ticker(clean_ticker).history(period="2y")
                if not hist.empty:
                    df = hist.reset_index()[['Date', 'Close', 'Volume']].rename(
                        columns={'Date': 'date', 'Close': 'close', 'Volume': 'volume'}
                    )
            except Exception:
                df = pd.DataFrame()

        # 1. Compute Historical Calculated Metrics (Volume and Beta)
        avg_vol_252 = None
        beta_nsei = None

        if not df.empty and 'close' in df.columns and 'volume' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df_sorted = df.sort_values('date').set_index('date')
            avg_vol_252 = self.calculate_avg_volume(df_sorted['volume'], period=252)
            beta_nsei = self.calculate_beta_nsei(df_sorted['close'], period=252)

        # 2. Fetch Fundamentals from Screener.in with automatic Yahoo Finance fallback
        screener_data: Optional[ScreenerCompanyFundamentals] = None
        try:
            screener_data = self.screener_fetcher.fetch_fundamentals(clean_ticker)
        except Exception as err:
            print(
                f"Screener.in fetch error for {clean_ticker} ({err}), "
                "falling back to Yahoo Finance."
            )

        market_cap_cr: Optional[float] = None
        market_cap: Optional[float] = None
        debt_to_equity: Optional[float] = None
        peg_ratio: Optional[float] = None
        roe: Optional[float] = None
        institutional_ownership: Optional[float] = None

        if screener_data is not None:
            market_cap_cr = screener_data.market_cap_cr
            if market_cap_cr is not None:
                market_cap = market_cap_cr * 1e7
            debt_to_equity = screener_data.debt_to_equity
            peg_ratio = screener_data.peg_ratio
            roe = screener_data.roe
            institutional_ownership = screener_data.institutional_ownership

        # Fallback to Yahoo Finance for any missing metrics or beta
        info: dict[str, Any] = {}
        needs_fallback = (
            market_cap_cr is None
            or debt_to_equity is None
            or peg_ratio is None
            or roe is None
            or institutional_ownership is None
        )
        if needs_fallback:
            info = self.fetch_yahoo_info(clean_ticker)

        if market_cap_cr is None and info.get('marketCap') is not None:
            market_cap = info.get('marketCap')
            market_cap_cr = (market_cap / 1e7) if market_cap is not None else None

        if debt_to_equity is None:
            d_to_e_raw = info.get('debtToEquity')
            if d_to_e_raw is not None:
                debt_to_equity = round(float(d_to_e_raw) / 100.0, 4)

        if peg_ratio is None and info.get('pegRatio') is not None:
            peg_ratio = round(float(info['pegRatio']), 3)

        if roe is None and info.get('returnOnEquity') is not None:
            roe = round(float(info['returnOnEquity']), 4)

        if institutional_ownership is None and info.get('heldPercentInstitutions') is not None:
            institutional_ownership = round(float(info['heldPercentInstitutions']), 4)

        # Get Yahoo built-in beta if available
        if not info and (market_cap_cr is not None):
            info = self.fetch_yahoo_info(clean_ticker)
        beta_yf = info.get('beta')
        if beta_yf is not None:
            beta_yf = round(float(beta_yf), 3)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        metrics = FundamentalMetrics(
            ticker=clean_ticker,
            updated_at=now_str,
            market_cap=market_cap,
            market_cap_cr=market_cap_cr,
            debt_to_equity=debt_to_equity,
            peg_ratio=peg_ratio,
            beta_nsei=beta_nsei,
            beta_yf=beta_yf,
            avg_volume_252=avg_vol_252,
            roe=roe,
            institutional_ownership=institutional_ownership,
        )

        # 3. Evaluate criteria
        is_passing, details = self.evaluate_criteria(metrics, criteria)
        metrics.is_passing = is_passing
        metrics.filter_details = details

        # 4. Cache in Database
        self.save_to_db(metrics)

        return metrics

    def evaluate_criteria(
        self,
        m: FundamentalMetrics,
        criteria: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate fundamental metrics against screening rules.

        Rules:
        - Peg ratio > 2.0
        - Debt to Equity < 0.50
        - Market Cap > 5,000 Cr INR (50 Billion INR)
        - Beta value > 1.2 (calculated relative to Nifty 50)
        - Average volume over 252 days > 30,00,000 (3M)
        - Institutional ownership >= 15% (0.15)
        - ROE > 20% (optional, default disabled / ignored as specified)

        Args:
            m (FundamentalMetrics): Extracted metrics instance.
            criteria (Optional[dict]): Threshold configuration dictionary.

        Returns:
            tuple[bool, dict[str, Any]]: Overall pass flag and breakdown dictionary.
        """
        c = {
            "min_peg": 2.0,
            "max_debt_to_equity": 0.50,
            "min_market_cap_cr": 5000.0,
            "min_beta": 1.2,
            "min_avg_volume_252": 3_000_000,
            "min_institutional_ownership": 0.15,
            "min_roe": None,  # Optional: set to 0.20 if ROE filter is activated
        }
        if criteria:
            c.update(criteria)

        details = {}

        # 1. Market Cap > 5k Cr
        if m.market_cap_cr is not None:
            pass_mcap = m.market_cap_cr >= c["min_market_cap_cr"]
            details["market_cap"] = {
                "value_cr": round(m.market_cap_cr, 2),
                "threshold_cr": c["min_market_cap_cr"],
                "passed": pass_mcap,
            }
        else:
            details["market_cap"] = {
                "value_cr": None,
                "threshold_cr": c["min_market_cap_cr"],
                "passed": False,
            }

        # 2. Debt to Equity < 0.50
        if m.debt_to_equity is not None:
            pass_de = m.debt_to_equity <= c["max_debt_to_equity"]
            details["debt_to_equity"] = {
                "value": m.debt_to_equity,
                "threshold": c["max_debt_to_equity"],
                "passed": pass_de,
            }
        else:
            # If debt_to_equity is None (e.g. Banks/Financials), mark not passed or flag
            details["debt_to_equity"] = {
                "value": None,
                "threshold": c["max_debt_to_equity"],
                "passed": False,
            }

        # 3. PEG ratio >= 2.0 (indicates strong growth expectations).
        # Stocks with no PEG data (e.g. cyclicals, financials) are given a pass
        # because the absence of a PEG should not disqualify an otherwise strong stock.
        if m.peg_ratio is not None:
            pass_peg = m.peg_ratio >= c["min_peg"]
            details["peg_ratio"] = {
                "value": m.peg_ratio,
                "threshold": c["min_peg"],
                "passed": pass_peg,
                "note": "below_threshold" if not pass_peg else None,
            }
        else:
            # Pass but flag as unavailable so analysts know to verify manually
            details["peg_ratio"] = {
                "value": None,
                "threshold": c["min_peg"],
                "passed": True,
                "note": "data_unavailable",
            }

        # 4. Beta > 1.2 (Prefer calculated Beta vs Nifty 50, fallback to Yahoo beta)
        effective_beta = m.beta_nsei if m.beta_nsei is not None else m.beta_yf
        if effective_beta is not None:
            pass_beta = effective_beta >= c["min_beta"]
            details["beta"] = {
                "value": effective_beta,
                "type": "Nifty50" if m.beta_nsei is not None else "Yahoo",
                "threshold": c["min_beta"],
                "passed": pass_beta,
            }
        else:
            details["beta"] = {"value": None, "threshold": c["min_beta"], "passed": False}

        # 5. Average Volume (252 days) > 3,000,000
        if m.avg_volume_252 is not None:
            pass_vol = m.avg_volume_252 >= c["min_avg_volume_252"]
            details["avg_volume_252"] = {
                "value": int(m.avg_volume_252),
                "threshold": c["min_avg_volume_252"],
                "passed": pass_vol,
            }
        else:
            details["avg_volume_252"] = {
                "value": None,
                "threshold": c["min_avg_volume_252"],
                "passed": False,
            }

        # 6. Institutional Ownership >= 15% (0.15)
        if m.institutional_ownership is not None:
            pass_inst = m.institutional_ownership >= c["min_institutional_ownership"]
            details["institutional_ownership"] = {
                "value_pct": round(m.institutional_ownership * 100, 2),
                "threshold_pct": round(c["min_institutional_ownership"] * 100, 2),
                "passed": pass_inst,
            }
        else:
            details["institutional_ownership"] = {
                "value_pct": None,
                "threshold_pct": round(c["min_institutional_ownership"] * 100, 2),
                "passed": False,
            }

        # 7. ROE > 20% (Optional)
        if c["min_roe"] is not None:
            if m.roe is not None:
                pass_roe = m.roe >= c["min_roe"]
                details["roe"] = {
                    "value_pct": round(m.roe * 100, 2),
                    "threshold_pct": round(c["min_roe"] * 100, 2),
                    "passed": pass_roe,
                }
            else:
                details["roe"] = {
                    "value_pct": None,
                    "threshold_pct": round(c["min_roe"] * 100, 2),
                    "passed": False,
                }
        else:
            details["roe"] = {
                "value_pct": round(m.roe * 100, 2) if m.roe is not None else None,
                "threshold_pct": "Ignored",
                "passed": True,
            }

        # Overall boolean result
        mandatory_checks = [
            details["market_cap"]["passed"],
            details["debt_to_equity"]["passed"],
            details["peg_ratio"]["passed"],
            details["beta"]["passed"],
            details["avg_volume_252"]["passed"],
            details["institutional_ownership"]["passed"],
            details["roe"]["passed"],
        ]
        is_passing = all(mandatory_checks)

        return is_passing, details

    def save_to_db(self, m: FundamentalMetrics) -> None:
        """Save or update fundamental metrics in SQLite database table.

        Args:
            m (FundamentalMetrics): Metrics object to persist.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM securities WHERE ticker = ?",
                    (m.ticker,),
                )
                sec_row = cursor.fetchone()
                if not sec_row:
                    return
                security_id = sec_row[0]

                filter_json = json.dumps(m.filter_details) if m.filter_details else None

                cursor.execute(
                    """
                    INSERT INTO security_fundamentals (
                        security_id, ticker, updated_at, market_cap, market_cap_cr,
                        debt_to_equity, peg_ratio, beta_nsei, beta_yf, avg_volume_252,
                        roe, institutional_ownership, is_passing, filter_details
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(security_id) DO UPDATE SET
                        ticker = excluded.ticker,
                        updated_at = excluded.updated_at,
                        market_cap = excluded.market_cap,
                        market_cap_cr = excluded.market_cap_cr,
                        debt_to_equity = excluded.debt_to_equity,
                        peg_ratio = excluded.peg_ratio,
                        beta_nsei = excluded.beta_nsei,
                        beta_yf = excluded.beta_yf,
                        avg_volume_252 = excluded.avg_volume_252,
                        roe = excluded.roe,
                        institutional_ownership = excluded.institutional_ownership,
                        is_passing = excluded.is_passing,
                        filter_details = excluded.filter_details
                    """,
                    (
                        security_id,
                        m.ticker,
                        m.updated_at,
                        m.market_cap,
                        m.market_cap_cr,
                        m.debt_to_equity,
                        m.peg_ratio,
                        m.beta_nsei,
                        m.beta_yf,
                        m.avg_volume_252,
                        m.roe,
                        m.institutional_ownership,
                        1 if m.is_passing else 0,
                        filter_json,
                    ),
                )
                conn.commit()
        except sqlite3.Error as err:
            print(f"Failed to persist fundamentals for {m.ticker}: {err}")

    def load_from_db(self, ticker: str) -> Optional[FundamentalMetrics]:
        """Load cached fundamental metrics for a ticker from database.

        Args:
            ticker (str): Security ticker symbol.

        Returns:
            Optional[FundamentalMetrics]: Stored metrics or None if absent.
        """
        clean_ticker = ticker.split(" ")[0].strip()
        query = """
            SELECT ticker, updated_at, market_cap, market_cap_cr, debt_to_equity,
                   peg_ratio, beta_nsei, beta_yf, avg_volume_252, roe,
                   institutional_ownership, is_passing, filter_details
            FROM security_fundamentals
            WHERE ticker = ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (clean_ticker,))
                row = cursor.fetchone()

            if not row:
                return None

            details = json.loads(row[12]) if row[12] else None

            return FundamentalMetrics(
                ticker=row[0],
                updated_at=row[1],
                market_cap=row[2],
                market_cap_cr=row[3],
                debt_to_equity=row[4],
                peg_ratio=row[5],
                beta_nsei=row[6],
                beta_yf=row[7],
                avg_volume_252=row[8],
                roe=row[9],
                institutional_ownership=row[10],
                is_passing=bool(row[11]),
                filter_details=details,
            )
        except (sqlite3.Error, json.JSONDecodeError) as err:
            print(f"Error loading fundamental cache for {clean_ticker}: {err}")
            return None

    def screen_universe(
        self,
        tickers: Optional[list[str]] = None,
        force_refresh: bool = False,
        criteria: Optional[dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """Screen a universe of securities and return summary DataFrame.

        Args:
            tickers (Optional[list[str]]): List of tickers. If None, queries all stocks from DB.
            force_refresh (bool): If True, re-fetches fundamentals live.
            criteria (Optional[dict]): Threshold configuration dictionary.

        Returns:
            pd.DataFrame: Table with all metrics and screening outcomes.
        """
        if tickers is None:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    query = (
                        "SELECT ticker FROM securities "
                        "WHERE asset_type = 'STOCK' ORDER BY ticker ASC"
                    )
                    cursor.execute(query)
                    tickers = [r[0] for r in cursor.fetchall()]
            except sqlite3.Error:
                tickers = []

        records = []
        for ticker in tickers:
            metrics = self.analyze_ticker(
                ticker=ticker,
                force_refresh=force_refresh,
                criteria=criteria,
            )
            mcap_val = (
                round(metrics.market_cap_cr, 2) if metrics.market_cap_cr else None
            )
            vol_val = int(metrics.avg_volume_252) if metrics.avg_volume_252 else None
            inst_val = (
                round(metrics.institutional_ownership * 100, 2)
                if metrics.institutional_ownership
                else None
            )
            roe_val = round(metrics.roe * 100, 2) if metrics.roe else None

            records.append({
                "Ticker": metrics.ticker,
                "MarketCap (Cr)": mcap_val,
                "Debt/Equity": metrics.debt_to_equity,
                "PEG Ratio": metrics.peg_ratio,
                "Beta (Nifty50)": metrics.beta_nsei,
                "Beta (YF)": metrics.beta_yf,
                "Avg Vol (252d)": vol_val,
                "Inst Own %": inst_val,
                "ROE %": roe_val,
                "Passes Screener": "YES" if metrics.is_passing else "NO",
            })

        return pd.DataFrame(records)
