"""Backtesting tab component for TradeBot dashboard."""

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from back_test_engine import BacktestEngine
from config import DEFAULT_INITIAL_CAPITAL, DEFAULT_RISK_PER_TRADE
from market_repository import MarketRepository
from strategies import STRATEGY_REGISTRY


class BacktestTab(QWidget):
    """Interactive Backtest analysis panel displaying strategy controls, KPIs, and trade logs."""

    def __init__(self, repo: MarketRepository):
        """Initialize the backtest tab with market repository reference and UI elements.

        Args:
            repo (MarketRepository): Data repository instance for fetching market prices.
        """
        super().__init__()
        self.repo = repo
        self.init_ui()

    def init_ui(self):
        """Construct backtesting control panel, KPI cards, and trade log table."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- Section 1: Configuration Controls Bar ---
        config_group = QGroupBox("Backtest Setup & Parameters")
        config_layout = QHBoxLayout(config_group)
        config_layout.setSpacing(12)

        # Strategy Selector
        config_layout.addWidget(QLabel("<b>Strategy:</b>"))
        self.strategy_selector = QComboBox()
        self.strategy_selector.addItems(list(STRATEGY_REGISTRY.keys()))
        config_layout.addWidget(self.strategy_selector)

        # Security / Ticker Selector
        config_layout.addWidget(QLabel("<b>Security:</b>"))
        self.ticker_selector = QComboBox()
        self.populate_tickers()
        config_layout.addWidget(self.ticker_selector)

        # Initial Capital Input
        config_layout.addWidget(QLabel("<b>Capital (INR):</b>"))
        self.capital_input = QDoubleSpinBox()
        self.capital_input.setRange(10_000, 100_000_000)
        self.capital_input.setSingleStep(50_000)
        self.capital_input.setValue(DEFAULT_INITIAL_CAPITAL)
        self.capital_input.setPrefix("₹ ")
        config_layout.addWidget(self.capital_input)

        # Risk Per Trade Input
        config_layout.addWidget(QLabel("<b>Risk/Trade:</b>"))
        self.risk_input = QDoubleSpinBox()
        self.risk_input.setRange(0.1, 10.0)
        self.risk_input.setSingleStep(0.25)
        self.risk_input.setValue(DEFAULT_RISK_PER_TRADE * 100)
        self.risk_input.setSuffix(" %")
        config_layout.addWidget(self.risk_input)

        # Execute Button
        self.run_button = QPushButton("Run Backtest")
        self.run_button.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.run_button.clicked.connect(self.execute_backtest)
        config_layout.addWidget(self.run_button)

        main_layout.addWidget(config_group)

        # Status & Diagnostic Banner
        self.fundamental_status_label = QLabel(
            "<b>Fundamental Screen:</b> Ready. Run backtest to analyze security metrics."
        )
        self.fundamental_status_label.setStyleSheet(
            "QLabel { background-color: #1e2227; color: #abb2bf; border: 1px solid #3b4048; "
            "border-radius: 4px; padding: 6px 10px; font-size: 11px; }"
        )
        main_layout.addWidget(self.fundamental_status_label)

        # --- Section 2: KPI Metrics Cards ---
        metrics_group = QGroupBox("Performance Summary")
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setSpacing(12)

        self.card_trades = self.create_metric_card("Total Trades", "0")
        self.card_pnl = self.create_metric_card("Total PnL (INR)", "₹ 0.00")
        self.card_winrate = self.create_metric_card("Win Rate", "0.0 %")
        self.card_wins = self.create_metric_card("Total Wins", "0")
        self.card_losses = self.create_metric_card("Total Losses", "0")
        self.card_final_capital = self.create_metric_card(
            "Final Capital", f"₹ {DEFAULT_INITIAL_CAPITAL:,.2f}"
        )

        metrics_layout.addWidget(self.card_trades["frame"], 0, 0)
        metrics_layout.addWidget(self.card_pnl["frame"], 0, 1)
        metrics_layout.addWidget(self.card_winrate["frame"], 0, 2)
        metrics_layout.addWidget(self.card_wins["frame"], 0, 3)
        metrics_layout.addWidget(self.card_losses["frame"], 0, 4)
        metrics_layout.addWidget(self.card_final_capital["frame"], 0, 5)

        main_layout.addWidget(metrics_group)

        # --- Section 3: Trade Execution Log Table ---
        log_group = QGroupBox("Trade Execution Journal")
        log_layout = QVBoxLayout(log_group)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Entry Date",
            "Exit Date",
            "Position Size",
            "Entry Price (INR)",
            "Exit Price (INR)",
            "PnL (INR)",
            "Return %",
            "Result",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        log_layout.addWidget(self.table)
        main_layout.addWidget(log_group)

    def create_metric_card(self, title: str, initial_value: str) -> dict:
        """Helper to create a formatted KPI summary card widget.

        Args:
            title (str): Metric label title.
            initial_value (str): Initial display string.

        Returns:
            dict: Dictionary with 'frame' (QFrame) and 'value_label' (QLabel).
        """
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 6px; padding: 6px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #9da5b4; font-size: 11px; font-weight: normal;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        value_label = QLabel(initial_value)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        value_label.setFont(font)
        value_label.setStyleSheet("color: #ffffff;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        return {"frame": frame, "value_label": value_label}

    def populate_tickers(self):
        """Populate the security selector dropdown from database."""
        tickers = self.repo.get_tickers()
        self.ticker_selector.clear()
        self.ticker_selector.addItems(tickers)

    def set_active_ticker(self, ticker_str: str):
        """Programmatically select a ticker in the dropdown.

        Args:
            ticker_str (str): Formatted ticker string (e.g. 'RELIANCE.NS (STOCK)').
        """
        index = self.ticker_selector.findText(ticker_str)
        if index >= 0:
            self.ticker_selector.setCurrentIndex(index)

    def execute_backtest(self):
        """Execute selected strategy backtest on chosen security and update UI."""
        strategy_name = self.strategy_selector.currentText()
        ticker_display = self.ticker_selector.currentText()

        if not ticker_display:
            QMessageBox.warning(self, "Selection Error", "Please select a security from the list.")
            return

        df_raw = self.repo.get_data(ticker_display)
        if df_raw.empty:
            QMessageBox.warning(
                self,
                "No Data Found",
                f"No price records discovered in database for {ticker_display}.",
            )
            return

        # Instantiate selected strategy
        strategy_class = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_class:
            QMessageBox.critical(self, "Error", f"Strategy '{strategy_name}' not found.")
            return

        capital = self.capital_input.value()
        risk_per_trade = self.risk_input.value() / 100.0

        strategy = strategy_class()
        signals_df = strategy.generate_signals(
            df_raw,
            capital=capital,
            risk_per_trade=risk_per_trade,
        )

        # Display security fundamental snapshot from repository cache if available
        fund_data = self.repo.get_fundamentals(ticker_display)
        if fund_data:
            beta_val = fund_data.get("beta_nsei") or fund_data.get("beta_yf")
            beta_str = f"{beta_val:.2f}" if beta_val is not None else "N/A"
            mcap_str = (
                f"₹ {fund_data['market_cap_cr']:,.0f} Cr"
                if fund_data.get("market_cap_cr")
                else "N/A"
            )
            de_str = (
                f"{fund_data['debt_to_equity']:.2f}"
                if fund_data.get("debt_to_equity") is not None
                else "N/A"
            )
            peg_str = (
                f"{fund_data['peg_ratio']:.2f}"
                if fund_data.get("peg_ratio") is not None
                else "N/A"
            )
            vol_str = (
                f"{int(fund_data['avg_volume_252']):,}"
                if fund_data.get("avg_volume_252")
                else "N/A"
            )
            inst_str = (
                f"{fund_data['institutional_ownership'] * 100:.1f}%"
                if fund_data.get("institutional_ownership")
                else "N/A"
            )
            self.fundamental_status_label.setText(
                f"<b>Security Fundamentals:</b> <b>MCap:</b> {mcap_str} | "
                f"<b>D/E:</b> {de_str} | <b>PEG:</b> {peg_str} | "
                f"<b>Beta (^NSEI):</b> {beta_str} | <b>252d Avg Vol:</b> {vol_str} | "
                f"<b>Inst Own:</b> {inst_str}"
            )
        else:
            self.fundamental_status_label.setText(
                "<b>Security Fundamentals:</b> No cached fundamental snapshot."
            )

        # Configure and execute backtesting engine
        engine = BacktestEngine(initial_capital=capital, risk_per_trade=risk_per_trade)
        results = engine.run(signals_df)

        metrics = results["Metrics"]
        trade_log = results["TradeLog"]

        # Update KPI Summary Cards
        self.update_metrics(metrics)

        # Populate Trade Log Table
        self.populate_trade_table(trade_log)

    def update_metrics(self, metrics: dict):
        """Update KPI metric card labels.

        Args:
            metrics (dict): Summary metrics output from BacktestEngine.
        """
        total_trades = metrics.get("TotalTrades", 0)
        total_pnl = metrics.get("TotalPnL", 0.0)
        win_rate = metrics.get("WinRatePct", 0.0)
        wins = metrics.get("Wins", 0)
        losses = metrics.get("Losses", 0)
        final_cap = metrics.get("FinalCapital", 0.0)

        self.card_trades["value_label"].setText(str(total_trades))

        pnl_text = f"₹ {total_pnl:+,.2f}"
        pnl_color = "#4caf50" if total_pnl >= 0 else "#f44336"
        self.card_pnl["value_label"].setText(pnl_text)
        self.card_pnl["value_label"].setStyleSheet(f"color: {pnl_color};")

        self.card_winrate["value_label"].setText(f"{win_rate:.1f} %")
        self.card_wins["value_label"].setText(str(wins))
        self.card_losses["value_label"].setText(str(losses))
        self.card_final_capital["value_label"].setText(f"₹ {final_cap:,.2f}")

    def populate_trade_table(self, trade_log):
        """Populate the trade execution journal table with trade log rows.

        Args:
            trade_log (pd.DataFrame): DataFrame containing executed trades.
        """
        self.table.setRowCount(0)
        if trade_log.empty:
            return

        self.table.setRowCount(len(trade_log))

        for row_idx, (_, row) in enumerate(trade_log.iterrows()):
            entry_date = str(row["EntryDate"])[:10]
            exit_date = str(row["ExitDate"])[:10]
            pos_size = f"{int(row['PositionSize']):,}"
            entry_price = f"₹ {row['EntryPrice']:,.2f}"
            exit_price = f"₹ {row['ExitPrice']:,.2f}"
            pnl_val = row["PnL"]
            pnl_str = f"₹ {pnl_val:+,.2f}"
            ret_str = f"{row['ReturnPct']:+.2f} %"
            exit_reason = row.get("ExitReason", "Signal")
            result_str = f"{row['Result']} ({exit_reason})"

            items = [
                QTableWidgetItem(entry_date),
                QTableWidgetItem(exit_date),
                QTableWidgetItem(pos_size),
                QTableWidgetItem(entry_price),
                QTableWidgetItem(exit_price),
                QTableWidgetItem(pnl_str),
                QTableWidgetItem(ret_str),
                QTableWidgetItem(result_str),
            ]

            # Text alignment and color-coding
            for col_idx, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx in (5, 6):  # PnL & Return %
                    color = QColor(76, 175, 80) if pnl_val >= 0 else QColor(244, 67, 54)
                    item.setForeground(color)
                elif col_idx == 7:  # Result badge
                    color = QColor(76, 175, 80) if row["Result"] == "Win" else QColor(244, 67, 54)
                    item.setForeground(color)

                self.table.setItem(row_idx, col_idx, item)
