"""Screener.in fundamental financial data fetcher for Indian equities.

Extracts key valuation, leverage, ownership, and profitability metrics directly
from public Screener.in company reports, providing high accuracy for NSE equities
where international aggregators (e.g. Yahoo Finance) frequently have data gaps.
"""

from dataclasses import dataclass
import re
from typing import Any, Optional
from urllib.parse import quote

import bs4
import requests


@dataclass
class ScreenerCompanyFundamentals:
    """Dataclass holding normalized fundamental metrics fetched from Screener.in."""

    symbol: str
    market_cap_cr: Optional[float] = None
    stock_pe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    peg_ratio: Optional[float] = None
    roe: Optional[float] = None
    institutional_ownership: Optional[float] = None
    compounded_profit_growth: Optional[float] = None
    book_value: Optional[float] = None
    dividend_yield: Optional[float] = None
    roce: Optional[float] = None
    source: str = "screener.in"

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass to standard dictionary."""
        return {
            "symbol": self.symbol,
            "market_cap_cr": self.market_cap_cr,
            "stock_pe": self.stock_pe,
            "debt_to_equity": self.debt_to_equity,
            "peg_ratio": self.peg_ratio,
            "roe": self.roe,
            "institutional_ownership": self.institutional_ownership,
            "compounded_profit_growth": self.compounded_profit_growth,
            "book_value": self.book_value,
            "dividend_yield": self.dividend_yield,
            "roce": self.roce,
            "source": self.source,
        }


class ScreenerDataFetcher:
    """HTTP client and HTML parser extracting fundamental financial data from Screener.in."""

    BASE_URL = "https://www.screener.in/company"
    DEFAULT_TIMEOUT = 10  # seconds

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize fetcher with configurable request timeout.

        Args:
            timeout (int): HTTP socket connection and read timeout in seconds.
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36 TradeBot/1.0"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    @staticmethod
    def clean_ticker_symbol(ticker: str) -> str:
        """Normalize ticker string to clean NSE symbol acceptable by Screener.in.

        Examples:
            'INFY.NS' -> 'INFY'
            'M&M.NS (STOCK)' -> 'M&M'
            'BAJAJ-AUTO.NS' -> 'BAJAJ-AUTO'

        Args:
            ticker (str): Raw ticker symbol string.

        Returns:
            str: Clean equity symbol.
        """
        symbol = ticker.split(" ")[0].strip()
        if symbol.endswith(".NS") or symbol.endswith(".BO"):
            symbol = symbol[:-3]
        return symbol

    @staticmethod
    def _parse_numeric(text: Optional[str]) -> Optional[float]:
        """Strip currency symbols, commas, percent signs and convert to float."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.-]", "", text)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def fetch_fundamentals(self, ticker: str) -> Optional[ScreenerCompanyFundamentals]:
        """Fetch and extract fundamental metrics from Screener.in for given ticker.

        Args:
            ticker (str): Stock ticker symbol (e.g. 'INFY.NS' or 'INFY').

        Returns:
            Optional[ScreenerCompanyFundamentals]: Parsed metrics, or None if fetch fails.
        """
        clean_symbol = self.clean_ticker_symbol(ticker)
        if not clean_symbol or clean_symbol.startswith("^"):
            # Skip indices or empty symbols
            return None

        encoded_symbol = quote(clean_symbol)
        # Attempt consolidated first (preferred for conglomerates), fallback to standalone
        urls = [
            f"{self.BASE_URL}/{encoded_symbol}/consolidated/",
            f"{self.BASE_URL}/{encoded_symbol}/",
        ]

        html_content: Optional[str] = None
        for url in urls:
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    html_content = response.text
                    break
            except (requests.RequestException, OSError) as err:
                print(f"Warning: HTTP fetch error for {clean_symbol} at {url}: {err}")
                continue

        if not html_content:
            return None

        return self._parse_html(clean_symbol, html_content)

    def _parse_html(
        self, clean_symbol: str, html: str
    ) -> ScreenerCompanyFundamentals:
        """Parse raw Screener.in HTML and construct normalized metrics object."""
        soup = bs4.BeautifulSoup(html, "html.parser")

        # ── 1. Top Financial Ratios Card ─────────────────────────────────────
        top_ratios: dict[str, str] = {}
        for li in soup.find_all("li", class_="flex-space-between"):
            name_el = li.find("span", class_="name")
            val_el = li.find("span", class_="nowrap")
            if name_el and val_el:
                top_ratios[name_el.get_text(strip=True)] = val_el.get_text(strip=True)

        mcap_cr = self._parse_numeric(top_ratios.get("Market Cap"))
        stock_pe = self._parse_numeric(top_ratios.get("Stock P/E"))
        book_val = self._parse_numeric(top_ratios.get("Book Value"))
        div_yield_pct = self._parse_numeric(top_ratios.get("Dividend Yield"))
        div_yield = (div_yield_pct / 100.0) if div_yield_pct is not None else None
        roce_pct = self._parse_numeric(top_ratios.get("ROCE"))
        roce = (roce_pct / 100.0) if roce_pct is not None else None
        roe_pct = self._parse_numeric(top_ratios.get("ROE"))
        roe = (roe_pct / 100.0) if roe_pct is not None else None

        # ── 2. Debt to Equity (from Balance Sheet) ───────────────────────────
        debt_to_equity: Optional[float] = None
        bs_sec = soup.find("section", id="balance-sheet")
        if bs_sec:
            table = bs_sec.find("table")
            if table:
                eq_capital, reserves, borrowings = 0.0, 0.0, 0.0
                has_borrowings = False
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if not tds:
                        continue
                    row_name = tds[0].get_text(strip=True).lower()
                    last_val = self._parse_numeric(tds[-1].get_text(strip=True)) or 0.0
                    if "equity capital" in row_name:
                        eq_capital = last_val
                    elif "reserves" in row_name:
                        reserves = last_val
                    elif "borrowing" in row_name:
                        borrowings = last_val
                        has_borrowings = True

                total_equity = eq_capital + reserves
                if total_equity > 0 and has_borrowings:
                    debt_to_equity = round(borrowings / total_equity, 4)

        # ── 3. Institutional Ownership (FII% + DII% from Shareholding) ───────
        institutional_ownership: Optional[float] = None
        sh_sec = soup.find("section", id="shareholding")
        if sh_sec:
            table = sh_sec.find("table")
            if table:
                fii_pct, dii_pct = 0.0, 0.0
                found_inst = False
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if not tds:
                        continue
                    row_name = tds[0].get_text(strip=True).lower()
                    val = self._parse_numeric(tds[-1].get_text(strip=True))
                    pct = (val / 100.0) if val is not None else 0.0
                    if "fii" in row_name:
                        fii_pct = pct
                        found_inst = True
                    elif "dii" in row_name:
                        dii_pct = pct
                        found_inst = True

                if found_inst:
                    institutional_ownership = round(fii_pct + dii_pct, 4)

        # ── 4. Compounded Profit Growth & PEG Ratio ───────────────────────────
        compounded_profit_growth: Optional[float] = None
        peg_ratio: Optional[float] = None

        for tbl in soup.find_all("table", class_="ranges-table"):
            table_text = tbl.get_text()
            if "Compounded Profit Growth" in table_text:
                m3 = re.search(r"3\s*Years:\s*(-?\d+)%", table_text)
                m5 = re.search(r"5\s*Years:\s*(-?\d+)%", table_text)
                growth: Optional[float] = None
                if m3 and float(m3.group(1)) > 0:
                    growth = float(m3.group(1))
                elif m5 and float(m5.group(1)) > 0:
                    growth = float(m5.group(1))

                if growth is not None:
                    compounded_profit_growth = growth
                    if stock_pe and stock_pe > 0 and growth > 0:
                        peg_ratio = round(stock_pe / growth, 3)
                break

        return ScreenerCompanyFundamentals(
            symbol=clean_symbol,
            market_cap_cr=mcap_cr,
            stock_pe=stock_pe,
            debt_to_equity=debt_to_equity,
            peg_ratio=peg_ratio,
            roe=roe,
            institutional_ownership=institutional_ownership,
            compounded_profit_growth=compounded_profit_growth,
            book_value=book_val,
            dividend_yield=div_yield,
            roce=roce,
            source="screener.in",
        )
