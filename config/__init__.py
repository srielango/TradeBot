"""Config package for TradeBot application."""

from config.indices import TARGET_INDICES
from config.settings import (
    BASE_DIR,
    DATA_DIR,
    DB_PATH,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_MAX_POSITIONS,
    DEFAULT_RISK_PER_TRADE,
    IST_TIMEZONE,
    NIFTY50_CSV_PATH,
    NIFTY200_CSV_PATH,
    RESOURCES_DIR,
    is_market_open_ist,
)

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "DB_PATH",
    "DEFAULT_INITIAL_CAPITAL",
    "DEFAULT_MAX_POSITIONS",
    "DEFAULT_RISK_PER_TRADE",
    "IST_TIMEZONE",
    "NIFTY50_CSV_PATH",
    "NIFTY200_CSV_PATH",
    "RESOURCES_DIR",
    "TARGET_INDICES",
    "is_market_open_ist",
]
