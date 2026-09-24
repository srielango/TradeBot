"""Interactive Market Sentiment & Macro Catalysts tab component for TradeBot dashboard.

Provides a dedicated workspace for live financial RSS feed aggregation, macro event
monitoring (geopolitical tensions, budget shocks, policy shifts), sentiment scoring,
and article inspection without crowding other analytical workspaces.
"""

from typing import Optional

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from market_sentiment_analyzer import (
    DEFAULT_RSS_FEEDS,
    MarketNewsItem,
    MarketSentimentAnalyzer,
    MarketSentimentSummary,
)


class SentimentNewsWorker(QThread):
    """Background worker fetching RSS feeds and assessing market sentiment."""

    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        analyzer: MarketSentimentAnalyzer,
        feed_name: Optional[str] = None,
    ) -> None:
        """Initialize worker with analyzer instance and optional feed filter.

        Args:
            analyzer (MarketSentimentAnalyzer): Market sentiment engine instance.
            feed_name (Optional[str]): Specific RSS feed identifier or None for all.
        """
        super().__init__()
        self.analyzer = analyzer
        self.feed_name = feed_name

    def run(self) -> None:
        """Fetch news and calculate sentiment scores in background thread."""
        try:
            summary = self.analyzer.analyze_market_sentiment(
                specific_feed=self.feed_name
            )
            self.finished_signal.emit(summary)
        except (OSError, ValueError, KeyError) as err:
            self.error_signal.emit(str(err))


class MarketSentimentTab(QWidget):
    """Dedicated dashboard tab for market sentiment analysis and breaking news monitoring."""

    def __init__(self, analyzer: Optional[MarketSentimentAnalyzer] = None) -> None:
        """Initialize market sentiment tab with analyzer and interactive controls.

        Args:
            analyzer (Optional[MarketSentimentAnalyzer]): Sentiment engine instance.
        """
        super().__init__()
        self.analyzer = analyzer or MarketSentimentAnalyzer()
        self.worker: Optional[SentimentNewsWorker] = None
        self.summary: Optional[MarketSentimentSummary] = None
        self.displayed_items: list[MarketNewsItem] = []

        self.init_ui()
        self.refresh_sentiment()

    def init_ui(self) -> None:
        """Construct control bar, alert banner, news table, and inspector panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # =====================================================================
        # Section 1: Header Bar & Controls
        # =====================================================================
        control_card = QFrame()
        control_card.setStyleSheet(
            "QFrame { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 6px; padding: 6px 12px; }"
        )
        control_layout = QVBoxLayout(control_card)
        control_layout.setSpacing(8)
        control_layout.setContentsMargins(8, 6, 8, 6)

        # Row 1: Badges & Readouts
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self.sentiment_badge = QLabel("● Analyzing RSS Feeds...")
        self.sentiment_badge.setStyleSheet(
            "QLabel {"
            "  background-color: #2c313a;"
            "  color: #abb2bf;"
            "  font-weight: bold;"
            "  padding: 5px 12px;"
            "  border-radius: 4px;"
            "  border: 1px solid #3b4048;"
            "  font-size: 12px;"
            "}"
        )
        status_row.addWidget(self.sentiment_badge)

        self.lbl_news_kpi = QLabel("0 Headlines Analyzed")
        self.lbl_news_kpi.setStyleSheet("color: #9da5b4; font-size: 12px;")
        status_row.addWidget(self.lbl_news_kpi)

        self.lbl_drastic_badge = QLabel("0 Drastic Catalysts")
        self.lbl_drastic_badge.setStyleSheet(
            "QLabel {"
            "  background-color: #3b4048;"
            "  color: #abb2bf;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "  padding: 4px 10px;"
            "  border-radius: 4px;"
            "}"
        )
        status_row.addWidget(self.lbl_drastic_badge)

        status_row.addStretch()

        self.btn_refresh_news = QPushButton("⟳ Refresh News")
        self.btn_refresh_news.setStyleSheet(
            "QPushButton { background-color: #1976d2; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #1e88e5; } "
            "QPushButton:disabled { background-color: #3b4048; color: #7f8c8d; }"
        )
        self.btn_refresh_news.clicked.connect(self.refresh_sentiment)
        status_row.addWidget(self.btn_refresh_news)

        control_layout.addLayout(status_row)

        # Row 2: Filtering Controls (Feed, Impact, Search)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        # Feed selector
        filter_row.addWidget(QLabel("<b>RSS Feed:</b>"))
        self.combo_feed = QComboBox()
        self.combo_feed.addItem("All Financial Feeds", None)
        for feed_key in DEFAULT_RSS_FEEDS.keys():
            self.combo_feed.addItem(feed_key, feed_key)
        self.combo_feed.currentIndexChanged.connect(self.refresh_sentiment)
        filter_row.addWidget(self.combo_feed)

        # Impact filter
        filter_row.addWidget(QLabel("<b>Impact:</b>"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("All Headlines", "all")
        self.combo_filter.addItem("🚨 Drastic Catalysts Only", "drastic")
        self.combo_filter.addItem("High & Medium Impact", "high_med")
        self.combo_filter.currentIndexChanged.connect(self.apply_filters)
        filter_row.addWidget(self.combo_filter)

        # Search box
        filter_row.addWidget(QLabel("<b>Search:</b>"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter headlines by keyword (e.g. RBI, Oil, War)...")
        self.search_input.textChanged.connect(self.apply_filters)
        filter_row.addWidget(self.search_input, stretch=1)

        control_layout.addLayout(filter_row)
        main_layout.addWidget(control_card)

        # =====================================================================
        # Section 2: Macro Catalysts Alert Banner
        # =====================================================================
        self.alert_banner = QLabel("Checking breaking macro events (War, Budget, Major Policy)...")
        self.alert_banner.setWordWrap(True)
        self.alert_banner.setStyleSheet(
            "QLabel {"
            "  background-color: #21252b;"
            "  border: 1px solid #3b4048;"
            "  border-radius: 6px;"
            "  padding: 8px 12px;"
            "  color: #abb2bf;"
            "  font-size: 11px;"
            "}"
        )
        main_layout.addWidget(self.alert_banner)

        # =====================================================================
        # Section 3: Live News Table
        # =====================================================================
        self.news_table = QTableWidget()
        news_headers = [
            "Time (IST / Pub)",
            "Sentiment",
            "Impact",
            "Catalyst Category",
            "Headline (Click to open link in browser)",
            "Source",
        ]
        self.news_table.setColumnCount(len(news_headers))
        self.news_table.setHorizontalHeaderLabels(news_headers)
        self.news_table.setAlternatingRowColors(True)
        self.news_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.news_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.news_table.setStyleSheet(
            "QTableWidget { background-color: #1e2227; alternate-background-color: #242930; "
            "color: #abb2bf; gridline-color: #3b4048; border: 1px solid #3b4048; "
            "border-radius: 6px; font-size: 12px; } "
            "QHeaderView::section { background-color: #181a1f; color: #d7dae0; "
            "font-weight: bold; border: 1px solid #3b4048; padding: 6px; font-size: 12px; } "
            "QTableWidget::item:selected { background-color: #2c313a; color: #ffffff; }"
        )
        news_header = self.news_table.horizontalHeader()
        news_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        news_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        news_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        news_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        news_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        news_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.news_table.cellClicked.connect(self._on_news_cell_clicked)
        self.news_table.itemSelectionChanged.connect(self._on_selection_changed)
        main_layout.addWidget(self.news_table, stretch=2)

        # =====================================================================
        # Section 4: Headline Detail Inspector
        # =====================================================================
        self.detail_group = QGroupBox("Selected Headline Overview & Context")
        detail_layout = QVBoxLayout(self.detail_group)
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(6)

        self.txt_detail = QTextBrowser()
        self.txt_detail.setMaximumHeight(85)
        self.txt_detail.setOpenExternalLinks(True)
        self.txt_detail.setStyleSheet(
            "QTextBrowser { background-color: #21252b; border: 1px solid #3b4048; "
            "border-radius: 4px; color: #abb2bf; font-size: 11px; padding: 4px; }"
        )
        self.txt_detail.setText("Select an article row above to preview full details and summary.")
        detail_layout.addWidget(self.txt_detail)

        main_layout.addWidget(self.detail_group)

    def refresh_sentiment(self) -> None:
        """Fetch RSS news and calculate market sentiments in background thread."""
        if self.worker and self.worker.isRunning():
            return

        selected_feed = self.combo_feed.currentData()
        self.btn_refresh_news.setEnabled(False)
        self.btn_refresh_news.setText("Fetching News...")
        self.sentiment_badge.setText("● Fetching RSS News...")
        self.sentiment_badge.setStyleSheet(
            "QLabel { background-color: #2c313a; color: #abb2bf; "
            "font-weight: bold; padding: 5px 12px; border-radius: 4px; "
            "border: 1px solid #3b4048; font-size: 12px; }"
        )

        self.worker = SentimentNewsWorker(self.analyzer, feed_name=selected_feed)
        self.worker.finished_signal.connect(self._on_sentiment_finished)
        self.worker.error_signal.connect(self._on_sentiment_error)
        self.worker.start()

    def _on_sentiment_finished(self, summary: MarketSentimentSummary) -> None:
        """Handle completion of background sentiment worker and render summary.

        Args:
            summary (MarketSentimentSummary): Completed sentiment report.
        """
        self.summary = summary
        self.btn_refresh_news.setEnabled(True)
        self.btn_refresh_news.setText("⟳ Refresh News")

        # Color-code overall sentiment badge
        score = summary.sentiment_score
        sign = "+" if score > 0 else ""
        if "BULLISH" in summary.overall_sentiment:
            bg_col = "#1b5e20"
            txt_col = "#a5d6a7"
        elif "BEARISH" in summary.overall_sentiment:
            bg_col = "#b71c1c"
            txt_col = "#ef9a9a"
        else:
            bg_col = "#37474f"
            txt_col = "#cfd8dc"

        self.sentiment_badge.setText(
            f"● {summary.overall_sentiment} ({sign}{score:.2f})"
        )
        self.sentiment_badge.setStyleSheet(
            f"QLabel {{ background-color: {bg_col}; color: {txt_col}; "
            f"font-weight: bold; padding: 5px 12px; border-radius: 4px; "
            f"border: 1px solid {txt_col}; font-size: 12px; }}"
        )

        tot_cnt = len(summary.all_items)
        self.lbl_news_kpi.setText(
            f"{tot_cnt} Headlines ({summary.bullish_count} Bullish | "
            f"{summary.bearish_count} Bearish | {summary.neutral_count} Neutral)"
        )

        drastic_cnt = summary.drastic_events_count
        if drastic_cnt > 0:
            self.lbl_drastic_badge.setText(f"🚨 {drastic_cnt} Drastic Catalyst(s)")
            self.lbl_drastic_badge.setStyleSheet(
                "QLabel { background-color: #8c1d1d; color: #ffcdd2; font-size: 11px; "
                "font-weight: bold; padding: 4px 10px; border-radius: 4px; "
                "border: 1px solid #ef5350; }"
            )
        else:
            self.lbl_drastic_badge.setText("✓ 0 Drastic Shocks")
            self.lbl_drastic_badge.setStyleSheet(
                "QLabel { background-color: #1e392a; color: #a5d6a7; font-size: 11px; "
                "font-weight: bold; padding: 4px 10px; border-radius: 4px; "
                "border: 1px solid #388e3c; }"
            )

        # Update Drastic Catalysts Alert Banner
        if drastic_cnt > 0:
            banner_lines = [
                f"<b>🚨 HIGH-IMPACT MARKET CATALYSTS DETECTED ({drastic_cnt} Drastic Movers):</b>"
            ]
            for item in summary.high_impact_items[:3]:
                sent_color = (
                    "#98c379"
                    if item.sentiment == "BULLISH"
                    else "#e06c75"
                    if item.sentiment == "BEARISH"
                    else "#abb2bf"
                )
                banner_lines.append(
                    f"• <b>[{item.catalyst_category}]</b> "
                    f"<span style='color: {sent_color}; font-weight: bold;'>"
                    f"({item.sentiment})</span> {item.title} <i>({item.source})</i>"
                )
            self.alert_banner.setText("<br/>".join(banner_lines))
            self.alert_banner.setStyleSheet(
                "QLabel { background-color: #2b1f22; border: 1px solid #e06c75; "
                "border-radius: 6px; padding: 8px 12px; color: #e5c07b; font-size: 11px; "
                "line-height: 1.3; }"
            )
        else:
            self.alert_banner.setText(
                "<b>✓ Stable Macro Sentiment:</b> No critical war outbreaks, "
                "extreme budget shocks, or emergency policy shifts detected in RSS feeds."
            )
            self.alert_banner.setStyleSheet(
                "QLabel { background-color: #1e2621; border: 1px solid #2ecc71; "
                "border-radius: 6px; padding: 8px 12px; color: #98c379; font-size: 11px; }"
            )

        self.apply_filters()

    def _on_sentiment_error(self, err_msg: str) -> None:
        """Handle failure during sentiment news fetch.

        Args:
            err_msg (str): Error description message.
        """
        self.btn_refresh_news.setEnabled(True)
        self.btn_refresh_news.setText("⟳ Refresh News")
        self.sentiment_badge.setText("● Offline / Fallback")
        self.sentiment_badge.setStyleSheet(
            "QLabel { background-color: #3b4048; color: #abb2bf; font-weight: bold; "
            "padding: 5px 12px; border-radius: 4px; font-size: 12px; }"
        )
        self.alert_banner.setText(
            f"Notice: Live RSS refresh failed ({err_msg}). Displaying fallback catalyst data."
        )

    def apply_filters(self) -> None:
        """Re-filter news items based on chosen impact mode and search keyword."""
        if not self.summary:
            return

        filter_mode = self.combo_filter.currentData() or "all"
        query = self.search_input.text().strip().lower()
        items = self.summary.all_items

        filtered: list[MarketNewsItem] = []
        for it in items:
            if filter_mode == "drastic" and not it.is_drastic:
                continue
            if filter_mode == "high_med" and it.impact_level not in ("HIGH", "MEDIUM"):
                continue

            if query:
                t_match = query in it.title.lower()
                c_match = query in it.catalyst_category.lower()
                s_match = query in it.source.lower()
                d_match = bool(it.description and query in it.description.lower())
                if not (t_match or c_match or s_match or d_match):
                    continue

            filtered.append(it)

        self.displayed_items = filtered
        self._populate_table(filtered)

    def _populate_table(self, items: list[MarketNewsItem]) -> None:
        """Render news items into the table widget."""
        self.news_table.setRowCount(len(items))

        for row_idx, it in enumerate(items):
            # Col 0: Time
            time_item = QTableWidgetItem(it.pub_date)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.news_table.setItem(row_idx, 0, time_item)

            # Col 1: Sentiment
            sent_item = QTableWidgetItem(it.sentiment)
            sent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if it.sentiment == "BULLISH":
                sent_item.setForeground(QColor("#98c379"))
            elif it.sentiment == "BEARISH":
                sent_item.setForeground(QColor("#e06c75"))
            else:
                sent_item.setForeground(QColor("#abb2bf"))
            self.news_table.setItem(row_idx, 1, sent_item)

            # Col 2: Impact
            impact_text = f"🚨 {it.impact_level}" if it.is_drastic else it.impact_level
            impact_item = QTableWidgetItem(impact_text)
            impact_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if it.is_drastic or it.impact_level == "HIGH":
                impact_item.setForeground(QColor("#e5c07b"))
            elif it.impact_level == "MEDIUM":
                impact_item.setForeground(QColor("#61afef"))
            else:
                impact_item.setForeground(QColor("#5c6370"))
            self.news_table.setItem(row_idx, 2, impact_item)

            # Col 3: Catalyst Category
            cat_item = QTableWidgetItem(it.catalyst_category)
            cat_item.setToolTip(it.catalyst_reason)
            self.news_table.setItem(row_idx, 3, cat_item)

            # Col 4: Title / Link
            title_item = QTableWidgetItem(it.title)
            title_item.setForeground(QColor("#61afef"))
            tooltip_msg = (
                f"{it.title}\n\nCategory: {it.catalyst_category}\n"
                f"Reason: {it.catalyst_reason}"
            )
            if it.description:
                tooltip_msg += f"\n\n{it.description}"
            if it.link:
                tooltip_msg += f"\n\nClick to open: {it.link}"
                title_item.setData(Qt.ItemDataRole.UserRole, it.link)
            title_item.setToolTip(tooltip_msg)
            self.news_table.setItem(row_idx, 4, title_item)

            # Col 5: Source
            source_item = QTableWidgetItem(it.source)
            source_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            source_item.setForeground(QColor("#9da5b4"))
            self.news_table.setItem(row_idx, 5, source_item)

        if items:
            self._update_inspector(items[0])

    def _on_selection_changed(self) -> None:
        """Update headline overview when row selection changes."""
        selected_rows = self.news_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row_idx = selected_rows[0].row()
        if 0 <= row_idx < len(self.displayed_items):
            self._update_inspector(self.displayed_items[row_idx])

    def _update_inspector(self, item: MarketNewsItem) -> None:
        """Update detail box with summary and direct link for selected article."""
        color = (
            "#98c379"
            if item.sentiment == "BULLISH"
            else "#e06c75"
            if item.sentiment == "BEARISH"
            else "#abb2bf"
        )
        html = (
            f"<b>Headline:</b> {item.title}<br/>"
            f"<b>Source:</b> {item.source} &nbsp;|&nbsp; "
            f"<b>Published:</b> {item.pub_date} &nbsp;|&nbsp; "
            f"<b>Sentiment:</b> <span style='color: {color}; font-weight: bold;'>"
            f"{item.sentiment} ({item.sentiment_score:+.2f})</span> &nbsp;|&nbsp; "
            f"<b>Category:</b> {item.catalyst_category}<br/>"
        )
        if item.catalyst_reason:
            html += f"<b>Catalyst Rationale:</b> {item.catalyst_reason}<br/>"
        if item.description:
            html += f"<b>Summary:</b> {item.description}<br/>"
        if item.link:
            html += f"<b>Direct Article Link:</b> <a href='{item.link}'>{item.link}</a>"

        self.txt_detail.setHtml(html)

    def _on_news_cell_clicked(self, row: int, col: int) -> None:
        """Open article link when Headline column (col 4) is clicked."""
        if col == 4:
            item = self.news_table.item(row, 4)
            if item:
                link = item.data(Qt.ItemDataRole.UserRole)
                if link and str(link).startswith("http"):
                    QDesktopServices.openUrl(QUrl(str(link)))
