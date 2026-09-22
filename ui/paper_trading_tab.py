"""Paper Trading Dashboard tab component for TradeBot desktop application.

Provides interactive order entry for Nifty 50 swing trading, 1% risk position sizing,
real-time price updates via yfinance on a background QThread, automatic stop loss
and profit target execution simulation, and comprehensive portfolio tracking.
"""

from datetime import datetime, timezone
from typing import Any

# pylint: disable=no-name-in-module
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from market_repository import MarketRepository
from paper_trading_engine import (
    BASELINE_RISK_PER_TRADE,
    MAX_TRADE_ALLOCATION,
    PaperTradingEngine,
    PositionSizingError,
)
from ui.nifty_header_widget import is_market_open_ist
from ui.paper_trading_dialogs import ModifyPositionDialog, PartialSellDialog
from ui.ticker_chart_popup import TickerChartPopupDialog


class PaperTradingWorker(QThread):
    """Background worker thread to fetch live quotes and trigger exit evaluations."""

    prices_updated = pyqtSignal(dict)
    trades_exited = pyqtSignal(list)
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, engine: PaperTradingEngine, interval_seconds: int = 10):
        """Initialize worker with paper trading engine instance.

        Args:
            engine (PaperTradingEngine): Backend engine instance.
            interval_seconds (int): Polling frequency in seconds. Defaults to 10.
        """
        super().__init__()
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._is_running = True
        self._manual_trigger = False

    def run(self) -> None:
        """Continuously poll live market prices for active open positions when market is open."""
        while self._is_running:
            try:
                is_open, desc = is_market_open_ist()
                if not is_open and not self._manual_trigger:
                    self.status_updated.emit(
                        f"Monitoring paused: Market closed ({desc} - ● NSE CLOSED)"
                    )
                else:
                    open_trades = self.engine.get_open_trades()
                    if open_trades:
                        tickers = list({t["ticker"] for t in open_trades})
                        self.status_updated.emit(
                            f"Fetching live quotes for {len(tickers)} active position(s)..."
                        )

                        price_map = self.engine.fetch_live_quotes_batch(tickers)
                        if price_map:
                            exited_trades = self.engine.evaluate_open_trades(price_map)
                            self.prices_updated.emit(price_map)

                            if exited_trades:
                                self.trades_exited.emit(exited_trades)

                        now_str = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
                        self.status_updated.emit(
                            f"Monitoring active: {len(tickers)} stock(s) updated at {now_str}"
                        )
                    else:
                        self.status_updated.emit("Monitoring idle: No active open positions.")

            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
                self.error_occurred.emit(str(err))

            # Sleep in 500ms intervals to respond promptly to stop requests
            sleep_chunks = int(self.interval_seconds * 2)
            for _ in range(sleep_chunks):
                if not self._is_running or self._manual_trigger:
                    break
                self.msleep(500)

            self._manual_trigger = False

    def trigger_now(self) -> None:
        """Wake up worker to execute immediate price refresh."""
        self._manual_trigger = True

    def stop(self) -> None:
        """Gracefully stop background thread loop."""
        self._is_running = False


class PaperTradingTab(QWidget):
    """Paper trading dashboard containing portfolio metrics, order entry, and trade tables."""

    def __init__(self, repo: Any | None = None):
        """Initialize paper trading tab with engine and UI components.

        Args:
            repo (Any | None): Optional MarketRepository instance (for Nifty 50 ticker list).
        """
        super().__init__()
        self.engine = PaperTradingEngine()
        self.repo = repo or MarketRepository()
        self.worker: PaperTradingWorker | None = None
        self._active_chart_dialog: TickerChartPopupDialog | None = None

        self.init_ui()
        self.refresh_all_views()
        self.start_background_worker()

    def init_ui(self) -> None:
        """Construct the dashboard layout, summary cards, form, and data tables."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 10, 12, 10)

        # =====================================================================
        # Top Section: Portfolio Summary Cards Banner
        # =====================================================================
        banner_layout = QHBoxLayout()
        banner_layout.setSpacing(10)

        self.kpi_cash = self._create_kpi_card("Available Cash", "₹5,00,000.00", "#abb2bf")
        self.kpi_invested = self._create_kpi_card("Active Deployed Capital", "₹0.00", "#61afef")
        self.kpi_unrealized = self._create_kpi_card("Open Unrealized PnL", "₹0.00 (0.0%)", "#98c379")
        self.kpi_realized = self._create_kpi_card("Realized PnL", "₹0.00", "#98c379")
        self.kpi_total_val = self._create_kpi_card("Total Portfolio Net Worth", "₹5,00,000.00", "#e5c07b")

        banner_layout.addWidget(self.kpi_cash["frame"])
        banner_layout.addWidget(self.kpi_invested["frame"])
        banner_layout.addWidget(self.kpi_unrealized["frame"])
        banner_layout.addWidget(self.kpi_realized["frame"])
        banner_layout.addWidget(self.kpi_total_val["frame"])

        main_layout.addLayout(banner_layout)

        # =====================================================================
        # Control Bar: Action Buttons & Worker Status
        # =====================================================================
        control_bar = QHBoxLayout()
        control_bar.setSpacing(8)

        self.btn_refresh = QPushButton("🔄 Refresh Live Quotes")
        self.btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #ffffff; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; border: 1px solid #4b5263; } "
            "QPushButton:hover { background-color: #4b5263; }"
        )
        self.btn_refresh.clicked.connect(self.manual_refresh)
        control_bar.addWidget(self.btn_refresh)

        self.btn_toggle_worker = QPushButton("⏸ Pause Auto-Monitor")
        self.btn_toggle_worker.setStyleSheet(
            "QPushButton { background-color: #2c313a; color: #abb2bf; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #3b4048; } "
            "QPushButton:hover { background-color: #3e4451; color: white; }"
        )
        self.btn_toggle_worker.clicked.connect(self.toggle_worker)
        control_bar.addWidget(self.btn_toggle_worker)

        self.btn_reset_portfolio = QPushButton("🔁 Reset Virtual Capital (₹5L)")
        self.btn_reset_portfolio.setStyleSheet(
            "QPushButton { background-color: #4c2222; color: #ff6b6b; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #7c2d2d; } "
            "QPushButton:hover { background-color: #7c2d2d; color: white; }"
        )
        self.btn_reset_portfolio.clicked.connect(self.confirm_reset_portfolio)
        control_bar.addWidget(self.btn_reset_portfolio)

        control_bar.addSpacing(15)
        self.lbl_status = QLabel("Engine Ready. Worker starting...")
        self.lbl_status.setStyleSheet("color: #7f848e; font-style: italic;")
        control_bar.addWidget(self.lbl_status, stretch=1)

        main_layout.addLayout(control_bar)

        # =====================================================================
        # Main Work Area: Splitter (Order Entry on Left, Tables on Right)
        # =====================================================================
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Column: Order Entry Form & Position Sizing
        left_container = self._create_order_entry_widget()
        splitter.addWidget(left_container)

        # Right Column: Tabbed Tables (Open Positions & Trade History)
        right_container = self._create_tables_widget()
        splitter.addWidget(right_container)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 800])

        main_layout.addWidget(splitter)

    def _create_kpi_card(self, title: str, initial_value: str, color_hex: str) -> dict[str, Any]:
        """Create a styled metric card container widget."""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 6px; padding: 6px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #9da5b4; font-size: 11px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        val_lbl = QLabel(initial_value)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        val_lbl.setFont(font)
        val_lbl.setStyleSheet(f"color: {color_hex};")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)

        return {"frame": frame, "value_label": val_lbl}

    def _create_order_entry_widget(self) -> QWidget:
        """Construct the order entry form with dynamic 1% risk position sizing readout."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        group = QGroupBox("Order Entry & Position Sizing (Nifty 50)")
        group.setStyleSheet(
            "QGroupBox { color: #abb2bf; font-weight: bold; border: 1px solid #3b4048; "
            "border-radius: 6px; margin-top: 8px; padding-top: 14px; background-color: #21252b; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        form_layout = QVBoxLayout(group)
        form_layout.setSpacing(8)

        # 1. Ticker Selection (Type to search Nifty 50 stocks)
        form_layout.addWidget(QLabel("<b>Nifty 50 Security:</b>"))
        self.ticker_combo = QComboBox()
        self.ticker_combo.setEditable(True)
        self.ticker_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._populate_tickers()

        # Configure QCompleter for substring / contains typing search
        completer = self.ticker_combo.completer()
        if completer:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.activated[str].connect(self._on_completer_activated)

        if self.ticker_combo.lineEdit():
            self.ticker_combo.lineEdit().setPlaceholderText("Type symbol or name to search...")
            self.ticker_combo.lineEdit().editingFinished.connect(self._on_ticker_editing_finished)

        self.ticker_combo.currentIndexChanged.connect(self._on_ticker_changed)
        form_layout.addWidget(self.ticker_combo)

        fetch_row = QHBoxLayout()
        self.btn_fetch_cmp = QPushButton("⚡ Fetch CMP")
        self.btn_fetch_cmp.setStyleSheet(
            "QPushButton { background-color: #2c313a; color: #61afef; font-size: 11px; "
            "padding: 4px 8px; border: 1px solid #3b4048; border-radius: 4px; font-weight: bold; } "
            "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
        )
        self.btn_fetch_cmp.clicked.connect(self.fetch_cmp_for_selected)
        fetch_row.addWidget(self.btn_fetch_cmp)

        self.btn_view_chart = QPushButton("📈 3M Chart")
        self.btn_view_chart.setStyleSheet(
            "QPushButton { background-color: #2c313a; color: #98c379; font-size: 11px; "
            "padding: 4px 8px; border: 1px solid #3b4048; border-radius: 4px; font-weight: bold; } "
            "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
        )
        self.btn_view_chart.setToolTip("Open 3-month interactive chart for the selected stock")
        self.btn_view_chart.clicked.connect(self._on_view_chart_clicked)
        fetch_row.addWidget(self.btn_view_chart)

        form_layout.addLayout(fetch_row)

        # 2. Entry Price
        form_layout.addWidget(QLabel("<b>Entry Price (₹):</b>"))
        self.spin_entry = QDoubleSpinBox()
        self.spin_entry.setRange(0.01, 1_000_000.00)
        self.spin_entry.setDecimals(2)
        self.spin_entry.setValue(280.00)
        self.spin_entry.valueChanged.connect(self.recalculate_position_size)
        form_layout.addWidget(self.spin_entry)

        # 3. Mandatory Stop Loss
        form_layout.addWidget(QLabel("<b>Mandatory Stop Loss (₹):</b>"))
        self.spin_sl = QDoubleSpinBox()
        self.spin_sl.setRange(0.01, 1_000_000.00)
        self.spin_sl.setDecimals(2)
        self.spin_sl.setValue(260.00)
        self.spin_sl.valueChanged.connect(self.recalculate_position_size)
        form_layout.addWidget(self.spin_sl)

        # 4. Optional Sell Target
        target_header_layout = QHBoxLayout()
        self.chk_target = QCheckBox("Sell Target (₹) [Optional]:")
        chk_target_font = self.chk_target.font()
        chk_target_font.setBold(True)
        self.chk_target.setFont(chk_target_font)
        self.chk_target.setChecked(True)
        self.chk_target.toggled.connect(self._on_target_toggled)
        target_header_layout.addWidget(self.chk_target)
        form_layout.addLayout(target_header_layout)

        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.01, 1_000_000.00)
        self.spin_target.setDecimals(2)
        self.spin_target.setValue(320.00)
        self.spin_target.valueChanged.connect(self.recalculate_position_size)
        form_layout.addWidget(self.spin_target)

        # 5. Position Sizing Breakdown Display Card
        calc_box = QFrame()
        calc_box.setStyleSheet(
            "QFrame { background-color: #1e2227; border: 1px solid #2d3139; "
            "border-radius: 4px; padding: 6px; }"
        )
        calc_layout = QGridLayout(calc_box)
        calc_layout.setSpacing(4)

        calc_layout.addWidget(QLabel("Risk Budget (1% of 1L):"), 0, 0)
        lbl_risk_budget = QLabel(f"₹{BASELINE_RISK_PER_TRADE:,.0f}")
        lbl_risk_budget.setStyleSheet("color: #e5c07b; font-weight: bold;")
        calc_layout.addWidget(lbl_risk_budget, 0, 1)

        calc_layout.addWidget(QLabel("Max Trade Capital:"), 1, 0)
        lbl_max_cap = QLabel(f"₹{MAX_TRADE_ALLOCATION:,.0f}")
        lbl_max_cap.setStyleSheet("color: #abb2bf;")
        calc_layout.addWidget(lbl_max_cap, 1, 1)

        calc_layout.addWidget(QLabel("<b>Allowed Quantity:</b>"), 2, 0)
        self.lbl_calc_qty = QLabel("50 Shares")
        self.lbl_calc_qty.setStyleSheet("color: #98c379; font-size: 13px; font-weight: bold;")
        calc_layout.addWidget(self.lbl_calc_qty, 2, 1)

        calc_layout.addWidget(QLabel("Trade Capital Required:"), 3, 0)
        self.lbl_calc_capital = QLabel("₹14,000.00")
        self.lbl_calc_capital.setStyleSheet("color: #61afef; font-weight: bold;")
        calc_layout.addWidget(self.lbl_calc_capital, 3, 1)

        calc_layout.addWidget(QLabel("Max Loss at SL:"), 4, 0)
        self.lbl_calc_loss = QLabel("-₹1,000.00 (-7.14%)")
        self.lbl_calc_loss.setStyleSheet("color: #e06c75;")
        calc_layout.addWidget(self.lbl_calc_loss, 4, 1)

        calc_layout.addWidget(QLabel("Max Gain at Target:"), 5, 0)
        self.lbl_calc_gain = QLabel("+₹2,000.00 (+14.29%)")
        self.lbl_calc_gain.setStyleSheet("color: #98c379;")
        calc_layout.addWidget(self.lbl_calc_gain, 5, 1)

        calc_layout.addWidget(QLabel("Risk : Reward:"), 6, 0)
        self.lbl_calc_rrr = QLabel("1 : 2.00")
        self.lbl_calc_rrr.setStyleSheet("color: #e5c07b; font-weight: bold;")
        calc_layout.addWidget(self.lbl_calc_rrr, 6, 1)

        form_layout.addWidget(calc_box)

        # 6. Action Button: Place Order
        self.btn_place_order = QPushButton("🚀 Place Paper Trade (BUY)")
        self.btn_place_order.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: #ffffff; font-weight: bold; "
            "font-size: 13px; padding: 10px 14px; border-radius: 4px; border: none; } "
            "QPushButton:hover { background-color: #2ecc71; } "
            "QPushButton:disabled { background-color: #3b4048; color: #7f848e; }"
        )
        self.btn_place_order.clicked.connect(self.place_paper_order)
        form_layout.addWidget(self.btn_place_order)

        form_layout.addStretch()
        layout.addWidget(group)

        # Initial calculation
        self.recalculate_position_size()
        return container

    def _create_tables_widget(self) -> QWidget:
        """Construct tables for active positions and historical trade journal."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Section A: Open Positions Table
        open_group = QGroupBox("Active Open Positions (Live-Market Monitoring)")
        open_group.setStyleSheet(
            "QGroupBox { color: #abb2bf; font-weight: bold; border: 1px solid #3b4048; "
            "border-radius: 6px; margin-top: 8px; padding-top: 14px; background-color: #21252b; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        open_layout = QVBoxLayout(open_group)
        open_layout.setContentsMargins(8, 8, 8, 8)

        self.table_open = QTableWidget()
        open_headers = [
            "Trade ID",
            "Entry Date",
            "Ticker",
            "Qty",
            "Entry (₹)",
            "Current (₹)",
            "Stop Loss (₹)",
            "Target (₹)",
            "Invested (₹)",
            "Market Val (₹)",
            "PnL (₹)",
            "PnL (%)",
            "Actions",
        ]
        self.table_open.setColumnCount(len(open_headers))
        self.table_open.setHorizontalHeaderLabels(open_headers)
        self.table_open.setAlternatingRowColors(True)
        self.table_open.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_open.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._apply_table_style(self.table_open)

        open_header = self.table_open.horizontalHeader()
        for idx in range(len(open_headers)):
            open_header.setSectionResizeMode(idx, QHeaderView.ResizeMode.ResizeToContents)
        open_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_open.cellClicked.connect(self._on_open_table_cell_clicked)
        self.table_open.itemDoubleClicked.connect(self._on_open_table_double_clicked)

        open_layout.addWidget(self.table_open)
        layout.addWidget(open_group, stretch=1)

        # Section B: Trade History Journal Table
        history_group = QGroupBox("Trade History Journal (Closed Positions)")
        history_group.setStyleSheet(
            "QGroupBox { color: #abb2bf; font-weight: bold; border: 1px solid #3b4048; "
            "border-radius: 6px; margin-top: 8px; padding-top: 14px; background-color: #21252b; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(8, 8, 8, 8)

        self.table_history = QTableWidget()
        history_headers = [
            "Trade ID",
            "Entry Date",
            "Exit Date",
            "Ticker",
            "Side",
            "Qty",
            "Entry (₹)",
            "Exit (₹)",
            "Realized PnL (₹)",
            "Return (%)",
            "Exit Reason",
            "Exit Time",
        ]
        self.table_history.setColumnCount(len(history_headers))
        self.table_history.setHorizontalHeaderLabels(history_headers)
        self.table_history.setAlternatingRowColors(True)
        self.table_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._apply_table_style(self.table_history)

        history_header = self.table_history.horizontalHeader()
        for idx in range(len(history_headers)):
            history_header.setSectionResizeMode(idx, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_history.cellClicked.connect(self._on_history_table_cell_clicked)
        self.table_history.itemDoubleClicked.connect(self._on_history_table_double_clicked)

        history_layout.addWidget(self.table_history)
        layout.addWidget(history_group, stretch=1)

        return container

    def _apply_table_style(self, table: QTableWidget) -> None:
        """Apply dark theme styling to table widget."""
        table.setStyleSheet(
            "QTableWidget { background-color: #21252b; alternate-background-color: #282c34; "
            "color: #abb2bf; gridline-color: #3b4048; border: 1px solid #3b4048; "
            "border-radius: 4px; } "
            "QHeaderView::section { background-color: #1e1e1e; color: #d7dae0; "
            "font-weight: bold; border: 1px solid #3b4048; padding: 5px; } "
            "QTableWidget::item:selected { background-color: #2c313a; color: #ffffff; }"
        )

    def _populate_tickers(self) -> None:
        """Populate ticker dropdown with Nifty 50 equities from database."""
        self.ticker_combo.clear()
        nifty_stocks = self.engine.get_nifty50_tickers()

        if not nifty_stocks and self.repo:
            all_tickers = self.repo.get_tickers()
            nifty_stocks = [
                {"ticker": t.split(" ")[0], "name": t}
                for t in all_tickers
                if "(STOCK)" in t
            ]

        for item in nifty_stocks:
            ticker = item["ticker"]
            name = item.get("name", "")
            display = f"{ticker} - {name}" if name else ticker
            self.ticker_combo.addItem(display, ticker)

        # Select RELIANCE.NS as default if present
        idx = self.ticker_combo.findData("RELIANCE.NS")
        if idx >= 0:
            self.ticker_combo.setCurrentIndex(idx)

    def _on_completer_activated(self, text: str) -> None:
        """Handle selection from auto-completer popup list."""
        idx = self.ticker_combo.findText(text)
        if idx >= 0:
            self.ticker_combo.setCurrentIndex(idx)
        self.recalculate_position_size()

    def _on_ticker_editing_finished(self) -> None:
        """Resolve typed text when user presses Enter or leaves ticker field."""
        raw_text = self.ticker_combo.currentText().strip()
        if not raw_text:
            return

        if (
            self.ticker_combo.currentIndex() >= 0
            and raw_text == self.ticker_combo.itemText(self.ticker_combo.currentIndex())
        ):
            return

        resolved_ticker = self._resolve_ticker_from_text(raw_text)
        if resolved_ticker:
            idx = self.ticker_combo.findData(resolved_ticker)
            if idx >= 0:
                self.ticker_combo.setCurrentIndex(idx)
        self.recalculate_position_size()

    def _resolve_ticker_from_text(self, text: str) -> str | None:
        """Find matching ticker from user-entered text (ticker symbol or company name).

        Args:
            text (str): Query string entered by user.

        Returns:
            str | None: Resolved clean ticker symbol or None.
        """
        clean = text.strip().upper()
        if not clean:
            return None

        # 1. Exact ticker match (with or without .NS)
        for i in range(self.ticker_combo.count()):
            data = str(self.ticker_combo.itemData(i)).upper()
            if data == clean or data == f"{clean}.NS" or data.replace(".NS", "") == clean:
                return str(self.ticker_combo.itemData(i))

        # 2. Substring match in display text (e.g. 'Tata Motors' or 'RELIANCE')
        for i in range(self.ticker_combo.count()):
            item_label = self.ticker_combo.itemText(i).upper()
            if clean in item_label:
                return str(self.ticker_combo.itemData(i))

        return None

    def _get_selected_ticker(self) -> str:
        """Extract valid selected ticker symbol from combo box data or line edit text.

        Returns:
            str: Resolved ticker symbol (e.g., 'RELIANCE.NS').
        """
        curr_text = self.ticker_combo.currentText().strip()
        if curr_text:
            resolved = self._resolve_ticker_from_text(curr_text)
            if resolved:
                return resolved

        curr_data = self.ticker_combo.currentData()
        if curr_data:
            return str(curr_data)

        return curr_text.split(" ")[0].upper()

    def _on_ticker_changed(self) -> None:
        """Handle stock selection change."""
        self.recalculate_position_size()

    def _on_target_toggled(self, checked: bool) -> None:
        """Enable or disable sell target input."""
        self.spin_target.setEnabled(checked)
        self.recalculate_position_size()

    def fetch_cmp_for_selected(self) -> None:
        """Fetch current market price for selected security and set as entry price."""
        ticker = self._get_selected_ticker()
        if not ticker:
            return

        self.lbl_status.setText(f"Fetching CMP for {ticker}...")
        price = self.engine.fetch_live_quote(ticker)
        if price and price > 0:
            self.spin_entry.setValue(round(price, 2))
            # Auto suggest sensible default SL (2% below) and Target (4% above)
            sl_default = round(price * 0.98, 2)
            target_default = round(price * 1.04, 2)
            self.spin_sl.setValue(sl_default)
            self.spin_target.setValue(target_default)
            self.recalculate_position_size()
            self.lbl_status.setText(f"Fetched {ticker} CMP: ₹{price:,.2f}")
        else:
            self.lbl_status.setText(f"Could not fetch CMP for {ticker}. Check connection.")

    def recalculate_position_size(self) -> None:
        """Dynamically compute allowed quantity and metrics based on user inputs."""
        entry = self.spin_entry.value()
        sl = self.spin_sl.value()
        has_target = self.chk_target.isChecked()
        target = self.spin_target.value() if has_target else None

        if entry <= 0 or sl <= 0 or sl >= entry:
            self.lbl_calc_qty.setText("0 Shares (Invalid SL)")
            self.lbl_calc_qty.setStyleSheet("color: #e06c75; font-weight: bold;")
            self.lbl_calc_capital.setText("₹0.00")
            self.lbl_calc_loss.setText("N/A")
            self.lbl_calc_gain.setText("N/A")
            self.lbl_calc_rrr.setText("N/A")
            self.btn_place_order.setEnabled(False)
            return

        try:
            sizing = self.engine.calculate_position_size(entry_price=entry, stop_loss=sl)
            qty = sizing["allowed_quantity"]
            cap_req = sizing["capital_required"]
            risk_amt = sizing["actual_risk"]

            if qty <= 0:
                self.lbl_calc_qty.setText("0 Shares (Cap Exceeded)")
                self.lbl_calc_qty.setStyleSheet("color: #e06c75; font-weight: bold;")
                self.btn_place_order.setEnabled(False)
            else:
                self.lbl_calc_qty.setText(f"{qty} Shares")
                self.lbl_calc_qty.setStyleSheet("color: #98c379; font-size: 13px; font-weight: bold;")
                self.btn_place_order.setEnabled(True)

            self.lbl_calc_capital.setText(f"₹{cap_req:,.2f}")
            pct_loss = ((sl - entry) / entry * 100.0) if entry > 0 else 0.0
            self.lbl_calc_loss.setText(f"-₹{risk_amt:,.2f} ({pct_loss:.2f}%)")

            if target and target > entry:
                gain_amt = qty * (target - entry)
                pct_gain = ((target - entry) / entry * 100.0) if entry > 0 else 0.0
                self.lbl_calc_gain.setText(f"+₹{gain_amt:,.2f} (+{pct_gain:.2f}%)")

                risk_per_sh = entry - sl
                reward_per_sh = target - entry
                rrr = reward_per_sh / risk_per_sh if risk_per_sh > 0 else 0.0
                self.lbl_calc_rrr.setText(f"1 : {rrr:.2f}")
            else:
                self.lbl_calc_gain.setText("No Target Specified")
                self.lbl_calc_rrr.setText("Open Exit")

        except PositionSizingError as err:
            self.lbl_calc_qty.setText(f"Error: {err}")
            self.lbl_calc_qty.setStyleSheet("color: #e06c75; font-size: 10px;")
            self.btn_place_order.setEnabled(False)

    def place_paper_order(self) -> None:
        """Validate inputs and place trade via engine."""
        ticker = self._get_selected_ticker()
        if not ticker:
            QMessageBox.warning(
                self, "Invalid Security", "Please select or type a valid Nifty 50 stock."
            )
            return

        entry = self.spin_entry.value()
        sl = self.spin_sl.value()
        has_target = self.chk_target.isChecked()
        target = self.spin_target.value() if has_target else None

        try:
            order = self.engine.place_order(
                ticker=ticker,
                entry_price=entry,
                stop_loss=sl,
                sell_target=target,
                side="BUY",
            )
            QMessageBox.information(
                self,
                "Paper Trade Placed",
                f"Successfully opened trade #{order['trade_id']} for {order['quantity']} {order['ticker']} "
                f"at ₹{order['entry_price']:,.2f}.\n\nTotal Capital: ₹{order['total_cost']:,.2f}",
            )
            self.refresh_all_views()
            if self.worker:
                self.worker.trigger_now()

        except PositionSizingError as err:
            QMessageBox.critical(self, "Order Placement Failed", str(err))

    def manual_square_off(self, trade_id: int) -> None:
        """Prompt user and manually exit an open trade at current market price."""
        reply = QMessageBox.question(
            self,
            "Confirm Square Off",
            f"Are you sure you want to manually close Trade #{trade_id} at current market price?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            open_trades = {t["trade_id"]: t for t in self.engine.get_open_trades()}
            trade = open_trades.get(trade_id)
            if not trade:
                return

            exit_price = trade["current_price"]
            report = self.engine.close_trade(
                trade_id=trade_id,
                exit_price=exit_price,
                exit_reason="MANUAL_EXIT",
            )
            pnl = report["realized_pnl"]
            pnl_str = f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"
            QMessageBox.information(
                self,
                "Position Closed",
                f"Trade #{trade_id} ({report['ticker']}) closed at ₹{exit_price:,.2f}.\nRealized PnL: {pnl_str}",
            )
            self.refresh_all_views()

    def open_modify_dialog(self, trade_id: int) -> None:
        """Open modal dialog to update stop loss and target for a trade.

        Args:
            trade_id (int): Identifier of the trade to modify.
        """
        open_trades = {t["trade_id"]: t for t in self.engine.get_open_trades()}
        trade = open_trades.get(trade_id)
        if not trade:
            QMessageBox.warning(self, "Trade Not Found", f"Trade #{trade_id} is no longer open.")
            return

        dialog = ModifyPositionDialog(self, trade=trade, engine=self.engine)
        if dialog.exec() == ModifyPositionDialog.DialogCode.Accepted and dialog.updated_result:
            res = dialog.updated_result
            target_str = f"₹{res['sell_target']:,.2f}" if res["sell_target"] else "Disabled"
            self.refresh_all_views()
            self.lbl_status.setText(
                f"Trade #{trade_id} ({res['ticker']}) updated: "
                f"SL=₹{res['stop_loss']:,.2f}, Target={target_str}"
            )
            QMessageBox.information(
                self,
                "Position Modified",
                f"Trade #{trade_id} ({res['ticker']}) updated successfully!\n\n"
                f"New Stop Loss: ₹{res['stop_loss']:,.2f}\n"
                f"New Sell Target: {target_str}",
            )

    def open_partial_sell_dialog(self, trade_id: int) -> None:
        """Open modal dialog to sell a partial quantity of an active position.

        Args:
            trade_id (int): Identifier of the trade to partially exit.
        """
        open_trades = {t["trade_id"]: t for t in self.engine.get_open_trades()}
        trade = open_trades.get(trade_id)
        if not trade:
            QMessageBox.warning(self, "Trade Not Found", f"Trade #{trade_id} is no longer open.")
            return

        dialog = PartialSellDialog(self, trade=trade, engine=self.engine)
        if dialog.exec() == PartialSellDialog.DialogCode.Accepted and dialog.partial_result:
            res = dialog.partial_result
            pnl = res["realized_pnl"]
            pnl_str = f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"
            self.refresh_all_views()

            sold_qty = res.get("sold_quantity", res.get("quantity"))
            cap_ret = res.get(
                "capital_returned", res.get("quantity", 0) * res["exit_price"]
            )
            remain_qty = res.get("remaining_quantity", 0)

            msg = (
                f"Successfully sold {sold_qty} shares of {res['ticker']} "
                f"at ₹{res['exit_price']:,.2f}.\n\n"
                f"Realized PnL: {pnl_str} ({res['return_pct']:+.2f}%)\n"
                f"Capital Returned: ₹{cap_ret:,.2f}\n"
                f"Remaining Shares: {remain_qty}\n"
                f"Updated Cash Balance: ₹{res['updated_cash']:,.2f}"
            )
            self.lbl_status.setText(
                f"Trade #{trade_id} partial exit: sold {sold_qty} shares "
                f"@ ₹{res['exit_price']:,.2f}"
            )
            QMessageBox.information(self, "Partial Sell Executed", msg)

    def confirm_reset_portfolio(self) -> None:
        """Show confirmation and reset portfolio balance to INR 5,00,000."""
        reply = QMessageBox.warning(
            self,
            "Reset Virtual Capital",
            "This will reset your cash balance to ₹5,00,000 and clear all active/historical paper trades.\n\n"
            "Do you wish to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.reset_portfolio()
            self.refresh_all_views()
            QMessageBox.information(
                self,
                "Portfolio Reset",
                "Virtual portfolio has been successfully reset to ₹5,00,000.00.",
            )

    def refresh_all_views(self) -> None:
        """Update KPI banners, open positions table, and trade journal."""
        summary = self.engine.get_portfolio_summary()

        # 1. Update KPI Banner
        self.kpi_cash["value_label"].setText(f"₹{summary['cash_balance']:,.2f}")
        self.kpi_invested["value_label"].setText(f"₹{summary['open_positions_value']:,.2f}")

        # Unrealized PnL
        u_pnl = summary["open_unrealized_pnl"]
        u_pct = (
            (u_pnl / summary["open_positions_value"] * 100.0)
            if summary["open_positions_value"] > 0
            else 0.0
        )
        u_color = "#98c379" if u_pnl >= 0 else "#e06c75"
        u_sign = "+" if u_pnl >= 0 else ""
        self.kpi_unrealized["value_label"].setText(f"{u_sign}₹{u_pnl:,.2f} ({u_sign}{u_pct:.2f}%)")
        self.kpi_unrealized["value_label"].setStyleSheet(f"color: {u_color};")

        # Realized PnL
        r_pnl = summary["total_realized_pnl"]
        r_color = "#98c379" if r_pnl >= 0 else "#e06c75"
        r_sign = "+" if r_pnl >= 0 else ""
        self.kpi_realized["value_label"].setText(f"{r_sign}₹{r_pnl:,.2f}")
        self.kpi_realized["value_label"].setStyleSheet(f"color: {r_color};")

        # Total Net Worth
        tot_val = summary["total_portfolio_value"]
        tot_color = "#98c379" if tot_val >= summary["initial_capital"] else "#e06c75"
        self.kpi_total_val["value_label"].setText(f"₹{tot_val:,.2f}")
        self.kpi_total_val["value_label"].setStyleSheet(f"color: {tot_color}; font-weight: bold;")

        # 2. Populate Open Positions Table
        open_trades = self.engine.get_open_trades()
        self.table_open.setRowCount(len(open_trades))

        for row_idx, trade in enumerate(open_trades):
            trade_id = trade["trade_id"]
            pnl = trade["unrealized_pnl"]
            pnl_pct = trade["pnl_pct"]
            pnl_color = QColor("#98c379") if pnl >= 0 else QColor("#e06c75")

            entry_d = trade.get("entry_date") or trade["timestamp"][:10]
            items = [
                QTableWidgetItem(f"#{trade_id}"),
                QTableWidgetItem(entry_d),
                QTableWidgetItem(trade["ticker"]),
                QTableWidgetItem(str(trade["quantity"])),
                QTableWidgetItem(f"₹{trade['entry_price']:,.2f}"),
                QTableWidgetItem(f"₹{trade['current_price']:,.2f}"),
                QTableWidgetItem(f"₹{trade['stop_loss']:,.2f}"),
                QTableWidgetItem(
                    f"₹{trade['sell_target']:,.2f}" if trade["sell_target"] else "—"
                ),
                QTableWidgetItem(f"₹{trade['invested_value']:,.2f}"),
                QTableWidgetItem(f"₹{trade['current_value']:,.2f}"),
                QTableWidgetItem(f"{'+' if pnl >= 0 else ''}₹{pnl:,.2f}"),
                QTableWidgetItem(f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%"),
            ]

            # Set text alignment and PnL color
            for col_idx, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    if col_idx in [3, 4, 5, 6, 7, 8, 9, 10, 11]
                    else Qt.AlignmentFlag.AlignCenter
                )
                if col_idx in [10, 11]:
                    item.setForeground(pnl_color)
                if col_idx == 2:
                    # Highlight ticker with interactive accent styling
                    item.setForeground(QColor("#61afef"))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                    item.setToolTip(f"Click to open 3-month chart for {trade['ticker']}")
                self.table_open.setItem(row_idx, col_idx, item)

            # Actions Container Widget (Modify, Sell Partial, Exit)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)

            # 1. Modify Stop Loss & Target Button
            btn_modify = QPushButton("✏ Modify")
            btn_modify.setStyleSheet(
                "QPushButton { background-color: #2c313a; color: #61afef; "
                "font-size: 11px; padding: 3px 6px; border: 1px solid #3b4048; "
                "border-radius: 3px; font-weight: bold; } "
                "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
            )
            btn_modify.setToolTip("Modify Stop Loss and Target price levels")
            btn_modify.clicked.connect(
                lambda _checked=False, tid=trade_id: self.open_modify_dialog(tid)
            )
            actions_layout.addWidget(btn_modify)

            # 2. Sell Partial Quantity Button
            btn_partial = QPushButton("✂ Sell Partial")
            btn_partial.setStyleSheet(
                "QPushButton { background-color: #2c313a; color: #e5c07b; "
                "font-size: 11px; padding: 3px 6px; border: 1px solid #3b4048; "
                "border-radius: 3px; font-weight: bold; } "
                "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
            )
            btn_partial.setToolTip("Sell a partial quantity of this position")
            btn_partial.clicked.connect(
                lambda _checked=False, tid=trade_id: self.open_partial_sell_dialog(tid)
            )
            actions_layout.addWidget(btn_partial)

            # 3. Square Off Full Position Button
            btn_close = QPushButton("✕ Exit")
            btn_close.setStyleSheet(
                "QPushButton { background-color: #3b2020; color: #e06c75; "
                "font-size: 11px; padding: 3px 6px; border: 1px solid #5c2828; "
                "border-radius: 3px; font-weight: bold; } "
                "QPushButton:hover { background-color: #e06c75; color: #ffffff; }"
            )
            btn_close.setToolTip("Square off full position at current market price")
            btn_close.clicked.connect(
                lambda _checked=False, tid=trade_id: self.manual_square_off(tid)
            )
            actions_layout.addWidget(btn_close)

            self.table_open.setCellWidget(row_idx, 12, actions_widget)

        # 3. Populate Trade History Journal Table
        history_trades = self.engine.get_trade_history()
        self.table_history.setRowCount(len(history_trades))

        for row_idx, trade in enumerate(history_trades):
            pnl = float(trade["realized_pnl"])
            ret_pct = float(trade["return_pct"])
            pnl_color = QColor("#98c379") if pnl >= 0 else QColor("#e06c75")

            entry_d = trade.get("entry_date") or trade["timestamp"][:10]
            exit_d = trade.get("exit_date") or (trade.get("exit_timestamp") or "")[:10]
            items = [
                QTableWidgetItem(f"#{trade['trade_id']}"),
                QTableWidgetItem(entry_d),
                QTableWidgetItem(exit_d if exit_d else "—"),
                QTableWidgetItem(trade["ticker"]),
                QTableWidgetItem(trade["side"]),
                QTableWidgetItem(str(trade["quantity"])),
                QTableWidgetItem(f"₹{trade['entry_price']:,.2f}"),
                QTableWidgetItem(f"₹{trade['exit_price']:,.2f}"),
                QTableWidgetItem(f"{'+' if pnl >= 0 else ''}₹{pnl:,.2f}"),
                QTableWidgetItem(f"{'+' if ret_pct >= 0 else ''}{ret_pct:.2f}%"),
                QTableWidgetItem(trade.get("exit_reason") or "CLOSED"),
                QTableWidgetItem(
                    trade["exit_timestamp"][:16] if trade.get("exit_timestamp") else "—"
                ),
            ]

            for col_idx, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    if col_idx in [5, 6, 7, 8, 9]
                    else Qt.AlignmentFlag.AlignCenter
                )
                if col_idx in [8, 9]:
                    item.setForeground(pnl_color)
                if col_idx == 3:
                    # Highlight ticker with interactive accent styling
                    item.setForeground(QColor("#61afef"))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                    item.setToolTip(f"Click to open 3-month chart for {trade['ticker']}")
                self.table_history.setItem(row_idx, col_idx, item)

    def start_background_worker(self) -> None:
        """Instantiate and start the background price monitor thread."""
        if self.worker is None:
            self.worker = PaperTradingWorker(self.engine, interval_seconds=10)
            self.worker.prices_updated.connect(self._on_prices_updated)
            self.worker.trades_exited.connect(self._on_trades_exited)
            self.worker.status_updated.connect(self._on_worker_status)
            self.worker.error_occurred.connect(self._on_worker_error)
            self.worker.start()

    def manual_refresh(self) -> None:
        """Trigger immediate price refresh via background worker."""
        if self.worker:
            self.worker.trigger_now()
        else:
            self.refresh_all_views()

    def toggle_worker(self) -> None:
        """Pause or resume background price monitor thread."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None
            self.btn_toggle_worker.setText("▶ Resume Auto-Monitor")
            self.lbl_status.setText("Auto-Monitor Paused.")
        else:
            self.start_background_worker()
            self.btn_toggle_worker.setText("⏸ Pause Auto-Monitor")
            self.lbl_status.setText("Auto-Monitor Resumed.")

    def _on_prices_updated(self, price_map: dict[str, float]) -> None:
        """Handle signal from background thread when quotes are updated."""
        self.refresh_all_views()

    def _on_trades_exited(self, exited_trades: list[dict[str, Any]]) -> None:
        """Notify user when an automatic exit trigger executes."""
        self.refresh_all_views()
        for trade in exited_trades:
            reason = trade["exit_reason"]
            pnl = trade["realized_pnl"]
            pnl_str = f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"
            QMessageBox.information(
                self,
                f"Auto-Execution Triggered ({reason})",
                f"Position #{trade['trade_id']} ({trade['ticker']}) triggered automatic exit "
                f"via {reason} at ₹{trade['exit_price']:,.2f}!\n\n"
                f"Realized PnL: {pnl_str}\nUpdated Cash: ₹{trade['updated_cash']:,.2f}",
            )

    def _on_open_table_cell_clicked(self, row: int, column: int) -> None:
        """Open 3-month chart popup when Ticker cell is clicked in open positions table."""
        if column == 2:
            item = self.table_open.item(row, 2)
            if item:
                self.open_chart_popup(item.text())

    def _on_open_table_double_clicked(self, item: QTableWidgetItem) -> None:
        """Open 3-month chart popup when an open position row is double-clicked."""
        row = item.row()
        ticker_item = self.table_open.item(row, 2)
        if ticker_item:
            self.open_chart_popup(ticker_item.text())

    def _on_history_table_cell_clicked(self, row: int, column: int) -> None:
        """Open 3-month chart popup when Ticker cell is clicked in trade history table."""
        if column == 3:
            item = self.table_history.item(row, 3)
            if item:
                self.open_chart_popup(item.text())

    def _on_history_table_double_clicked(self, item: QTableWidgetItem) -> None:
        """Open 3-month chart popup when a trade history row is double-clicked."""
        row = item.row()
        ticker_item = self.table_history.item(row, 3)
        if ticker_item:
            self.open_chart_popup(ticker_item.text())

    def _on_view_chart_clicked(self) -> None:
        """Open 3-month chart popup for the currently selected ticker in order entry."""
        current_text = self.ticker_combo.currentText().strip()
        if current_text:
            self.open_chart_popup(current_text)

    def open_chart_popup(self, ticker: str) -> None:
        """Display interactive 3-month chart popup for the specified ticker symbol.

        Args:
            ticker (str): Stock ticker symbol.
        """
        if not ticker:
            return
        clean_ticker = ticker.split(" ")[0]
        if self._active_chart_dialog and self._active_chart_dialog.isVisible():
            self._active_chart_dialog.load_ticker(clean_ticker)
            self._active_chart_dialog.raise_()
            self._active_chart_dialog.activateWindow()
        else:
            self._active_chart_dialog = TickerChartPopupDialog(
                ticker=clean_ticker,
                repo=self.repo,
                parent=self,
                default_period_months=3,
            )
            self._active_chart_dialog.show()
            self._active_chart_dialog.raise_()
            self._active_chart_dialog.activateWindow()

    def _on_worker_status(self, msg: str) -> None:
        """Update status bar label with contextual badge coloring."""
        self.lbl_status.setText(msg)
        if "NSE CLOSED" in msg or "paused" in msg.lower():
            self.lbl_status.setStyleSheet("color: #e5c07b; font-weight: bold;")
        elif "active" in msg.lower() or "fetching" in msg.lower():
            self.lbl_status.setStyleSheet("color: #98c379; font-weight: bold;")
        else:
            self.lbl_status.setStyleSheet("color: #7f848e; font-style: italic;")

    def _on_worker_error(self, err_msg: str) -> None:
        """Log background worker error and display on status label."""
        self.lbl_status.setText(f"Worker Notice: {err_msg}")

    def closeEvent(self, event: Any) -> None:
        """Ensure background worker thread stops cleanly when widget is closed."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        super().closeEvent(event)
