"""Centralized configuration and environment settings for TradeBot."""

from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESOURCES_DIR = BASE_DIR / "resources"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration
DB_PATH = DATA_DIR / "tradebot.db"

# Data assets
NIFTY200_CSV_PATH = RESOURCES_DIR / "ind_nifty200list.csv"

# Portfolio & Risk Management Defaults
DEFAULT_INITIAL_CAPITAL = 1_000_000.0  # 10 Lakhs INR
DEFAULT_RISK_PER_TRADE = 0.01          # 1% risk per trade
DEFAULT_MAX_POSITIONS = 10             # Max simultaneous open positions
