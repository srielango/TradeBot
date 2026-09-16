"""Visual Market Data Synchronization panel component for TradeBot UI."""

from datetime import datetime, timezone

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_sync_service import DataSyncService


class DataSyncWidget(QGroupBox):
    """Sidebar widget presenting controls and live progress for daily market data updates."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize sync widget, layout controls, and connect service signals.

        Args:
            parent (QWidget | None): Optional parent widget container.
        """
        super().__init__("Market Data Sync", parent)
        self.service = DataSyncService.get_instance()
        self.init_ui()
        self.connect_signals()
        self.refresh_display()

    def init_ui(self) -> None:
        """Construct the visual progress bar, control buttons, and status labels."""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header status row with visual status dot
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #4caf50; font-size: 14px;")
        status_row.addWidget(self.status_dot)

        self.header_status = QLabel("Data ready")
        self.header_status.setStyleSheet("font-weight: bold; font-size: 11px; color: #abb2bf;")
        status_row.addWidget(self.header_status)
        status_row.addStretch()
        layout.addLayout(status_row)

        # Action Button (Sync / Cancel)
        self.sync_button = QPushButton("⟳ Sync Market Data")
        self.sync_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #27ae60;"
            "  color: white;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  border-radius: 4px;"
            "  border: none;"
            "}"
            "QPushButton:hover {"
            "  background-color: #2ecc71;"
            "}"
            "QPushButton:disabled {"
            "  background-color: #3b4048;"
            "  color: #7f8c8d;"
            "}"
        )
        self.sync_button.clicked.connect(self._on_sync_button_clicked)
        layout.addWidget(self.sync_button)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            "  height: 16px;"
            "  border: 1px solid #3c4048;"
            "  border-radius: 4px;"
            "  background-color: #1e2227;"
            "  color: #abb2bf;"
            "  font-size: 10px;"
            "  font-weight: bold;"
            "}"
            "QProgressBar::chunk {"
            "  background: qlineargradient("
            "    x1:0, y1:0, x2:1, y2:0,"
            "    stop:0 #1b5e20, stop:1 #4caf50"
            "  );"
            "  border-radius: 3px;"
            "}"
        )
        layout.addWidget(self.progress_bar)

        # Detailed Status & Last Sync Label
        self.detail_label = QLabel("Checking database status...")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #8a929e; font-size: 10px; line-height: 1.2;")
        layout.addWidget(self.detail_label)

        # Auto-sync on startup checkbox
        self.auto_sync_check = QCheckBox("Auto-sync on startup")
        self.auto_sync_check.setChecked(self.service.get_auto_sync_on_startup())
        self.auto_sync_check.setStyleSheet("color: #abb2bf; font-size: 10px;")
        self.auto_sync_check.toggled.connect(self._on_auto_sync_toggled)
        layout.addWidget(self.auto_sync_check)

    def connect_signals(self) -> None:
        """Connect DataSyncService signals to local UI update handlers."""
        self.service.sync_started.connect(self._on_sync_started)
        self.service.progress_updated.connect(self._on_progress_updated)
        self.service.sync_finished.connect(self._on_sync_finished)
        self.service.sync_error.connect(self._on_sync_error)
        self.service.sync_cancelled.connect(self._on_sync_cancelled)

    def refresh_display(self) -> None:
        """Update widget state and labels from stored metadata and latest DB records."""
        if self.service.is_syncing():
            self._set_syncing_state()
            return

        info = self.service.get_last_sync_info()
        latest_bar = self.service.get_latest_bar_date()

        last_sync = info.get("last_sync_timestamp")
        last_bars = info.get("last_sync_bars", 0)

        if last_sync:
            # Format concise local time description
            sync_text = f"Last synced: {last_sync[:16]}\n"
            if latest_bar:
                sync_text += f"Latest bar: {latest_bar[:16]}"
            self.detail_label.setText(sync_text)
            self.header_status.setText("Data up to date")
            self.status_dot.setStyleSheet("color: #4caf50; font-size: 14px;")
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat(f"100% (+{last_bars} bars)")
        elif latest_bar:
            self.detail_label.setText(f"Latest bar: {latest_bar[:16]}\nClick sync to refresh.")
            self.header_status.setText("Ready to sync")
            self.status_dot.setStyleSheet("color: #e5c07b; font-size: 14px;")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")
        else:
            self.detail_label.setText("No data recorded.\nClick sync to download.")
            self.header_status.setText("Needs sync")
            self.status_dot.setStyleSheet("color: #e06c75; font-size: 14px;")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")

        self._set_idle_state()

    # ── State Presentation Helpers ───────────────────────────────────────────

    def _set_syncing_state(self) -> None:
        """Style button and indicators for active background synchronization."""
        self.sync_button.setText("⏹ Stop Sync")
        self.sync_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #d9534f;"
            "  color: white;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  border-radius: 4px;"
            "  border: none;"
            "}"
            "QPushButton:hover {"
            "  background-color: #c9302c;"
            "}"
        )
        self.status_dot.setStyleSheet("color: #e5c07b; font-size: 14px;")
        self.header_status.setText("Syncing market data...")

    def _set_idle_state(self) -> None:
        """Style button for ready/idle state."""
        self.sync_button.setText("⟳ Sync Market Data")
        self.sync_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #27ae60;"
            "  color: white;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  border-radius: 4px;"
            "  border: none;"
            "}"
            "QPushButton:hover {"
            "  background-color: #2ecc71;"
            "}"
        )

    # ── Event & Signal Handlers ──────────────────────────────────────────────

    def _on_sync_button_clicked(self) -> None:
        """Handle button click to start or stop synchronization."""
        if self.service.is_syncing():
            self.sync_button.setEnabled(False)
            self.detail_label.setText("Stopping sync at next security...")
            self.service.cancel_sync()
        else:
            self.service.start_sync()

    def _on_auto_sync_toggled(self, checked: bool) -> None:
        """Persist preference when auto-sync checkbox is toggled."""
        self.service.set_auto_sync_on_startup(checked)

    def _on_sync_started(self) -> None:
        """Update visual state when synchronization starts."""
        self.sync_button.setEnabled(True)
        self._set_syncing_state()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")
        self.detail_label.setText("Starting synchronization...")

    def _on_progress_updated(self, current: int, total: int, msg: str) -> None:
        """Update progress bar percentage and detailed progress message.

        Args:
            current (int): Progress index.
            total (int): Total expected operations.
            msg (str): Progress message.
        """
        pct = max(0, min(100, int((current / max(1, total)) * 100)))
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{pct}% ({current}/{total})")
        self.detail_label.setText(msg)

    def _on_sync_finished(self, bars: int, funds: int, summary: str) -> None:
        """Display success state and update timestamp upon completion.

        Args:
            bars (int): Number of newly inserted bars.
            funds (int): Number of updated fundamental records.
            summary (str): Completed sync summary message.
        """
        self.sync_button.setEnabled(True)
        self._set_idle_state()
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat(f"100% (+{bars} bars)")

        now_time = datetime.now(timezone.utc).strftime("%H:%M UTC")
        self.status_dot.setStyleSheet("color: #4caf50; font-size: 14px;")
        self.header_status.setText("Sync complete")
        self.detail_label.setText(
            f"Synced at {now_time}\nAdded {bars} bars, updated {funds} fundamentals."
        )

    def _on_sync_error(self, err_msg: str) -> None:
        """Display error alert on synchronization failure.

        Args:
            err_msg (str): Error description message.
        """
        self.sync_button.setEnabled(True)
        self._set_idle_state()
        self.status_dot.setStyleSheet("color: #e06c75; font-size: 14px;")
        self.header_status.setText("Sync error")
        self.detail_label.setText(f"Error: {err_msg}")

    def _on_sync_cancelled(self) -> None:
        """Display cancellation confirmation to user."""
        self.sync_button.setEnabled(True)
        self._set_idle_state()
        self.status_dot.setStyleSheet("color: #e5c07b; font-size: 14px;")
        self.header_status.setText("Sync stopped")
        self.detail_label.setText("Synchronization cancelled by user.")
