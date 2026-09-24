"""Trading application graphical interface module for TradeBot."""

import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adx_indicator import calculate_adx
from bollinger_bands import calculate_bollinger_bands
from config import DB_PATH, TARGET_INDICES
from data_sync_service import DataSyncService
from market_repository import MarketRepository
from rsi_indicator import calculate_rsi
from stoch_rsi_indicator import calculate_stoch_rsi
from ui.backtest_tab import BacktestTab
from ui.data_sync_widget import DataSyncWidget
from ui.fundamental_screener_tab import FundamentalScreenerTab
from ui.market_sentiment_tab import MarketSentimentTab
from ui.morning_scanner_tab import MorningScannerTab
from ui.nifty_header_widget import NiftyHeaderWidget
from ui.paper_trading_tab import PaperTradingTab
from ui.ticker_chart_popup import show_ticker_chart_popup


class TradingApp(QMainWindow):
    """Main graphical interface for the Tradebot Management Studio desktop application."""

    def __init__(self):
        """Initialize the main window, data repository, and user interface components."""
        super().__init__()
        self.setWindowTitle('Tradebot Management Studio')

        # Adaptively size window to fit comfortable proportions of available screen work area
        screen = QApplication.primaryScreen()
        if screen:
            avail_geo = screen.availableGeometry()
            target_w = min(1380, max(950, int(avail_geo.width() * 0.88)))
            target_h = min(880, max(600, int(avail_geo.height() * 0.88)))
            self.resize(target_w, target_h)
        else:
            self.resize(1150, 720)

        self.repo = MarketRepository(DB_PATH)

        # Store full ticker list so the search filter can operate on it
        self._all_tickers: list[str] = []

        self.init_ui()
        self.check_database_health()
        self._setup_sync_listener()

    def init_ui(self):
        """Construct layout, sidebar controls, charts, and data tabs."""
        # Root layout with persistent Nifty live data header visible across all tabs
        root_widget = QWidget()
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Persistent Nifty Live Benchmark Header
        self.header_widget = NiftyHeaderWidget(self)
        self.header_widget.ticker_clicked.connect(self._on_header_ticker_clicked)
        root_layout.addWidget(self.header_widget)

        # Tab Navigation Layout
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)
        self.setCentralWidget(root_widget)

        # Interactive Chart Tab (Analysis Terminal)
        self.chart_tab = QWidget()
        chart_tab_layout = QHBoxLayout(self.chart_tab)

        # Sidebar container & layout inside Analysis Terminal
        sidebar = QVBoxLayout()
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(240)
        sidebar_container.setLayout(sidebar)
        chart_tab_layout.addWidget(sidebar_container)

        # ── Data Synchronization Panel ───────────────────────────────────────
        self.sync_widget = DataSyncWidget()
        sidebar.addWidget(self.sync_widget)

        # ── Asset Watchlist ──────────────────────────────────────────────────

        sidebar.addWidget(QLabel('<b>Asset List</b>'))

        # Live search/filter input
        self.ticker_search = QLineEdit()
        self.ticker_search.setPlaceholderText('Search stock or index…')
        self.ticker_search.textChanged.connect(self._filter_ticker_list)
        sidebar.addWidget(self.ticker_search)

        self.ticker_list = QListWidget()
        self._all_tickers = self.repo.get_tickers()
        # Block signals during population so addItems does not prematurely
        # trigger refresh_chart before all sidebar widgets are constructed.
        self.ticker_list.blockSignals(True)
        self.ticker_list.addItems(self._all_tickers)
        self.ticker_list.blockSignals(False)
        self.ticker_list.currentTextChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.ticker_list)

        # ── Chart Period Selector ────────────────────────────────────────────

        sidebar.addWidget(QLabel('<b>Chart Period</b>'))
        self.period_selector = QComboBox()
        self.period_selector.addItem('1 Month', 1)
        self.period_selector.addItem('3 Months', 3)
        self.period_selector.addItem('6 Months', 6)
        self.period_selector.addItem('1 Year', 12)
        self.period_selector.addItem('2 Years', 24)
        self.period_selector.addItem('5 Years', 60)
        self.period_selector.addItem('All', None)
        self.period_selector.setCurrentIndex(3)
        self.period_selector.currentIndexChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.period_selector)

        # ── Active Indicators (checkboxes) ───────────────────────────────────

        sidebar.addWidget(QLabel('<b>Active Indicators</b>'))

        # Stochastic Oscillator checkbox
        self.stoch_check = QCheckBox('Stochastic Oscillator')
        self.stoch_check.stateChanged.connect(self._on_stoch_toggled)
        sidebar.addWidget(self.stoch_check)

        # Stochastic parameter widget (hidden by default)
        self.stochastic_widget = QWidget()
        stochastic_layout = QVBoxLayout(self.stochastic_widget)
        stochastic_layout.setContentsMargins(12, 0, 0, 0)

        self.k_period = QSpinBox()
        self.k_period.setRange(2, 50)
        self.k_period.setValue(8)
        stochastic_layout.addWidget(QLabel('K Period'))
        stochastic_layout.addWidget(self.k_period)

        self.k_smooth = QSpinBox()
        self.k_smooth.setRange(1, 10)
        self.k_smooth.setValue(3)
        stochastic_layout.addWidget(QLabel('K Smoothing'))
        stochastic_layout.addWidget(self.k_smooth)

        self.d_smooth = QSpinBox()
        self.d_smooth.setRange(1, 10)
        self.d_smooth.setValue(3)
        stochastic_layout.addWidget(QLabel('D Smoothing'))
        stochastic_layout.addWidget(self.d_smooth)

        self.k_period.valueChanged.connect(self.refresh_chart)
        self.k_smooth.valueChanged.connect(self.refresh_chart)
        self.d_smooth.valueChanged.connect(self.refresh_chart)

        self.stochastic_widget.setVisible(False)
        sidebar.addWidget(self.stochastic_widget)

        # Moving Average checkbox
        self.ma_check = QCheckBox('Moving Average')
        self.ma_check.stateChanged.connect(self._on_ma_toggled)
        sidebar.addWidget(self.ma_check)

        # Moving Average parameter widget (hidden by default)
        self.ma_widget = QWidget()
        ma_layout = QVBoxLayout(self.ma_widget)
        ma_layout.setContentsMargins(12, 0, 0, 0)

        self.ma_period = QSpinBox()
        self.ma_period.setRange(2, 200)
        self.ma_period.setValue(20)
        ma_layout.addWidget(QLabel('MA Period'))
        ma_layout.addWidget(self.ma_period)

        self.ma_type = QComboBox()
        self.ma_type.addItems(['SMA', 'EMA'])
        ma_layout.addWidget(QLabel('MA Type'))
        ma_layout.addWidget(self.ma_type)

        self.ma_period.valueChanged.connect(self.refresh_chart)
        self.ma_type.currentIndexChanged.connect(self.refresh_chart)

        self.ma_widget.setVisible(False)
        sidebar.addWidget(self.ma_widget)

        # Multiple EMAs checkbox
        self.multi_ema_check = QCheckBox('Multiple EMAs')
        self.multi_ema_check.stateChanged.connect(self._on_multi_ema_toggled)
        sidebar.addWidget(self.multi_ema_check)

        # Multiple EMAs parameter widget (hidden by default)
        self.multi_ema_widget = QWidget()
        multi_ema_layout = QVBoxLayout(self.multi_ema_widget)
        multi_ema_layout.setContentsMargins(12, 0, 0, 0)

        # Standard preset checkboxes
        self.ema_20_check = QCheckBox('EMA 20')
        self.ema_20_check.setChecked(True)
        self.ema_20_check.setStyleSheet("color: #FFD700; font-weight: bold;")
        self.ema_20_check.stateChanged.connect(self.refresh_chart)
        multi_ema_layout.addWidget(self.ema_20_check)

        self.ema_50_check = QCheckBox('EMA 50')
        self.ema_50_check.setChecked(True)
        self.ema_50_check.setStyleSheet("color: #00E5FF; font-weight: bold;")
        self.ema_50_check.stateChanged.connect(self.refresh_chart)
        multi_ema_layout.addWidget(self.ema_50_check)

        self.ema_100_check = QCheckBox('EMA 100')
        self.ema_100_check.setStyleSheet("color: #E040FB; font-weight: bold;")
        self.ema_100_check.stateChanged.connect(self.refresh_chart)
        multi_ema_layout.addWidget(self.ema_100_check)

        self.ema_200_check = QCheckBox('EMA 200')
        self.ema_200_check.setStyleSheet("color: #FF6D00; font-weight: bold;")
        self.ema_200_check.stateChanged.connect(self.refresh_chart)
        multi_ema_layout.addWidget(self.ema_200_check)

        # Custom EMAs text input
        multi_ema_layout.addWidget(QLabel('Custom EMAs (e.g. 9, 21):'))
        self.custom_ema_input = QLineEdit()
        self.custom_ema_input.setPlaceholderText('e.g. 9, 21')
        self.custom_ema_input.textChanged.connect(self.refresh_chart)
        multi_ema_layout.addWidget(self.custom_ema_input)

        self.multi_ema_widget.setVisible(False)
        sidebar.addWidget(self.multi_ema_widget)

        # Bollinger Bands checkbox
        self.bb_check = QCheckBox('Bollinger Bands')
        self.bb_check.stateChanged.connect(self._on_bb_toggled)
        sidebar.addWidget(self.bb_check)

        # Bollinger Bands parameter widget (hidden by default)
        self.bb_widget = QWidget()
        bb_layout = QVBoxLayout(self.bb_widget)
        bb_layout.setContentsMargins(12, 0, 0, 0)

        self.bb_period = QSpinBox()
        self.bb_period.setRange(2, 100)
        self.bb_period.setValue(20)
        bb_layout.addWidget(QLabel('BB Period'))
        bb_layout.addWidget(self.bb_period)

        self.bb_std = QDoubleSpinBox()
        self.bb_std.setRange(0.5, 5.0)
        self.bb_std.setSingleStep(0.1)
        self.bb_std.setDecimals(1)
        self.bb_std.setValue(2.0)
        bb_layout.addWidget(QLabel('Std Deviations'))
        bb_layout.addWidget(self.bb_std)

        self.bb_period.valueChanged.connect(self.refresh_chart)
        self.bb_std.valueChanged.connect(self.refresh_chart)

        self.bb_widget.setVisible(False)
        sidebar.addWidget(self.bb_widget)

        # Relative Strength Index (RSI) checkbox
        self.rsi_check = QCheckBox('RSI')
        self.rsi_check.stateChanged.connect(self._on_rsi_toggled)
        sidebar.addWidget(self.rsi_check)

        # RSI parameter widget (hidden by default)
        self.rsi_widget = QWidget()
        rsi_layout = QVBoxLayout(self.rsi_widget)
        rsi_layout.setContentsMargins(12, 0, 0, 0)

        self.rsi_period = QSpinBox()
        self.rsi_period.setRange(2, 100)
        self.rsi_period.setValue(14)
        rsi_layout.addWidget(QLabel('RSI Period'))
        rsi_layout.addWidget(self.rsi_period)

        self.rsi_overbought = QSpinBox()
        self.rsi_overbought.setRange(50, 95)
        self.rsi_overbought.setValue(70)
        rsi_layout.addWidget(QLabel('Overbought Level'))
        rsi_layout.addWidget(self.rsi_overbought)

        self.rsi_oversold = QSpinBox()
        self.rsi_oversold.setRange(5, 50)
        self.rsi_oversold.setValue(30)
        rsi_layout.addWidget(QLabel('Oversold Level'))
        rsi_layout.addWidget(self.rsi_oversold)

        self.rsi_period.valueChanged.connect(self.refresh_chart)
        self.rsi_overbought.valueChanged.connect(self.refresh_chart)
        self.rsi_oversold.valueChanged.connect(self.refresh_chart)

        self.rsi_widget.setVisible(False)
        sidebar.addWidget(self.rsi_widget)

        # Stochastic RSI checkbox
        self.stoch_rsi_check = QCheckBox('Stochastic RSI')
        self.stoch_rsi_check.stateChanged.connect(self._on_stoch_rsi_toggled)
        sidebar.addWidget(self.stoch_rsi_check)

        # Stochastic RSI parameter widget (hidden by default)
        self.stoch_rsi_widget = QWidget()
        stoch_rsi_layout = QVBoxLayout(self.stoch_rsi_widget)
        stoch_rsi_layout.setContentsMargins(12, 0, 0, 0)

        self.stoch_rsi_period = QSpinBox()
        self.stoch_rsi_period.setRange(2, 100)
        self.stoch_rsi_period.setValue(14)
        stoch_rsi_layout.addWidget(QLabel('RSI Period'))
        stoch_rsi_layout.addWidget(self.stoch_rsi_period)

        self.stoch_rsi_window = QSpinBox()
        self.stoch_rsi_window.setRange(2, 100)
        self.stoch_rsi_window.setValue(14)
        stoch_rsi_layout.addWidget(QLabel('Stoch Window'))
        stoch_rsi_layout.addWidget(self.stoch_rsi_window)

        self.stoch_rsi_k = QSpinBox()
        self.stoch_rsi_k.setRange(1, 20)
        self.stoch_rsi_k.setValue(3)
        stoch_rsi_layout.addWidget(QLabel('%K Smoothing'))
        stoch_rsi_layout.addWidget(self.stoch_rsi_k)

        self.stoch_rsi_d = QSpinBox()
        self.stoch_rsi_d.setRange(1, 20)
        self.stoch_rsi_d.setValue(3)
        stoch_rsi_layout.addWidget(QLabel('%D Smoothing'))
        stoch_rsi_layout.addWidget(self.stoch_rsi_d)

        self.stoch_rsi_period.valueChanged.connect(self.refresh_chart)
        self.stoch_rsi_window.valueChanged.connect(self.refresh_chart)
        self.stoch_rsi_k.valueChanged.connect(self.refresh_chart)
        self.stoch_rsi_d.valueChanged.connect(self.refresh_chart)

        self.stoch_rsi_widget.setVisible(False)
        sidebar.addWidget(self.stoch_rsi_widget)

        # Average Directional Index (ADX) checkbox
        self.adx_check = QCheckBox('ADX')
        self.adx_check.stateChanged.connect(self._on_adx_toggled)
        sidebar.addWidget(self.adx_check)

        # ADX parameter widget (hidden by default)
        self.adx_widget = QWidget()
        adx_layout = QVBoxLayout(self.adx_widget)
        adx_layout.setContentsMargins(12, 0, 0, 0)

        self.adx_period = QSpinBox()
        self.adx_period.setRange(2, 100)
        self.adx_period.setValue(14)
        adx_layout.addWidget(QLabel('ADX Period'))
        adx_layout.addWidget(self.adx_period)

        self.adx_threshold = QSpinBox()
        self.adx_threshold.setRange(10, 50)
        self.adx_threshold.setValue(25)
        adx_layout.addWidget(QLabel('Trend Threshold'))
        adx_layout.addWidget(self.adx_threshold)

        self.adx_show_di = QCheckBox('Show +DI / -DI')
        self.adx_show_di.setChecked(True)
        adx_layout.addWidget(self.adx_show_di)

        self.adx_period.valueChanged.connect(self.refresh_chart)
        self.adx_threshold.valueChanged.connect(self.refresh_chart)
        self.adx_show_di.stateChanged.connect(self.refresh_chart)

        self.adx_widget.setVisible(False)
        sidebar.addWidget(self.adx_widget)

        # Beta checkbox
        self.beta_check = QCheckBox('Beta')
        self.beta_check.stateChanged.connect(self._on_beta_toggled)
        sidebar.addWidget(self.beta_check)

        # Beta parameter widget (hidden by default)
        self.beta_widget = QWidget()
        beta_layout = QVBoxLayout(self.beta_widget)
        beta_layout.setContentsMargins(12, 0, 0, 0)

        self.beta_period = QSpinBox()
        self.beta_period.setRange(30, 756)
        self.beta_period.setValue(252)
        beta_layout.addWidget(QLabel('Rolling Window (days)'))
        beta_layout.addWidget(self.beta_period)

        self.beta_benchmark = QComboBox()
        for ticker, name in TARGET_INDICES.items():
            self.beta_benchmark.addItem(name, ticker)
        beta_layout.addWidget(QLabel('Benchmark'))
        beta_layout.addWidget(self.beta_benchmark)

        self.beta_period.valueChanged.connect(self.refresh_chart)
        self.beta_benchmark.currentIndexChanged.connect(self.refresh_chart)

        self.beta_widget.setVisible(False)
        sidebar.addWidget(self.beta_widget)

        sidebar.addStretch()

        # Interactive Chart View with Header Card
        chart_content_widget = QWidget()
        chart_content_layout = QVBoxLayout(chart_content_widget)
        chart_content_layout.setContentsMargins(4, 0, 4, 4)
        chart_content_layout.setSpacing(6)

        # Header metric card
        self.chart_header_card = QFrame()
        self.chart_header_card.setStyleSheet(
            "QFrame { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 6px; padding: 4px 12px; }"
        )
        header_card_layout = QHBoxLayout(self.chart_header_card)
        header_card_layout.setContentsMargins(8, 4, 8, 4)
        header_card_layout.setSpacing(12)

        # Ticker Title & Name
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lbl_chart_symbol = QLabel("^NSEI")
        sym_font = QFont()
        sym_font.setPointSize(15)
        sym_font.setBold(True)
        self.lbl_chart_symbol.setFont(sym_font)
        self.lbl_chart_symbol.setStyleSheet("color: #61afef; font-weight: bold;")
        title_box.addWidget(self.lbl_chart_symbol)

        self.lbl_chart_company = QLabel("Nifty 50 Index • Benchmark")
        self.lbl_chart_company.setStyleSheet("color: #7f848e; font-size: 11px;")
        title_box.addWidget(self.lbl_chart_company)
        header_card_layout.addLayout(title_box, stretch=2)

        # Price Readout
        self.lbl_chart_price = QLabel("—")
        price_font = QFont()
        price_font.setPointSize(14)
        price_font.setBold(True)
        self.lbl_chart_price.setFont(price_font)
        self.lbl_chart_price.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header_card_layout.addWidget(self.lbl_chart_price)

        self.lbl_chart_change = QLabel("—")
        self.lbl_chart_change.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.lbl_chart_change.setStyleSheet("font-size: 12px; font-weight: bold;")
        header_card_layout.addWidget(self.lbl_chart_change)

        header_card_layout.addSpacing(10)

        self.lbl_chart_range = QLabel("High: — | Low: —")
        self.lbl_chart_range.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.lbl_chart_range.setStyleSheet("color: #9da5b4; font-size: 11px;")
        header_card_layout.addWidget(self.lbl_chart_range)

        chart_content_layout.addWidget(self.chart_header_card)

        # Interactive Chart View
        self.plotly_view = QWebEngineView(self.chart_tab)
        chart_content_layout.addWidget(self.plotly_view, stretch=1)
        chart_tab_layout.addWidget(chart_content_widget, stretch=1)
        self.tabs.addTab(self.chart_tab, 'Analysis Terminal')

        # Select Nifty 50 as default *after* all widgets are fully constructed
        # so that the initial refresh_chart call has access to period_selector
        # and all other sidebar controls.
        self._select_default_ticker('^NSEI')

        # Strategy Backtester Tab
        self.backtest_tab = BacktestTab(self.repo)
        self.tabs.addTab(self.backtest_tab, 'Strategy Backtester')

        # Fundamental Screener Tab
        self.screener_tab = FundamentalScreenerTab(self.repo)
        self.screener_tab.ticker_selected.connect(self.on_screener_ticker_selected)
        self.tabs.addTab(self.screener_tab, 'Fundamental Screener')

        # Scanner Tab (Stock Signals)
        self.scanner_tab = MorningScannerTab(self.repo)
        self.scanner_tab.ticker_selected.connect(self.on_scanner_ticker_selected)
        self.tabs.addTab(self.scanner_tab, 'Scanner')

        # Dedicated Market Sentiment Tab
        self.sentiment_tab = MarketSentimentTab()
        self.scanner_tab.open_sentiment_tab_requested.connect(
            lambda: self.tabs.setCurrentWidget(self.sentiment_tab)
        )
        self.tabs.addTab(self.sentiment_tab, 'Market Sentiment')

        # Paper Trading Dashboard Tab
        self.paper_trading_tab = PaperTradingTab(self.repo)
        self.tabs.addTab(self.paper_trading_tab, 'Paper Trading')

    # ── Indicator toggle helpers ─────────────────────────────────────────────

    def _on_stoch_toggled(self) -> None:
        """Show/hide Stochastic Oscillator parameter panel based on checkbox state."""
        self.stochastic_widget.setVisible(self.stoch_check.isChecked())
        self.refresh_chart()

    def _on_ma_toggled(self) -> None:
        """Show/hide Moving Average parameter panel based on checkbox state."""
        self.ma_widget.setVisible(self.ma_check.isChecked())
        self.refresh_chart()

    def _on_multi_ema_toggled(self) -> None:
        """Show/hide Multiple EMAs parameter panel based on checkbox state."""
        self.multi_ema_widget.setVisible(self.multi_ema_check.isChecked())
        self.refresh_chart()

    def _on_bb_toggled(self) -> None:
        """Show/hide Bollinger Bands parameter panel based on checkbox state."""
        self.bb_widget.setVisible(self.bb_check.isChecked())
        self.refresh_chart()

    def _on_rsi_toggled(self) -> None:
        """Show/hide RSI parameter panel based on checkbox state."""
        self.rsi_widget.setVisible(self.rsi_check.isChecked())
        self.refresh_chart()

    def _on_stoch_rsi_toggled(self) -> None:
        """Show/hide Stochastic RSI parameter panel based on checkbox state."""
        self.stoch_rsi_widget.setVisible(self.stoch_rsi_check.isChecked())
        self.refresh_chart()

    def _on_adx_toggled(self) -> None:
        """Show/hide ADX parameter panel based on checkbox state."""
        self.adx_widget.setVisible(self.adx_check.isChecked())
        self.refresh_chart()

    def _on_beta_toggled(self) -> None:
        """Show/hide Beta parameter panel based on checkbox state."""
        self.beta_widget.setVisible(self.beta_check.isChecked())
        self.refresh_chart()

    # ── Ticker search/filter ─────────────────────────────────────────────────

    def _filter_ticker_list(self, text: str) -> None:
        """Filter the visible ticker list items to those containing *text*.

        Args:
            text (str): The current search string typed by the user.
        """
        query = text.strip().lower()

        # Preserve the currently selected ticker so selection is not lost
        current_item = self.ticker_list.currentItem()
        current_text = current_item.text() if current_item else ''

        self.ticker_list.blockSignals(True)
        self.ticker_list.clear()

        # Build filtered list; show all items when query is empty
        matches = [
            t for t in self._all_tickers
            if query in t.lower()
        ]
        self.ticker_list.addItems(matches)

        # Re-apply previous selection if it is still visible
        for i in range(self.ticker_list.count()):
            if self.ticker_list.item(i).text() == current_text:
                self.ticker_list.setCurrentRow(i)
                break

        self.ticker_list.blockSignals(False)

    def _select_default_ticker(self, prefix: str) -> None:
        """Select the first ticker whose text starts with *prefix*.

        Args:
            prefix (str): Ticker symbol prefix to match (e.g. '^NSEI').
        """
        for i in range(self.ticker_list.count()):
            if self.ticker_list.item(i).text().startswith(prefix):
                self.ticker_list.setCurrentRow(i)
                return

        # Fallback: select first item if prefix not found
        if self.ticker_list.count() > 0:
            self.ticker_list.setCurrentRow(0)

    def _on_header_ticker_clicked(self, ticker: str) -> None:
        """Handle header benchmark card click by switching to Analysis Terminal and loading chart.

        Args:
            ticker (str): Selected benchmark ticker symbol (e.g. '^NSEI').
        """
        self.tabs.setCurrentIndex(0)
        self._select_default_ticker(ticker)

    # ── Main chart rendering ─────────────────────────────────────────────────

    def on_screener_ticker_selected(self, ticker_str: str) -> None:
        """Handle ticker selection from Fundamental Screener by opening 3-month chart popup.

        Args:
            ticker_str (str): Selected ticker string, e.g. 'INFY.NS (STOCK)'.
        """
        show_ticker_chart_popup(ticker_str, repo=self.repo, parent=self)

    def on_scanner_ticker_selected(self, ticker_str: str) -> None:
        """Handle ticker selection from Scanner tab by opening 3-month chart popup.

        Args:
            ticker_str (str): Selected ticker string, e.g. 'INFY.NS (STOCK)'.
        """
        show_ticker_chart_popup(ticker_str, repo=self.repo, parent=self)

    def refresh_chart(self):
        """Update and re-render Plotly chart with candlesticks, volume, and indicators.

        Subplot layout adapts dynamically:
          - Row 1 : Price candlesticks (+ Moving Average overlay when active)
          - Row 2 : Volume bars
          - Row 3 : Stochastic Oscillator (when active) or Beta (when only Beta is active)
          - Row 4 : Beta (only added when both Stochastic and Beta are active)
        """
        item = self.ticker_list.currentItem()
        if item is None:
            return
        display_string = item.text()
        if not display_string:
            return

        # Always pull full history from repository for accurate indicator calculation
        df_full = self.repo.get_data(display_string)
        if df_full.empty:
            print(f"Warning: No database records discovered for {display_string}")
            return

        df_full = df_full.copy()
        df_full['date'] = pd.to_datetime(df_full['date'])

        # Slice data based on selected chart display timeframe
        horizon_months = self.period_selector.currentData()
        if horizon_months is not None:  # None corresponds to 'All'
            cutoff_date = df_full['date'].max() - pd.DateOffset(months=horizon_months)
            df_display = df_full[df_full['date'] >= cutoff_date].copy()
        else:
            df_display = df_full.copy()

        # Determine which indicators are active
        stoch_active = self.stoch_check.isChecked()
        ma_active = self.ma_check.isChecked()
        multi_ema_active = self.multi_ema_check.isChecked()
        bb_active = self.bb_check.isChecked()
        rsi_active = self.rsi_check.isChecked()
        stoch_rsi_active = self.stoch_rsi_check.isChecked()
        adx_active = self.adx_check.isChecked()
        beta_active = self.beta_check.isChecked()

        # Identify active subplots (excluding row 1 and row 2 which are Price and Volume)
        active_subplots: list[str] = []
        if stoch_active:
            active_subplots.append('Stochastic')
        if rsi_active:
            active_subplots.append('RSI')
        if stoch_rsi_active:
            active_subplots.append('StochRSI')
        if adx_active:
            active_subplots.append('ADX')
        if beta_active:
            active_subplots.append('Beta')

        # Determine row layout and heights dynamically
        num_sub = len(active_subplots)
        if num_sub == 0:
            num_rows = 2
            row_heights = [0.75, 0.25]
            subplot_titles = ('Price', 'Volume')
        elif num_sub == 1:
            num_rows = 3
            row_heights = [0.60, 0.18, 0.22]
            subplot_titles = ('Price', 'Volume', active_subplots[0])
        elif num_sub == 2:
            num_rows = 4
            row_heights = [0.50, 0.16, 0.17, 0.17]
            subplot_titles = ('Price', 'Volume', active_subplots[0], active_subplots[1])
        elif num_sub == 3:
            num_rows = 5
            row_heights = [0.44, 0.11, 0.15, 0.15, 0.15]
            subplot_titles = tuple(['Price', 'Volume'] + active_subplots)
        else:  # 4 or more sub-indicators
            num_rows = 2 + num_sub
            sub_h = 0.48 / num_sub
            row_heights = [0.40, 0.12] + [sub_h] * num_sub
            subplot_titles = tuple(['Price', 'Volume'] + active_subplots)

        def get_sub_row(name: str) -> int:
            """Return 1-indexed subplot row number for the given active indicator."""
            return 3 + active_subplots.index(name)

        # Build multi-panel subplot layout
        fig = make_subplots(
            rows=num_rows,
            cols=1,
            shared_xaxes=True,
            row_heights=row_heights,
            vertical_spacing=0.04,
            subplot_titles=subplot_titles,
        )

        # Subplot 1: Price Candlesticks with TradingView color palette
        fig.add_trace(
            go.Candlestick(
                x=df_display['date'],
                open=df_display['open'],
                high=df_display['high'],
                low=df_display['low'],
                close=df_display['close'],
                name='Price',
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            ),
            row=1,
            col=1,
        )

        # Subplot 2: Volume Bars with bull/bear dynamic color-coding
        vol_colors = [
            "#26a69a" if c >= o else "#ef5350"
            for o, c in zip(df_display["open"], df_display["close"])
        ]
        fig.add_trace(
            go.Bar(
                x=df_display['date'],
                y=df_display['volume'],
                name='Volume',
                marker_color=vol_colors,
                opacity=0.65,
            ),
            row=2,
            col=1,
        )

        # Subplot: Stochastic Oscillator
        if stoch_active:
            stoch_row = get_sub_row('Stochastic')
            k_period = self.k_period.value()
            k_smooth = self.k_smooth.value()
            d_smooth = self.d_smooth.value()

            low_min = df_full['low'].rolling(window=k_period).min()
            high_max = df_full['high'].rolling(window=k_period).max()
            df_full['%K'] = 100 * (df_full['close'] - low_min) / (high_max - low_min)
            df_full['%K'] = df_full['%K'].rolling(window=k_smooth).mean()
            df_full['%D'] = df_full['%K'].rolling(window=d_smooth).mean()

            # Plot filtered slice
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=df_full.loc[df_display.index, '%K'],
                    mode='lines',
                    name='%K',
                    line={'color': 'orange'},
                ),
                row=stoch_row,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=df_full.loc[df_display.index, '%D'],
                    mode='lines',
                    name='%D',
                    line={'color': 'blue'},
                ),
                row=stoch_row,
                col=1,
            )

            fig.update_yaxes(
                title_text="Stochastic",
                row=stoch_row,
                col=1,
                tickvals=[0, 20, 40, 60, 80, 100],
            )

        # Subplot 1 overlay: Moving Average
        if ma_active:
            ma_period = self.ma_period.value()
            ma_type = self.ma_type.currentText()

            if ma_type == 'SMA':
                df_full['MA'] = df_full['close'].rolling(window=ma_period).mean()
            else:
                df_full['MA'] = df_full['close'].ewm(span=ma_period, adjust=False).mean()

            # Plot filtered slice
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=df_full.loc[df_display.index, 'MA'],
                    mode='lines',
                    name=f'{ma_type} {ma_period}',
                    line={'color': 'yellow'},
                ),
                row=1,
                col=1,
            )

        # Subplot 1 overlay: Multiple EMAs
        if multi_ema_active:
            ema_configs: list[tuple[int, str, float]] = []
            if self.ema_20_check.isChecked():
                ema_configs.append((20, "#FFD700", 1.8))
            if self.ema_50_check.isChecked():
                ema_configs.append((50, "#00E5FF", 1.8))
            if self.ema_100_check.isChecked():
                ema_configs.append((100, "#E040FB", 1.5))
            if self.ema_200_check.isChecked():
                ema_configs.append((200, "#FF6D00", 1.5))

            # Parse custom EMAs
            custom_text = self.custom_ema_input.text().strip()
            if custom_text:
                custom_palette = ["#76FF03", "#FF4081", "#FFD600", "#18FFFF"]
                for idx, token in enumerate(custom_text.split(",")):
                    token_str = token.strip()
                    if token_str.isdigit():
                        period = int(token_str)
                        if period >= 2 and period not in [p for p, _, _ in ema_configs]:
                            color = custom_palette[idx % len(custom_palette)]
                            ema_configs.append((period, color, 1.5))

            # Plot each EMA line on Subplot 1
            for period, color, width in ema_configs:
                col_name = f"EMA_{period}"
                df_full[col_name] = (
                    df_full["close"].ewm(span=period, adjust=False).mean()
                )
                fig.add_trace(
                    go.Scatter(
                        x=df_display["date"],
                        y=df_full.loc[df_display.index, col_name],
                        mode="lines",
                        name=f"EMA {period}",
                        line={"color": color, "width": width},
                    ),
                    row=1,
                    col=1,
                )

        # Subplot 1 overlay: Bollinger Bands
        if bb_active:
            bb_period = self.bb_period.value()
            bb_std = self.bb_std.value()

            bb_df = calculate_bollinger_bands(
                df_full['close'], period=bb_period, num_std=bb_std
            )

            # Upper Band
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=bb_df.loc[df_display.index, 'BB_Upper'],
                    mode='lines',
                    name=f'BB Upper ({bb_period}, {bb_std}\u03c3)',
                    line={'color': 'rgba(38, 166, 154, 0.65)', 'width': 1.2},
                ),
                row=1,
                col=1,
            )

            # Lower Band (fill='tonexty' fills area between Upper and Lower Band)
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=bb_df.loc[df_display.index, 'BB_Lower'],
                    mode='lines',
                    name=f'BB Lower ({bb_period}, {bb_std}\u03c3)',
                    line={'color': 'rgba(38, 166, 154, 0.65)', 'width': 1.2},
                    fill='tonexty',
                    fillcolor='rgba(38, 166, 154, 0.08)',
                ),
                row=1,
                col=1,
            )

            # Middle Band (SMA)
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=bb_df.loc[df_display.index, 'BB_Middle'],
                    mode='lines',
                    name=f'BB Middle ({bb_period})',
                    line={'color': '#FFA726', 'width': 1.2, 'dash': 'dot'},
                ),
                row=1,
                col=1,
            )

        # Subplot: Relative Strength Index (RSI)
        if rsi_active:
            rsi_row = get_sub_row('RSI')
            rsi_period = self.rsi_period.value()
            ob_level = self.rsi_overbought.value()
            os_level = self.rsi_oversold.value()

            df_full['RSI'] = calculate_rsi(df_full['close'], period=rsi_period)

            # Plot RSI line
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=df_full.loc[df_display.index, 'RSI'],
                    mode='lines',
                    name=f'RSI ({rsi_period})',
                    line={'color': '#00E5FF', 'width': 1.5},
                ),
                row=rsi_row,
                col=1,
            )

            # Overbought reference line
            fig.add_hline(
                y=ob_level,
                line_dash='dash',
                line_color='#FF5252',
                row=rsi_row,
                col=1,
                annotation_text=f'OB ({ob_level})',
                annotation_position='right',
            )

            # Oversold reference line
            fig.add_hline(
                y=os_level,
                line_dash='dash',
                line_color='#69F0AE',
                row=rsi_row,
                col=1,
                annotation_text=f'OS ({os_level})',
                annotation_position='right',
            )

            # Midline reference line at 50
            fig.add_hline(
                y=50,
                line_dash='dot',
                line_color='gray',
                row=rsi_row,
                col=1,
            )

            rsi_ticks = sorted({0, 20, os_level, 40, 50, 60, ob_level, 80, 100})
            fig.update_yaxes(
                title_text="RSI",
                row=rsi_row,
                col=1,
                range=[0, 100],
                tickvals=rsi_ticks,
            )

        # Subplot: Stochastic RSI
        if stoch_rsi_active:
            stoch_rsi_row = get_sub_row('StochRSI')
            rsi_p = self.stoch_rsi_period.value()
            stoch_p = self.stoch_rsi_window.value()
            k_p = self.stoch_rsi_k.value()
            d_p = self.stoch_rsi_d.value()

            srsi_df = calculate_stoch_rsi(
                df_full['close'],
                rsi_period=rsi_p,
                stoch_period=stoch_p,
                k_period=k_p,
                d_period=d_p,
            )

            # %K Line
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=srsi_df.loc[df_display.index, 'StochRSI_K'],
                    mode='lines',
                    name=f'StochRSI %K ({rsi_p},{stoch_p},{k_p})',
                    line={'color': '#00E5FF', 'width': 1.5},
                ),
                row=stoch_rsi_row,
                col=1,
            )

            # %D Line
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=srsi_df.loc[df_display.index, 'StochRSI_D'],
                    mode='lines',
                    name=f'StochRSI %D ({d_p})',
                    line={'color': '#FF4081', 'width': 1.2},
                ),
                row=stoch_rsi_row,
                col=1,
            )

            # Overbought reference line (80)
            fig.add_hline(
                y=80,
                line_dash='dash',
                line_color='#FF5252',
                row=stoch_rsi_row,
                col=1,
                annotation_text='OB (80)',
                annotation_position='right',
            )

            # Oversold reference line (20)
            fig.add_hline(
                y=20,
                line_dash='dash',
                line_color='#69F0AE',
                row=stoch_rsi_row,
                col=1,
                annotation_text='OS (20)',
                annotation_position='right',
            )

            # Midline reference line (50)
            fig.add_hline(
                y=50,
                line_dash='dot',
                line_color='gray',
                row=stoch_rsi_row,
                col=1,
            )

            fig.update_yaxes(
                title_text="Stoch RSI",
                row=stoch_rsi_row,
                col=1,
                range=[0, 100],
                tickvals=[0, 20, 50, 80, 100],
            )

        # Subplot: Average Directional Index (ADX)
        if adx_active:
            adx_row = get_sub_row('ADX')
            adx_period = self.adx_period.value()
            trend_threshold = self.adx_threshold.value()
            show_di = self.adx_show_di.isChecked()

            adx_data = calculate_adx(df_full, period=adx_period)

            # Plot ADX line
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=adx_data.loc[df_display.index, 'ADX'],
                    mode='lines',
                    name=f'ADX ({adx_period})',
                    line={'color': '#FFD700', 'width': 2.0},
                ),
                row=adx_row,
                col=1,
            )

            # Plot +DI and -DI lines when enabled
            if show_di:
                fig.add_trace(
                    go.Scatter(
                        x=df_display['date'],
                        y=adx_data.loc[df_display.index, '+DI'],
                        mode='lines',
                        name=f'+DI ({adx_period})',
                        line={'color': '#00E676', 'width': 1.2},
                    ),
                    row=adx_row,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df_display['date'],
                        y=adx_data.loc[df_display.index, '-DI'],
                        mode='lines',
                        name=f'-DI ({adx_period})',
                        line={'color': '#FF1744', 'width': 1.2},
                    ),
                    row=adx_row,
                    col=1,
                )

            # Trend threshold reference line (e.g. 25)
            fig.add_hline(
                y=trend_threshold,
                line_dash='dash',
                line_color='#FFA726',
                row=adx_row,
                col=1,
                annotation_text=f'Trend ({trend_threshold})',
                annotation_position='right',
            )

            # Weak trend reference line at 20
            fig.add_hline(
                y=20,
                line_dash='dot',
                line_color='gray',
                row=adx_row,
                col=1,
                annotation_text='Weak (20)',
                annotation_position='right',
            )

            adx_ticks = sorted({0, 20, trend_threshold, 40, 60, 80})
            fig.update_yaxes(
                title_text="ADX",
                row=adx_row,
                col=1,
                range=[0, 80],
                tickvals=adx_ticks,
            )

        # Subplot: Rolling Beta
        if beta_active:
            beta_row = get_sub_row('Beta')
            beta_window = self.beta_period.value()
            benchmark_ticker = self.beta_benchmark.currentData()
            benchmark_display = f"{benchmark_ticker} (INDEX)"

            df_bench = self.repo.get_data(benchmark_display)

            if not df_bench.empty:
                df_bench = df_bench.copy()
                df_bench['date'] = pd.to_datetime(df_bench['date'])

                # Compute daily percentage returns for stock and benchmark
                df_full['stock_ret'] = df_full['close'].pct_change()
                bench_ret = (
                    df_bench.set_index('date')['close']
                    .pct_change()
                    .rename('bench_ret')
                )

                # Align stock and benchmark returns on common trading dates
                combined = (
                    df_full.set_index('date')[['stock_ret']]
                    .join(bench_ret, how='inner')
                    .dropna()
                )

                # Rolling beta = Cov(stock, benchmark) / Var(benchmark)
                roll_cov = combined['stock_ret'].rolling(window=beta_window).cov(
                    combined['bench_ret']
                )
                roll_var = combined['bench_ret'].rolling(window=beta_window).var()
                combined['beta'] = roll_cov / roll_var

                # Slice to display window
                if horizon_months is not None:
                    beta_cutoff = (
                        combined.index.max() - pd.DateOffset(months=horizon_months)
                    )
                    combined_display = combined[combined.index >= beta_cutoff]
                else:
                    combined_display = combined

                # Plot rolling beta line
                fig.add_trace(
                    go.Scatter(
                        x=combined_display.index,
                        y=combined_display['beta'],
                        mode='lines',
                        name=f'Beta ({beta_window}d)',
                        line={'color': 'mediumpurple'},
                    ),
                    row=beta_row,
                    col=1,
                )

                # Dashed reference line at beta = 1.0 (market-neutral)
                fig.add_hline(
                    y=1.0,
                    line_dash='dash',
                    line_color='gray',
                    row=beta_row,
                    col=1,
                    annotation_text='\u03b2=1',
                    annotation_position='right',
                )

                # Dashed reference line at beta = 1.2 (high-beta buy threshold)
                fig.add_hline(
                    y=1.2,
                    line_dash='dash',
                    line_color='orange',
                    row=beta_row,
                    col=1,
                    annotation_text='\u03b2=1.2',
                    annotation_position='right',
                )

                # Limit y-axis ticks to 5 decimal places; fix range 0.0–1.5
                # to keep both reference lines (beta=1.0 and beta=1.2) in frame
                fig.update_yaxes(
                    title_text="Beta",
                    row=beta_row,
                    col=1,
                    tickformat='.5f',
                    range=[0.0, 1.5],
                )

                # Annotate with cached beta_nsei from fundamentals when available
                fundamentals = self.repo.get_fundamentals(display_string)
                if fundamentals and fundamentals.get('beta_nsei') is not None:
                    cached_beta = round(float(fundamentals['beta_nsei']), 2)
                    fig.add_annotation(
                        text=f"Cached \u03b2 (NSEI): {cached_beta}",
                        xref='paper',
                        yref='paper',
                        x=0.01,
                        y=1.01,
                        showarrow=False,
                        font={'size': 11, 'color': 'lightgreen'},
                        align='left',
                    )
            else:
                print(
                    f"Warning: No benchmark data found for {benchmark_display}. "
                    "Beta indicator cannot be rendered."
                )

        # Visual layout configuration with seamless dark background & tight margins
        fig.update_layout(
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            margin=dict(l=50, r=40, t=30, b=30),
            paper_bgcolor="#1e2227",
            plot_bgcolor="#1e2227",
            legend={
                'orientation': 'h',
                'yanchor': 'bottom',
                'y': 1.02,
                'xanchor': 'right',
                'x': 1,
            },
        )
        fig.update_yaxes(title_text="Price (₹)", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)

        # Always show x-axis label on the bottom-most subplot row
        fig.update_xaxes(title_text="Date", row=num_rows, col=1)

        # Hide weekends and overnight non-trading hours to avoid gaps on intraday hourly charts
        fig.update_xaxes(
            rangebreaks=[
                {'bounds': ['sat', 'mon']},  # Hide weekends
                {'bounds': [15.5, 9.25], 'pattern': 'hour'},  # Hide overnight hours (3:30PM-9:15AM)
            ]
        )

        # Render HTML string into WebEngine view
        html = fig.to_html(include_plotlyjs='cdn')
        self.plotly_view.setHtml(html)

        # Update Header Metric Card readout
        clean_sym = display_string.split(" ")[0].strip()
        metadata = self.repo.get_stock_metadata()
        company_name = metadata.get(clean_sym, clean_sym)
        self.lbl_chart_symbol.setText(clean_sym)
        self.lbl_chart_company.setText(
            f"{company_name} • {'Index Benchmark' if clean_sym.startswith('^') else 'NSE Equity'}"
        )

        first_close = float(df_display['close'].iloc[0])
        latest_close = float(df_display['close'].iloc[-1])
        net_change = latest_close - first_close
        pct_change = (net_change / first_close * 100.0) if first_close > 0 else 0.0

        period_high = float(df_display['high'].max())
        period_low = float(df_display['low'].min())

        color_hex = "#26a69a" if net_change >= 0 else "#ef5350"
        sign_str = "+" if net_change >= 0 else ""

        self.lbl_chart_price.setText(f"₹{latest_close:,.2f}")
        self.lbl_chart_price.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
        self.lbl_chart_change.setText(
            f"{sign_str}₹{net_change:,.2f} ({sign_str}{pct_change:.2f}%)"
        )
        self.lbl_chart_change.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
        self.lbl_chart_range.setText(
            f"Period High: ₹{period_high:,.2f} | Low: ₹{period_low:,.2f} | Bars: {len(df_display)}"
        )

    def check_database_health(self):
        """Verify presence of database file and populated securities on startup."""
        if not os.path.exists(self.repo.db_path):
            QMessageBox.critical(
                self,
                'Database missing',
                f'Could not find tradebot.db file at path:\n{self.repo.db_path}',
            )
        elif self.ticker_list.count() == 0:
            QMessageBox.warning(
                self,
                'Empty Watchlist',
                'Connected to tradebot.db, but the "securities" table contains zero rows.',
            )

    def _setup_sync_listener(self) -> None:
        """Register callbacks for data synchronization events and schedule auto-sync."""
        sync_service = DataSyncService.get_instance()
        sync_service.sync_finished.connect(self._on_data_sync_completed)

        # Trigger auto-sync on startup if preference is enabled
        if sync_service.get_auto_sync_on_startup():
            QTimer.singleShot(1500, self._trigger_startup_sync)

    def _trigger_startup_sync(self) -> None:
        """Initiate background synchronization on initial application launch."""
        DataSyncService.get_instance().start_sync()

    def _on_data_sync_completed(self, bars: int, funds: int, summary: str) -> None:
        """Refresh active chart and ticker list when background synchronization completes.

        Args:
            bars (int): Count of newly added price bars.
            funds (int): Count of updated fundamental records.
            summary (str): Completed sync summary message.
        """
        if bars > 0:
            current_selection = self.ticker_list.currentItem()
            selected_text = current_selection.text() if current_selection else None
            self._all_tickers = self.repo.get_tickers()
            self.ticker_list.blockSignals(True)
            self.ticker_list.clear()
            self.ticker_list.addItems(self._all_tickers)
            if selected_text:
                items = self.ticker_list.findItems(
                    selected_text, Qt.MatchFlag.MatchExactly
                )
                if items:
                    self.ticker_list.setCurrentItem(items[0])
            self.ticker_list.blockSignals(False)
            self.refresh_chart()

    def closeEvent(self, event) -> None:
        """Clean up background workers and threads on application exit."""
        DataSyncService.get_instance().cancel_sync()
        if hasattr(self, 'header_widget') and self.header_widget:
            self.header_widget.cleanup()
        if hasattr(self, 'paper_trading_tab') and self.paper_trading_tab.worker:
            self.paper_trading_tab.worker.stop()
            self.paper_trading_tab.worker.wait(1500)
        super().closeEvent(event)
