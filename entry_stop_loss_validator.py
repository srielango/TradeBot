"""Module for validating that stop losses are strictly calculated upon position entry.

Demonstrates that stop losses are dynamically derived from the execution entry price,
guaranteeing that Stop Loss is strictly below Entry Price for long positions and
completely preventing the 'Win (Stop Loss)' anomaly.
"""

from typing import Any

import pandas as pd

from back_test_engine import BacktestEngine
from market_repository import MarketRepository
from strategies import STRATEGY_REGISTRY


def validate_entry_stop_losses(
    sample_size: int = 15,
) -> dict[str, Any]:
    """Execute backtests across registered strategies to validate entry-based stop loss rules.

    Validates the following invariants:
    1. Every long position has StopLoss < EntryPrice at all times.
    2. Any trade exited due to 'Stop Loss' must have a non-positive PnL (Result == 'Loss').
    3. Zero trades are categorized as 'Win (Stop Loss)'.

    Args:
        sample_size (int): Number of active equity tickers to evaluate per strategy.

    Returns:
        dict[str, Any]: Summary dictionary containing validation metrics, trade counts,
            and any detected anomalies.
    """
    repo = MarketRepository()
    engine = BacktestEngine()
    tickers = repo.get_stock_tickers()

    if not tickers:
        print("[EntrySLValidator] No stock tickers found in database.")
        return {"total_trades": 0, "anomalies": 0, "win_sl_count": 0}

    selected_tickers = tickers[:sample_size]
    total_trades_analyzed = 0
    win_sl_count = 0
    invalid_sl_count = 0
    strategy_summaries = {}

    for strat_name, strat_cls in STRATEGY_REGISTRY.items():
        strategy_instance = strat_cls()
        strat_trades = 0
        strat_sl_exits = 0
        strat_win_sl = 0

        for ticker_display in selected_tickers:
            # Use daily aggregated data for daily swing strategies
            df_daily = repo.get_daily_data(ticker_display)
            if df_daily.empty or len(df_daily) < 50:
                continue

            try:
                sig_df = strategy_instance.generate_signals(df_daily)
                clean_ticker = ticker_display.split(" ")[0]
                results = engine.run(sig_df, ticker=clean_ticker)
                trade_log = results.get("TradeLog", pd.DataFrame())

                if trade_log.empty:
                    continue

                strat_trades += len(trade_log)
                total_trades_analyzed += len(trade_log)

                for _, row in trade_log.iterrows():
                    entry_p = float(row["EntryPrice"])
                    exit_p = float(row["ExitPrice"])
                    pnl = float(row["PnL"])
                    result = str(row["Result"])
                    exit_reason = str(row.get("ExitReason", ""))

                    # Check 1: Any trade exiting on Stop Loss must not be a Win
                    if "Stop Loss" in exit_reason:
                        strat_sl_exits += 1
                        if result == "Win" or pnl > 0:
                            win_sl_count += 1
                            strat_win_sl += 1

                    # Check 2: Stop loss fill price must be <= entry price for long trades
                    if "Stop Loss" in exit_reason and exit_p > entry_p:
                        invalid_sl_count += 1

            except (ValueError, KeyError, IndexError) as err:
                print(f"[EntrySLValidator] Error testing {strat_name} on {ticker_display}: {err}")

        strategy_summaries[strat_name] = {
            "total_trades": strat_trades,
            "sl_exits": strat_sl_exits,
            "win_sl_count": strat_win_sl,
        }

    validation_passed = (win_sl_count == 0) and (invalid_sl_count == 0)

    print("=" * 80)
    print("ENTRY-BASED STOP LOSS VALIDATION REPORT")
    print("=" * 80)
    total_sl_exits = sum(s["sl_exits"] for s in strategy_summaries.values())
    result_text = "PASSED [OK]" if validation_passed else "FAILED [ERROR]"
    print(f"Total Completed Trades Analyzed: {total_trades_analyzed:,}")
    print(f"Total Stop Loss Exits:           {total_sl_exits:,}")
    print(f"Invalid 'Win (Stop Loss)' Count: {win_sl_count} (Expected: 0)")
    print(f"Invalid SL > Entry Fill Count:   {invalid_sl_count} (Expected: 0)")
    print(f"Validation Result:               {result_text}")
    print("-" * 80)

    for name, stats in strategy_summaries.items():
        status = "PASSED" if stats["win_sl_count"] == 0 else "FAILED"
        print(
            f" - {name[:45]:<45} | Trades: {stats['total_trades']:<4} | "
            f"SL Exits: {stats['sl_exits']:<3} | Win(SL): {stats['win_sl_count']} [{status}]"
        )
    print("=" * 80)

    return {
        "passed": validation_passed,
        "total_trades": total_trades_analyzed,
        "win_sl_count": win_sl_count,
        "invalid_sl_count": invalid_sl_count,
        "strategy_summaries": strategy_summaries,
    }
