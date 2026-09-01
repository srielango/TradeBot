"""Trading application graphical interface module for TradeBot."""

import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DB_PATH, TARGET_INDICES
from market_repository import MarketRepository
from ui.backtest_tab import BacktestTab
from ui.fundamental_screener_tab import FundamentalScreenerTab


class TradingApp(QMainWindow):
    """Main graphical interface for the Tradebot Management Studio desktop application."""

    def __init__(self):
        """Initialize the main window, data repository, and user interface components."""
        super().__init__()
        self.setWindowTitle('Tradebot Management Studio')
        self.resize(1400, 900)
        self.repo = MarketRepository(DB_PATH)

        # Store full ticker list so the search filter can operate on it
        self._all_tickers: list[str] = []

        self.init_ui()
        self.check_database_health()

    def init_ui(self):
        """Construct layout, sidebar controls, charts, and data tabs."""
        # Tab Navigation Layout
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Interactive Chart Tab (Analysis Terminal)
        self.chart_tab = QWidget()
        chart_tab_layout = QHBoxLayout(self.chart_tab)

        # Sidebar container & layout inside Analysis Terminal
        sidebar = QVBoxLayout()
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(240)
        sidebar_container.setLayout(sidebar)
        chart_tab_layout.addWidget(sidebar_container)

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

        # Interactive Chart View
        self.plotly_view = QWebEngineView(self.chart_tab)
        chart_tab_layout.addWidget(self.plotly_view)
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

        # Morning Scanner Tab
        self.scanner_tab = QTableWidget(10, 4)
        self.scanner_tab.setHorizontalHeaderLabels([
            'Ticker', 'Indicator Setup', 'Signal Output', 'Target Action',
        ])
        self.tabs.addTab(self.scanner_tab, 'Morning Scanner')

        # Trade Execution Journal Tab
        self.journal_tab = QTableWidget(5, 5)
        self.journal_tab.setHorizontalHeaderLabels([
            'Execution Date', 'Ticker', 'Type', 'Entry Price', 'Net PnL (INR)',
        ])
        self.tabs.addTab(self.journal_tab, 'Execution Journal')

    # ── Indicator toggle helpers ─────────────────────────────────────────────

    def _on_stoch_toggled(self) -> None:
        """Show/hide Stochastic Oscillator parameter panel based on checkbox state."""
        self.stochastic_widget.setVisible(self.stoch_check.isChecked())
        self.refresh_chart()

    def _on_ma_toggled(self) -> None:
        """Show/hide Moving Average parameter panel based on checkbox state."""
        self.ma_widget.setVisible(self.ma_check.isChecked())
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

    # ── Main chart rendering ─────────────────────────────────────────────────

    def on_screener_ticker_selected(self, ticker_str: str) -> None:
        """Handle ticker double-click from Fundamental Screener tab by switching to Backtest.

        Args:
            ticker_str (str): Selected ticker string, e.g. 'INFY.NS (STOCK)'.
        """
        self.backtest_tab.set_active_ticker(ticker_str)
        self.tabs.setCurrentWidget(self.backtest_tab)

    def refresh_chart(self):  # noqa: C901
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
        beta_active = self.beta_check.isChecked()

        # When both Stochastic and Beta are active a 4th row is added so each
        # indicator has its own dedicated panel; otherwise 3 rows suffice.
        both_sub_active = stoch_active and beta_active
        beta_row = 4 if both_sub_active else 3

        if both_sub_active:
            num_rows = 4
            row_heights = [0.5, 0.15, 0.175, 0.175]
            subplot_titles = ("Price", "Volume", "Stochastic", "Beta")
        elif stoch_active:
            num_rows = 3
            row_heights = [0.6, 0.2, 0.2]
            subplot_titles = ("Price", "Volume", "Stochastic")
        elif beta_active:
            num_rows = 3
            row_heights = [0.6, 0.2, 0.2]
            subplot_titles = ("Price", "Volume", "Beta")
        else:
            num_rows = 3
            row_heights = [0.6, 0.2, 0.2]
            subplot_titles = ("Price", "Volume", "Indicators")

        # Build multi-panel subplot layout
        fig = make_subplots(
            rows=num_rows,
            cols=1,
            shared_xaxes=True,
            row_heights=row_heights,
            vertical_spacing=0.05,
            subplot_titles=subplot_titles,
        )

        # Subplot 1: Price Candlesticks
        fig.add_trace(
            go.Candlestick(
                x=df_display['date'],
                open=df_display['open'],
                high=df_display['high'],
                low=df_display['low'],
                close=df_display['close'],
                name='Price',
            ),
            row=1,
            col=1,
        )

        # Subplot 2: Volume Bars
        fig.add_trace(
            go.Bar(
                x=df_display['date'],
                y=df_display['volume'],
                name='Volume',
                marker_color='lightblue',
                opacity=0.6,
            ),
            row=2,
            col=1,
        )

        # Subplot 3 (row 3): Stochastic Oscillator
        if stoch_active:
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
                row=3,
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
                row=3,
                col=1,
            )

            fig.update_yaxes(
                title_text="Stochastic",
                row=3,
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

        # Subplot 3 or 4: Rolling Beta
        if beta_active:
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

        # Add empty placeholder in row 3 when no indicator occupies it
        if not stoch_active and not beta_active:
            fig.add_trace(
                go.Scatter(
                    x=df_display['date'],
                    y=[None] * len(df_display),
                    showlegend=False,
                    hoverinfo='skip',
                ),
                row=3,
                col=1,
            )

        # Visual layout configuration
        fig.update_layout(
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            legend={
                'orientation': 'h',
                'yanchor': 'bottom',
                'y': 1.02,
                'xanchor': 'right',
                'x': 1,
            },
        )
        fig.update_yaxes(title_text="Price", row=1, col=1)
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
