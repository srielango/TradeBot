"""Nifty benchmark live data header widget and background polling worker."""

from datetime import datetime
import math
from typing import Any

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import yfinance as yf

from config import IST_TIMEZONE, is_market_open_ist


class NiftyLiveWorker(QThread):
    """Background worker thread to continuously fetch live Nifty index quotes via yfinance."""

    quotes_updated = pyqtSignal(dict)
    refresh_started = pyqtSignal()
    refresh_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, tickers: list[str] | None = None, interval_seconds: int = 15):
        """Initialize worker thread with index tickers and polling interval.

        Args:
            tickers (list[str] | None): List of index tickers. Defaults to ['^NSEI', '^NSEBANK'].
            interval_seconds (int): Auto-refresh interval in seconds. Defaults to 15.
        """
        super().__init__()
        self.tickers = tickers or ["^NSEI", "^NSEBANK"]
        self.interval_seconds = interval_seconds
        self._is_running = True
        self._manual_trigger = False

    def set_interval(self, seconds: int) -> None:
        """Update polling interval in seconds. Set to 0 or negative to pause auto-polling."""
        self.interval_seconds = seconds

    def trigger_now(self) -> None:
        """Signal the worker to execute an immediate quote refresh."""
        self._manual_trigger = True

    def stop(self) -> None:
        """Gracefully stop worker execution loop."""
        self._is_running = False

    def run(self) -> None:
        """Execution loop polling live quotes at the configured interval."""
        while self._is_running:
            self.refresh_started.emit()
            try:
                data = self._fetch_all_quotes()
                if data:
                    self.quotes_updated.emit(data)
            except (ValueError, KeyError, IndexError, AttributeError) as err:
                self.error_occurred.emit(str(err))
            finally:
                self.refresh_finished.emit()

            # Sleep in 250ms chunks to remain immediately responsive to stop or manual refresh
            sleep_chunks = (
                max(1, int(self.interval_seconds * 4))
                if self.interval_seconds > 0
                else 40
            )
            for _ in range(sleep_chunks):
                if not self._is_running or self._manual_trigger:
                    break
                self.msleep(250)

            self._manual_trigger = False

    def _fetch_all_quotes(self) -> dict[str, dict[str, Any]]:
        """Fetch quotes for configured index tickers from yfinance.

        Returns:
            dict[str, dict[str, Any]]: Mapping of ticker symbol to quote attributes.
        """
        results: dict[str, dict[str, Any]] = {}
        for ticker in self.tickers:
            if not self._is_running:
                break
            quote = self._fetch_single_quote(ticker)
            if quote:
                results[ticker] = quote
        return results

    @staticmethod
    def _fetch_single_quote(ticker: str) -> dict[str, Any] | None:
        """Fetch latest price and daily range metrics for a single ticker.

        Args:
            ticker (str): Yahoo Finance symbol (e.g. '^NSEI').

        Returns:
            dict[str, Any] | None: Parsed quote dictionary or None if fetch fails.
        """
        try:
            t = yf.Ticker(ticker)
            fast = t.fast_info
            last_price = getattr(fast, "last_price", None)
            prev_close = getattr(fast, "previous_close", None)
            open_price = getattr(fast, "open", None)
            day_high = getattr(fast, "day_high", None)
            day_low = getattr(fast, "day_low", None)

            # Fallback to history if fast_info does not provide valid last price
            if last_price is None or math.isnan(last_price) or last_price <= 0:
                hist = t.history(period="2d")
                if not hist.empty and "Close" in hist.columns:
                    last_price = float(hist["Close"].iloc[-1])
                    if len(hist) > 1:
                        prev_close = float(hist["Close"].iloc[-2])
                    if "High" in hist.columns:
                        day_high = float(hist["High"].iloc[-1])
                    if "Low" in hist.columns:
                        day_low = float(hist["Low"].iloc[-1])
                    if "Open" in hist.columns:
                        open_price = float(hist["Open"].iloc[-1])

            if last_price is None or math.isnan(last_price) or last_price <= 0:
                return None

            # Calculate change metrics
            net_change = 0.0
            pct_change = 0.0
            if prev_close and not math.isnan(prev_close) and prev_close > 0:
                net_change = last_price - prev_close
                pct_change = (net_change / prev_close) * 100.0

            # Calculate day range percentage (0.0 to 1.0)
            range_ratio = 0.5
            if (
                day_high is not None
                and day_low is not None
                and not math.isnan(day_high)
                and not math.isnan(day_low)
                and day_high > day_low
            ):
                range_ratio = max(0.0, min(1.0, (last_price - day_low) / (day_high - day_low)))

            name = "NIFTY 50" if ticker == "^NSEI" else (
                "BANK NIFTY" if ticker == "^NSEBANK" else ticker
            )

            return {
                "ticker": ticker,
                "name": name,
                "last_price": float(last_price),
                "prev_close": float(prev_close) if prev_close else None,
                "open": float(open_price) if open_price else None,
                "day_high": float(day_high) if day_high else None,
                "day_low": float(day_low) if day_low else None,
                "net_change": float(net_change),
                "pct_change": float(pct_change),
                "range_ratio": float(range_ratio),
                "timestamp": datetime.now(IST_TIMEZONE).strftime("%H:%M:%S"),
            }
        except (ValueError, KeyError, IndexError, AttributeError):
            return None


class NiftyIndexCard(QFrame):
    """Visual card displaying live index quote metrics with interactive navigation on click."""

    card_clicked = pyqtSignal(str)

    def __init__(self, ticker: str, default_name: str, parent: QWidget | None = None):
        """Initialize index card UI elements.

        Args:
            ticker (str): Index ticker symbol.
            default_name (str): Human-readable name.
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self.ticker = ticker
        self.default_name = default_name
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(f"Click to analyze {default_name} ({ticker}) in Analysis Terminal")
        self.init_ui()

    def init_ui(self) -> None:
        """Construct card layout, typography, change badges, and range bar."""
        self.setObjectName("IndexCard")
        self.setStyleSheet(
            "#IndexCard {"
            "  background-color: #21252b;"
            "  border: 1px solid #333842;"
            "  border-radius: 6px;"
            "  padding: 4px 10px;"
            "}"
            "#IndexCard:hover {"
            "  background-color: #282c34;"
            "  border: 1px solid #61afef;"
            "}"
        )

        card_layout = QHBoxLayout(self)
        card_layout.setContentsMargins(6, 4, 8, 4)
        card_layout.setSpacing(12)

        # Left block: Title and symbol tag
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.lbl_name = QLabel(self.default_name)
        self.lbl_name.setStyleSheet("color: #e5e5e5; font-weight: bold; font-size: 12px;")
        self.lbl_ticker = QLabel(self.ticker)
        self.lbl_ticker.setStyleSheet("color: #61afef; font-size: 9px; font-weight: 500;")
        title_box.addWidget(self.lbl_name)
        title_box.addWidget(self.lbl_ticker)
        card_layout.addLayout(title_box)

        # Center block: Current Price and Change Badge
        price_box = QVBoxLayout()
        price_box.setSpacing(1)
        self.lbl_price = QLabel("--")
        self.lbl_price.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold;")

        self.lbl_change = QLabel("--")
        self.lbl_change.setStyleSheet(
            "color: #abb2bf; font-size: 11px; font-weight: bold;"
        )
        price_box.addWidget(self.lbl_price)
        price_box.addWidget(self.lbl_change)
        card_layout.addLayout(price_box)

        # Right block: Day Range bar (Low -- Position -- High)
        range_container = QWidget()
        range_container.setFixedWidth(130)
        range_box = QVBoxLayout(range_container)
        range_box.setContentsMargins(0, 0, 0, 0)
        range_box.setSpacing(2)

        range_labels = QHBoxLayout()
        range_labels.setSpacing(0)
        self.lbl_low = QLabel("L: --")
        self.lbl_low.setStyleSheet("color: #7f848e; font-size: 9px;")
        self.lbl_high = QLabel("H: --")
        self.lbl_high.setStyleSheet("color: #7f848e; font-size: 9px;")
        self.lbl_high.setAlignment(Qt.AlignmentFlag.AlignRight)
        range_labels.addWidget(self.lbl_low)
        range_labels.addWidget(self.lbl_high)
        range_box.addLayout(range_labels)

        self.range_bar = QProgressBar()
        self.range_bar.setRange(0, 100)
        self.range_bar.setValue(50)
        self.range_bar.setTextVisible(False)
        self.range_bar.setFixedHeight(5)
        self.range_bar.setStyleSheet(
            "QProgressBar {"
            "  background-color: #1e2227;"
            "  border-radius: 2px;"
            "  border: 1px solid #333842;"
            "}"
            "QProgressBar::chunk {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #61afef, stop:1 #98c379);"
            "  border-radius: 2px;"
            "}"
        )
        range_box.addWidget(self.range_bar)
        card_layout.addWidget(range_container)

    def mousePressEvent(self, event) -> None:
        """Handle card click event to trigger chart navigation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_clicked.emit(self.ticker)
        super().mousePressEvent(event)

    def update_quote(self, quote: dict[str, Any]) -> None:
        """Render updated quote data into the card widgets.

        Args:
            quote (dict[str, Any]): Dictionary of updated quote values.
        """
        last_price = quote.get("last_price", 0.0)
        net_change = quote.get("net_change", 0.0)
        pct_change = quote.get("pct_change", 0.0)
        day_low = quote.get("day_low")
        day_high = quote.get("day_high")
        range_ratio = quote.get("range_ratio", 0.5)

        self.lbl_price.setText(f"{last_price:,.2f}")

        if net_change > 0:
            color = "#98c379"  # Green
            arrow = "▲"
            prefix = "+"
        elif net_change < 0:
            color = "#e06c75"  # Crimson Red
            arrow = "▼"
            prefix = ""
        else:
            color = "#abb2bf"  # Gray
            arrow = "■"
            prefix = ""

        self.lbl_change.setText(f"{arrow} {prefix}{net_change:,.2f} ({prefix}{pct_change:.2f}%)")
        self.lbl_change.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")

        # Update range metrics
        if day_low is not None:
            self.lbl_low.setText(f"L: {day_low:,.1f}")
        if day_high is not None:
            self.lbl_high.setText(f"H: {day_high:,.1f}")

        bar_val = int(range_ratio * 100)
        self.range_bar.setValue(max(0, min(100, bar_val)))

        # Update tooltip with full summary
        open_val = quote.get("open")
        prev_close = quote.get("prev_close")
        open_str = f"{open_val:,.2f}" if open_val else "--"
        prev_str = f"{prev_close:,.2f}" if prev_close else "--"
        low_str = f"{day_low:,.2f}" if day_low else "--"
        high_str = f"{day_high:,.2f}" if day_high else "--"

        tooltip_text = (
            f"<b>{self.default_name} ({self.ticker})</b><br>"
            f"LTP: <b>INR {last_price:,.2f}</b> ({prefix}{pct_change:.2f}%)<br>"
            f"Open: {open_str} | Prev Close: {prev_str}<br>"
            f"Day Range: {low_str} – {high_str}<br>"
            f"<i>Click to view chart in Analysis Terminal</i>"
        )
        self.setToolTip(tooltip_text)


class NiftyHeaderWidget(QFrame):
    """Top-level market benchmark header visible across all application tabs."""

    ticker_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        """Initialize header banner, child cards, market status indicator, and worker.

        Args:
            parent (QWidget | None): Optional parent container.
        """
        super().__init__(parent)
        self.setObjectName("MarketHeaderWidget")
        self.worker: NiftyLiveWorker | None = None
        self.cards: dict[str, NiftyIndexCard] = {}

        self.init_ui()
        self.setup_worker()

        # Update IST clock every second
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock_and_market_status)
        self.clock_timer.start(1000)
        self._update_clock_and_market_status()

    def init_ui(self) -> None:
        """Construct the visual header layout and child elements."""
        self.setFixedHeight(58)
        self.setStyleSheet(
            "#MarketHeaderWidget {"
            "  background-color: #1e2227;"
            "  border-bottom: 1px solid #282c34;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(14)

        # ── 1. Branding & Market Status Badge ────────────────────────────────
        brand_box = QHBoxLayout()
        brand_box.setSpacing(8)

        self.lbl_logo = QLabel("TRADEBOT")
        self.lbl_logo.setStyleSheet(
            "color: #61afef; font-weight: 900; font-size: 13px; letter-spacing: 1px;"
        )
        brand_box.addWidget(self.lbl_logo)

        self.lbl_status_badge = QLabel("● NSE OPEN")
        self.lbl_status_badge.setStyleSheet(
            "background-color: #1b382b; color: #98c379; font-weight: bold; "
            "font-size: 10px; padding: 3px 7px; border-radius: 4px; border: 1px solid #27ae60;"
        )
        brand_box.addWidget(self.lbl_status_badge)

        self.lbl_clock = QLabel("IST 00:00:00")
        self.lbl_clock.setStyleSheet("color: #7f848e; font-size: 10px; font-family: monospace;")
        brand_box.addWidget(self.lbl_clock)

        layout.addLayout(brand_box)

        # Divider line
        layout.addWidget(self._create_separator())

        # ── 2. Primary Index Cards: NIFTY 50 & BANK NIFTY ────────────────────
        cards_container = QHBoxLayout()
        cards_container.setSpacing(10)

        self.nifty_card = NiftyIndexCard("^NSEI", "NIFTY 50")
        self.nifty_card.card_clicked.connect(self._on_card_clicked)
        self.cards["^NSEI"] = self.nifty_card
        cards_container.addWidget(self.nifty_card)

        self.bank_nifty_card = NiftyIndexCard("^NSEBANK", "BANK NIFTY")
        self.bank_nifty_card.card_clicked.connect(self._on_card_clicked)
        self.cards["^NSEBANK"] = self.bank_nifty_card
        cards_container.addWidget(self.bank_nifty_card)

        layout.addLayout(cards_container)

        layout.addStretch()

        # Divider line
        layout.addWidget(self._create_separator())

        # ── 3. Controls: Auto-refresh interval, manual refresh & timestamp ──
        ctrl_box = QHBoxLayout()
        ctrl_box.setSpacing(8)

        self.lbl_last_updated = QLabel("Updating...")
        self.lbl_last_updated.setStyleSheet("color: #7f848e; font-size: 10px;")
        ctrl_box.addWidget(self.lbl_last_updated)

        self.combo_interval = QComboBox()
        self.combo_interval.addItem("Auto 15s", 15)
        self.combo_interval.addItem("Auto 30s", 30)
        self.combo_interval.addItem("Auto 60s", 60)
        self.combo_interval.addItem("Auto Off", 0)
        self.combo_interval.setStyleSheet(
            "QComboBox {"
            "  background-color: #282c34;"
            "  color: #abb2bf;"
            "  border: 1px solid #3e4451;"
            "  border-radius: 4px;"
            "  padding: 2px 6px;"
            "  font-size: 10px;"
            "}"
            "QComboBox::drop-down { border: none; }"
        )
        self.combo_interval.currentIndexChanged.connect(self._on_interval_changed)
        ctrl_box.addWidget(self.combo_interval)

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setStyleSheet(
            "QPushButton {"
            "  background-color: #2c313a;"
            "  color: #abb2bf;"
            "  border: 1px solid #3e4451;"
            "  border-radius: 4px;"
            "  padding: 3px 9px;"
            "  font-size: 10px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #3e4451;"
            "  color: #ffffff;"
            "  border-color: #61afef;"
            "}"
            "QPushButton:disabled {"
            "  color: #5c6370;"
            "  background-color: #21252b;"
            "}"
        )
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        ctrl_box.addWidget(self.btn_refresh)

        layout.addLayout(ctrl_box)

    @staticmethod
    def _create_separator() -> QFrame:
        """Construct a vertical separator line.

        Returns:
            QFrame: Styled vertical divider.
        """
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #2c313a; background-color: #2c313a; max-height: 28px;")
        return sep

    def setup_worker(self) -> None:
        """Initialize and launch the background quote updater worker thread."""
        self.worker = NiftyLiveWorker(tickers=["^NSEI", "^NSEBANK"], interval_seconds=15)
        self.worker.quotes_updated.connect(self._on_quotes_updated)
        self.worker.refresh_started.connect(self._on_refresh_started)
        self.worker.refresh_finished.connect(self._on_refresh_finished)
        self.worker.error_occurred.connect(self._on_refresh_error)
        self.worker.start()

    def _on_card_clicked(self, ticker: str) -> None:
        """Forward card clicked event as widget signal."""
        self.ticker_clicked.emit(ticker)

    def _on_interval_changed(self) -> None:
        """Handle interval combo selection change."""
        seconds = self.combo_interval.currentData()
        if self.worker:
            self.worker.set_interval(int(seconds))

    def _on_refresh_clicked(self) -> None:
        """Handle manual refresh button click."""
        if self.worker:
            self.worker.trigger_now()

    def _on_refresh_started(self) -> None:
        """Provide visual indication when a quote refresh commences."""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⟳ Updating…")

    def _on_refresh_finished(self) -> None:
        """Restore refresh button state after fetch cycle completes."""
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("⟳ Refresh")

    def _on_refresh_error(self, err_msg: str) -> None:
        """Handle quote fetch error without crashing UI."""
        self.lbl_last_updated.setText("Sync error (retrying)")
        self.lbl_last_updated.setToolTip(f"Last error: {err_msg}")

    def _on_quotes_updated(self, quotes: dict[str, dict[str, Any]]) -> None:
        """Update child index cards with newly fetched quote dictionaries.

        Args:
            quotes (dict[str, dict[str, Any]]): Map of ticker to quote data.
        """
        for ticker, quote in quotes.items():
            if ticker in self.cards:
                self.cards[ticker].update_quote(quote)

        now_str = datetime.now(IST_TIMEZONE).strftime("%H:%M:%S")
        self.lbl_last_updated.setText(f"Updated {now_str} IST")
        self.lbl_last_updated.setToolTip("Quotes fetched live via yfinance")

    def _update_clock_and_market_status(self) -> None:
        """Update live IST clock and market status badge."""
        now_ist = datetime.now(IST_TIMEZONE)
        self.lbl_clock.setText(now_ist.strftime("IST %H:%M:%S"))

        is_open, desc = is_market_open_ist()
        if is_open:
            self.lbl_status_badge.setText("● NSE OPEN")
            self.lbl_status_badge.setStyleSheet(
                "background-color: #1b382b; color: #98c379; font-weight: bold; "
                "font-size: 10px; padding: 3px 7px; border-radius: 4px; border: 1px solid #27ae60;"
            )
        else:
            self.lbl_status_badge.setText("● NSE CLOSED")
            self.lbl_status_badge.setStyleSheet(
                "background-color: #2d2627; color: #e5c07b; font-weight: bold; "
                "font-size: 10px; padding: 3px 7px; border-radius: 4px; border: 1px solid #665235;"
            )
        self.lbl_status_badge.setToolTip(f"NSE Equity Status: {desc}")

    def cleanup(self) -> None:
        """Gracefully stop background worker thread and timers on application close."""
        if self.clock_timer.isActive():
            self.clock_timer.stop()
        if self.worker:
            self.worker.stop()
            self.worker.wait(1500)
