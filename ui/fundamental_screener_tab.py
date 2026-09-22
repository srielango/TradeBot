"""Interactive Fundamental Screener tab component for TradeBot dashboard."""

import sqlite3
from typing import Any

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fundamental_screener import FundamentalScreener
from market_repository import MarketRepository
from ui.ticker_chart_popup import TickerChartPopupDialog


class FundamentalSyncWorker(QThread):
    """Background worker thread for fetching online fundamentals from Yahoo Finance."""

    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(int, int)

    def __init__(self, tickers: list[str], screener: FundamentalScreener):
        """Initialize worker with list of ticker symbols and screener instance."""
        super().__init__()
        self.tickers = tickers
        self.screener = screener
        self._is_cancelled = False

    def run(self) -> None:
        """Execute sequential background download and evaluation."""
        total = len(self.tickers)
        success_count = 0
        for idx, ticker in enumerate(self.tickers, start=1):
            if self._is_cancelled:
                break
            try:
                self.screener.analyze_ticker(ticker, force_refresh=True)
                success_count += 1
            except Exception as err:
                print(f"Background sync error for {ticker}: {err}")
            self.progress_signal.emit(idx, total, ticker)

        self.finished_signal.emit(success_count, total)

    def cancel(self) -> None:
        """Flag the worker thread to stop execution."""
        self._is_cancelled = True


class FundamentalScreenerTab(QWidget):
    """Interactive tab allowing dynamic filtering of universe equities by fundamental criteria."""

    ticker_selected = pyqtSignal(str)

    def __init__(self, repo: MarketRepository):
        """Initialize fundamental screener tab with repository and interactive controls.

        Args:
            repo (MarketRepository): Data repository instance.
        """
        super().__init__()
        self.repo = repo
        self.screener = FundamentalScreener(self.repo.db_path)
        self.all_securities: list[dict[str, Any]] = []
        self.current_rows_data: list[dict[str, Any]] = []
        self.worker: FundamentalSyncWorker | None = None
        self._active_chart_dialog: TickerChartPopupDialog | None = None

        self.init_ui()
        self.load_securities_data()
        self.apply_filters()

    def init_ui(self) -> None:
        """Construct filter controls, action toolbar, status cards, and stock results table."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # =====================================================================
        # Section 1: Dynamic Filter Controls Panel
        # =====================================================================
        filter_group = QGroupBox("Customizable Fundamental Criteria")
        filter_layout = QGridLayout(filter_group)
        filter_layout.setSpacing(10)
        filter_layout.setContentsMargins(12, 12, 12, 12)

        # 1. Market Cap
        self.cb_mcap = QCheckBox("Market Cap (Cr) >=")
        self.cb_mcap.setChecked(True)
        self.sb_mcap = QDoubleSpinBox()
        self.sb_mcap.setRange(0, 5_000_000)
        self.sb_mcap.setSingleStep(500)
        self.sb_mcap.setValue(5000.0)
        self.sb_mcap.setPrefix("₹ ")
        self.sb_mcap.setSuffix(" Cr")
        self.cb_mcap.toggled.connect(self.sb_mcap.setEnabled)
        self.cb_mcap.toggled.connect(self.apply_filters)
        self.sb_mcap.valueChanged.connect(self.apply_filters)

        # 2. Debt to Equity
        self.cb_de = QCheckBox("Debt to Equity <=")
        self.cb_de.setChecked(True)
        self.sb_de = QDoubleSpinBox()
        self.sb_de.setRange(0.0, 20.0)
        self.sb_de.setSingleStep(0.05)
        self.sb_de.setDecimals(2)
        self.sb_de.setValue(0.50)
        self.cb_de.toggled.connect(self.sb_de.setEnabled)
        self.cb_de.toggled.connect(self.apply_filters)
        self.sb_de.valueChanged.connect(self.apply_filters)

        # 3. PEG Ratio
        self.cb_peg = QCheckBox("PEG Ratio >=")
        self.cb_peg.setChecked(True)
        self.sb_peg = QDoubleSpinBox()
        self.sb_peg.setRange(0.0, 50.0)
        self.sb_peg.setSingleStep(0.25)
        self.sb_peg.setDecimals(2)
        self.sb_peg.setValue(2.00)
        self.cb_peg.toggled.connect(self.sb_peg.setEnabled)
        self.cb_peg.toggled.connect(self.apply_filters)
        self.sb_peg.valueChanged.connect(self.apply_filters)

        # 4. Beta vs Nifty 50 (^NSEI)
        self.cb_beta = QCheckBox("Beta vs Nifty 50 >=")
        self.cb_beta.setChecked(True)
        self.sb_beta = QDoubleSpinBox()
        self.sb_beta.setRange(0.0, 10.0)
        self.sb_beta.setSingleStep(0.10)
        self.sb_beta.setDecimals(2)
        self.sb_beta.setValue(1.20)
        self.cb_beta.toggled.connect(self.sb_beta.setEnabled)
        self.cb_beta.toggled.connect(self.apply_filters)
        self.sb_beta.valueChanged.connect(self.apply_filters)

        # 5. Average Volume (252 days)
        self.cb_vol = QCheckBox("252d Avg Volume >=")
        self.cb_vol.setChecked(True)
        self.sb_vol = QSpinBox()
        self.sb_vol.setRange(0, 100_000_000)
        self.sb_vol.setSingleStep(250_000)
        self.sb_vol.setValue(3_000_000)
        self.cb_vol.toggled.connect(self.sb_vol.setEnabled)
        self.cb_vol.toggled.connect(self.apply_filters)
        self.sb_vol.valueChanged.connect(self.apply_filters)

        # 6. Institutional Ownership %
        self.cb_inst = QCheckBox("Inst. Ownership % >=")
        self.cb_inst.setChecked(True)
        self.sb_inst = QDoubleSpinBox()
        self.sb_inst.setRange(0.0, 100.0)
        self.sb_inst.setSingleStep(1.0)
        self.sb_inst.setDecimals(1)
        self.sb_inst.setValue(15.0)
        self.sb_inst.setSuffix(" %")
        self.cb_inst.toggled.connect(self.sb_inst.setEnabled)
        self.cb_inst.toggled.connect(self.apply_filters)
        self.sb_inst.valueChanged.connect(self.apply_filters)

        # 7. ROE % (Optional / unchecked by default)
        self.cb_roe = QCheckBox("ROE % >=")
        self.cb_roe.setChecked(False)
        self.sb_roe = QDoubleSpinBox()
        self.sb_roe.setRange(0.0, 100.0)
        self.sb_roe.setSingleStep(1.0)
        self.sb_roe.setDecimals(1)
        self.sb_roe.setValue(20.0)
        self.sb_roe.setSuffix(" %")
        self.sb_roe.setEnabled(False)
        self.cb_roe.toggled.connect(self.sb_roe.setEnabled)
        self.cb_roe.toggled.connect(self.apply_filters)
        self.sb_roe.valueChanged.connect(self.apply_filters)

        # Grid Placement (3 criteria per row for clean responsiveness on all displays)
        filter_layout.addWidget(self.cb_mcap, 0, 0)
        filter_layout.addWidget(self.sb_mcap, 0, 1)

        filter_layout.addWidget(self.cb_de, 0, 2)
        filter_layout.addWidget(self.sb_de, 0, 3)

        filter_layout.addWidget(self.cb_peg, 0, 4)
        filter_layout.addWidget(self.sb_peg, 0, 5)

        filter_layout.addWidget(self.cb_beta, 1, 0)
        filter_layout.addWidget(self.sb_beta, 1, 1)

        filter_layout.addWidget(self.cb_vol, 1, 2)
        filter_layout.addWidget(self.sb_vol, 1, 3)

        filter_layout.addWidget(self.cb_inst, 1, 4)
        filter_layout.addWidget(self.sb_inst, 1, 5)

        filter_layout.addWidget(self.cb_roe, 2, 0)
        filter_layout.addWidget(self.sb_roe, 2, 1)

        # Reset & Select All Actions
        btn_reset = QPushButton("Reset Criteria")
        btn_reset.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #abb2bf; padding: 4px 10px; "
            "border-radius: 4px; } QPushButton:hover { background-color: #4b5263; color: white; }"
        )
        btn_reset.clicked.connect(self.reset_filters)
        filter_layout.addWidget(btn_reset, 2, 2, 1, 2)

        main_layout.addWidget(filter_group)

        # =====================================================================
        # Section 2: Toolbar & Search Bar
        # =====================================================================
        toolbar_layout = QHBoxLayout()

        # Quick Search
        toolbar_layout.addWidget(QLabel("<b>Filter by Symbol/Name:</b>"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search e.g. INFY, Tata, HDFC...")
        self.search_input.textChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(self.search_input)

        # Quick View Option
        self.cb_show_passing_only = QCheckBox("Show Passing Stocks Only")
        self.cb_show_passing_only.setChecked(False)
        self.cb_show_passing_only.toggled.connect(self.apply_filters)
        toolbar_layout.addWidget(self.cb_show_passing_only)

        # Sync Fundamentals Button
        self.btn_sync = QPushButton("Sync Online Fundamentals")
        self.btn_sync.setStyleSheet(
            "QPushButton { background-color: #1976d2; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #1e88e5; }"
        )
        self.btn_sync.clicked.connect(self.start_online_sync)
        toolbar_layout.addWidget(self.btn_sync)

        # Export CSV Button
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #abb2bf; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #4b5263; } "
            "QPushButton:hover { background-color: #4b5263; color: white; }"
        )
        self.btn_export_csv.clicked.connect(self.export_to_csv)
        toolbar_layout.addWidget(self.btn_export_csv)

        # Export Excel Button
        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_excel.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #388e3c; } "
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.btn_export_excel.clicked.connect(self.export_to_excel)
        toolbar_layout.addWidget(self.btn_export_excel)

        main_layout.addLayout(toolbar_layout)

        # Progress Bar for background download
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #3b4048; border-radius: 4px; text-align: center; } "
            "QProgressBar::chunk { background-color: #2e7d32; }"
        )
        main_layout.addWidget(self.progress_bar)

        # Summary Header Label
        self.summary_label = QLabel("Loading fundamental metrics...")
        self.summary_label.setStyleSheet(
            "QLabel { background-color: #1e2227; color: #abb2bf; border: 1px solid #3b4048; "
            "border-radius: 4px; padding: 6px 10px; font-size: 11px; font-weight: bold; }"
        )
        main_layout.addWidget(self.summary_label)

        # =====================================================================
        # Section 3: Stock Results Table
        # =====================================================================
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Ticker",
            "Company Name",
            "Market Cap (Cr)",
            "Debt / Equity",
            "PEG Ratio",
            "Beta (^NSEI)",
            "252d Avg Volume",
            "Inst Own %",
            "ROE %",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.on_table_double_click)
        self.table.cellClicked.connect(self._on_table_cell_clicked)

        main_layout.addWidget(self.table)

    def load_securities_data(self) -> None:
        """Fetch all stock securities and cached fundamental metrics from database."""
        query = """
            SELECT s.ticker, s.name, f.market_cap_cr, f.debt_to_equity,
                   f.peg_ratio, f.beta_nsei, f.beta_yf, f.avg_volume_252,
                   f.roe, f.institutional_ownership, f.is_passing, f.updated_at
            FROM securities s
            LEFT JOIN security_fundamentals f ON s.id = f.security_id
            WHERE s.asset_type = 'STOCK'
            ORDER BY s.ticker ASC
        """
        try:
            with sqlite3.connect(self.repo.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()

            self.all_securities = []
            for r in rows:
                self.all_securities.append({
                    "ticker": r[0],
                    "name": r[1],
                    "market_cap_cr": r[2],
                    "debt_to_equity": r[3],
                    "peg_ratio": r[4],
                    "beta_nsei": r[5],
                    "beta_yf": r[6],
                    "avg_volume_252": r[7],
                    "roe": r[8],
                    "institutional_ownership": r[9],
                    "is_passing": bool(r[10]),
                    "updated_at": r[11],
                })
        except sqlite3.Error as err:
            print(f"Error loading securities for fundamental screener: {err}")
            self.all_securities = []

    def apply_filters(self) -> None:
        """Evaluate securities against current active UI filter criteria and refresh table."""
        search_query = self.search_input.text().strip().lower()
        show_passing_only = self.cb_show_passing_only.isChecked()

        mcap_enabled = self.cb_mcap.isChecked()
        min_mcap = self.sb_mcap.value() if mcap_enabled else None

        de_enabled = self.cb_de.isChecked()
        max_de = self.sb_de.value() if de_enabled else None

        peg_enabled = self.cb_peg.isChecked()
        min_peg = self.sb_peg.value() if peg_enabled else None

        beta_enabled = self.cb_beta.isChecked()
        min_beta = self.sb_beta.value() if beta_enabled else None

        vol_enabled = self.cb_vol.isChecked()
        min_vol = self.sb_vol.value() if vol_enabled else None

        inst_enabled = self.cb_inst.isChecked()
        min_inst = (self.sb_inst.value() / 100.0) if inst_enabled else None

        roe_enabled = self.cb_roe.isChecked()
        min_roe = (self.sb_roe.value() / 100.0) if roe_enabled else None

        matching_rows = []
        passing_count = 0

        for s in self.all_securities:
            # Text search filter
            if search_query:
                ticker_match = search_query in s["ticker"].lower()
                name_match = search_query in s["name"].lower()
                if not ticker_match and not name_match:
                    continue

            # Individual criteria evaluation
            mcap_val = s["market_cap_cr"]
            de_val = s["debt_to_equity"]
            peg_val = s["peg_ratio"]
            beta_val = s["beta_nsei"] if s["beta_nsei"] is not None else s["beta_yf"]
            vol_val = s["avg_volume_252"]
            inst_val = s["institutional_ownership"]
            roe_val = s["roe"]

            pass_mcap = (mcap_val is not None and mcap_val >= min_mcap) if mcap_enabled else True
            pass_de = (de_val is not None and de_val <= max_de) if de_enabled else True
            pass_peg = (peg_val is not None and peg_val >= min_peg) if peg_enabled else True
            pass_beta = (beta_val is not None and beta_val >= min_beta) if beta_enabled else True
            pass_vol = (vol_val is not None and vol_val >= min_vol) if vol_enabled else True
            pass_inst = (inst_val is not None and inst_val >= min_inst) if inst_enabled else True
            pass_roe = (roe_val is not None and roe_val >= min_roe) if roe_enabled else True

            is_overall_pass = all([
                pass_mcap, pass_de, pass_peg, pass_beta,
                pass_vol, pass_inst, pass_roe,
            ])

            if is_overall_pass:
                passing_count += 1

            if show_passing_only and not is_overall_pass:
                continue

            matching_rows.append({
                "sec": s,
                "is_pass": is_overall_pass,
                "checks": {
                    "mcap": pass_mcap,
                    "de": pass_de,
                    "peg": pass_peg,
                    "beta": pass_beta,
                    "vol": pass_vol,
                    "inst": pass_inst,
                    "roe": pass_roe,
                },
            })        # Update Summary Label
        total_total = len(self.all_securities)
        matched_count = len(matching_rows)
        self.current_rows_data = matching_rows
        self.summary_label.setText(
            f"Showing {matched_count} stocks | Passing Criteria: {passing_count} / {total_total} "
            f"({(passing_count / total_total * 100) if total_total else 0.0:.1f}%) | "
            f"Double-click any row to open in Strategy Backtester."
        )

        # Render Table Rows
        self.populate_table(matching_rows)

    def populate_table(self, rows_data: list[dict[str, Any]]) -> None:
        """Populate the table with filtered stock records and styled cells.

        Args:
            rows_data (list[dict]): Processed rows with security data and pass/fail checks.
        """
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows_data))

        for row_idx, item in enumerate(rows_data):
            s = item["sec"]
            checks = item["checks"]

            mcap_str = f"₹ {s['market_cap_cr']:,.0f}" if s['market_cap_cr'] else "N/A"
            de_str = f"{s['debt_to_equity']:.2f}" if s['debt_to_equity'] is not None else "N/A"
            peg_str = f"{s['peg_ratio']:.2f}" if s['peg_ratio'] is not None else "N/A"
            beta_str = f"{s['beta_nsei']:.2f}" if s['beta_nsei'] is not None else "N/A"
            vol_str = f"{int(s['avg_volume_252']):,}" if s['avg_volume_252'] else "N/A"
            inst_str = (
                f"{s['institutional_ownership'] * 100:.1f}%"
                if s['institutional_ownership'] is not None
                else "N/A"
            )
            roe_str = f"{s['roe'] * 100:.1f}%" if s['roe'] is not None else "N/A"

            items = [
                QTableWidgetItem(s["ticker"]),
                QTableWidgetItem(s["name"]),
                QTableWidgetItem(mcap_str),
                QTableWidgetItem(de_str),
                QTableWidgetItem(peg_str),
                QTableWidgetItem(beta_str),
                QTableWidgetItem(vol_str),
                QTableWidgetItem(inst_str),
                QTableWidgetItem(roe_str),
            ]

            # Style alignment and colors
            for col_idx, widget_item in enumerate(items):
                if col_idx in (0, 1):
                    widget_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    widget_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col_idx == 0:
                    widget_item.setForeground(QColor("#61afef"))
                    f = widget_item.font()
                    f.setBold(True)
                    widget_item.setFont(f)
                    widget_item.setToolTip(f"Click to open 3-month chart for {s['ticker']}")
                elif col_idx == 2:  # Market Cap
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["mcap"] else QColor(244, 67, 54)
                    )
                elif col_idx == 3:  # D/E
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["de"] else QColor(244, 67, 54)
                    )
                elif col_idx == 4:  # PEG
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["peg"] else QColor(244, 67, 54)
                    )
                elif col_idx == 5:  # Beta
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["beta"] else QColor(244, 67, 54)
                    )
                elif col_idx == 6:  # Avg Vol
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["vol"] else QColor(244, 67, 54)
                    )
                elif col_idx == 7:  # Inst Own
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["inst"] else QColor(244, 67, 54)
                    )
                elif col_idx == 8 and s["roe"] is not None:  # ROE
                    widget_item.setForeground(
                        QColor(76, 175, 80) if checks["roe"] else QColor(244, 67, 54)
                    )

                self.table.setItem(row_idx, col_idx, widget_item)

    def reset_filters(self) -> None:
        """Reset all criteria check-boxes and spin-boxes to strategy default values."""
        self.cb_mcap.setChecked(True)
        self.sb_mcap.setValue(5000.0)

        self.cb_de.setChecked(True)
        self.sb_de.setValue(0.50)

        self.cb_peg.setChecked(True)
        self.sb_peg.setValue(2.00)

        self.cb_beta.setChecked(True)
        self.sb_beta.setValue(1.20)

        self.cb_vol.setChecked(True)
        self.sb_vol.setValue(3_000_000)

        self.cb_inst.setChecked(True)
        self.sb_inst.setValue(15.0)

        self.cb_roe.setChecked(False)
        self.sb_roe.setValue(20.0)

        self.cb_show_passing_only.setChecked(False)
        self.search_input.clear()
        self.apply_filters()

    def start_online_sync(self) -> None:
        """Launch background worker to sync fundamentals for all tracked stocks."""
        if not self.all_securities:
            QMessageBox.warning(
                self, "No Securities", "No securities discovered in local database."
            )
            return

        tickers = [s["ticker"] for s in self.all_securities]
        self.btn_sync.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(tickers))
        self.progress_bar.setValue(0)

        self.sync_worker = FundamentalSyncWorker(tickers, self.screener)
        self.sync_worker.progress_signal.connect(self.on_sync_progress)
        self.sync_worker.finished_signal.connect(self.on_sync_finished)
        self.sync_worker.start()

    def on_sync_progress(self, current: int, total: int, ticker: str) -> None:
        """Update progress bar label during background sync."""
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Syncing [{current}/{total}] {ticker}...")

    def on_sync_finished(self, success: int, total: int) -> None:
        """Handle background sync completion and refresh UI view."""
        self.btn_sync.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(
            self,
            "Sync Complete",
            f"Successfully updated fundamentals for {success} of {total} securities.",
        )
        self.load_securities_data()
        self.apply_filters()

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        """Handle single click on table cells, opening 3-month chart popup if Ticker is clicked."""
        if col == 0:
            item = self.table.item(row, 0)
            if item:
                self.open_chart_popup(item.text())

    def on_table_double_click(self) -> None:
        """Open 3-month chart popup when a table row is double-clicked."""
        current_row = self.table.currentRow()
        if current_row >= 0:
            ticker_item = self.table.item(current_row, 0)
            if ticker_item:
                self.open_chart_popup(ticker_item.text())

    def open_chart_popup(self, ticker_str: str) -> None:
        """Open the interactive 3-month chart popup for the specified ticker.

        Args:
            ticker_str (str): Stock ticker symbol.
        """
        if not ticker_str:
            return
        clean_ticker = ticker_str.split(" ")[0]
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

    def _get_export_dataframe(self) -> pd.DataFrame:
        """Convert current filtered screener rows into a formatted DataFrame for export."""
        records = []
        for item in self.current_rows_data:
            s = item["sec"]
            records.append({
                "Ticker": s["ticker"],
                "Company Name": s["name"],
                "Market Cap (Cr INR)": s["market_cap_cr"],
                "Debt to Equity": s["debt_to_equity"],
                "PEG Ratio": s["peg_ratio"],
                "Beta (^NSEI)": s["beta_nsei"],
                "252d Avg Volume": s["avg_volume_252"],
                "Institutional Ownership (%)": (
                    s["institutional_ownership"] * 100
                    if s["institutional_ownership"] is not None
                    else None
                ),
                "ROE (%)": s["roe"] * 100 if s["roe"] is not None else None,
            })
        return pd.DataFrame(records)

    def export_to_csv(self) -> None:
        """Export current filtered fundamental screener rows to a CSV file."""
        if not self.current_rows_data:
            QMessageBox.information(
                self,
                "No Data to Export",
                "There are no stock records to export.",
            )
            return

        df_export = self._get_export_dataframe()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Fundamental Screener as CSV",
            "fundamental_screener_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )

        if not file_path:
            return

        try:
            df_export.to_csv(file_path, index=False)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {len(df_export)} stocks to:\n{file_path}",
            )
        except Exception as err:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export CSV file:\n{err}",
            )

    def export_to_excel(self) -> None:
        """Export current filtered fundamental screener rows to an Excel workbook."""
        if not self.current_rows_data:
            QMessageBox.information(
                self,
                "No Data to Export",
                "There are no stock records to export.",
            )
            return

        df_export = self._get_export_dataframe()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Fundamental Screener as Excel",
            "fundamental_screener_results.xlsx",
            "Excel Files (*.xlsx);;All Files (*)",
        )

        if not file_path:
            return

        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df_export.to_excel(writer, sheet_name="Fundamental Screen", index=False)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {len(df_export)} stocks to:\n{file_path}",
            )
        except Exception as err:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export Excel file:\n{err}",
            )
