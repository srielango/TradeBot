"""Config package for TradeBot application."""

from config.indices import TARGET_INDICES
from config.settings import (
    BASE_DIR,
    DATA_DIR,
    DB_PATH,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_MAX_POSITIONS,
    DEFAULT_RISK_PER_TRADE,
    NIFTY200_CSV_PATH,
    RESOURCES_DIR,
)

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "DB_PATH",
    "DEFAULT_INITIAL_CAPITAL",
    "DEFAULT_MAX_POSITIONS",
    "DEFAULT_RISK_PER_TRADE",
    "NIFTY200_CSV_PATH",
    "RESOURCES_DIR",
    "TARGET_INDICES",
]
