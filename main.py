"""Tradebot Management Studio - Desktop analytical dashboard and showcase entry point."""

import sys

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtWidgets import QApplication

from adx_indicator import analyze_adx
from back_test_engine import BacktestEngine
from daily_data_updater import run_daily_sync
from data_sync_service import DataSyncService
from entry_stop_loss_validator import validate_entry_stop_losses
from fundamental_screener import FundamentalScreener
from market_repository import MarketRepository
from market_sentiment_analyzer import MarketSentimentAnalyzer
from morning_scanner import MorningScanner
from paper_trade_cagr import (
    calculate_portfolio_cagr,
    calculate_trade_cagr,
    generate_cagr_report,
)
from paper_trading_engine import PaperTradingEngine
from rsi_indicator import analyze_rsi
from screener_data_fetcher import ScreenerDataFetcher
from strategies.adx_ema_swing import (
    AdxEmaBacktester,
    AdxEmaSwingStrategy,
)
from strategies.bollinger_stoch_rsi import BollingerStochRsi
from strategies.bullish_kicker import BullishKicker
from strategies.bullish_outside_bar import BullishOutsideBar
from strategies.dual_moving_average_adx import DualMovingAverageAdx
from strategies.moving_average_stochastic import MovingAverageStochastic
from strategies.nifty_dual_momentum_breakout import NiftyDualMomentumBreakout
from strategies.rsi_bull_trend_pullback import RsiBullTrendPullback
from ui import (
    NiftyHeaderWidget,
    TickerChartPopupDialog,
    TradingApp,
    show_ticker_chart_popup,
)


def example_trading_dashboard() -> None:
    """Showcase and launch Tradebot Management Studio graphical interface."""
    app = QApplication(sys.argv)
    window = TradingApp()
    window.show()
    sys.exit(app.exec())


def example_nifty_live_header() -> None:
    """Showcase live Nifty benchmark header component with real-time quote streaming."""
    print("=" * 80)
    print("NIFTY LIVE BENCHMARK HEADER SHOWCASE")
    print("=" * 80)
    print("Launching TradeBot Studio with real-time Nifty 50 & Bank Nifty benchmark header...")
    print(f"Header component class: {NiftyHeaderWidget.__name__}")
    print("Features: Live quotes, net/pct change, day high/low gauge, IST clock, click navigation.")
    print("-" * 80)
    app = QApplication(sys.argv)
    window = TradingApp()
    window.show()
    sys.exit(app.exec())


def example_ticker_chart_popup(ticker: str = "RELIANCE.NS") -> None:
    """Showcase interactive 3-month ticker chart popup dialog component.

    Args:
        ticker (str): Ticker symbol to display. Defaults to 'RELIANCE.NS'.
    """
    print("=" * 80)
    print("TICKER CHART POPUP DIALOG SHOWCASE")
    print("=" * 80)
    print(f"Launching interactive 3-month chart popup for: {ticker}")
    print(f"Component: {TickerChartPopupDialog.__name__}")
    print("Features:")
    print("  - Default 3-month timeframe display")
    print("  - Interactive timeframe switcher (1M, 3M, 6M, 1Y, All)")
    print("  - Candlestick price chart + Volume subplot")
    print("  - EMA 20 & EMA 50 overlay toggles")
    print("  - Metric summary: Latest Price, Period Return, Period High/Low")
    print("-" * 80)
    app = QApplication.instance() or QApplication(sys.argv)
    repo = MarketRepository()
    dialog = show_ticker_chart_popup(ticker=ticker, repo=repo)
    dialog.show()
    sys.exit(app.exec())


def example_screener_fetcher(ticker: str = "INFY.NS") -> None:
    """Showcase fundamental equity data extraction from Screener.in.

    Args:
        ticker (str): Ticker symbol to query. Defaults to 'INFY.NS'.
    """
    print("=" * 80)
    print("SCREENER.IN FUNDAMENTAL DATA FETCHER SHOWCASE")
    print("=" * 80)
    print(f"Fetching fundamental company metrics for: {ticker}")
    fetcher = ScreenerDataFetcher()
    data = fetcher.fetch_fundamentals(ticker)
    if data:
        print(f"Symbol:                   {data.symbol}")
        mcap = f"INR {data.market_cap_cr:,.2f} Cr" if data.market_cap_cr else "N/A"
        print(f"Market Cap (Cr):          {mcap}")
        print(f"Stock P/E:                {data.stock_pe}")
        roe_val = f"{data.roe * 100:.2f}%" if data.roe else "N/A"
        print(f"ROE:                      {roe_val}")
        inst_pct = data.institutional_ownership * 100 if data.institutional_ownership else None
        inst = f"{inst_pct:.2f}%" if inst_pct is not None else "N/A"
        print(f"Institutional Ownership:  {inst}")
        growth = f"{data.compounded_profit_growth}%" if data.compounded_profit_growth else "N/A"
        print(f"Compounded Profit Growth: {growth}")
        print(f"PEG Ratio:                {data.peg_ratio}")
        roce_val = f"{data.roce * 100:.2f}%" if data.roce else "N/A"
        print(f"ROCE:                     {roce_val}")
        div = f"{data.dividend_yield * 100:.2f}%" if data.dividend_yield else "N/A"
        print(f"Dividend Yield:           {div}")
        print(f"Data Source:              {data.source}")
    else:
        print(f"No fundamental records discovered for {ticker}.")
    print("-" * 80)


def example_bullish_kicker() -> None:
    """Showcase Bullish Kicker candlestick strategy with 10% target and 1% risk sizing."""
    print("=" * 80)
    print("BULLISH KICKER CANDLESTICK PATTERN STRATEGY SHOWCASE")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Setup Identification (Daily Charts):")
    print("     - Candle 1 (Day t-1): Decisive bearish candle (Close < Open).")
    print("     - Candle 2 (Day t): Gap-up open at/above Day 1 Open and decisive bullish close.")
    print("  2. Validating Strength:")
    print("     - High volume reversal (Volume > Day 1 Volume or >= 20-day SMA volume).")
    print("  3. Stop Loss & Position Sizing:")
    print("     - Stop Loss: Low of Candle 1 (Day t-1 low).")
    print("     - Position Sizing: Risk 1% of total portfolio capital per trade.")
    print("  4. Profit Target Exit:")
    print("     - Exit upon achieving 10.0% profit target.")
    print("-" * 80)

    repo = MarketRepository()
    strategy = BullishKicker(target_profit_pct=0.10)

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "ASIANPAINT.NS"]
    print("\n[1] Single-Security Backtest Sample (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<14} | {'Trades':<8} | {'Wins':<6} | {'Losses':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    engine = BacktestEngine(initial_capital=1_000_000.0)
    for ticker in sample_tickers:
        df = repo.get_data(ticker)
        if df.empty:
            continue
        signals_df = strategy.generate_signals(df)
        res = engine.run(signals_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        print(
            f"{ticker:<14} | {m['TotalTrades']:<8} | {m['Wins']:<6} | {m['Losses']:<8} | "
            f"{m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All Active Stocks, 10% Capital Allocation):")
    stocks_data = repo.get_all_stocks_data()
    print(f"Loaded price records for {len(stocks_data)} active stocks from database.")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine_portfolio = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    portfolio_results = engine_portfolio.run_portfolio(signals_dict)

    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Total Trades   : {pm['TotalTrades']}")
    print(f"  Winning Trades : {pm['Wins']}")
    print(f"  Losing Trades  : {pm['Losses']}")
    print(f"  Win Rate       : {pm['WinRatePct']:.1f} %")
    print(f"  Total PnL      : INR {pm['TotalPnL']:+,.2f} ({pm['TotalPnLPct']:+.2f}%)")
    print(f"  CAGR           : {pm['CAGRPct']:+.2f} %")
    print(f"  Final Capital  : INR {pm['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Exit Reasons Breakdown]:")
        for reason, count in trade_log["ExitReason"].value_counts().items():
            print(f"  - {reason:<22}: {count:>4} trades")

        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_bullish_outside_bar() -> None:
    """Showcase Bullish Outside Bar strategy with 20% target in 2-3 weeks."""
    print("=" * 80)
    print("BULLISH OUTSIDE BAR (ENGULFING) REVERSAL STRATEGY SHOWCASE")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Spotting the Setup (Preferred: Daily / Weekly Charts):")
    print("     - Prior downtrend of at least 6-10% over the lookback window.")
    print("     - Bar 1 (t-1): Bearish candle (Close < Open).")
    print("     - Bar 2 (t): Engulfs Bar 1 completely (High > High[1], Low < Low[1]).")
    print("  2. Validating Strength:")
    print("     - Reversal candle body >= 40% of its high-low range (decisive).")
    print("     - Close near the high: (Close - Low) / Range >= 60%.")
    print("     - Volume spike >= 20-bar volume SMA (adds conviction).")
    print("  3. Stop Loss & Position Sizing:")
    print("     - Stop Loss: Low of the reversal candle (Bar 2 low).")
    print("     - Position Sizing: Risk 1% of total portfolio capital per trade.")
    print("  4. Exit Plan:")
    print("     - Profit Target: 20.0% gain.")
    print("     - Time Exit: 2 to 3 weeks (15 trading days max holding).")
    print("-" * 80)

    repo = MarketRepository()
    strategy = BullishOutsideBar(target_profit_pct=0.20, max_holding_days=15)

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "ASIANPAINT.NS"]
    print("\n[1] Single-Security Backtest Sample (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<14} | {'Trades':<8} | {'Wins':<6} | {'Losses':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    engine = BacktestEngine(initial_capital=1_000_000.0)
    for ticker in sample_tickers:
        df = repo.get_daily_data(ticker)
        if df.empty:
            continue
        signals_df = strategy.generate_signals(df)
        res = engine.run(signals_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        print(
            f"{ticker:<14} | {m['TotalTrades']:<8} | {m['Wins']:<6} | {m['Losses']:<8} | "
            f"{m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All Active Stocks, 10% Capital Allocation):")
    stocks_data = repo.get_all_stocks_daily_data()
    print(f"Loaded price records for {len(stocks_data)} active stocks from database.")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine_portfolio = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    portfolio_results = engine_portfolio.run_portfolio(signals_dict)

    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Total Trades   : {pm['TotalTrades']}")
    print(f"  Winning Trades : {pm['Wins']}")
    print(f"  Losing Trades  : {pm['Losses']}")
    print(f"  Win Rate       : {pm['WinRatePct']:.1f} %")
    print(f"  Total PnL      : INR {pm['TotalPnL']:+,.2f} ({pm['TotalPnLPct']:+.2f}%)")
    print(f"  CAGR           : {pm['CAGRPct']:+.2f} %")
    print(f"  Final Capital  : INR {pm['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Exit Reasons Breakdown]:")
        for reason, count in trade_log["ExitReason"].value_counts().items():
            print(f"  - {reason:<22}: {count:>4} trades")

        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_all_stocks_backtest() -> None:
    """Showcase multi-stock portfolio strategy backtest across all stocks with 10% allocation."""
    print("=" * 80)
    print("MULTI-STOCK STRATEGY BACKTEST (ALL STOCKS - 10% CAPITAL ALLOCATION)")
    print("=" * 80)

    repo = MarketRepository()
    stocks_data = repo.get_all_stocks_data()
    print(f"Loaded price records for {len(stocks_data)} active stocks from database.")

    strategy = MovingAverageStochastic()
    print(f"Generating signals using strategy: {strategy.name}...")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    results = engine.run_portfolio(signals_dict)

    m = results["Metrics"]
    trade_log = results["TradeLog"]

    print("\n[Performance Metrics Summary]:")
    print(f"  Total Trades   : {m['TotalTrades']}")
    print(f"  Winning Trades : {m['Wins']}")
    print(f"  Losing Trades  : {m['Losses']}")
    print(f"  Win Rate       : {m['WinRatePct']:.1f} %")
    print(f"  Total PnL      : INR {m['TotalPnL']:+,.2f} ({m['TotalPnLPct']:+.2f}%)")
    print(f"  CAGR           : {m['CAGRPct']:+.2f} %")
    print(f"  Final Capital  : INR {m['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_fundamental_screener() -> None:
    """Showcase fundamental screening and Moving Average + Stochastic strategy execution."""
    print("=" * 80)
    print("MOVING AVERAGE + STOCHASTIC (FUNDAMENTALS -> TECHNICALS -> EXITS)")
    print("=" * 80)
    print("Strategy Flow:")
    print("  1. Run Fundamental Analysis:")
    print("     - PEG Ratio > 2.0")
    print("     - Debt to Equity < 0.50")
    print("     - Market Cap > 5,000 Cr INR")
    print("     - Beta vs Nifty 50 (^NSEI, 252d) > 1.2")
    print("     - Average Volume (252d) > 30,00,000 (3M)")
    print("     - Institutional Ownership >= 15%")
    print("     - ROE > 20% (Optional / Configurable)")
    print("  2. Run Technical Indicators:")
    print("     - 200-day Trend-following Moving Average")
    print("     - Stochastic Oscillator (8, 3, 3) oversold crossover (< 20)")
    print("  3. Stop Loss & Profit Target Execution:")
    print("     - Allow buy entry only when fundamentals pass")
    print("     - Stop Loss: 5-day swing low")
    print("     - Profit Target: Book profit when profit percentage is above 15.0%")
    print("-" * 80)

    repo = MarketRepository()
    screener = FundamentalScreener()

    sample_tickers = ["INFY.NS", "TCS.NS", "BSE.NS", "TRENT.NS", "HDFCBANK.NS"]

    print("\n[1] Fundamental Screening Evaluation:")
    header = (
        f"{'Ticker':<12} | {'MCap (Cr)':<10} | {'D/E':<5} | {'PEG':<5} | "
        f"{'Beta(^NSEI)':<11} | {'AvgVol(252d)':<12} | {'Inst%':<7} | {'Pass?'}"
    )
    print(header)
    print("-" * len(header))

    for ticker in sample_tickers:
        m = screener.analyze_ticker(ticker)
        mcap_str = f"{m.market_cap_cr:,.0f}" if m.market_cap_cr else "N/A"
        de_str = f"{m.debt_to_equity:.2f}" if m.debt_to_equity is not None else "N/A"
        peg_str = f"{m.peg_ratio:.2f}" if m.peg_ratio is not None else "N/A"
        beta_str = f"{m.beta_nsei:.2f}" if m.beta_nsei is not None else "N/A"
        vol_str = f"{int(m.avg_volume_252):,}" if m.avg_volume_252 else "N/A"
        inst_str = (
            f"{m.institutional_ownership * 100:.1f}%"
            if m.institutional_ownership
            else "N/A"
        )
        pass_str = "YES" if m.is_passing else "NO"

        print(
            f"{ticker:<12} | {mcap_str:<10} | {de_str:<5} | {peg_str:<5} | "
            f"{beta_str:<11} | {vol_str:<12} | {inst_str:<7} | {pass_str}"
        )

    print("\n[2] Moving Average + Stochastic Technical Backtest:")
    btest_header = (
        f"{'Ticker':<12} | {'Strategy':<32} | {'Trades':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(btest_header)
    print("-" * len(btest_header))

    strategy = MovingAverageStochastic()

    for ticker in sample_tickers[:3]:
        df = repo.get_data(ticker)
        if df.empty:
            continue

        signals_df = strategy.generate_signals(df)
        engine = BacktestEngine()
        results = engine.run(signals_df, ticker=ticker)
        m = results['Metrics']

        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"

        print(
            f"{ticker:<12} | {'Moving Average + Stochastic':<32} | "
            f"{m['TotalTrades']:<8} | {m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
        print("-" * len(btest_header))


def example_rsi_indicator() -> None:
    """Showcase RSI (Relative Strength Index) technical indicator calculation and analysis."""
    print("=" * 80)
    print("RELATIVE STRENGTH INDEX (RSI) INDICATOR SHOWCASE")
    print("=" * 80)
    print("Indicator Overview:")
    print("  - Formula: RSI = 100 - (100 / (1 + RS)), where RS = Avg Gain / Avg Loss")
    print("  - Smoothing: Wilder's Exponential Smoothing (Lookback: 14 periods)")
    print("  - Overbought Threshold: RSI >= 70 (Potential bearish reversal / exhaustion)")
    print("  - Oversold Threshold: RSI <= 30 (Potential bullish rebound / accumulation)")
    print("-" * 80)

    repo = MarketRepository()
    sample_tickers = [
        "INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "^NSEI",
    ]

    print("\n[1] Sample Securities Current RSI (14-Period, 70/30 Thresholds):")
    header = (
        f"{'Ticker':<14} | {'Latest Price':<14} | {'RSI (14)':<10} | "
        f"{'Signal Status':<16} | {'Condition'}"
    )
    print(header)
    print("-" * len(header))

    for ticker in sample_tickers:
        display_ticker = f"{ticker} (INDEX)" if ticker.startswith("^") else f"{ticker} (STOCK)"
        df = repo.get_data(display_ticker)
        if df.empty:
            continue

        res = analyze_rsi(df, period=14, overbought=70, oversold=30)
        latest_price = df['close'].iloc[-1]
        rsi_val = res['current_rsi']
        status = res['status']

        rsi_str = f"{rsi_val:.2f}" if rsi_val is not None else "N/A"
        price_str = f"INR {latest_price:,.2f}"

        if status == "Overbought":
            condition = "Caution: Overextended Upwards"
        elif status == "Oversold":
            condition = "Opportunity: Dip Reversal Watch"
        else:
            condition = "Neutral Momentum Zone"

        print(
            f"{ticker:<14} | {price_str:<14} | {rsi_str:<10} | "
            f"{status:<16} | {condition}"
        )
    print("-" * len(header))


def example_adx_indicator() -> None:
    """Showcase ADX (Average Directional Index) trend strength & directional movement."""
    print("=" * 80)
    print("AVERAGE DIRECTIONAL INDEX (ADX) & DIRECTIONAL MOVEMENT SYSTEM")
    print("=" * 80)
    print("Indicator Overview:")
    print("  - ADX Trend Strength: ADX >= 25 (Strong Trend), ADX < 20 (Weak / Ranging)")
    print("  - Directional Bias: +DI > -DI (Bullish Dominance), -DI > +DI (Bearish Dominance)")
    print("  - Smoothing: Wilder's Exponential Smoothing (Lookback: 14 periods)")
    print("-" * 80)

    repo = MarketRepository()
    sample_tickers = [
        "INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "^NSEI",
    ]

    print("\n[1] Sample Securities Current ADX, +DI, and -DI (14-Period, Trend Threshold: 25):")
    header = (
        f"{'Ticker':<14} | {'ADX (14)':<10} | {'+DI':<8} | {'-DI':<8} | "
        f"{'Trend Strength':<18} | {'Directional Bias'}"
    )
    print(header)
    print("-" * len(header))

    for ticker in sample_tickers:
        display_ticker = f"{ticker} (INDEX)" if ticker.startswith("^") else f"{ticker} (STOCK)"
        df = repo.get_data(display_ticker)
        if df.empty:
            continue

        res = analyze_adx(df, period=14, threshold=25)
        adx_val = res['current_adx']
        pos_di = res['current_pos_di']
        neg_di = res['current_neg_di']
        strength = res['trend_strength']
        bias = res['directional_bias']

        adx_str = f"{adx_val:.2f}" if adx_val is not None else "N/A"
        pos_str = f"{pos_di:.2f}" if pos_di is not None else "N/A"
        neg_str = f"{neg_di:.2f}" if neg_di is not None else "N/A"

        print(
            f"{ticker:<14} | {adx_str:<10} | {pos_str:<8} | {neg_str:<8} | "
            f"{strength:<18} | {bias}"
        )
    print("-" * len(header))


def example_morning_scanner(
    lookback_months: int = 6,
    trigger_scope: str = "previous_day",
) -> None:
    """Showcase TradeBot Morning Scanner for pre-market buy and sell signal detection.

    Demonstrates:
    1. Evaluating open positions and detecting SELL signals when required profit
       target or stop loss is reached on previous close.
    2. Scanning universe for BUY signals triggered across registered strategies.
    3. Conservative multi-strategy confluence selection: choosing the strategy
       with the least profit to define both Stop Loss and Take Profit levels.

    Args:
        lookback_months (int): Historical window (3 to 6 months) for indicator warm-up.
        trigger_scope (str): 'last_bar' (strict close) or 'previous_day' (full day session).
    """
    scope_label = (
        "Previous Close Bar (Strict 15:15)"
        if trigger_scope == "last_bar"
        else "Previous Trading Day (Full Session)"
    )
    print("=" * 105)
    print("TRADEBOT MORNING SCANNER - PRE-MARKET BUY & SELL SIGNALS")
    print("=" * 105)
    print("Scanner Architecture & Rules:")
    print("  1. Universe: All 50 active equity stocks from database (excluding market indices).")
    print(f"  2. Indicator Warm-up: Past {lookback_months} months of historical data used.")
    print(f"  3. Trigger Scope: {scope_label}.")
    print(
        "  4. Open Position Monitoring: Checks active trades; "
        "signals SELL when profit target hit."
    )
    print("  5. Least-Profit Confluence: When multiple strategies trigger BUY, selects the setup")
    print(
        "     yielding the lowest profit target to derive conservative "
        "Stop Loss and Take Profit."
    )
    print("-" * 105)

    scanner = MorningScanner()
    results = scanner.scan(
        lookback_months=lookback_months,
        trigger_scope=trigger_scope,
    )

    if not results:
        print("No stock price records found to scan.")
        return

    # Aggregate KPI summary metrics
    total_scanned = len(results)
    sell_stocks = [r for r in results if r["indicator"] == "SELL"]
    buy_stocks = [r for r in results if r["indicator"] in ("BUY", "STRONG BUY")]
    confluence_stocks = [r for r in results if r["confluence_count"] >= 2]
    prev_close_date = results[0]["prev_close_date"] if results else "N/A"

    print(f"\n[1] Scan Summary Metrics (Session Close: {prev_close_date}):")
    print(f"  - Total Equities Evaluated     : {total_scanned} stocks")
    print(f"  - Sell Signals (Profit Target) : {len(sell_stocks)} position(s)")
    print(f"  - Buy Signals (Prev Close)     : {len(buy_stocks)} stocks")
    print(
        f"  - Multi-Strategy Confluence    : {len(confluence_stocks)} stocks "
        "(confirmed by 2+ strategies)"
    )

    # Section 2: Actionable SELL signals for open positions reaching required profit
    print(f"\n[2] Actionable SELL Signals for Open Positions ({len(sell_stocks)} Positions):")
    sell_header = (
        f"{'Ticker':<14} | {'Indicator':<24} | {'Prev Close':<12} | "
        f"{'Target / SL':<14} | {'Target Action / Exit Guidance'}"
    )
    print(sell_header)
    print("-" * len(sell_header))

    if not sell_stocks:
        print("No open positions have reached their required profit target or stop loss.")
    else:
        for r in sell_stocks:
            ticker = r["ticker"]
            badge = r["indicator_badge"]
            close_str = f"INR {r['prev_close_price']:>7.2f}"
            tp_str = f"INR {r['take_profit']:>7.2f}" if r["take_profit"] else "N/A"
            action_str = r["target_action"]
            print(
                f"{ticker:<14} | {badge:<24} | {close_str:<12} | "
                f"{tp_str:<14} | {action_str}"
            )
    print("-" * len(sell_header))

    # Section 3: Display stocks triggering BUY signals on previous close
    print(f"\n[3] Actionable Stocks Triggering BUY on Previous Close ({len(buy_stocks)} Stocks):")
    buy_header = (
        f"{'Ticker':<14} | {'Indicator':<18} | {'Prev Close':<12} | "
        f"{'Stop Loss':<12} | {'Take Profit':<14} | {'Triggered Strategies'}"
    )
    print(buy_header)
    print("-" * len(buy_header))

    if not buy_stocks:
        print("No stocks triggered a buy signal on the previous close.")
    else:
        for r in buy_stocks:
            ticker = r["ticker"]
            badge = r["indicator_badge"]
            close_str = f"INR {r['prev_close_price']:>7.2f}"
            sl_str = f"INR {r['stop_loss']:>7.2f}" if r["stop_loss"] else "N/A"
            tp_str = (
                f"INR {r['take_profit']:>7.2f}"
                if r["take_profit"]
                else "N/A"
            )
            strats = r["strategies_str"]
            print(
                f"{ticker:<14} | {badge:<18} | {close_str:<12} | "
                f"{sl_str:<12} | {tp_str:<14} | {strats}"
            )
    print("-" * len(buy_header))

    # Section 4: Sample breakdown showing strategy evaluation and least-profit attribution
    if buy_stocks:
        sample_stock = buy_stocks[0]
        sym = sample_stock['ticker']
        s_name = sample_stock['name']
        chosen = sample_stock.get('chosen_strategy')
        print(f"\n[4] Strategy Verification Sample for {sym} ({s_name}):")
        if chosen and sample_stock['confluence_count'] >= 2:
            print(f"    * Chosen Conservative Strategy (Least Profit): {chosen}")
        for st_name, s_info in sample_stock["strategy_details"].items():
            triggered_status = "TRIGGERED [BUY]" if s_info["is_buy"] else "NO SIGNAL"
            sl_info = (
                f" | SL: INR {s_info['stop_loss']:,.2f}"
                if s_info.get("stop_loss")
                else ""
            )
            tp_info = (
                f" | TP: INR {s_info['take_profit']:,.2f}"
                if s_info.get("take_profit")
                else ""
            )
            selected_note = " <== (SELECTED: LEAST PROFIT)" if st_name == chosen else ""
            print(f"    * {st_name:<48}: {triggered_status}{sl_info}{tp_info}{selected_note}")


def example_adx_ema_swing() -> None:
    """Showcase Linda Raschke's ADX + 20 EMA swing trading strategy (The Holy Grail)."""
    print("=" * 80)
    print("LINDA RASCHKE'S ADX + 20 EMA SWING STRATEGY (THE HOLY GRAIL) SHOWCASE")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Trend & Momentum Identification (Daily OHLCV):")
    print("     - 14-period ADX > 30 and rising into the move.")
    print("     - Trend direction: +DMI > -DMI for Long, -DMI > +DMI for Short.")
    print("     - 20-period EMA defines baseline trend support/resistance.")
    print("  2. Setup Bar (The Retracement):")
    print("     - Long: Price retraces and touches 20 EMA (Low <= 20 EMA).")
    print("     - Short: Price rallies and touches 20 EMA (High >= 20 EMA).")
    print("  3. Entry Trigger (Breakout of Touch Candle):")
    print("     - Long: Enter Long on break above EMA-touch candle high.")
    print("     - Short: Enter Short on break below EMA-touch candle low.")
    print("  4. Stop-Loss & Position Sizing:")
    print("     - Stop-Loss: Placed at recent swing low (Long) or recent swing high (Short).")
    print("     - Position Sizing: Risk exactly 1% of portfolio capital per trade.")
    print("  5. Multi-Condition Exits:")
    print("     - Stop-Loss: Intraday protection against adverse reversal.")
    print("     - 2R Target: Profit target exit at 2 x Initial Risk (R).")
    print("     - ADX < 30: Trend momentum dissipation signal.")
    print("     - 20 EMA Break: Close below 20 EMA (Long) or close above 20 EMA (Short).")
    print("-" * 80)

    repo = MarketRepository()
    strategy = AdxEmaSwingStrategy()
    backtester = AdxEmaBacktester(strategy=strategy, initial_capital=1_000_000.0)

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "TCS.NS", "SBIN.NS", "BHARTIARTL.NS", "RELIANCE.NS"]
    print("\n[1] Single-Security Backtest Samples (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<13} | {'Trades':<6} | {'Long':<4} | {'Short':<5} | "
        f"{'Wins':<4} | {'Losses':<6} | {'Win Rate':<8} | {'Total PnL (INR)':<15} | {'PF':<5}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    for ticker in sample_tickers:
        daily_df = repo.get_daily_data(ticker)
        if daily_df.empty:
            continue
        res = backtester.run(daily_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>10,.2f}"
        print(
            f"{ticker:<13} | {m['TotalTrades']:<6} | {m['LongTrades']:<4} | "
            f"{m['ShortTrades']:<5} | {m['Wins']:<4} | {m['Losses']:<6} | "
            f"{m['WinRatePct']:<7.1f}% | {pnl_str:<15} | {m['ProfitFactor']:<5.2f}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all active stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All 50 Nifty Stocks, Daily OHLCV):")
    stocks_daily = repo.get_all_stocks_daily_data()
    print(f"Loaded daily OHLCV datasets for {len(stocks_daily)} stocks from database.")

    def cli_progress_tracker(current: int, total: int, ticker: str) -> None:
        pct = float(current) / total
        bar_len = 28
        filled = int(bar_len * pct)
        bar = "=" * filled + "-" * (bar_len - filled)
        print(
            f"\r  Progress: [{bar}] {pct * 100:>5.1f}% ({current:>2}/{total}) - {ticker:<14}",
            end="",
            flush=True,
        )
        if current == total:
            print()

    portfolio_results = backtester.run_portfolio(
        stocks_daily, progress_callback=cli_progress_tracker
    )
    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Starting Capital : INR {pm['InitialCapital']:,.2f}")
    print(f"  Final Capital    : INR {pm['FinalCapital']:,.2f}")
    print(f"  Total PnL        : INR {pm['TotalPnL']:+,.2f} ({pm['TotalReturnPct']:+.2f}%)")
    print(f"  Total Trades     : {pm['TotalTrades']}")
    print(f"  Long Trades      : {pm['LongTrades']}")
    print(f"  Short Trades     : {pm['ShortTrades']}")
    print(f"  Winning Trades   : {pm['Wins']}")
    print(f"  Losing Trades    : {pm['Losses']}")
    print(f"  Win Rate         : {pm['WinRatePct']:.1f} %")
    print(f"  Profit Factor    : {pm['ProfitFactor']:.2f}")
    print(f"  Average Win      : INR {pm['AverageWin']:,.2f}")
    print(f"  Average Loss     : INR {pm['AverageLoss']:,.2f}")
    print(f"  Win / Loss Ratio : {pm['WinLossRatio']:.2f}")
    print(f"  Average R-Mult   : {pm['AverageR']:+.2f} R")
    print(f"  Max Drawdown     : INR {pm['MaxDrawdown']:,.2f} ({pm['MaxDrawdownPct']:.2f}%)")

    if not trade_log.empty:
        print("\n[Exit Reasons Breakdown]:")
        for reason, count in pm["ExitReasons"].items():
            print(f"  - {reason:<22}: {count:>4} trades")

        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "TradeID", "Security", "Type", "EntryDate", "ExitDate",
            "PositionSize", "EntryPrice", "ExitPrice", "PnL", "RMultiple", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_dual_moving_average_adx() -> None:
    """Showcase Dual Moving Average & Volatility Filter (Conservative Trend Follower)."""
    print("=" * 80)
    print("DUAL MOVING AVERAGE & VOLATILITY FILTER (THE CONSERVATIVE TREND FOLLOWER)")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Indicators Needed:")
    print("     - 20-day Exponential Moving Average (EMA)")
    print("     - 50-day Exponential Moving Average (EMA)")
    print("     - 14-day Average Directional Index (ADX)")
    print("  2. Buy Trigger:")
    print("     - 20 EMA crosses above 50 EMA (Bullish Crossover)")
    print("     - AND 14-day ADX is above 20 (indicating trend strength)")
    print("  3. Stop Loss:")
    print("     - Lowest price of recent swing low, or hard 5% below entry price")
    print("       to absorb overnight equity gaps.")
    print("  4. Sell / Exit Signal:")
    print("     - 20 EMA crosses back below 50 EMA (Bearish Crossover)")
    print("     - OR price hits a fixed 1:2 risk-to-reward target (2R profit).")
    print("  5. Position Sizing:")
    print("     - Risk exactly 1% of total portfolio capital per trade.")
    print("-" * 80)

    repo = MarketRepository()
    strategy = DualMovingAverageAdx()

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
    print("\n[1] Single-Security Backtest Sample (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<14} | {'Trades':<8} | {'Wins':<6} | {'Losses':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    engine = BacktestEngine(initial_capital=1_000_000.0)
    for ticker in sample_tickers:
        df = repo.get_daily_data(ticker)
        if df.empty:
            continue
        signals_df = strategy.generate_signals(df)
        res = engine.run(signals_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        print(
            f"{ticker:<14} | {m['TotalTrades']:<8} | {m['Wins']:<6} | {m['Losses']:<8} | "
            f"{m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All Active Stocks, 10% Capital Allocation):")
    stocks_data = repo.get_all_stocks_daily_data()
    print(f"Loaded daily price records for {len(stocks_data)} active stocks from database.")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine_portfolio = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    portfolio_results = engine_portfolio.run_portfolio(signals_dict)

    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Total Trades   : {pm['TotalTrades']}")
    print(f"  Winning Trades : {pm['Wins']}")
    print(f"  Losing Trades  : {pm['Losses']}")
    print(f"  Win Rate       : {pm['WinRatePct']:.1f} %")
    print(f"  Total Net PnL  : INR {pm['TotalPnL']:,.2f} ({pm['TotalPnLPct']:+.2f}%)")
    print(f"  CAGR           : {pm['CAGRPct']:+.2f} %")
    print(f"  Final Capital  : INR {pm['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_rsi_bull_trend_pullback() -> None:
    """Showcase RSI Pullback in a Bull Trend strategy (200 SMA + RSI 40-70 + 15d)."""
    print("=" * 80)
    print("RSI PULLBACK IN A BULL TREND STRATEGY SHOWCASE")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Indicators Needed:")
    print("     - 200-day Simple Moving Average (SMA) for structural trend.")
    print("     - 14-period Relative Strength Index (RSI).")
    print("  2. Buy Trigger:")
    print("     - Closing price must be completely above 200 SMA (Structural Bull Market).")
    print("     - 14-day RSI drops below 40 (Oversold pullback in uptrend).")
    print("     - Buy on next candle's open as soon as RSI crosses back above 40.")
    print("  3. Stop Loss:")
    print("     - Lower of the last 5 days' price low, or a close below the 200 SMA.")
    print("  4. Sell / Exit Signal:")
    print("     - Exit when RSI reaches overbought zone of 70 (RSI >= 70).")
    print("     - OR after a maximum holding period of 15 trading days.")
    print("     - OR structural breakdown (close < 200 SMA).")
    print("  5. Position Sizing:")
    print("     - Risk exactly 1% of total portfolio capital per trade.")
    print("-" * 80)

    repo = MarketRepository()
    strategy = RsiBullTrendPullback()

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
    print("\n[1] Single-Security Backtest Sample (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<14} | {'Trades':<8} | {'Wins':<6} | {'Losses':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    engine = BacktestEngine(initial_capital=1_000_000.0)
    for ticker in sample_tickers:
        df = repo.get_daily_data(ticker)
        if df.empty:
            continue
        signals_df = strategy.generate_signals(df)
        res = engine.run(signals_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        print(
            f"{ticker:<14} | {m['TotalTrades']:<8} | {m['Wins']:<6} | {m['Losses']:<8} | "
            f"{m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All Active Stocks, 10% Capital Allocation):")
    stocks_data = repo.get_all_stocks_daily_data()
    print(f"Loaded daily price records for {len(stocks_data)} active stocks from database.")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine_portfolio = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    portfolio_results = engine_portfolio.run_portfolio(signals_dict)

    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Total Trades   : {pm['TotalTrades']}")
    print(f"  Winning Trades : {pm['Wins']}")
    print(f"  Losing Trades  : {pm['Losses']}")
    print(f"  Win Rate       : {pm['WinRatePct']:.1f} %")
    print(f"  Total Net PnL  : INR {pm['TotalPnL']:,.2f}")
    print(f"  Final Capital  : INR {pm['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_bollinger_stoch_rsi() -> None:
    """Showcase Mean Reversion via Bollinger Bands & Stochastic RSI strategy."""
    print("=" * 80)
    print("MEAN REVERSION VIA BOLLINGER BANDS & STOCHASTIC RSI SHOWCASE")
    print("=" * 80)
    print("Strategy Checklist Rules:")
    print("  1. Indicators Needed:")
    print("     - Bollinger Bands (20-period SMA, 2.0 Standard Deviations).")
    print("     - Stochastic RSI (14-period RSI, 14-period Stoch, %K 3, %D 3).")
    print("     - Average True Range (14-period ATR) for risk control.")
    print("  2. Buy Trigger:")
    print("     - Price touches or closes below Lower Bollinger Band (low <= BB_Lower).")
    print("     - Stochastic RSI %K crosses above %D below 20 level (Oversold territory).")
    print("     - Execute entry on next candle's open.")
    print("  3. Stop Loss:")
    print("     - Strict stop loss at 1.5 ATR below entry setup candle low.")
    print("  4. Sell / Exit Signal:")
    print("     - Price touches or crosses Middle Bollinger Band (20 SMA mean).")
    print("     - OR Stochastic RSI %K crosses below %D above 80 level.")
    print("     - OR Stop Loss hit.")
    print("  5. Position Sizing:")
    print("     - Risk exactly 1% of total portfolio capital per trade.")
    print("-" * 80)

    repo = MarketRepository()
    strategy = BollingerStochRsi()

    # 1. Single-Security Samples
    sample_tickers = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
    print("\n[1] Single-Security Backtest Sample (INR 1,000,000 Capital, 1% Risk):")
    sample_header = (
        f"{'Ticker':<14} | {'Trades':<8} | {'Wins':<6} | {'Losses':<8} | "
        f"{'Win Rate':<10} | {'Total PnL (INR)':<16}"
    )
    print(sample_header)
    print("-" * len(sample_header))

    engine = BacktestEngine(initial_capital=1_000_000.0)
    for ticker in sample_tickers:
        df = repo.get_daily_data(ticker)
        if df.empty:
            continue
        signals_df = strategy.generate_signals(df)
        res = engine.run(signals_df, ticker=ticker)
        m = res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        print(
            f"{ticker:<14} | {m['TotalTrades']:<8} | {m['Wins']:<6} | {m['Losses']:<8} | "
            f"{m['WinRatePct']:<9.1f}% | {pnl_str}"
        )
    print("-" * len(sample_header))

    # 2. Multi-Stock Portfolio Backtest across all stocks
    print("\n[2] Multi-Stock Portfolio Backtest (All Active Stocks, 10% Capital Allocation):")
    stocks_data = repo.get_all_stocks_daily_data()
    print(f"Loaded daily price records for {len(stocks_data)} active stocks from database.")

    signals_dict = {}
    for ticker, df in stocks_data.items():
        signals_dict[ticker] = strategy.generate_signals(df)

    engine_portfolio = BacktestEngine(
        initial_capital=1_000_000.0,
        allocation_fraction=0.10,
    )
    portfolio_results = engine_portfolio.run_portfolio(signals_dict)

    pm = portfolio_results["Metrics"]
    trade_log = portfolio_results["TradeLog"]

    print("\n[Portfolio Performance Metrics Summary]:")
    print(f"  Total Trades   : {pm['TotalTrades']}")
    print(f"  Winning Trades : {pm['Wins']}")
    print(f"  Losing Trades  : {pm['Losses']}")
    print(f"  Win Rate       : {pm['WinRatePct']:.1f} %")
    print(f"  Total Net PnL  : INR {pm['TotalPnL']:,.2f}")
    print(f"  Final Capital  : INR {pm['FinalCapital']:,.2f}")

    if not trade_log.empty:
        print("\n[Recent Trades Sample (Last 10)]:")
        display_cols = [
            "Security", "EntryDate", "ExitDate", "PositionSize",
            "EntryPrice", "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
        ]
        sample_df = trade_log[display_cols].tail(10)
        print(sample_df.to_string(index=False))


def example_paper_trading() -> None:
    """Showcase Paper Trading Engine with 1% risk position sizing and live monitoring."""
    print("=" * 80)
    print("PAPER TRADING ENGINE - NIFTY 50 SWING TRADING SHOWCASE")
    print("=" * 80)
    print("Core Rules & Framework:")
    print("  1. Virtual Starting Capital : INR 5,00,000.00 (SQLite 'paper_portfolio')")
    print("  2. Risk per Trade           : Strictly 1% of INR 1,00,000 baseline = INR 1,000.00")
    print("  3. Deployment Cap           : Maximum INR 1,00,000 per trade (or remaining cash)")
    print("  4. Position Sizing Formula  : Quantity = Risk / (Entry - Stop Loss)")
    print("  5. Real-time Monitoring     : Auto-exit when CMP <= Stop Loss or CMP >= Target")
    print("-" * 80)

    engine = PaperTradingEngine()
    summary = engine.get_portfolio_summary()
    print("\n[1] Portfolio State (Database: tradebot.db):")
    print(f"  Available Cash Balance : INR {summary['cash_balance']:>12,.2f}")
    print(f"  Open Positions Value   : INR {summary['open_positions_value']:>12,.2f}")
    print(f"  Total Realized PnL     : INR {summary['total_realized_pnl']:>12,.2f}")
    print(f"  Total Portfolio Worth  : INR {summary['total_portfolio_value']:>12,.2f}")

    print("\n[2] Position Sizing Verification Test Cases:")
    test_cases = [
        {"desc": "Exact Specification Case", "entry": 280.0, "sl": 260.0, "target": 320.0},
        {"desc": "Capital Cap Constraint", "entry": 50.0, "sl": 49.9, "target": 55.0},
        {"desc": "Large Cap Stock (TCS)", "entry": 3200.0, "sl": 3100.0, "target": 3450.0},
        {"desc": "Mid-Range Stock (Reliance)", "entry": 1280.0, "sl": 1250.0, "target": 1340.0},
    ]

    header = (
        f"{'Scenario':<26} | {'Entry':<8} | {'SL':<8} | {'Target':<8} | "
        f"{'Qty':<5} | {'Capital':<13} | {'Risk (INR)':<10} | {'Capped By':<14}"
    )
    print(header)
    print("-" * len(header))

    for tc in test_cases:
        s = engine.calculate_position_size(tc["entry"], tc["sl"])
        print(
            f"{tc['desc']:<26} | {tc['entry']:<8.2f} | {tc['sl']:<8.2f} | "
            f"{tc['target']:<8.2f} | {s['allowed_quantity']:<5} | "
            f"INR {s['capital_required']:<9,.2f} | {s['actual_risk']:<10.2f} | {s['capped_by']:<14}"
        )
    print("-" * len(header))

    print("\n[3] Live Market Quote Fetching via yfinance (Sample Nifty 50 Equities):")
    sample_symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    quotes = engine.fetch_live_quotes_batch(sample_symbols)
    for sym in sample_symbols:
        q = quotes.get(sym)
        q_str = f"INR {q:,.2f}" if q else "Unavailable (Market Closed / Offline)"
        print(f"  {sym:<14} -> Last Traded / Close: {q_str}")

    print("\n[4] Active Open Positions Summary:")
    open_trades = engine.get_open_trades()
    if open_trades:
        print(f"  {len(open_trades)} active open position(s) currently being monitored:")
        for t in open_trades:
            print(
                f"  Trade #{t['trade_id']}: {t['quantity']} {t['ticker']} @ "
                f"INR {t['entry_price']:,.2f} | CMP: INR {t['current_price']:,.2f} | "
                f"SL: {t['stop_loss']:,.2f} | Unrealized PnL: INR {t['unrealized_pnl']:,.2f}"
            )
    else:
        print("  No open positions currently in database.")

    print("\n[5] Trade History Journal Sample (Last 5 Closed):")
    history = engine.get_trade_history()
    if history:
        for t in history[:5]:
            print(
                f"  Trade #{t['trade_id']}: {t['ticker']} | Qty: {t['quantity']} | "
                f"Entry: INR {t['entry_price']:,.2f} | Exit: INR {t['exit_price']:,.2f} | "
                f"Realized PnL: INR {t['realized_pnl']:,.2f} ({t.get('exit_reason')})"
            )
    else:
        print("  No closed trades recorded yet.")

    print("\n[Paper Trading Dashboard Graphical UI]:")
    print("  Launch desktop app using 'python main.py' to access the interactive")
    print("  'Paper Trading' tab with real-time yfinance monitor and one-click order execution.")
    print("=" * 80)


def example_paper_trading_enhancements() -> None:
    """Showcase paper trading enhancements: searchable security, SL/target modification,
    and partial selling.
    """
    print("=" * 85)
    print("PAPER TRADING ENHANCEMENTS SHOWCASE")
    print("=" * 85)
    print("Enhancements Implemented:")
    print("  1. Interactive Stock Search by Typing: Substring/contains filtering across Nifty 50.")
    print("  2. Open Position Modification: Update Stop Loss and Target with live risk preview.")
    print("  3. Partial Position Selling: Sell partial quantities, credit capital, and record PnL.")
    print("-" * 85)

    engine = PaperTradingEngine()

    # Part 1: Stock Search Simulation
    print("\n[1] Substring / Contains Search across Nifty 50 Securities:")
    search_queries = ["tata", "sbi", "reliance", "infy", "motor"]
    all_stocks = engine.get_nifty50_tickers()
    for q in search_queries:
        matches = [
            s
            for s in all_stocks
            if q.upper() in s["ticker"].upper() or q.upper() in s.get("name", "").upper()
        ]
        sample_str = ", ".join([f"{m['ticker']} ({m['name']})" for m in matches[:3]])
        print(f"  Search '{q:<8}' -> Found {len(matches):>2} match(es): {sample_str}")

    # Part 2: Place a temporary showcase trade
    print("\n[2] Executing a Controlled Showcase Trade (INFY.NS):")
    initial_cash = engine.get_cash_balance()
    ticker = "INFY.NS"
    entry_price = 1800.00
    stop_loss = 1750.00
    sell_target = 1950.00
    order = engine.place_order(
        ticker=ticker,
        entry_price=entry_price,
        stop_loss=stop_loss,
        sell_target=sell_target,
        override_quantity=100,
    )
    trade_id = order["trade_id"]
    print(
        f"  Opened Trade #{trade_id}: {order['quantity']} shares of {order['ticker']} "
        f"@ INR {order['entry_price']:,.2f} "
        f"(SL: INR {order['stop_loss']:,.2f}, Target: INR {order['sell_target']:,.2f})"
    )
    print(f"  Initial Trade Capital : INR {order['total_cost']:,.2f}")
    print(f"  Remaining Cash        : INR {order['remaining_cash']:,.2f}")

    # Part 3: Modify Stop Loss and Target
    print("\n[3] Modifying Stop Loss & Target on Active Trade:")
    new_sl = 1780.00
    new_target = 2000.00
    mod_res = engine.update_trade_sl_and_target(
        trade_id=trade_id,
        stop_loss=new_sl,
        sell_target=new_target,
    )
    print(
        f"  Trade #{trade_id} Updated Successfully:\n"
        f"    Old SL: INR {stop_loss:,.2f}  ->  New Trailing SL: INR {mod_res['stop_loss']:,.2f}\n"
        f"    Old Target: INR {sell_target:,.2f}  ->  New Target: INR {mod_res['sell_target']:,.2f}"
    )

    # Part 4: Execute Partial Sell (Sell 40 shares at profit price 1850.00)
    print("\n[4] Executing Partial Sale (Tranche 1: Sell 40 Shares at INR 1,850.00):")
    partial_res = engine.partial_close_trade(
        trade_id=trade_id,
        sell_quantity=40,
        exit_price=1850.00,
        exit_reason="PARTIAL_PROFIT_TAKING",
    )
    print(f"  Sold Quantity         : {partial_res['sold_quantity']} shares")
    print(f"  Exit Execution Price  : INR {partial_res['exit_price']:,.2f}")
    print(
        f"  Realized PnL          : INR {partial_res['realized_pnl']:+,.2f} "
        f"({partial_res['return_pct']:+.2f}%)"
    )
    print(f"  Capital Returned      : INR {partial_res['capital_returned']:,.2f}")
    print(f"  Remaining Active Qty  : {partial_res['remaining_quantity']} shares")
    print(f"  Updated Portfolio Cash: INR {partial_res['updated_cash']:,.2f}")
    print(f"  Closed Tranche ID     : Trade #{partial_res['closed_trade_id']}")

    # Part 5: Execute Final Close of Remaining 60 shares
    print("\n[5] Executing Final Liquidation of Remaining 60 Shares at INR 1,880.00:")
    final_res = engine.partial_close_trade(
        trade_id=trade_id,
        sell_quantity=60,
        exit_price=1880.00,
        exit_reason="FINAL_TARGET_EXIT",
    )
    print(f"  Closed Final Qty      : {final_res['quantity']} shares")
    print(f"  Exit Execution Price  : INR {final_res['exit_price']:,.2f}")
    print(
        f"  Realized PnL          : INR {final_res['realized_pnl']:+,.2f} "
        f"({final_res['return_pct']:+.2f}%)"
    )
    print(f"  Final Updated Cash    : INR {final_res['updated_cash']:,.2f}")

    print("\n[6] Portfolio Summary State Verification:")
    summary = engine.get_portfolio_summary()
    print(f"  Available Cash        : INR {summary['cash_balance']:>12,.2f}")
    print(f"  Open Positions Value  : INR {summary['open_positions_value']:>12,.2f}")
    print(f"  Total Realized PnL    : INR {summary['total_realized_pnl']:>12,.2f}")
    print(f"  Total Portfolio Worth : INR {summary['total_portfolio_value']:>12,.2f}")

    # Part 7: Cleanup Showcase Data to Preserve Database Integrity
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM paper_trades WHERE trade_id IN (?, ?)",
            (trade_id, partial_res['closed_trade_id']),
        )
        cursor.execute(
            "UPDATE paper_portfolio SET cash_balance = ? WHERE id = 1",
            (initial_cash,),
        )
        conn.commit()
    print("\n[7] Showcase Cleanup:")
    print(f"  Demonstration trades removed; cash preserved at INR {initial_cash:,.2f}.")
    print("=" * 85)


def example_paper_trading_cagr() -> None:
    """Showcase Paper Trading Entry/Exit dates persistence and CAGR calculation.

    Demonstrates:
    1. Database schema migration: Verification of entry_date and exit_date columns.
    2. Preservation of existing records: Open positions defaulted to today's date.
    3. Order placement and closure: Recording entry_date and exit_date on new orders.
    4. Individual Trade CAGR: Holding duration in calendar days and annualized returns.
    5. Overall Portfolio CAGR: Seed capital vs net portfolio value evaluation.
    """
    print("=" * 90)
    print("PAPER TRADING ENTRY/EXIT DATES & CAGR SHOWCASE")
    print("=" * 90)
    print("Key Highlights:")
    print("  1. Schema Updates          : 'entry_date' and 'exit_date' columns in 'paper_trades'")
    print("  2. Existing Records        : Preserved; open positions defaulted to today's date")
    print("  3. Holding Duration        : Exact calendar days computed for trades")
    print("  4. CAGR Calculation        : Annualized Compound Growth Rate for trades and portfolio")
    print("-" * 90)

    engine = PaperTradingEngine()

    # Part 1: Schema Verification
    print("\n[1] Database Schema Verification (table: 'paper_trades'):")
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(paper_trades)")
        columns = [row["name"] for row in cursor.fetchall()]
        print(f"  Total Columns: {len(columns)}")
        print(f"  'entry_date' Present: {'entry_date' in columns}")
        print(f"  'exit_date' Present : {'exit_date' in columns}")

    # Part 2: Existing Open Positions Verification
    print("\n[2] Existing Open Positions in Database (Preserved with Default Entry Date):")
    open_trades = engine.get_open_trades()
    print(f"  Found {len(open_trades)} active open position(s):")
    for t in open_trades:
        print(
            f"  Trade #{t['trade_id']}: {t['quantity']} shares of {t['ticker']} | "
            f"Entry Date: {t['entry_date']} | Holding Days: {t['holding_days']} | "
            f"Entry: INR {t['entry_price']:,.2f} | CMP: INR {t['current_price']:,.2f} | "
            f"Unrealized PnL: INR {t['unrealized_pnl']:+,.2f} ({t['pnl_pct']:+.2f}%)"
        )

    # Part 3: Live Order Placement & Execution Demonstration with Entry/Exit Dates
    print("\n[3] Executing Showcase Trade with Explicit Entry Date & Exit Date:")
    initial_cash = engine.get_cash_balance()
    test_ticker = "TCS.NS"
    entry_price = 3200.00
    stop_loss = 3100.00
    sell_target = 3400.00
    order = engine.place_order(
        ticker=test_ticker,
        entry_price=entry_price,
        stop_loss=stop_loss,
        sell_target=sell_target,
        override_quantity=20,
    )
    trade_id = order["trade_id"]
    print(
        f"  Opened Trade #{trade_id}: {order['quantity']} shares of {order['ticker']} "
        f"@ INR {order['entry_price']:,.2f}"
    )
    print(f"  Recorded Entry Date   : {order['entry_date']}")
    print(f"  Remaining Cash        : INR {order['remaining_cash']:,.2f}")

    # Partial close to demonstrate tranche split with date inheritance
    print("\n[4] Partial Closure (Sell 10 shares at INR 3,300.00):")
    partial_res = engine.partial_close_trade(
        trade_id=trade_id,
        sell_quantity=10,
        exit_price=3300.00,
        exit_reason="CAGR_SHOWCASE_PARTIAL",
    )
    print(
        f"  Closed Tranche #{partial_res['closed_trade_id']}: "
        f"{partial_res['sold_quantity']} shares | "
        f"Entry Date: {partial_res['entry_date']} | Exit Date: {partial_res['exit_date']}"
    )
    print(
        f"  Realized PnL: INR {partial_res['realized_pnl']:+,.2f} "
        f"({partial_res['return_pct']:+.2f}%)"
    )

    # Full closure of remaining shares
    print("\n[5] Final Closure (Sell remaining 10 shares at INR 3,350.00):")
    final_res = engine.close_trade(
        trade_id=trade_id,
        exit_price=3350.00,
        exit_reason="CAGR_SHOWCASE_FINAL",
    )
    print(
        f"  Closed Trade #{final_res['trade_id']}: {final_res['quantity']} shares | "
        f"Entry Date: {final_res['entry_date']} | Exit Date: {final_res['exit_date']}"
    )
    print(
        f"  Realized PnL: INR {final_res['realized_pnl']:+,.2f} "
        f"({final_res['return_pct']:+.2f}%)"
    )

    # Part 6: Trade-Level CAGR Calculation Breakdown
    print("\n[6] Trade-Level CAGR Calculation Example:")
    cagr_sample = calculate_trade_cagr(
        entry_price=3200.00,
        exit_price=3350.00,
        entry_date="2026-06-16",
        exit_date="2026-09-16",
    )
    print(f"  Entry Price       : INR 3,200.00 ({cagr_sample['entry_date']})")
    print(f"  Exit Price        : INR 3,350.00 ({cagr_sample['exit_date']})")
    print(
        f"  Holding Duration  : {cagr_sample['holding_days']} days "
        f"({cagr_sample['duration_years']:.2f} yrs)"
    )
    print(f"  Absolute Return   : {cagr_sample['return_pct']:+.2f}%")
    print(f"  Annualized CAGR   : {cagr_sample['cagr_pct']:+.2f}%")

    # Cleanup demonstration trades to preserve database state
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM paper_trades WHERE trade_id IN (?, ?)",
            (trade_id, partial_res["closed_trade_id"]),
        )
        cursor.execute(
            "UPDATE paper_portfolio SET cash_balance = ? WHERE id = 1",
            (initial_cash,),
        )
        conn.commit()
    print("\n[7] Demonstration Trades Cleaned Up; Database Preserved.")

    # Part 8: Comprehensive Portfolio CAGR Report
    port_metrics = calculate_portfolio_cagr(engine)
    print(
        f"\n[8] Portfolio Metrics: Net Worth INR {port_metrics['total_portfolio_value']:,.2f} | "
        f"Portfolio CAGR: {port_metrics['portfolio_cagr_pct']:+.2f}%"
    )
    print("\n" + generate_cagr_report(engine))
    print("=" * 90)


def example_paper_trading_limit_orders() -> None:
    """Showcase Paper Trading Limit Buy orders, pending queues, and NSE market open triggers.

    Demonstrates:
    1. Placing an order outside trading window (waits for NSE open).
    2. Placing an order with no buy price (defaults to CMP; executes at opening CMP).
    3. Placing an order with a buy price (limit: executes only if opening CMP <= buy price).
    4. Simulating NSE open with price updates and evaluating limit executions.
    5. Order cancellation of remaining pending orders.
    """
    print("=" * 88)
    print("PAPER TRADING LIMIT ORDERS & NSE TRADING WINDOW EXECUTION SHOWCASE")
    print("=" * 88)
    print("Rules Evaluated:")
    print("  1. Buy on or below a specific price (Limit Order): Default to CMP if empty.")
    print("  2. Outside trading window: Queue as PENDING, wait until NSE opens.")
    print("  3. When NSE opens:")
    print("     - If no buy price: executes at CMP.")
    print("     - If buy price entered: executes only if CMP <= buy price.")
    print("-" * 88)

    engine = PaperTradingEngine()
    initial_cash = engine.get_cash_balance()

    # Step 1: Place an order outside trading window WITHOUT buy price (Market Order -> use CMP)
    print("\n[1] Submitting Order 1 (Market Order: No buy price entered outside trading window):")
    order1 = engine.submit_order(
        ticker="INFY.NS",
        buy_price=None,
        stop_loss=1750.00,
        sell_target=1950.00,
        current_cmp=1800.00,
        market_open_override=False,
    )
    print(f"  Order ID     : #{order1['order_id']}")
    print(f"  Ticker       : {order1['ticker']}")
    print(f"  Buy Price    : {order1['buy_price']} (None -> defaulted to CMP)")
    print(f"  Status       : {order1['status']}")
    print(f"  Reason       : {order1['status_reason']}")
    print(f"  Est. Shares  : {order1['quantity']}")

    # Step 2: Place an order outside trading window WITH buy price (Limit Order: <= 2450.00)
    print("\n[2] Submitting Order 2 (Limit Order: Buy on or below INR 2,450.00):")
    order2 = engine.submit_order(
        ticker="RELIANCE.NS",
        buy_price=2450.00,
        stop_loss=2400.00,
        sell_target=2600.00,
        current_cmp=2480.00,
        market_open_override=False,
    )
    print(f"  Order ID     : #{order2['order_id']}")
    print(f"  Ticker       : {order2['ticker']}")
    print(f"  Buy Price    : INR {order2['buy_price']:,.2f} (Buy on or below)")
    print(f"  Status       : {order2['status']}")
    print(f"  Reason       : {order2['status_reason']}")
    print(f"  Est. Shares  : {order2['quantity']}")

    # Step 3: Inspect Pending Orders Queue in SQLite
    print("\n[3] Current Pending Orders Queue in 'paper_orders':")
    pending = engine.get_pending_orders()
    for p in pending:
        b_str = (
            f"INR {p['buy_price']:,.2f}"
            if p["buy_price"] is not None
            else "CMP (Market)"
        )
        print(
            f"  Order #{p['order_id']}: {p['ticker']} | Type: {b_str} | "
            f"SL: INR {p['stop_loss']:,.2f} | Status: {p['status']} ({p['status_reason']})"
        )

    # Step 4: Simulate NSE Market Open
    print("\n[4] Simulating NSE Market Open (9:15 AM IST):")
    simulated_open_prices = {
        "INFY.NS": 1810.00,
        "RELIANCE.NS": 2440.00,
    }
    executed = engine.process_pending_orders(
        price_map=simulated_open_prices,
        market_open_override=True,
    )
    print(f"  Executed {len(executed)} pending order(s) on market open:")
    for ex in executed:
        print(
            f"  -> Order #{ex['order_id']} ({ex['ticker']}) EXECUTED at CMP "
            f"INR {ex['entry_price']:,.2f}! Qty: {ex['quantity']} shares | "
            f"Trade ID: #{ex['trade_id']} | Total Cost: INR {ex['total_cost']:,.2f}"
        )

    # Step 5: Test Limit Price Above Market CMP Condition
    print(
        "\n[5] Submitting Order 3 with Limit Price Below Open "
        "(TCS.NS limit 3100.0 vs CMP 3200.0):"
    )
    order3 = engine.submit_order(
        ticker="TCS.NS",
        buy_price=3100.00,
        stop_loss=3000.00,
        sell_target=3300.00,
        current_cmp=3200.00,
        market_open_override=True,
    )
    print(f"  Order ID     : #{order3['order_id']}")
    print(f"  Ticker       : {order3['ticker']}")
    print(f"  Status       : {order3['status']} ({order3['status_reason']})")

    # Step 6: Cancel Remaining Pending Order
    print(f"\n[6] Cancelling Pending Order #{order3['order_id']} (TCS.NS):")
    cancel_success = engine.cancel_order(order3["order_id"])
    print(
        f"  Cancellation Result: "
        f"{'SUCCESS (Order Cancelled)' if cancel_success else 'FAILED'}"
    )

    # Step 7: Final Portfolio Summary and Cleanup
    print("\n[7] Final Order Book Status Summary:")
    all_orders = engine.order_manager.get_all_orders()
    for o in all_orders[:5]:
        print(
            f"  Order #{o['order_id']}: {o['ticker']} | Status: {o['status']} | "
            f"Reason: {o['status_reason']}"
        )

    # Cleanup demonstration records
    trade_ids = [ex["trade_id"] for ex in executed]
    order_ids = [order1["order_id"], order2["order_id"], order3["order_id"]]
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        for tid in trade_ids:
            cursor.execute("DELETE FROM paper_trades WHERE trade_id = ?", (tid,))
        for oid in order_ids:
            cursor.execute("DELETE FROM paper_orders WHERE order_id = ?", (oid,))
        cursor.execute(
            "UPDATE paper_portfolio SET cash_balance = ? WHERE id = 1",
            (initial_cash,),
        )
        conn.commit()
    print("\n[8] Demonstration Orders and Trades Cleaned Up; Database Preserved.")
    print("=" * 88)


def example_nifty_dual_momentum_breakout() -> None:
    """Showcase Nifty Dual Momentum Breakout strategy for hourly Nifty 50 cash stocks.

    Demonstrates:
    1. Strategy checklist rules and technical filters (200 EMA, 20D High, 1.5x Volume MA).
    2. Framework standard on_candle_close output format returning an explicit dictionary:
       {'symbol', 'signal' (BUY/HOLD), 'entry_price', 'stop_loss', 'take_profit'}.
    3. Hourly execution with 3.5% initial Stop Loss, 7.0% Take Profit (1:2 RRR),
       and 1:1 RRR breakeven trailing stop (+3.5% gain triggers stop move to entry).
    4. Backtest simulation metrics and trade log displaying breakeven vs target exits.
    """
    print("=" * 85)
    print("NIFTY DUAL MOMENTUM BREAKOUT STRATEGY SHOWCASE (HOURLY CASH EQUITIES)")
    print("=" * 85)
    print("Strategy Checklist Rules:")
    print("  1. Long-Only Momentum Breakout (Cash Segment Only, No Short, No Leverage):")
    print("     - Nifty 50 universe evaluated on the HOURLY timeframe.")
    print("  2. Technical Filters (Daily Equivalent using Hourly Data):")
    print("     - Trend Filter: Close > 200 EMA (200 * 7 = 1,400 hourly periods EMA).")
    print("     - Breakout Trigger: Current hour's close > highest high of last 20 trading days")
    print("       (20 days * 7 trading hours = 140 hourly periods).")
    print("     - Volume Confirmation: Breakout hour volume > 1.5x 20-period Volume Moving Average")
    print("       (140 hourly periods).")
    print("  3. Execution & Risk Management:")
    print("     - Entry: Market order on close of confirming hourly breakout candle.")
    print("     - Stop Loss: Placed strictly 3.5% below entry price.")
    print("     - Take Profit: 1:2 Risk-to-Reward Ratio (7.0% target profit from entry).")
    print("     - Trailing Stop: When price reaches +3.5% (1:1 RRR), move Stop Loss to exact")
    print("       entry price (breakeven), locking out downside risk.")
    print("-" * 85)

    repo = MarketRepository()
    strategy = NiftyDualMomentumBreakout()

    sample_tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS"]

    # Section 1: Standard on_candle_close dictionary output
    print("\n[1] Framework Standard on_candle_close Signal Evaluation (Latest Hourly Candle):")
    signal_header = (
        f"{'Ticker':<14} | {'Signal':<6} | {'Entry Price':<14} | "
        f"{'Stop Loss':<14} | {'Take Profit':<14} | {'Condition / Status'}"
    )
    print(signal_header)
    print("-" * len(signal_header))

    for ticker in sample_tickers:
        df = repo.get_data(ticker)
        if df.empty:
            continue

        result_dict = strategy.on_candle_close(symbol=ticker, candle_or_df=df)
        sym = result_dict["symbol"]
        sig = result_dict["signal"]
        ep = result_dict["entry_price"]
        sl = result_dict["stop_loss"]
        tp = result_dict["take_profit"]

        ep_str = f"INR {ep:,.2f}" if ep is not None else "N/A (Holding)"
        sl_str = f"INR {sl:,.2f}" if sl is not None else "N/A"
        tp_str = f"INR {tp:,.2f}" if tp is not None else "N/A"

        if sig == "BUY":
            status = "CONFIRMED BREAKOUT [BUY TRIGGER]"
        else:
            status = "Consolidating / Waiting for Breakout"

        print(
            f"{sym:<14} | {sig:<6} | {ep_str:<14} | "
            f"{sl_str:<14} | {tp_str:<14} | {status}"
        )
    print("-" * len(signal_header))

    # Section 2: Hourly Backtest simulation across sample securities
    print("\n[2] Hourly Historical Backtest Sample (INR 1,000,000 Capital, 10% Allocation):")
    btest_header = (
        f"{'Ticker':<14} | {'Trades':<6} | {'Wins':<5} | {'Losses':<6} | "
        f"{'Win Rate':<9} | {'Total PnL (INR)':<16} | {'PnL %':<8} | {'CAGR':<8} | {'PF':<5}"
    )
    print(btest_header)
    print("-" * len(btest_header))

    for ticker in sample_tickers:
        df = repo.get_data(ticker)
        if df.empty:
            continue

        btest_res = strategy.backtest(df, ticker=ticker, initial_capital=1_000_000.0)
        m = btest_res["Metrics"]
        pnl_str = f"INR {m['TotalPnL']:>11,.2f}"
        pnl_pct_str = f"{m.get('TotalPnLPct', 0.0):+.2f}%"
        cagr_str = f"{m.get('CAGRPct', 0.0):+.2f}%"
        pf_str = f"{m['ProfitFactor']:.2f}" if m['ProfitFactor'] != float("inf") else "inf"

        print(
            f"{ticker:<14} | {m['TotalTrades']:<6} | {m['Wins']:<5} | {m['Losses']:<6} | "
            f"{m['WinRatePct']:<8.1f}% | {pnl_str} | {pnl_pct_str:<8} | {cagr_str:<8} | {pf_str}"
        )
    print("-" * len(btest_header))

    # Section 3: Trade Journal Sample demonstrating 1:1 RRR Breakeven Trailing Stop
    sample_ticker = "RELIANCE.NS"
    sample_df = repo.get_data(sample_ticker)
    if not sample_df.empty:
        sample_res = strategy.backtest(
            sample_df, ticker=sample_ticker, initial_capital=1_000_000.0
        )
        trade_log = sample_res["TradeLog"]
        if not trade_log.empty:
            print(f"\n[3] Trade Journal Sample ({sample_ticker} - Hourly Execution & Trailing):")
            display_cols = [
                "EntryDate", "ExitDate", "PositionSize", "EntryPrice",
                "ExitPrice", "PnL", "ReturnPct", "Result", "ExitReason",
            ]
            print(trade_log[display_cols].tail(8).to_string(index=False))

    print("\n" + "=" * 85)


def example_entry_stop_loss() -> None:
    """Showcase and validate entry-based stop loss calculation across all strategies."""
    print("=" * 80)
    print("VALIDATING ENTRY-BASED STOP LOSS CALCULATIONS ACROSS SECURITIES")
    print("=" * 80)
    validate_entry_stop_losses(sample_size=20)


def example_daily_data_updater() -> None:
    """Showcase in-app daily market data synchronization and status checking."""
    print("=" * 80)
    print("DAILY MARKET DATA SYNCHRONIZATION SHOWCASE")
    print("=" * 80)
    service = DataSyncService.get_instance()
    info = service.get_last_sync_info()
    latest_bar = service.get_latest_bar_date()

    print(f"Latest Database Bar Date    : {latest_bar or 'None'}")
    print(f"Last Sync Timestamp         : {info.get('last_sync_timestamp') or 'Never'}")
    print(f"Last Sync Status            : {info.get('last_sync_status')}")
    print(f"Last Sync Bars Added        : {info.get('last_sync_bars', 0)}")
    print(f"Last Sync Fundamentals      : {info.get('last_sync_funds', 0)}")
    print(f"Auto-Sync On App Startup    : {service.get_auto_sync_on_startup()}")
    print("-" * 80)
    print("Executing market data synchronization (price bars only)...")

    def progress_printer(cur: int, tot: int, msg: str) -> None:
        pct = int((cur / max(1, tot)) * 100)
        print(f"[{pct:>3}%] ({cur:>3}/{tot}) {msg}")

    bars = run_daily_sync(progress_callback=progress_printer)
    print("=" * 80)
    print(f"Synchronization Complete! Added {bars} new price bars.")
    print("Note: Fundamentals are synced separately via the Fundamental Screener tab.")
    print("=" * 80)


def example_market_sentiment() -> None:
    """Showcase market sentiment analysis and drastic macro catalyst detection from RSS feeds."""
    print("=" * 80)
    print("MARKET SENTIMENT & MACRO CATALYST ANALYSIS SHOWCASE")
    print("=" * 80)
    analyzer = MarketSentimentAnalyzer()
    print("Ingesting live market RSS feeds (Economic Times, Livemint, Moneycontrol, Google)...")
    summary = analyzer.analyze_market_sentiment()

    print(f"Overall Market Sentiment     : {summary.overall_sentiment}")
    print(f"Composite Sentiment Score    : {summary.sentiment_score:+0.2f}")
    print(f"Total News Headlines Analyzed: {len(summary.all_items)}")
    print(
        f"Sentiment Breakdown          : {summary.bullish_count} Bullish | "
        f"{summary.bearish_count} Bearish | {summary.neutral_count} Neutral"
    )
    print(f"Drastic Catalysts Detected   : {summary.drastic_events_count}")
    print("-" * 80)
    print("Summary Alert Headline:")
    print(f"  {summary.summary_headline}")
    print("=" * 80)

    if summary.high_impact_items:
        print("\nTOP HIGH-IMPACT / DRASTIC MARKET CATALYSTS:")
        print("-" * 80)
        for idx, item in enumerate(summary.high_impact_items[:6], start=1):
            safe_title = item.title.encode("ascii", "replace").decode("ascii")
            print(
                f"[{idx}] {item.catalyst_category} | Impact: {item.impact_level} | "
                f"Sentiment: {item.sentiment} ({item.sentiment_score:+0.2f})"
            )
            print(f"    Headline : {safe_title}")
            print(f"    Source   : {item.source} ({item.pub_date})")
            print(f"    Trigger  : {item.catalyst_reason}")
            print()
    else:
        print("No critical geopolitical, budget, or systemic crisis catalysts detected.")

    print("-" * 80)
    print(f"Recent Headlines ({min(5, len(summary.all_items))} of {len(summary.all_items)}):")
    for item in summary.all_items[:5]:
        safe_title = item.title.encode("ascii", "replace").decode("ascii")
        print(f"  [{item.sentiment:<7}] [{item.impact_level:<6}] {safe_title} ({item.source})")
    print("=" * 80)


def main() -> None:
    """Initialize and showcase the primary application functionality."""
    if (
        "--momentum" in sys.argv
        or "--nifty-momentum" in sys.argv
        or "--dual-momentum" in sys.argv
        or "--breakout" in sys.argv
    ):
        example_nifty_dual_momentum_breakout()
    elif (
        "--entry-sl" in sys.argv
        or "--entry-stop-loss" in sys.argv
        or "--verify-stops" in sys.argv
    ):
        example_entry_stop_loss()
    elif (
        "--paper-cagr" in sys.argv
        or "--cagr" in sys.argv
        or "--paper-dates" in sys.argv
    ):
        example_paper_trading_cagr()
    elif (
        "--paper-enhancements" in sys.argv
        or "--paper-trading-enhancements" in sys.argv
        or "--paper-mods" in sys.argv
    ):
        example_paper_trading_enhancements()
    elif (
        "--paper-trading" in sys.argv
        or "--paper" in sys.argv
        or "--paper-engine" in sys.argv
    ):
        example_paper_trading()
    elif (
        "--bb-stoch-rsi" in sys.argv
        or "--bollinger-stoch-rsi" in sys.argv
        or "--mean-reversion" in sys.argv
    ):
        example_bollinger_stoch_rsi()
    elif (
        "--rsi-pullback" in sys.argv
        or "--bull-pullback" in sys.argv
        or "--rsi-bull" in sys.argv
    ):
        example_rsi_bull_trend_pullback()
    elif (
        "--dual-ema" in sys.argv
        or "--conservative-trend" in sys.argv
        or "--dual-moving-average" in sys.argv
    ):
        example_dual_moving_average_adx()
    elif "--holy-grail" in sys.argv or "--adx-ema" in sys.argv or "--linda-raschke" in sys.argv:
        example_adx_ema_swing()
    elif "--kicker" in sys.argv or "--bullish-kicker" in sys.argv:
        example_bullish_kicker()
    elif "--outside-bar" in sys.argv or "--bullish-outside-bar" in sys.argv:
        example_bullish_outside_bar()
    elif "--backtest" in sys.argv or "--all-stocks" in sys.argv:
        example_all_stocks_backtest()
    elif "--cli" in sys.argv or "--screener" in sys.argv:
        example_fundamental_screener()
    elif "--rsi" in sys.argv or "--rsi-indicator" in sys.argv:
        example_rsi_indicator()
    elif "--adx" in sys.argv or "--adx-indicator" in sys.argv:
        example_adx_indicator()
    elif "--scanner" in sys.argv or "--morning-scanner" in sys.argv:
        scope = (
            "last_bar"
            if "--last-bar" in sys.argv
            else "previous_day"
        )
        example_morning_scanner(trigger_scope=scope)
    elif (
        "--sync" in sys.argv
        or "--data-sync" in sys.argv
        or "--updater" in sys.argv
    ):
        example_daily_data_updater()
    elif (
        "--nifty" in sys.argv
        or "--nifty-header" in sys.argv
        or "--header" in sys.argv
    ):
        example_nifty_live_header()
    elif (
        "--chart-popup" in sys.argv
        or "--popup-chart" in sys.argv
        or "--popup" in sys.argv
    ):
        target_ticker = "RELIANCE.NS"
        for arg in sys.argv:
            if arg.startswith("--ticker="):
                target_ticker = arg.split("=")[1]
        example_ticker_chart_popup(ticker=target_ticker)
    elif (
        "--sentiment" in sys.argv
        or "--market-sentiment" in sys.argv
        or "--news-sentiment" in sys.argv
        or "--rss" in sys.argv
    ):
        example_market_sentiment()
    elif "--screener-fetcher" in sys.argv or "--screener-in" in sys.argv:
        target_ticker = "INFY.NS"
        for arg in sys.argv:
            if arg.startswith("--ticker="):
                target_ticker = arg.split("=")[1]
        example_screener_fetcher(ticker=target_ticker)
    elif (
        "--paper-orders" in sys.argv
        or "--pending-orders" in sys.argv
        or "--limit-orders" in sys.argv
    ):
        example_paper_trading_limit_orders()
    else:
        example_trading_dashboard()


if __name__ == '__main__':
    main()
