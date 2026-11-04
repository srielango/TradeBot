"""Interactive Ticker Chart Popup Dialog component for TradeBot."""

import sqlite3

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

from market_repository import MarketRepository


class TickerChartPopupDialog(QDialog):
    """Popup dialog window displaying an interactive 3-month candlestick & volume chart.

    Defaults to a 3-month timeframe upon opening, while allowing the user to
    seamlessly switch horizons (1M, 3M, 6M, 1Y, All) or toggle technical indicator overlays
    (20 EMA, 50 EMA, Volume bars).
    """

    def __init__(
        self,
        ticker: str,
        repo: MarketRepository | None = None,
        parent: QWidget | None = None,
        default_period_months: int = 3,
    ):
        """Initialize ticker chart popup dialog.

        Args:
            ticker (str): Stock or index ticker symbol (e.g., 'RELIANCE.NS' or 'INFY.NS (STOCK)').
            repo (MarketRepository | None): Market data repository instance.
            parent (QWidget | None): Parent widget for Qt hierarchy.
            default_period_months (int): Initial display timeframe in months. Defaults to 3.
        """
        super().__init__(parent)
        self.ticker_raw = ticker.strip()
        self.ticker_symbol = self.ticker_raw.split(" ")[0]
        self.repo = repo or MarketRepository()
        self.selected_months: int | None = default_period_months
        self.selected_interval: str = "daily"
        self.df_history: pd.DataFrame = pd.DataFrame()
        self.company_name: str = self.ticker_symbol

        # Configure dialog window properties
        self.setWindowTitle(f"{self.ticker_symbol} — 3-Month Interactive Price Chart")
        self.resize(1020, 680)
        self.setMinimumSize(780, 500)
        # Allow dialog to be non-modal so users can keep it open side-by-side with tables
        self.setModal(False)

        self.init_ui()
        self.load_data()
        self.render_chart()

    def init_ui(self) -> None:
        """Construct popup header, metric banner, horizon toolbar, and WebEngine chart."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # Style dialog background
        self.setStyleSheet(
            "QDialog { background-color: #1e2227; color: #abb2bf; } "
            "QLabel { color: #abb2bf; } "
            "QFrame { border: none; }"
        )

        # =====================================================================
        # Section 1: Header Bar & Stock Metric Banner
        # =====================================================================
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 6px; padding: 6px 12px; }"
        )
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(12)

        # Ticker Title & Company Name
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.lbl_symbol = QLabel(self.ticker_symbol)
        sym_font = QFont()
        sym_font.setPointSize(16)
        sym_font.setBold(True)
        self.lbl_symbol.setFont(sym_font)
        self.lbl_symbol.setStyleSheet("color: #61afef; font-weight: bold;")
        title_box.addWidget(self.lbl_symbol)

        self.lbl_company = QLabel("Loading company details...")
        self.lbl_company.setStyleSheet("color: #7f848e; font-size: 11px;")
        title_box.addWidget(self.lbl_company)
        header_layout.addLayout(title_box, stretch=2)

        # Key Metrics Readout (Latest Price, Period Return, High / Low)
        self.lbl_price = QLabel("—")
        price_font = QFont()
        price_font.setPointSize(15)
        price_font.setBold(True)
        self.lbl_price.setFont(price_font)
        self.lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self.lbl_price)

        self.lbl_change = QLabel("—")
        self.lbl_change.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_change.setStyleSheet("font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.lbl_change)

        header_layout.addSpacing(10)

        self.lbl_range_stats = QLabel("High: — | Low: —")
        self.lbl_range_stats.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.lbl_range_stats.setStyleSheet("color: #9da5b4; font-size: 11px;")
        header_layout.addWidget(self.lbl_range_stats)

        main_layout.addWidget(header_card)

        # =====================================================================
        # Section 2: Toolbar (Timeframe Selector & Indicator Toggles)
        # =====================================================================
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)

        # Interval pill buttons (Daily vs Hourly)
        lbl_int = QLabel("<b>Interval:</b>")
        lbl_int.setStyleSheet("color: #d7dae0; font-size: 12px;")
        toolbar_layout.addWidget(lbl_int)

        self.btn_group_int = QButtonGroup(self)
        self.btn_group_int.setExclusive(True)

        self.int_buttons: dict[str, QPushButton] = {}
        for label, interval_val in [("1D", "daily"), ("1H", "hourly")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (interval_val == self.selected_interval)
            btn.setChecked(is_active)
            self._style_timeframe_button(btn, is_active)
            btn.setProperty("interval", interval_val)
            btn.clicked.connect(self._on_interval_clicked)
            self.btn_group_int.addButton(btn)
            self.int_buttons[label] = btn
            toolbar_layout.addWidget(btn)

        toolbar_layout.addSpacing(10)

        # Timeframe pill buttons
        lbl_tf = QLabel("<b>Period:</b>")
        lbl_tf.setStyleSheet("color: #d7dae0; font-size: 12px;")
        toolbar_layout.addWidget(lbl_tf)

        self.btn_group_tf = QButtonGroup(self)
        self.btn_group_tf.setExclusive(True)

        # Map button label -> months (None = All)
        timeframes = [
            ("1M", 1),
            ("3M", 3),   # Default!
            ("6M", 6),
            ("1Y", 12),
            ("All", None),
        ]

        self.tf_buttons: dict[str, QPushButton] = {}
        for label, months in timeframes:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_default = (months == self.selected_months)
            btn.setChecked(is_default)
            self._style_timeframe_button(btn, is_default)

            # Store months on button property
            btn.setProperty("months", months)
            btn.clicked.connect(self._on_timeframe_clicked)
            self.btn_group_tf.addButton(btn)
            self.tf_buttons[label] = btn
            toolbar_layout.addWidget(btn)

        toolbar_layout.addSpacing(15)

        # Technical Indicator Overlays
        lbl_ind = QLabel("<b>Overlays:</b>")
        lbl_ind.setStyleSheet("color: #d7dae0; font-size: 12px;")
        toolbar_layout.addWidget(lbl_ind)

        self.chk_ema20 = QCheckBox("EMA 20")
        self.chk_ema20.setChecked(True)
        self.chk_ema20.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11px;")
        self.chk_ema20.toggled.connect(self.render_chart)
        toolbar_layout.addWidget(self.chk_ema20)

        self.chk_ema50 = QCheckBox("EMA 50")
        self.chk_ema50.setChecked(True)
        self.chk_ema50.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 11px;")
        self.chk_ema50.toggled.connect(self.render_chart)
        toolbar_layout.addWidget(self.chk_ema50)

        self.chk_volume = QCheckBox("Volume")
        self.chk_volume.setChecked(True)
        self.chk_volume.setStyleSheet("color: #abb2bf; font-weight: bold; font-size: 11px;")
        self.chk_volume.toggled.connect(self.render_chart)
        toolbar_layout.addWidget(self.chk_volume)

        toolbar_layout.addStretch(1)

        # Close Button
        btn_close = QPushButton("✕ Close")
        btn_close.setStyleSheet(
            "QPushButton { background-color: #2c313a; color: #abb2bf; "
            "border: 1px solid #3b4048; border-radius: 4px; padding: 4px 12px; "
            "font-size: 11px; font-weight: bold; } "
            "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
        )
        btn_close.clicked.connect(self.accept)
        toolbar_layout.addWidget(btn_close)

        main_layout.addLayout(toolbar_layout)

        # =====================================================================
        # Section 3: Plotly Interactive Chart View
        # =====================================================================
        self.chart_view = QWebEngineView()
        self.chart_view.setStyleSheet(
            "background-color: #1e2227; border: 1px solid #3b4048; border-radius: 6px;"
        )
        main_layout.addWidget(self.chart_view, stretch=1)

    def _style_timeframe_button(self, button: QPushButton, active: bool) -> None:
        """Apply active or inactive pill style to a timeframe selector button."""
        if active:
            button.setStyleSheet(
                "QPushButton { background-color: #1976d2; color: #ffffff; font-weight: bold; "
                "font-size: 11px; padding: 4px 10px; border-radius: 4px; "
                "border: 1px solid #2196f3; } "
                "QPushButton:hover { background-color: #2196f3; }"
            )
        else:
            button.setStyleSheet(
                "QPushButton { background-color: #282c34; color: #abb2bf; font-weight: normal; "
                "font-size: 11px; padding: 4px 10px; border-radius: 4px; "
                "border: 1px solid #3b4048; } "
                "QPushButton:hover { background-color: #353b45; color: #ffffff; }"
            )

    def _on_timeframe_clicked(self) -> None:
        """Handle timeframe button click by updating selected horizon and re-rendering."""
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return

        for btn in self.tf_buttons.values():
            self._style_timeframe_button(btn, btn == sender)

        self.selected_months = sender.property("months")
        self.render_chart()

    def _on_interval_clicked(self) -> None:
        """Handle interval button click (1D vs 1H)."""
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return

        for btn in self.int_buttons.values():
            self._style_timeframe_button(btn, btn == sender)

        self.selected_interval = sender.property("interval")
        self.load_data()
        self.render_chart()

    def load_data(self) -> None:
        """Fetch historical records from database repository or fallback to yfinance."""
        # 1. Look up company metadata
        try:
            metadata = self.repo.get_stock_metadata()
            self.company_name = metadata.get(self.ticker_symbol, self.ticker_symbol)
        except (sqlite3.Error, KeyError, AttributeError):
            self.company_name = self.ticker_symbol

        self.lbl_company.setText(f"{self.company_name} • NSE Equity")

        # 2. Query historical data from SQLite database
        if self.selected_interval == "hourly":
            df = self.repo.get_data(self.ticker_symbol)
        else:
            df = self.repo.get_daily_data(self.ticker_symbol)

        # 3. Fallback to online yfinance fetch if local records are absent
        if df.empty:
            try:
                yf_interval = "1h" if self.selected_interval == "hourly" else "1d"
                yf_df = yf.download(
                    self.ticker_symbol,
                    period="1y",
                    interval=yf_interval,
                    progress=False,
                )
                if not yf_df.empty:
                    if isinstance(yf_df.columns, pd.MultiIndex):
                        yf_df.columns = [c[0].lower() for c in yf_df.columns]
                    else:
                        yf_df.columns = [c.lower() for c in yf_df.columns]
                    yf_df = yf_df.reset_index()
                    if "Date" in yf_df.columns:
                        yf_df.rename(columns={"Date": "date"}, inplace=True)
                    elif "datetime" in yf_df.columns:
                        yf_df.rename(columns={"datetime": "date"}, inplace=True)
                    df = yf_df
            except (ValueError, KeyError, IndexError, AttributeError) as err:
                print(f"yfinance fallback download failed for {self.ticker_symbol}: {err}")

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df.sort_values("date", inplace=True)
            df.reset_index(drop=True, inplace=True)

        self.df_history = df

    def render_chart(self) -> None:
        """Construct Plotly candlestick & volume chart for selected horizon and render."""
        if self.df_history.empty:
            empty_html = (
                "<div style='color:#abb2bf; text-align:center; padding-top:100px; "
                "font-family:sans-serif;'>"
                f"<h3>No Historical Price Data Found for {self.ticker_symbol}</h3>"
                "<p>Please ensure data synchronization is completed.</p>"
                "</div>"
            )
            self.chart_view.setHtml(empty_html)
            return

        df_full = self.df_history.copy()

        # Filter slice based on selected horizon (default: 3 months)
        if self.selected_months is not None:
            max_date = df_full["date"].max()
            cutoff_date = max_date - pd.DateOffset(months=self.selected_months)
            df_slice = df_full[df_full["date"] >= cutoff_date].copy()
            if df_slice.empty:
                df_slice = df_full.copy()
        else:
            df_slice = df_full.copy()

        # Update metric readouts in header
        first_close = float(df_slice["close"].iloc[0])
        latest_close = float(df_slice["close"].iloc[-1])
        net_change = latest_close - first_close
        pct_change = (net_change / first_close * 100.0) if first_close > 0 else 0.0

        period_high = float(df_slice["high"].max())
        period_low = float(df_slice["low"].min())

        color_hex = "#98c379" if net_change >= 0 else "#e06c75"
        sign_str = "+" if net_change >= 0 else ""

        self.lbl_price.setText(f"₹{latest_close:,.2f}")
        self.lbl_price.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
        self.lbl_change.setText(f"{sign_str}₹{net_change:,.2f} ({sign_str}{pct_change:.2f}%)")
        self.lbl_change.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
        interval_tag = "Daily" if self.selected_interval == "daily" else "Hourly"
        self.lbl_range_stats.setText(
            f"Period High: ₹{period_high:,.2f} | Low: ₹{period_low:,.2f} | "
            f"Bars: {len(df_slice)} ({interval_tag})"
        )

        # Check toggle states
        show_vol = self.chk_volume.isChecked()
        show_ema20 = self.chk_ema20.isChecked()
        show_ema50 = self.chk_ema50.isChecked()

        # Compute moving averages on the full series for indicator continuity
        if show_ema20:
            df_full["ema20"] = df_full["close"].ewm(span=20, adjust=False).mean()
        if show_ema50:
            df_full["ema50"] = df_full["close"].ewm(span=50, adjust=False).mean()

        # Configure subplot rows (Row 1: Candlestick, Row 2: Volume)
        if show_vol:
            fig = make_subplots(
                rows=2,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.04,
                row_heights=[0.75, 0.25],
                subplot_titles=("", ""),
            )
        else:
            fig = make_subplots(
                rows=1,
                cols=1,
                shared_xaxes=True,
                subplot_titles=("",),
            )

        # Candlestick trace
        fig.add_trace(
            go.Candlestick(
                x=df_slice["date"],
                open=df_slice["open"],
                high=df_slice["high"],
                low=df_slice["low"],
                close=df_slice["close"],
                name="Price",
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            ),
            row=1,
            col=1,
        )

        # EMA 20 overlay
        if show_ema20 and "ema20" in df_full.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_slice["date"],
                    y=df_full.loc[df_slice.index, "ema20"],
                    mode="lines",
                    name="EMA 20",
                    line=dict(color="#00e5ff", width=1.5),
                ),
                row=1,
                col=1,
            )

        # EMA 50 overlay
        if show_ema50 and "ema50" in df_full.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_slice["date"],
                    y=df_full.loc[df_slice.index, "ema50"],
                    mode="lines",
                    name="EMA 50",
                    line=dict(color="#ff9800", width=1.5),
                ),
                row=1,
                col=1,
            )

        # Volume bars
        if show_vol:
            vol_colors = [
                "#26a69a" if c >= o else "#ef5350"
                for o, c in zip(df_slice["open"], df_slice["close"])
            ]
            fig.add_trace(
                go.Bar(
                    x=df_slice["date"],
                    y=df_slice["volume"],
                    name="Volume",
                    marker_color=vol_colors,
                    opacity=0.65,
                ),
                row=2,
                col=1,
            )
            fig.update_yaxes(title_text="Volume", row=2, col=1)

        # Layout styling
        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            margin=dict(l=50, r=40, t=20, b=30),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1.0,
            ),
            paper_bgcolor="#1e2227",
            plot_bgcolor="#1e2227",
        )
        fig.update_yaxes(title_text="Price (₹)", row=1, col=1)

        # Configure x-axis rangebreaks: hide weekends on all charts,
        # and hide overnight non-trading hours only on intraday hourly charts
        rangebreaks = [dict(bounds=["sat", "mon"])]
        if self.selected_interval == "hourly":
            rangebreaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))

        fig.update_xaxes(rangebreaks=rangebreaks)

        html_content = fig.to_html(include_plotlyjs="cdn")
        self.chart_view.setHtml(html_content)

    def load_ticker(self, ticker: str) -> None:
        """Switch popup dialog to display another ticker symbol without re-instantiating.

        Args:
            ticker (str): New ticker symbol string.
        """
        self.ticker_raw = ticker.strip()
        self.ticker_symbol = self.ticker_raw.split(" ")[0]
        self.setWindowTitle(f"{self.ticker_symbol} — 3-Month Interactive Price Chart")
        self.lbl_symbol.setText(self.ticker_symbol)
        self.load_data()
        self.render_chart()


def show_ticker_chart_popup(
    ticker: str,
    repo: MarketRepository | None = None,
    parent: QWidget | None = None,
    default_period_months: int = 3,
) -> TickerChartPopupDialog:
    """Helper factory function to construct and display a ticker chart popup dialog.

    Args:
        ticker (str): Ticker symbol string, e.g. 'RELIANCE.NS'.
        repo (MarketRepository | None): Market data repository instance.
        parent (QWidget | None): Parent widget.
        default_period_months (int): Initial timeframe horizon in months. Defaults to 3.

    Returns:
        TickerChartPopupDialog: The activated dialog window instance.
    """
    dialog = TickerChartPopupDialog(
        ticker=ticker,
        repo=repo,
        parent=parent,
        default_period_months=default_period_months,
    )
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
