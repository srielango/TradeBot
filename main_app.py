import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QListWidget, QPushButton, QTabWidget,
    QLabel, QComboBox, QTableWidget, QMessageBox, QSpinBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from lightweight_charts.widgets import QtChart
import os
from market_repository import MarketRepository

class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Tradebot Management Studio')
        self.resize(1400, 900)
        self.repo = MarketRepository('tradebot.db')
        self.init_ui()
        self.check_database_health()

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        # Left control panel sidebar
        sidebar = QVBoxLayout()
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(240)
        sidebar_container.setLayout(sidebar)
        main_layout.addWidget(sidebar_container)

        sidebar.addWidget(QLabel("<b>Nifty 200 Stocks Asset List</b>"))
        self.ticker_list = QListWidget()
        self.ticker_list.addItems(self.repo.get_tickers())
        self.ticker_list.currentTextChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.ticker_list)

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
        self.period_selector.currentIndexChanged.connect(self.toggle_strategy_controls)
        self.period_selector.currentIndexChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.period_selector)

        sidebar.addWidget(QLabel('<b>Active Execution Strategy</b>'))
        self.strategy_selector = QComboBox()
        self.strategy_selector.addItems([
            'MACD + RSI Trend Cross', 
            'Mean Reversion Bollinger', 
            'Volume Breakout Scanner',
            'Stochastic Oscillator',
            'Moving Average'
        ])
        self.strategy_selector.currentIndexChanged.connect(self.toggle_strategy_controls)
        self.strategy_selector.currentIndexChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.strategy_selector)

        # Stochastic Parameters
        self.stochastic_container = QVBoxLayout()
        self.stochastic_widget = QWidget()
        self.stochastic_widget.setLayout(self.stochastic_container)
        sidebar.addWidget(self.stochastic_widget)
        self.stochastic_widget.hide()

        self.k_period = QSpinBox()
        self.k_period.setRange(2, 50)
        self.k_period.setValue(8)
        self.stochastic_container.addWidget(QLabel('K Period'))
        self.stochastic_container.addWidget(self.k_period)

        self.k_smooth = QSpinBox()
        self.k_smooth.setRange(1, 10)
        self.k_smooth.setValue(3)
        self.stochastic_container.addWidget(QLabel('K Smoothing'))
        self.stochastic_container.addWidget(self.k_smooth)

        self.d_smooth = QSpinBox()
        self.d_smooth.setRange(1, 10)
        self.d_smooth.setValue(3)
        self.stochastic_container.addWidget(QLabel('D Smoothing'))
        self.stochastic_container.addWidget(self.d_smooth)

        # Moving Average parameters
        self.ma_container = QVBoxLayout()
        self.ma_widget = QWidget()
        self.ma_widget.setLayout(self.ma_container)
        sidebar.addWidget(self.ma_widget)
        self.ma_widget.hide()

        self.ma_period = QSpinBox()
        self.ma_period.setRange(2, 200)
        self.ma_period.setValue(20)
        self.ma_container.addWidget(QLabel('MA Period'))
        self.ma_container.addWidget(self.ma_period)

        self.ma_type = QComboBox()
        self.ma_type.addItems(['SMA', 'EMA'])
        self.ma_container.addWidget(QLabel('MA Type'))
        self.ma_container.addWidget(self.ma_type)

        self.backtest_btn = QPushButton('Execute backtest Matrix')
        sidebar.addWidget(self.backtest_btn)
        sidebar.addStretch()

        self.ma_period.valueChanged.connect(self.refresh_chart)
        self.ma_type.currentIndexChanged.connect(self.refresh_chart)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.chart_tab = QWidget()
        chart_tab_layout = QVBoxLayout(self.chart_tab)
        self.plotly_view = QWebEngineView(self.chart_tab)
        chart_tab_layout.addWidget(self.plotly_view)
        self.tabs.addTab(self.chart_tab, 'Analysis Terminal')

        self.scanner_tab = QTableWidget(10, 4)
        self.scanner_tab.setHorizontalHeaderLabels(['Ticker', 'Strategy Setup', 'Signal Output', 'Target Action'])
        self.tabs.addTab(self.scanner_tab, 'Morning Scanner')

        self.journal_tab = QTableWidget(5, 5)
        self.journal_tab.setHorizontalHeaderLabels(['Execution Date', 'Ticker', 'Type', 'Entry Price', 'Net PnL (INR)'])
        self.tabs.addTab(self.journal_tab, 'Execution Journal')

    def toggle_strategy_controls(self):
        if self.strategy_selector.currentText() == 'Stochastic Oscillator':
            self.stochastic_widget.show()
            self.ma_widget.hide()
        elif self.strategy_selector.currentText() == 'Moving Average':
            self.ma_widget.show()
            self.stochastic_widget.hide()
        else:
            self.stochastic_widget.hide()
            self.ma_widget.hide()

    def refresh_chart(self):
        item = self.ticker_list.currentItem()
        if item is None:
            return
        display_string = item.text()
        if not display_string:
            return

        horizon_months = self.period_selector.currentData()
        df = self.repo.get_data(display_string, horizon_months)

        if df.empty:
            print(f"Warning: No database records discovered for {display_string}")
            return

        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])

        # Base subplot layout
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2],
            vertical_spacing=0.05,
            subplot_titles=("Price", "Volume", "Indicators")
        )

        # Price candlesticks
        fig.add_trace(go.Candlestick(
            x=df['date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price'
        ), row=1, col=1)

        # Volume bars
        fig.add_trace(go.Bar(
            x=df['date'],
            y=df['volume'],
            name='Volume',
            marker_color='lightblue',
            opacity=0.6
        ), row=2, col=1)

        # Strategy overlays
        if self.strategy_selector.currentText() == 'Stochastic Oscillator':
            k_period = self.k_period.value()
            k_smooth = self.k_smooth.value()
            d_smooth = self.d_smooth.value()

            low_min = df['low'].rolling(window=k_period).min()
            high_max = df['high'].rolling(window=k_period).max()
            df['%K'] = 100 * (df['close'] - low_min) / (high_max - low_min)
            df['%K'] = df['%K'].rolling(window=k_smooth).mean()
            df['%D'] = df['%K'].rolling(window=d_smooth).mean()

            fig.add_trace(go.Scatter(
                x=df['date'], y=df['%K'], mode='lines', name='%K', line=dict(color='orange')
            ), row=3, col=1)
            fig.add_trace(go.Scatter(
                x=df['date'], y=df['%D'], mode='lines', name='%D', line=dict(color='blue')
            ), row=3, col=1)

            fig.update_yaxes(title_text="Stochastic", row=3, col=1, tickvals=[0,20,40,60,80,100])

        elif self.strategy_selector.currentText() == 'Moving Average':
            ma_period = self.ma_period.value()
            ma_type = self.ma_type.currentText()

            if ma_type == 'SMA':
                df['MA'] = df['close'].rolling(window=ma_period).mean()
            else:  # EMA
                df['MA'] = df['close'].ewm(span=ma_period, adjust=False).mean()

            fig.add_trace(go.Scatter(
                x=df['date'], y=df['MA'], mode='lines', name=f'{ma_type} {ma_period}',
                line=dict(color='yellow')
            ), row=1, col=1)

        fig.update_layout(
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # Axis labels
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)

        # Render into the PyQt web view
        html = fig.to_html(include_plotlyjs='cdn')
        self.plotly_view.setHtml(html)

    def check_database_health(self):
        if not os.path.exists(self.repo.db_path):
            QMessageBox.critical(self, 'Database missing', f'Could not find tradebot.db file at path:\n{self.repo.db_path}')
        elif self.ticker_list.count() == 0:
            QMessageBox.warning(self, 'Empty Watchlist', 'Connected to tradebot.db successfully, but the "securities" table contains zero rows.')

if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = TradingApp()
    window.show()

    sys.exit(app.exec())