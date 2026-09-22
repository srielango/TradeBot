"""Interactive Morning Scanner tab component for TradeBot desktop dashboard."""

from typing import Any

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data_sync_service import DataSyncService
from market_repository import MarketRepository
from morning_scanner import MorningScanner
from strategies import STRATEGY_REGISTRY
from ui.ticker_chart_popup import TickerChartPopupDialog


class ScannerWorker(QThread):
    """Background thread worker to execute Morning Scanner without freezing UI."""

    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        scanner: MorningScanner,
        lookback_months: int = 6,
        trigger_scope: str = "previous_day",
    ):
        """Initialize worker with scanner instance and parameters."""
        super().__init__()
        self.scanner = scanner
        self.lookback_months = lookback_months
        self.trigger_scope = trigger_scope

    def run(self) -> None:
        """Execute full market scanning in background thread."""
        try:
            results = self.scanner.scan(
                lookback_months=self.lookback_months,
                trigger_scope=self.trigger_scope,
            )
            self.finished_signal.emit(results)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
            self.error_signal.emit(str(err))


class MorningScannerTab(QWidget):
    """Morning Scanner dashboard tab identifying actionable buy and sell signals."""

    ticker_selected = pyqtSignal(str)

    def __init__(self, repo: MarketRepository):
        """Initialize morning scanner tab with repository and interactive controls.

        Args:
            repo (MarketRepository): Data repository instance for fetching prices.
        """
        super().__init__()
        self.repo = repo
        self.scanner = MorningScanner(self.repo)
        self.worker: ScannerWorker | None = None
        self.all_results: list[dict[str, Any]] = []
        self.filtered_results: list[dict[str, Any]] = []
        self._active_chart_dialog: TickerChartPopupDialog | None = None

        self.init_ui()
        self._connect_sync_service()
        # Automatically run initial scan
        self.run_scanner()

    def init_ui(self) -> None:
        """Construct control bar, KPI status cards, results table, and strategy inspector."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # =====================================================================
        # Section 1: Toolbar & Scan Controls
        # =====================================================================
        control_group = QGroupBox("Morning Scanner Controls & Parameters")
        control_layout = QGridLayout(control_group)
        control_layout.setSpacing(10)
        control_layout.setContentsMargins(12, 10, 12, 10)

        # Lookback Window Selector
        control_layout.addWidget(QLabel("<b>Analysis Lookback:</b>"), 0, 0)
        self.lookback_combo = QComboBox()
        self.lookback_combo.addItem("6 Months (Recommended for 200 MA)", 6)
        self.lookback_combo.addItem("3 Months (Fast Momentum)", 3)
        self.lookback_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.lookback_combo.setMinimumContentsLength(18)
        self.lookback_combo.setCurrentIndex(0)
        self.lookback_combo.currentIndexChanged.connect(self.run_scanner)
        control_layout.addWidget(self.lookback_combo, 0, 1)

        # Trigger Scope Selector
        control_layout.addWidget(QLabel("<b>Trigger Scope:</b>"), 0, 2)
        self.trigger_scope_combo = QComboBox()
        self.trigger_scope_combo.addItem("Previous Trading Day (Full Session)", "previous_day")
        self.trigger_scope_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.trigger_scope_combo.setMinimumContentsLength(18)
        self.trigger_scope_combo.setCurrentIndex(0)
        self.trigger_scope_combo.currentIndexChanged.connect(self.run_scanner)
        control_layout.addWidget(self.trigger_scope_combo, 0, 3)

        # Signal Status Filter
        control_layout.addWidget(QLabel("<b>Filter Signal:</b>"), 1, 0)
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Stocks (50)", "all")
        self.filter_combo.addItem("Sell Signals (Open Positions)", "sell_only")
        self.filter_combo.addItem("Buy Signals Only", "buy_only")
        self.filter_combo.addItem("Multi-Strategy Confluence (2+)", "confluence_only")
        self.filter_combo.addItem("Open Positions Only", "open_positions")
        self.filter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.filter_combo.setMinimumContentsLength(18)
        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.currentIndexChanged.connect(self.apply_table_filters)
        control_layout.addWidget(self.filter_combo, 1, 1)

        # Live Search by Ticker / Company & Action Buttons
        search_actions_layout = QHBoxLayout()
        search_actions_layout.setSpacing(8)
        search_actions_layout.addWidget(QLabel("<b>Search:</b>"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search ticker or company name...")
        self.search_input.textChanged.connect(self.apply_table_filters)
        search_actions_layout.addWidget(self.search_input)

        self.btn_run_scan = QPushButton("▶ Run Morning Scan")
        self.btn_run_scan.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self.btn_run_scan.clicked.connect(self.run_scanner)
        search_actions_layout.addWidget(self.btn_run_scan)

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #abb2bf; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #4b5263; } "
            "QPushButton:hover { background-color: #4b5263; color: white; }"
        )
        self.btn_export_csv.clicked.connect(self.export_csv)
        search_actions_layout.addWidget(self.btn_export_csv)

        self.btn_sync_data = QPushButton("⟳ Sync Data")
        self.btn_sync_data.setToolTip("Synchronize latest market bars and fundamentals")
        self.btn_sync_data.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #388e3c; } "
            "QPushButton:hover { background-color: #388e3c; } "
            "QPushButton:disabled { background-color: #3b4048; color: #7f8c8d; "
            "border: 1px solid #4b5263; }"
        )
        self.btn_sync_data.clicked.connect(self._on_sync_data_clicked)
        search_actions_layout.addWidget(self.btn_sync_data)

        control_layout.addLayout(search_actions_layout, 1, 2, 1, 2)

        main_layout.addWidget(control_group)

        # Progress Bar for background scanning
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate animation
        self.progress_bar.setStyleSheet(
            "QProgressBar { height: 6px; border-radius: 3px; background-color: #2c313a; } "
            "QProgressBar::chunk { background-color: #27ae60; border-radius: 3px; }"
        )
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # =====================================================================
        # Section 2: Summary KPI Cards
        # =====================================================================
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(12)

        self.kpi_total = self._create_kpi_card("Total Stocks", "50", "#abb2bf")
        self.kpi_sells = self._create_kpi_card("Sell Signals (Profit Hit)", "0", "#e06c75")
        self.kpi_buys = self._create_kpi_card("Buy Signals (Prev Close)", "0", "#2ecc71")
        self.kpi_confluence = self._create_kpi_card("Multi-Strategy Confluence", "0", "#f1c40f")
        self.kpi_session_date = self._create_kpi_card("Previous Close Date", "N/A", "#61afef")

        kpi_layout.addWidget(self.kpi_total["frame"])
        kpi_layout.addWidget(self.kpi_sells["frame"])
        kpi_layout.addWidget(self.kpi_buys["frame"])
        kpi_layout.addWidget(self.kpi_confluence["frame"])
        kpi_layout.addWidget(self.kpi_session_date["frame"])

        main_layout.addLayout(kpi_layout)

        # =====================================================================
        # Section 3: Morning Scanner Results Table
        # =====================================================================
        self.table = QTableWidget()
        headers = [
            "Ticker",
            "Company Name",
            "Signal Indicator",
            "Triggered Strategies (Previous Close)",
            "Previous Close (INR)",
            "Stop Loss (INR)",
            "Take Profit (INR)",
            "Target Action / Setup",
            "Close Date",
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #21252b; alternate-background-color: #282c34; "
            "color: #abb2bf; gridline-color: #3b4048; border: 1px solid #3b4048; "
            "border-radius: 4px; } "
            "QHeaderView::section { background-color: #1e1e1e; color: #d7dae0; "
            "font-weight: bold; border: 1px solid #3b4048; padding: 6px; } "
            "QTableWidget::item:selected { background-color: #2c313a; color: #ffffff; }"
        )

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        main_layout.addWidget(self.table)

        # =====================================================================
        # Section 4: Detailed Strategy Inspector Panel for Selected Stock
        # =====================================================================
        self.detail_group = QGroupBox(
            "Selected Stock Strategy Breakdown (Previous Close Evaluation)"
        )
        detail_layout = QGridLayout(self.detail_group)
        detail_layout.setSpacing(8)
        detail_layout.setContentsMargins(12, 8, 12, 8)

        self.strategy_labels: dict[str, QLabel] = {}
        for idx, strat_name in enumerate(STRATEGY_REGISTRY.keys()):
            row = idx // 2
            col = (idx % 2) * 2
            title_lbl = QLabel(f"<b>{strat_name}:</b>")
            title_lbl.setStyleSheet("color: #9da5b4;")
            title_lbl.setWordWrap(True)
            val_lbl = QLabel("Awaiting selection...")
            val_lbl.setStyleSheet("color: #abb2bf;")
            val_lbl.setWordWrap(True)
            detail_layout.addWidget(title_lbl, row, col)
            detail_layout.addWidget(val_lbl, row, col + 1)
            self.strategy_labels[strat_name] = val_lbl

        main_layout.addWidget(self.detail_group)

    def _create_kpi_card(self, title: str, initial_value: str, color_hex: str) -> dict:
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
        font.setPointSize(13)
        font.setBold(True)
        val_lbl.setFont(font)
        val_lbl.setStyleSheet(f"color: {color_hex};")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)

        return {"frame": frame, "value_label": val_lbl}

    def run_scanner(self) -> None:
        """Trigger background thread scan across all active equity stocks."""
        if self.worker and self.worker.isRunning():
            return

        lookback = self.lookback_combo.currentData() or 6
        trigger_scope = self.trigger_scope_combo.currentData() or "previous_day"
        self.btn_run_scan.setEnabled(False)
        self.btn_run_scan.setText("Scanning Database...")
        self.progress_bar.setVisible(True)

        self.worker = ScannerWorker(
            self.scanner,
            lookback_months=lookback,
            trigger_scope=trigger_scope,
        )
        self.worker.finished_signal.connect(self._on_scan_finished)
        self.worker.error_signal.connect(self._on_scan_error)
        self.worker.start()

    def _on_scan_finished(self, results: list[dict[str, Any]]) -> None:
        """Handle completion of background scanner worker."""
        self.all_results = results
        self.btn_run_scan.setEnabled(True)
        self.btn_run_scan.setText("▶ Run Morning Scan")
        self.progress_bar.setVisible(False)

        # Update KPI summary numbers
        total_stocks = len(results)
        sell_stocks = sum(1 for r in results if r["indicator"] == "SELL")
        buy_stocks = sum(1 for r in results if r["indicator"] in ("BUY", "STRONG BUY"))
        confluence_stocks = sum(1 for r in results if r["confluence_count"] >= 2)

        latest_date = results[0]["prev_close_date"] if results else "N/A"
        date_str = latest_date.split(" ")[0] if " " in latest_date else latest_date

        self.kpi_total["value_label"].setText(str(total_stocks))
        self.kpi_sells["value_label"].setText(str(sell_stocks))
        self.kpi_buys["value_label"].setText(str(buy_stocks))
        self.kpi_confluence["value_label"].setText(str(confluence_stocks))
        self.kpi_session_date["value_label"].setText(date_str)

        self.apply_table_filters()

    def _on_scan_error(self, err_msg: str) -> None:
        """Handle error thrown during scan execution."""
        self.btn_run_scan.setEnabled(True)
        self.btn_run_scan.setText("▶ Run Morning Scan")
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Scan Error", f"Failed to execute scan: {err_msg}")

    def apply_table_filters(self) -> None:
        """Filter and render results into the table based on search query and signal filter."""
        filter_mode = self.filter_combo.currentData()
        search_query = self.search_input.text().strip().lower()

        filtered = []
        for r in self.all_results:
            # Signal mode filter
            if filter_mode == "sell_only" and r["indicator"] != "SELL":
                continue
            if filter_mode == "buy_only" and r["indicator"] not in ("BUY", "STRONG BUY"):
                continue
            if filter_mode == "confluence_only" and r["confluence_count"] < 2:
                continue
            if filter_mode == "open_positions" and not r.get("has_open_position"):
                continue

            # Search text filter
            if search_query:
                t_match = search_query in r["ticker"].lower()
                n_match = search_query in r["name"].lower()
                s_match = search_query in r["strategies_str"].lower()
                ind_match = search_query in r["indicator_badge"].lower()
                act_match = search_query in r["target_action"].lower()
                if not (t_match or n_match or s_match or ind_match or act_match):
                    continue

            filtered.append(r)

        self.filtered_results = filtered
        self.render_table(filtered)

    def render_table(self, rows: list[dict[str, Any]]) -> None:
        """Populate the QTableWidget with formatted scan result rows."""
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))

        for row_idx, r in enumerate(rows):
            # Ticker
            item_ticker = QTableWidgetItem(r["ticker"])
            item_ticker.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = item_ticker.font()
            font.setBold(True)
            item_ticker.setFont(font)
            item_ticker.setForeground(QColor("#61afef"))
            item_ticker.setToolTip(f"Click to open 3-month chart for {r['ticker']}")
            self.table.setItem(row_idx, 0, item_ticker)

            # Company Name
            item_name = QTableWidgetItem(r["name"])
            self.table.setItem(row_idx, 1, item_name)

            # Indicator Badge (Color-coded)
            item_indicator = QTableWidgetItem(r["indicator_badge"])
            item_indicator.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ind_font = item_indicator.font()
            ind_font.setBold(True)
            item_indicator.setFont(ind_font)

            if r["indicator"] == "SELL":
                item_indicator.setForeground(QColor("#e06c75"))  # Vivid Red/Coral for Sell
            elif r["confluence_count"] >= 2:
                item_indicator.setForeground(QColor("#2ecc71"))  # Vivid Emerald
            elif r["confluence_count"] == 1:
                item_indicator.setForeground(QColor("#27ae60"))  # Green
            elif r["indicator"] == "HOLD":
                item_indicator.setForeground(QColor("#e5c07b"))  # Warm Gold for Hold
            else:
                item_indicator.setForeground(QColor("#7f8c8d"))  # Gray
            self.table.setItem(row_idx, 2, item_indicator)

            # Triggered Strategies (Previous Close)
            item_strats = QTableWidgetItem(r["strategies_str"])
            if r["confluence_count"] > 0:
                item_strats.setForeground(QColor("#61afef"))  # Light blue highlight
                s_font = item_strats.font()
                s_font.setBold(r["confluence_count"] >= 2)
                item_strats.setFont(s_font)
            self.table.setItem(row_idx, 3, item_strats)

            # Previous Close
            item_close = QTableWidgetItem(f"INR {r['prev_close_price']:,.2f}")
            item_close.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row_idx, 4, item_close)

            # Stop Loss
            sl_text = f"INR {r['stop_loss']:,.2f}" if r["stop_loss"] else "-"
            item_sl = QTableWidgetItem(sl_text)
            item_sl.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if r["stop_loss"]:
                item_sl.setForeground(QColor("#e06c75"))  # Soft red for stop loss
            self.table.setItem(row_idx, 5, item_sl)

            # Take Profit
            tp_text = f"INR {r['take_profit']:,.2f}" if r["take_profit"] else "-"
            item_tp = QTableWidgetItem(tp_text)
            item_tp.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if r["take_profit"]:
                item_tp.setForeground(QColor("#98c379"))  # Soft green for take profit
            self.table.setItem(row_idx, 6, item_tp)

            # Target Action / Setup
            item_action = QTableWidgetItem(r["target_action"])
            if r["indicator"] == "SELL":
                item_action.setForeground(QColor("#e06c75"))
                act_font = item_action.font()
                act_font.setBold(True)
                item_action.setFont(act_font)
            self.table.setItem(row_idx, 7, item_action)

            # Close Date
            item_date = QTableWidgetItem(r["prev_close_date"])
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 8, item_date)

        # Update strategy inspector for first row if available
        if rows:
            self._update_detail_inspector(rows[0])

    def _on_row_selected(self) -> None:
        """Update strategy inspector panel when a table row is clicked."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row_idx = selected_rows[0].row()
        if 0 <= row_idx < len(self.filtered_results):
            self._update_detail_inspector(self.filtered_results[row_idx])

    def _update_detail_inspector(self, stock_record: dict[str, Any]) -> None:
        """Update the detailed bottom panel with per-strategy breakdown and position status."""
        ticker = stock_record["ticker"]
        name = stock_record["name"]
        chosen = stock_record.get("chosen_strategy")
        has_pos = stock_record.get("has_open_position", False)

        header_parts = [
            (
                f"Strategy Breakdown for {ticker} ({name}) - Previous Close: INR "
                f"{stock_record['prev_close_price']:,.2f} on {stock_record['prev_close_date']}"
            )
        ]
        if has_pos:
            header_parts.append("[ACTIVE OPEN POSITION]")
        if chosen and stock_record["confluence_count"] >= 2:
            header_parts.append(f"[Chosen Least-Profit Setup: {chosen}]")

        self.detail_group.setTitle(" | ".join(header_parts))

        strat_details = stock_record.get("strategy_details", {})
        for strat_name, label in self.strategy_labels.items():
            info = strat_details.get(strat_name)
            if not info:
                label.setText("Not evaluated")
                label.setStyleSheet("color: #7f8c8d;")
                continue

            if info.get("is_buy"):
                sl = info.get("stop_loss")
                tp = info.get("take_profit")
                details = ["BUY SIGNAL TRIGGERED"]
                prev_price = stock_record.get("prev_close_price", 0.0)
                if sl and prev_price > 0:
                    sl_diff = prev_price - sl
                    sl_pct = (sl_diff / prev_price) * 100.0
                    details.append(f"SL: INR {sl:,.2f} (-{sl_pct:.2f}%)")
                elif sl:
                    details.append(f"SL: INR {sl:,.2f}")

                if tp and prev_price > 0:
                    tp_diff = tp - prev_price
                    tp_pct = (tp_diff / prev_price) * 100.0
                    details.append(f"Target: INR {tp:,.2f} (+{tp_pct:.2f}%)")
                elif tp:
                    details.append(f"Target: INR {tp:,.2f}")

                is_chosen = (strat_name == chosen and stock_record["confluence_count"] >= 2)
                if is_chosen:
                    details.append("(SELECTED: LEAST PROFIT)")
                    label.setText(f"[YES - ACTIVE] {' | '.join(details)}")
                    label.setStyleSheet("color: #61afef; font-weight: bold;")
                else:
                    label.setText(f"[YES] {' | '.join(details)}")
                    label.setStyleSheet("color: #2ecc71; font-weight: bold;")
            else:
                label.setText("[NO] No Buy Signal")
                label.setStyleSheet("color: #7f8c8d;")

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Handle cell click in the scan results table.

        - Clicking on Column 0 (Ticker): Shows bottom signal details AND opens 3-month chart popup.
        - Clicking on any other column (col > 0): Shows bottom buy signal trigger details without
          opening popup.
        """
        if 0 <= row < len(self.filtered_results):
            record = self.filtered_results[row]
            self.table.selectRow(row)
            self._update_detail_inspector(record)

            if col == 0:
                self.open_chart_popup(record["ticker"])

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        """Open 3-month chart popup and update strategy details when a row is double-clicked."""
        row_idx = item.row()
        if 0 <= row_idx < len(self.filtered_results):
            record = self.filtered_results[row_idx]
            self.table.selectRow(row_idx)
            self._update_detail_inspector(record)
            self.open_chart_popup(record["ticker"])

    def open_chart_popup(self, ticker: str) -> None:
        """Display interactive 3-month chart popup for the specified ticker.

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
                clean_ticker,
                repo=self.repo,
                parent=self,
                default_period_months=3,
            )
            self._active_chart_dialog.show()
            self._active_chart_dialog.raise_()
            self._active_chart_dialog.activateWindow()

    def export_csv(self) -> None:
        """Export current filtered morning scanner results to a CSV spreadsheet."""
        if not self.filtered_results:
            QMessageBox.information(
                self, "Export CSV", "No scan results available to export."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Morning Scanner Results",
            "morning_scanner_results.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        df_export = self.scanner.to_dataframe(self.filtered_results)
        try:
            df_export.to_csv(file_path, index=False)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {len(df_export)} scan records to:\n{file_path}",
            )
        except OSError as err:
            QMessageBox.critical(self, "Export Error", f"Failed to save CSV: {err}")

    # ── Market Data Synchronization Handlers ─────────────────────────────────

    def _connect_sync_service(self) -> None:
        """Subscribe to DataSyncService events to update button status."""
        sync_service = DataSyncService.get_instance()
        sync_service.sync_started.connect(self._on_sync_started)
        sync_service.progress_updated.connect(self._on_sync_progress)
        sync_service.sync_finished.connect(self._on_sync_finished)
        sync_service.sync_error.connect(self._on_sync_error)
        sync_service.sync_cancelled.connect(self._on_sync_cancelled)

    def _on_sync_data_clicked(self) -> None:
        """Trigger background market data synchronization."""
        DataSyncService.get_instance().start_sync()

    def _on_sync_started(self) -> None:
        """Update button when data synchronization begins."""
        self.btn_sync_data.setEnabled(False)
        self.btn_sync_data.setText("Syncing...")

    def _on_sync_progress(self, current: int, total: int, _msg: str) -> None:
        """Update button with synchronization progress percentage.

        Args:
            current (int): Current step index.
            total (int): Total sync steps.
            _msg (str): Informational step message (unused here).
        """
        pct = max(0, min(100, int((current / max(1, total)) * 100)))
        self.btn_sync_data.setText(f"Syncing {pct}%")

    def _on_sync_finished(self, _bars: int, _funds: int, _summary: str) -> None:
        """Restore button state upon synchronization completion."""
        self.btn_sync_data.setEnabled(True)
        self.btn_sync_data.setText("⟳ Sync Data")

    def _on_sync_error(self, _err: str) -> None:
        """Restore button state on synchronization error."""
        self.btn_sync_data.setEnabled(True)
        self.btn_sync_data.setText("⟳ Sync Data")

    def _on_sync_cancelled(self) -> None:
        """Restore button state if synchronization was cancelled."""
        self.btn_sync_data.setEnabled(True)
        self.btn_sync_data.setText("⟳ Sync Data")
