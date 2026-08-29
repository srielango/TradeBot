"""Tradebot Management Studio - Desktop analytical dashboard and showcase entry point."""

import sys

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtWidgets import QApplication

from back_test_engine import BacktestEngine
from fundamental_screener import FundamentalScreener
from market_repository import MarketRepository
from strategies.bullish_kicker import BullishKicker
from strategies.moving_average_stochastic import MovingAverageStochastic
from ui import TradingApp


def example_trading_dashboard() -> None:
    """Showcase and launch Tradebot Management Studio graphical interface."""
    app = QApplication(sys.argv)
    window = TradingApp()
    window.show()
    sys.exit(app.exec())


def example_bullish_kicker() -> None:
    """Showcase Bullish Kicker candlestick strategy with 9% target and 1% risk sizing."""
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
    print("     - Exit upon achieving 9.0% profit target.")
    print("-" * 80)

    repo = MarketRepository()
    strategy = BullishKicker(target_profit_pct=0.09)

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
    print(f"  Total PnL      : INR {pm['TotalPnL']:+,.2f}")
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
    print(f"  Total PnL      : INR {m['TotalPnL']:+,.2f}")
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


def main() -> None:
    """Initialize and showcase the primary application functionality."""
    if "--kicker" in sys.argv or "--bullish-kicker" in sys.argv:
        example_bullish_kicker()
    elif "--backtest" in sys.argv or "--all-stocks" in sys.argv:
        example_all_stocks_backtest()
    elif "--cli" in sys.argv or "--screener" in sys.argv:
        example_fundamental_screener()
    else:
        example_trading_dashboard()


if __name__ == '__main__':
    main()
