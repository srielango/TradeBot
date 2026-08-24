import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QListWidget, QPushButton, QTabWidget,
    QLabel, QComboBox, QTableWidget, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

import plotly.graph_objects as go

from lightweight_charts.widgets import QtChart
import sqlite3
import os


class MarketRepository:
    def __init__(self, db_name='tradebot.db'):
        self.db_path = os.path.abspath(db_name)

    def get_tickers(self):
        query = """
        SELECT ticker, name, asset_type FROM securities ORDER BY asset_type DESC, ticker ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)
                return [
                    f"{row['ticker']} ({row['asset_type']})"
                    for _, row in df.iterrows()
                ]
        except sqlite3.Error:
            return []

    def get_data(self, display_string: str, horizon_months: int = None):
        if not display_string:
            return pd.DataFrame()
            
        ticker = display_string.split(" ")[0]
        
        # 1. Base query: Pull raw dates directly
        query = """
            SELECT p.date, p.open, p.high, p.low, p.close, p.volume
            FROM daily_prices p
            JOIN securities s ON p.security_id = s.id
            WHERE s.ticker = ?
        """
        params = [ticker]
        
        # 2. SQLite exact dynamic math modifier 
        if horizon_months is not None:
            query += """ 
                AND p.date >= date(
                    (SELECT MAX(date) FROM daily_prices pd JOIN securities sd ON pd.security_id = sd.id WHERE sd.ticker = ?), 
                    ?
                )
            """
            params.extend([ticker, f'-{horizon_months} months'])
            
        query += " ORDER BY p.date ASC"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)
                
            if df.empty: return df

            # Standardize names to lowercase
            df.columns = df.columns.str.lower()
            return df
            
        except sqlite3.Error as e:
            print(f"Database error while loading daily prices: {e}")
            return pd.DataFrame()


class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Tradebot Management Studio')
        self.resize(1400, 900)
        self.repo = MarketRepository('tradebot.db')
        self.candle_series = None  # Track our active candle overlay container
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
        
        # Instantiate the main Lightweight Charts widget container
        self.tv_chart = QtChart(self.chart_tab)
        chart_tab_layout.addWidget(self.tv_chart.get_webview())
        self.tabs.addTab(self.chart_tab, 'Analysis Terminal')

        # Initialize the low level candle container series exactly once
        # self.candle_series = self.tv_chart.create_candlestick()

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

        df['time'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
        self.tv_chart.set(df)


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