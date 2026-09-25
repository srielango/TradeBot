from datetime import datetime, timedelta, timezone
from pathlib import Path

# Indian Standard Time (IST) offset: UTC + 5:30
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def is_market_open_ist() -> tuple[bool, str]:
    """Determine whether the Indian equity market (NSE) is currently open.

    Regular trading hours on NSE are Monday to Friday from 9:15 AM to 3:30 PM IST.

    Returns:
        tuple[bool, str]: (is_open, status_description).
    """
    now_ist = datetime.now(IST_TIMEZONE)
    # Weekday check (0 = Monday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday)
    if now_ist.weekday() >= 5:
        return False, "Market Closed (Weekend)"

    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    if market_open <= now_ist <= market_close:
        return True, "Market Open"
    if now_ist < market_open:
        return False, "Pre-Market"
    return False, "Market Closed"


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
NIFTY50_CSV_PATH = RESOURCES_DIR / "ind_nifty50list.csv"
NIFTY200_CSV_PATH = RESOURCES_DIR / "ind_nifty200list.csv"

# Portfolio & Risk Management Defaults
DEFAULT_INITIAL_CAPITAL = 1_000_000.0  # 10 Lakhs INR
DEFAULT_RISK_PER_TRADE = 0.01          # 1% risk per trade
DEFAULT_MAX_POSITIONS = 10             # Max simultaneous open positions
