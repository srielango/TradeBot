"""Centralized data synchronization service and background worker for TradeBot."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from config import DATA_DIR
from daily_data_updater import get_latest_database_bar_date, run_full_daily_update

SYNC_SETTINGS_PATH: Path = DATA_DIR / "sync_settings.json"


class DataSyncWorker(QThread):
    """Background worker thread executing market data synchronization."""

    progress_updated = pyqtSignal(int, int, str)
    sync_finished = pyqtSignal(int, int, str)
    sync_error = pyqtSignal(str)
    sync_cancelled = pyqtSignal()

    def __init__(self) -> None:
        """Initialize worker thread and cancellation flag."""
        super().__init__()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Signal thread to abort execution at next checkpoint."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Check whether cancellation was requested.

        Returns:
            bool: True if cancellation requested, otherwise False.
        """
        return self._is_cancelled

    def run(self) -> None:
        """Run daily price bars and fundamentals update pipeline."""
        try:
            def on_progress(current: int, total: int, msg: str) -> None:
                self.progress_updated.emit(current, total, msg)

            bars, funds = run_full_daily_update(
                progress_callback=on_progress,
                is_cancelled=self.is_cancelled,
            )

            if self._is_cancelled:
                self.sync_cancelled.emit()
            else:
                summary = (
                    f"Sync complete: {bars} new price bars and {funds} fundamentals updated."
                )
                self.sync_finished.emit(bars, funds, summary)

        except (ValueError, KeyError, IndexError, OSError) as err:
            self.sync_error.emit(f"Sync error: {err}")


class DataSyncService(QObject):
    """Singleton service coordinating market data updates across TradeBot UI components."""

    _instance: "DataSyncService | None" = None

    sync_started = pyqtSignal()
    progress_updated = pyqtSignal(int, int, str)
    sync_finished = pyqtSignal(int, int, str)
    sync_error = pyqtSignal(str)
    sync_cancelled = pyqtSignal()
    settings_changed = pyqtSignal()

    def __init__(self) -> None:
        """Initialize data synchronization service and load settings."""
        super().__init__()
        self._worker: DataSyncWorker | None = None
        self._settings: dict[str, Any] = self._load_settings()

    @classmethod
    def get_instance(cls) -> "DataSyncService":
        """Access global shared instance of DataSyncService.

        Returns:
            DataSyncService: Active singleton instance.
        """
        if cls._instance is None:
            cls._instance = DataSyncService()
        return cls._instance

    # ── Persistence & Configuration ──────────────────────────────────────────

    def _load_settings(self) -> dict[str, Any]:
        """Load stored user synchronization preferences from disk.

        Returns:
            dict[str, Any]: Settings dictionary containing preferences and metadata.
        """
        default_settings: dict[str, Any] = {
            "auto_sync_on_startup": True,
            "last_sync_timestamp": None,
            "last_sync_bars": 0,
            "last_sync_funds": 0,
            "last_sync_status": "Never synced",
        }
        if SYNC_SETTINGS_PATH.exists():
            try:
                with open(SYNC_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_settings.update(data)
            except (json.JSONDecodeError, OSError) as err:
                print(f"Warning: Could not read sync settings ({err}), using defaults.")

        return default_settings

    def _save_settings(self) -> None:
        """Save active synchronization preferences and metadata to disk."""
        try:
            with open(SYNC_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
            self.settings_changed.emit()
        except OSError as err:
            print(f"Warning: Could not save sync settings: {err}")

    def get_auto_sync_on_startup(self) -> bool:
        """Check if automatic synchronization on startup is enabled.

        Returns:
            bool: True if auto-sync is enabled, False otherwise.
        """
        return bool(self._settings.get("auto_sync_on_startup", True))

    def set_auto_sync_on_startup(self, enabled: bool) -> None:
        """Enable or disable automatic synchronization upon application launch.

        Args:
            enabled (bool): Desired preference state.
        """
        if self._settings.get("auto_sync_on_startup") != enabled:
            self._settings["auto_sync_on_startup"] = enabled
            self._save_settings()

    def get_last_sync_info(self) -> dict[str, Any]:
        """Retrieve details regarding the latest completed synchronization run.

        Returns:
            dict[str, Any]: Metadata containing timestamp, bars added, and status.
        """
        return dict(self._settings)

    def get_latest_bar_date(self) -> str | None:
        """Retrieve newest bar timestamp recorded in the database.

        Returns:
            str | None: Newest bar timestamp string or None if empty.
        """
        return get_latest_database_bar_date()

    # ── Synchronization Execution ────────────────────────────────────────────

    def is_syncing(self) -> bool:
        """Check whether synchronization is currently executing.

        Returns:
            bool: True if worker thread is active, False otherwise.
        """
        return self._worker is not None and self._worker.isRunning()

    def start_sync(self) -> bool:
        """Start daily market data synchronization in a non-blocking background thread.

        Returns:
            bool: True if synchronization was initiated, False if already running.
        """
        if self.is_syncing():
            return False

        self._worker = DataSyncWorker()
        self._worker.progress_updated.connect(self._on_worker_progress)
        self._worker.sync_finished.connect(self._on_worker_finished)
        self._worker.sync_error.connect(self._on_worker_error)
        self._worker.sync_cancelled.connect(self._on_worker_cancelled)

        self.sync_started.emit()
        self._worker.start()
        return True

    def cancel_sync(self) -> None:
        """Request immediate cancellation of active background synchronization worker."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    # ── Worker Signal Handlers ───────────────────────────────────────────────

    def _on_worker_progress(self, current: int, total: int, msg: str) -> None:
        """Relay progress update from worker to UI components.

        Args:
            current (int): Index of current item being processed.
            total (int): Total count of items in current batch.
            msg (str): Informative display message.
        """
        self.progress_updated.emit(current, total, msg)

    def _on_worker_finished(self, bars: int, funds: int, summary: str) -> None:
        """Update metadata on successful sync completion and notify listeners.

        Args:
            bars (int): Number of newly inserted hourly bars.
            funds (int): Number of updated fundamental stock records.
            summary (str): User-readable completion description.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._settings["last_sync_timestamp"] = now_str
        self._settings["last_sync_bars"] = bars
        self._settings["last_sync_funds"] = funds
        self._settings["last_sync_status"] = "Success"
        self._save_settings()

        self.sync_finished.emit(bars, funds, summary)

    def _on_worker_error(self, err_msg: str) -> None:
        """Handle worker failure and propagate error to listeners.

        Args:
            err_msg (str): Error description message.
        """
        self._settings["last_sync_status"] = f"Failed: {err_msg}"
        self._save_settings()
        self.sync_error.emit(err_msg)

    def _on_worker_cancelled(self) -> None:
        """Handle worker cancellation and propagate state change."""
        self._settings["last_sync_status"] = "Cancelled"
        self._save_settings()
        self.sync_cancelled.emit()
