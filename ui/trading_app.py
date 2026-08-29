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
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DB_PATH
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

        # Asset Watchlist
        sidebar.addWidget(QLabel("<b>Nifty 50 Stocks Asset List</b>"))
        self.ticker_list = QListWidget()
        self.ticker_list.addItems(self.repo.get_tickers())
        self.ticker_list.currentTextChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.ticker_list)

        # Chart Period Selector
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

        # Active Indicator Multi-selection
        sidebar.addWidget(QLabel('<b>Active Indicators</b>'))
        self.indicator_list = QListWidget()
        self.indicator_list.addItems([
            'Stochastic Oscillator',
            'Moving Average',
        ])
        self.indicator_list.setSelectionMode(
            self.indicator_list.SelectionMode.MultiSelection
        )
        self.indicator_list.itemSelectionChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.indicator_list)

        # Stochastic Oscillator parameter inputs
        self.stochastic_widget = QWidget()
        stochastic_layout = QVBoxLayout(self.stochastic_widget)
        sidebar.addWidget(self.stochastic_widget)

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

        # Moving Average parameter inputs
        self.ma_widget = QWidget()
        ma_layout = QVBoxLayout(self.ma_widget)
        sidebar.addWidget(self.ma_widget)

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

        sidebar.addStretch()

        # Interactive Chart View
        self.plotly_view = QWebEngineView(self.chart_tab)
        chart_tab_layout.addWidget(self.plotly_view)
        self.tabs.addTab(self.chart_tab, 'Analysis Terminal')

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

    def on_screener_ticker_selected(self, ticker_str: str) -> None:
        """Handle ticker double-click from Fundamental Screener tab by switching to Backtest.

        Args:
            ticker_str (str): Selected ticker string, e.g. 'INFY.NS (STOCK)'.
        """
        self.backtest_tab.set_active_ticker(ticker_str)
        self.tabs.setCurrentWidget(self.backtest_tab)

    def refresh_chart(self):
        """Update and re-render Plotly chart with candlesticks, volume, and indicators."""
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

        # Build multi-panel subplot layout
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2],
            vertical_spacing=0.05,
            subplot_titles=("Price", "Volume", "Indicators"),
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

        # Subplot 3: Technical Indicators
        selected = [item.text() for item in self.indicator_list.selectedItems()]

        if 'Stochastic Oscillator' in selected:
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

        if 'Moving Average' in selected:
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

        if 'Stochastic Oscillator' not in selected:
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

        # Always show x-axis ticks at the bottom
        fig.update_xaxes(title_text="Date", row=3, col=1)

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
