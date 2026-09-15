"""Morning scanner module for evaluating market signals on previous close.

Scans all active equity stocks (excluding indices) from the SQLite database,
feeds 3 to 6 months of historical data into all registered strategies to
warm up technical indicators, identifies buy signals triggered on the
previous session close, and monitors active open positions to generate
sell indicators when their required profit target or stop loss is reached.
"""

from datetime import datetime, timezone

import pandas as pd

from market_repository import MarketRepository
from paper_trading_engine import PaperTradingEngine
from strategies import STRATEGY_REGISTRY


class MorningScanner:
    """Scanner engine to detect pre-market buy and sell signals across active stocks."""

    def __init__(
        self,
        repo: MarketRepository | None = None,
        paper_engine: PaperTradingEngine | None = None,
    ):
        """Initialize the morning scanner with data repository and paper trading instances.

        Args:
            repo (MarketRepository | None): Market data repository. Defaults to new instance.
            paper_engine (PaperTradingEngine | None): Paper trading engine. Defaults to new instance.
        """
        self.repo = repo if repo is not None else MarketRepository()
        self.paper_engine = (
            paper_engine if paper_engine is not None else PaperTradingEngine()
        )

    def scan(
        self,
        lookback_months: int = 6,
        trigger_scope: str = "previous_day",
        open_positions: list[dict] | None = None,
    ) -> list[dict]:
        """Execute scan across all active equity stocks using historical lookback.

        For each stock:
        1. Checks whether an active open position exists from paper trading.
           If the position's required profit target (or stop loss) has been
           achieved on the previous close, flags an actionable SELL signal.
        2. Evaluates every strategy in STRATEGY_REGISTRY to compute indicators
           and checks whether a BUY signal was triggered on previous close.
        3. If multiple strategies trigger a BUY signal, selects the strategy
           giving the least profit and calculates stop loss and take profit
           strictly based on that chosen strategy.

        Args:
            lookback_months (int): Number of months of historical price data to
                feed into strategy calculations (3 to 6 months recommended).
                Defaults to 6.
            trigger_scope (str): Scope of the trigger check:
                - "previous_day": On any bar of previous completed trading day.
                - "last_bar": Strictly on final completed bar (previous close).
                Defaults to "previous_day".
            open_positions (list[dict] | None): Optional list of open trade
                dictionaries. If None, queries PaperTradingEngine directly.

        Returns:
            list[dict]: List of scan result dictionaries for all evaluated stocks,
                sorted with SELL signals first, then highest buy confluence.
        """
        # Fetch stock metadata (ticker -> company name) and all price series
        metadata = self.repo.get_stock_metadata()
        stocks_data = self.repo.get_all_stocks_data()

        if not stocks_data:
            return []

        # Retrieve active open positions if not explicitly passed
        if open_positions is None:
            try:
                open_positions = self.paper_engine.get_open_trades()
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
                print(f"Warning: Failed to fetch open positions from paper engine: {err}")
                open_positions = []

        # Index open positions by normalized ticker for fast lookup
        open_positions_by_ticker: dict[str, list[dict]] = {}
        for pos in open_positions:
            raw_t = str(pos.get("ticker", "")).strip().upper()
            base_t = raw_t.replace(".NS", "")
            open_positions_by_ticker.setdefault(raw_t, []).append(pos)
            if base_t != raw_t:
                open_positions_by_ticker.setdefault(base_t, []).append(pos)

        results = []

        for ticker, df in stocks_data.items():
            if df.empty or len(df) < 20:
                continue

            # Ensure date column is parseable and compute cutoff date
            df_work = df.copy()
            df_work["dt"] = pd.to_datetime(df_work["date"])
            max_date = df_work["dt"].max()

            # Slice the past 3 to 6 months for indicator warm-up
            lookback_days = max(30, int(lookback_months * 30.5))
            cutoff_date = max_date - pd.Timedelta(days=lookback_days)
            df_slice = (
                df_work[df_work["dt"] >= cutoff_date]
                .drop(columns=["dt"])
                .reset_index(drop=True)
            )

            # Ensure sufficient records exist for indicator rolling windows
            if len(df_slice) < 20:
                df_slice = df.copy().reset_index(drop=True)

            prev_close_bar = df_slice.iloc[-1]
            prev_close_date = str(prev_close_bar["date"])
            prev_close_price = float(prev_close_bar["close"])

            # Determine target scope evaluation rows
            latest_day_str = prev_close_date[:10]

            # -----------------------------------------------------------------
            # Step 1: Check Open Position Status & Required Profit Signal
            # -----------------------------------------------------------------
            clean_ticker = ticker.strip().upper()
            base_ticker = clean_ticker.replace(".NS", "")
            matching_positions = (
                open_positions_by_ticker.get(clean_ticker)
                or open_positions_by_ticker.get(base_ticker)
                or []
            )
            has_open_position = len(matching_positions) > 0

            pos_sell_triggered = False
            pos_sell_reason = ""
            pos_target_price: float | None = None
            pos_sl_price: float | None = None
            pos_entry_price: float = 0.0
            pos_pnl_pct: float = 0.0
            pos_trade_id: int | None = None

            if has_open_position:
                for pos in matching_positions:
                    p_entry = float(pos.get("entry_price", 0.0))
                    p_target = (
                        float(pos.get("sell_target"))
                        if pos.get("sell_target") is not None
                        else None
                    )
                    p_sl = (
                        float(pos.get("stop_loss"))
                        if pos.get("stop_loss") is not None
                        else None
                    )
                    p_id = pos.get("trade_id")

                    # Check required profit target reached
                    target_reached = False
                    if p_target is not None and p_target > 0:
                        session_high = (
                            float(prev_close_bar["high"])
                            if "high" in prev_close_bar and pd.notna(prev_close_bar["high"])
                            else prev_close_price
                        )
                        if prev_close_price >= p_target or session_high >= p_target:
                            target_reached = True

                    # If no explicit sell target in trade record, check default 1:2 R:R
                    elif p_sl is not None and p_entry > p_sl:
                        calc_target = round(p_entry + 2.0 * (p_entry - p_sl), 2)
                        if prev_close_price >= calc_target:
                            target_reached = True
                            p_target = calc_target

                    if target_reached:
                        pos_sell_triggered = True
                        pos_sell_reason = "PROFIT_TARGET"
                        pos_target_price = p_target
                        pos_sl_price = p_sl
                        pos_entry_price = p_entry
                        pos_trade_id = p_id
                        pos_pnl_pct = (
                            round((prev_close_price - p_entry) / p_entry * 100.0, 2)
                            if p_entry > 0
                            else 0.0
                        )
                        break

                    # Check stop loss hit
                    sl_hit = False
                    if p_sl is not None and p_sl > 0:
                        session_low = (
                            float(prev_close_bar["low"])
                            if "low" in prev_close_bar and pd.notna(prev_close_bar["low"])
                            else prev_close_price
                        )
                        if prev_close_price <= p_sl or session_low <= p_sl:
                            sl_hit = True

                    if sl_hit and not pos_sell_triggered:
                        pos_sell_triggered = True
                        pos_sell_reason = "STOP_LOSS"
                        pos_target_price = p_target
                        pos_sl_price = p_sl
                        pos_entry_price = p_entry
                        pos_trade_id = p_id
                        pos_pnl_pct = (
                            round((prev_close_price - p_entry) / p_entry * 100.0, 2)
                            if p_entry > 0
                            else 0.0
                        )

            # -----------------------------------------------------------------
            # Step 2: Evaluate All Strategies for Buy Signals
            # -----------------------------------------------------------------
            triggered_strategies: list[str] = []
            strategy_details: dict[str, dict] = {}

            for strat_name, strat_cls in STRATEGY_REGISTRY.items():
                try:
                    strategy_instance = strat_cls()
                    signals_df = strategy_instance.generate_signals(df_slice)

                    if signals_df.empty or "Signal" not in signals_df.columns:
                        continue

                    # Evaluate trigger window based on chosen trigger_scope
                    if trigger_scope == "previous_day":
                        scope_bars = signals_df[
                            signals_df["date"].astype(str).str.startswith(latest_day_str)
                        ]
                        if scope_bars.empty:
                            scope_bars = signals_df.iloc[-1:]
                    else:
                        scope_bars = signals_df.iloc[-1:]

                    is_buy = bool((scope_bars["Signal"] == 1).any())

                    sl_val = None
                    tp_val = None
                    last_signal_val = 0

                    if is_buy:
                        buy_bars = scope_bars[scope_bars["Signal"] == 1]
                        eval_row = buy_bars.iloc[-1]
                        last_signal_val = 1
                    else:
                        eval_row = scope_bars.iloc[-1]
                        last_signal_val = (
                            int(eval_row["Signal"]) if pd.notna(eval_row["Signal"]) else 0
                        )

                    if "StopLoss" in scope_bars.columns:
                        raw_sl = eval_row["StopLoss"]
                        if pd.notna(raw_sl) and float(raw_sl) > 0:
                            sl_val = round(float(raw_sl), 2)

                    if "TakeProfit" in scope_bars.columns:
                        raw_tp = eval_row["TakeProfit"]
                        if pd.notna(raw_tp) and float(raw_tp) > 0:
                            tp_val = round(float(raw_tp), 2)

                    strategy_details[strat_name] = {
                        "is_buy": is_buy,
                        "signal_val": last_signal_val,
                        "stop_loss": sl_val,
                        "take_profit": tp_val,
                    }

                    if is_buy:
                        triggered_strategies.append(strat_name)

                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
                    print(f"Error evaluating '{strat_name}' on '{ticker}': {err}")

            confluence_count = len(triggered_strategies)

            # -----------------------------------------------------------------
            # Step 3: Least-Profit Strategy Selection for Buy Signals
            # -----------------------------------------------------------------
            chosen_strat_name: str | None = None
            strategy_sl: float | None = None
            strategy_tp: float | None = None
            strategy_profit_pct: float | None = None

            if confluence_count > 0:
                # Rank triggered strategies by expected profit to pick the least profit
                candidates_with_profit = []
                for s_name in triggered_strategies:
                    s_info = strategy_details[s_name]
                    s_tp = s_info.get("take_profit")
                    s_sl = s_info.get("stop_loss")
                    if s_tp is not None and s_tp > prev_close_price:
                        profit_amt = s_tp - prev_close_price
                        profit_pct = (profit_amt / prev_close_price) * 100.0
                        candidates_with_profit.append(
                            (profit_amt, profit_pct, s_name, s_sl, s_tp)
                        )

                if candidates_with_profit:
                    # Select the strategy with the lowest positive profit
                    candidates_with_profit.sort(key=lambda item: item[0])
                    (
                        _,
                        strategy_profit_pct,
                        chosen_strat_name,
                        strategy_sl,
                        strategy_tp,
                    ) = candidates_with_profit[0]
                    strategy_profit_pct = round(strategy_profit_pct, 2)
                else:
                    # If no strategy specified take profit > close, choose first triggered
                    chosen_strat_name = triggered_strategies[0]
                    strategy_sl = strategy_details[chosen_strat_name].get("stop_loss")
                    strategy_tp = strategy_details[chosen_strat_name].get("take_profit")
                    if strategy_tp and strategy_tp > prev_close_price:
                        strategy_profit_pct = round(
                            (strategy_tp - prev_close_price) / prev_close_price * 100.0, 2
                        )

            # -----------------------------------------------------------------
            # Step 4: Determine Indicator, Effective SL/TP, and Action Guidance
            # -----------------------------------------------------------------
            if pos_sell_triggered:
                if pos_sell_reason == "PROFIT_TARGET":
                    indicator_status = "SELL"
                    indicator_badge = "[SELL (PROFIT TARGET)]"
                    indicator_color = "#e06c75"
                    effective_sl = pos_sl_price
                    effective_tp = pos_target_price
                    target_action = (
                        f"Action: SELL to lock profit | Pos #{pos_trade_id} "
                        f"Entry: INR {pos_entry_price:,.2f} | "
                        f"Target: INR {pos_target_price:,.2f} reached "
                        f"(Gain: +{pos_pnl_pct:.1f}%)"
                    )
                else:
                    indicator_status = "SELL"
                    indicator_badge = "[SELL (STOP LOSS)]"
                    indicator_color = "#e06c75"
                    effective_sl = pos_sl_price
                    effective_tp = pos_target_price
                    target_action = (
                        f"Action: SELL to cut loss | Pos #{pos_trade_id} "
                        f"Entry: INR {pos_entry_price:,.2f} | "
                        f"SL: INR {pos_sl_price:,.2f} breached "
                        f"(Loss: {pos_pnl_pct:.1f}%)"
                    )
            elif confluence_count >= 2:
                indicator_status = "STRONG BUY"
                indicator_badge = f"[STRONG BUY ({confluence_count})]"
                indicator_color = "#2ecc71"
                effective_sl = strategy_sl
                effective_tp = strategy_tp
                action_parts = ["Action: Buy at Market Open"]
                if chosen_strat_name:
                    action_parts.append(f"Setup: {chosen_strat_name}")
                if effective_sl:
                    action_parts.append(f"SL: INR {effective_sl:,.2f}")
                if effective_tp:
                    tp_str = f"Target: INR {effective_tp:,.2f}"
                    if strategy_profit_pct is not None:
                        tp_str += f" (+{strategy_profit_pct:.1f}%)"
                    action_parts.append(tp_str)
                target_action = " | ".join(action_parts)
            elif confluence_count == 1:
                indicator_status = "BUY"
                indicator_badge = "[BUY (1)]"
                indicator_color = "#27ae60"
                effective_sl = strategy_sl
                effective_tp = strategy_tp
                action_parts = ["Action: Buy at Market Open"]
                if chosen_strat_name:
                    action_parts.append(f"Setup: {chosen_strat_name}")
                if effective_sl:
                    action_parts.append(f"SL: INR {effective_sl:,.2f}")
                if effective_tp:
                    tp_str = f"Target: INR {effective_tp:,.2f}"
                    if strategy_profit_pct is not None:
                        tp_str += f" (+{strategy_profit_pct:.1f}%)"
                    action_parts.append(tp_str)
                target_action = " | ".join(action_parts)
            elif has_open_position:
                first_pos = matching_positions[0]
                p_entry = float(first_pos.get("entry_price", 0.0))
                p_target = first_pos.get("sell_target")
                p_sl = first_pos.get("stop_loss")
                p_id = first_pos.get("trade_id")
                u_pnl_pct = (
                    round((prev_close_price - p_entry) / p_entry * 100.0, 2)
                    if p_entry > 0
                    else 0.0
                )
                indicator_status = "HOLD"
                indicator_badge = "[HOLD (OPEN)]"
                indicator_color = "#e5c07b"
                effective_sl = float(p_sl) if p_sl is not None else None
                effective_tp = float(p_target) if p_target is not None else None
                if p_target is not None:
                    target_action = (
                        f"Action: Hold open position #{p_id} | Entry: INR {p_entry:,.2f} | "
                        f"Target: INR {float(p_target):,.2f} (Current PnL: {u_pnl_pct:+.1f}%)"
                    )
                else:
                    target_action = (
                        f"Action: Hold open position #{p_id} | Entry: INR {p_entry:,.2f} "
                        f"(Current PnL: {u_pnl_pct:+.1f}%)"
                    )
            else:
                indicator_status = "NEUTRAL"
                indicator_badge = "[NEUTRAL]"
                indicator_color = "#7f8c8d"
                effective_sl = None
                effective_tp = None
                target_action = "No Buy / Sell Signal on Previous Close"

            company_name = metadata.get(ticker, ticker)

            results.append({
                "ticker": ticker,
                "name": company_name,
                "prev_close_date": prev_close_date,
                "prev_close_price": prev_close_price,
                "indicator": indicator_status,
                "indicator_badge": indicator_badge,
                "indicator_color": indicator_color,
                "confluence_count": confluence_count,
                "triggered_strategies": triggered_strategies,
                "strategies_str": (
                    ", ".join(triggered_strategies) if triggered_strategies else "-"
                ),
                "chosen_strategy": chosen_strat_name,
                "stop_loss": effective_sl,
                "take_profit": effective_tp,
                "profit_pct": (
                    pos_pnl_pct if pos_sell_triggered else strategy_profit_pct
                ),
                "target_action": target_action,
                "strategy_details": strategy_details,
                "has_open_position": has_open_position,
                "matching_positions": matching_positions,
                "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

        # Order by priority: SELL first, then STRONG BUY, BUY, HOLD, NEUTRAL
        def _sort_priority(item: dict) -> tuple:
            ind = item["indicator"]
            if ind == "SELL":
                return (0, -item.get("profit_pct", 0), item["ticker"])
            if ind == "STRONG BUY":
                return (1, -item["confluence_count"], item["ticker"])
            if ind == "BUY":
                return (2, -item["confluence_count"], item["ticker"])
            if ind == "HOLD":
                return (3, 0, item["ticker"])
            return (4, 0, item["ticker"])

        results.sort(key=_sort_priority)
        return results

    def to_dataframe(self, scan_results: list[dict]) -> pd.DataFrame:
        """Convert scan results into a tabular pandas DataFrame.

        Args:
            scan_results (list[dict]): Output list from scan().

        Returns:
            pd.DataFrame: Formatted DataFrame ready for table display or CSV export.
        """
        if not scan_results:
            return pd.DataFrame(columns=[
                "Ticker",
                "Company Name",
                "Indicator",
                "Confluence",
                "Triggered Strategies",
                "Previous Close (INR)",
                "Stop Loss (INR)",
                "Take Profit (INR)",
                "Target Action",
                "Close Date",
            ])

        records = []
        for r in scan_results:
            records.append({
                "Ticker": r["ticker"],
                "Company Name": r["name"],
                "Indicator": r["indicator_badge"],
                "Confluence": r["confluence_count"],
                "Triggered Strategies": r["strategies_str"],
                "Previous Close (INR)": round(r["prev_close_price"], 2),
                "Stop Loss (INR)": (
                    round(r["stop_loss"], 2) if r["stop_loss"] is not None else "N/A"
                ),
                "Take Profit (INR)": (
                    round(r["take_profit"], 2) if r["take_profit"] is not None else "N/A"
                ),
                "Target Action": r["target_action"],
                "Close Date": r["prev_close_date"],
            })

        return pd.DataFrame(records)
