import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QListWidget, QPushButton, QTabWidget,
    QLabel, QComboBox, QTableWidget, QMessageBox
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
        self.period_selector.currentIndexChanged.connect(self.refresh_chart)
        sidebar.addWidget(self.period_selector)

        sidebar.addWidget(QLabel('<b>Active Execution Strategy</b>'))
        self.strategy_selector = QComboBox()
        self.strategy_selector.addItems([
            'MACD + RSI Trend Cross', 
            'Mean Reversion Bollinger', 
            'Volume Breakout Scanner'
        ])
        sidebar.addWidget(self.strategy_selector)

        self.backtest_btn = QPushButton('Execute backtest Matrix')
        sidebar.addWidget(self.backtest_btn)
        sidebar.addStretch()

        # Right workplace tabs
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

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3]
        )

        fig.add_trace(
            go.Candlestick(
                x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Bar(
                x=df['date'],
                y=df['volume'],
                name='Volume',
                marker_color='rgba(128, 128, 128, 0.6)',
            ),
            row=2, col=1
        )

        fig.update_layout(
            template='plotly_dark',
            title='Asset Price and Volume Terminal',
            yaxis_title='Price',
            yaxis2_title='Volume',
            xaxis_rangeslider_visible=False,
            height=600
        )

        #fig.show()

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