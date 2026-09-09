"""Morning scanner module for evaluating market buy signals on previous close.

Scans all active equity stocks (excluding indices) from the SQLite database,
feeds 3 to 6 months of historical data into all registered strategies to
warm up technical indicators, and identifies buy signals triggered on the
previous session close.
"""

from datetime import datetime, timezone

import pandas as pd

from market_repository import MarketRepository
from strategies import STRATEGY_REGISTRY


class MorningScanner:
    """Scanner engine to detect pre-market buy signals across all active stocks."""

    def __init__(self, repo: MarketRepository | None = None):
        """Initialize the morning scanner with a data repository instance.

        Args:
            repo (MarketRepository | None): Market data repository. Defaults to new instance.
        """
        self.repo = repo if repo is not None else MarketRepository()

    def scan(
        self,
        lookback_months: int = 6,
        trigger_scope: str = "last_bar",
    ) -> list[dict]:
        """Execute scan across all active equity stocks using historical lookback.

        For each stock, feeds the past `lookback_months` (typically 3 to 6 months)
        of historical records into every strategy in STRATEGY_REGISTRY to compute
        indicators, and checks whether a buy signal (Signal == 1) was triggered
        on the previous close.

        Args:
            lookback_months (int): Number of months of historical price data to
                feed into strategy calculations (3 to 6 months recommended).
                Defaults to 6.
            trigger_scope (str): Scope of the trigger check:
                - "last_bar": Strictly on the final completed bar (previous close candle).
                - "previous_day": On any bar of the previous completed trading day's session.
                Defaults to "last_bar".

        Returns:
            list[dict]: List of scan result dictionaries for all evaluated stocks,
                sorted with highest confluence (multiple buy strategies) first.
        """
        # Fetch stock metadata (ticker -> company name) and all price series
        metadata = self.repo.get_stock_metadata()
        stocks_data = self.repo.get_all_stocks_data()

        if not stocks_data:
            return []

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

            triggered_strategies: list[str] = []
            strategy_details: dict[str, dict] = {}
            stop_loss_candidates: list[float] = []
            take_profit_candidates: list[float] = []

            # Evaluate each registered strategy on the historical price slice
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
                        if sl_val is not None:
                            stop_loss_candidates.append(sl_val)
                        if tp_val is not None:
                            take_profit_candidates.append(tp_val)

                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
                    # Log strategy evaluation error without crashing scan
                    print(f"Error evaluating '{strat_name}' on '{ticker}': {err}")

            confluence_count = len(triggered_strategies)

            # Determine visual status indicator and badge
            if confluence_count >= 2:
                indicator_status = "STRONG BUY"
                indicator_badge = f"[STRONG BUY ({confluence_count})]"
                indicator_color = "#2ecc71"
            elif confluence_count == 1:
                indicator_status = "BUY"
                indicator_badge = "[BUY (1)]"
                indicator_color = "#27ae60"
            else:
                indicator_status = "NEUTRAL"
                indicator_badge = "[NEUTRAL]"
                indicator_color = "#7f8c8d"

            # Determine composite stop loss and take profit
            effective_sl = (
                max(stop_loss_candidates) if stop_loss_candidates else None
            )
            effective_tp = (
                min(take_profit_candidates) if take_profit_candidates else None
            )

            # Construct actionable target guidance string
            if confluence_count > 0:
                action_parts = ["Action: Buy at Market Open"]
                if effective_sl:
                    action_parts.append(f"SL: INR {effective_sl:,.2f}")
                if effective_tp:
                    action_parts.append(f"Target: INR {effective_tp:,.2f}")
                target_action = " | ".join(action_parts)
            else:
                target_action = "No Buy Signal on Previous Close"

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
                "stop_loss": effective_sl,
                "take_profit": effective_tp,
                "target_action": target_action,
                "strategy_details": strategy_details,
                "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

        # Order by confluence count (descending) so top setups appear first, then ticker
        results.sort(key=lambda x: (-x["confluence_count"], x["ticker"]))
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
