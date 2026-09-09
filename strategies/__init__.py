"""Strategies package containing base strategy definitions and implementations."""

from strategies.adx_ema_swing import AdxEmaSwingStrategy
from strategies.base_strategy import BaseStrategy
from strategies.bullish_kicker import BullishKicker
from strategies.bullish_outside_bar import BullishOutsideBar
from strategies.macd_rsi_swing import MacdRsiSwing
from strategies.moving_average_stochastic import MovingAverageStochastic

STRATEGY_REGISTRY = {
    "Moving Average + Stochastic (200 MA, 8,3,3, 15% Target)": MovingAverageStochastic,
    "MACD RSI Swing (12, 26, 9)": MacdRsiSwing,
    "Bullish Kicker Pattern (Daily, 9% Target)": BullishKicker,
    "Bullish Outside Bar (Weekly, 10% Target)": BullishOutsideBar,
    "Linda Raschke ADX + 20 EMA Swing (The Holy Grail)": AdxEmaSwingStrategy,
}

__all__ = [
    "STRATEGY_REGISTRY",
    "AdxEmaSwingStrategy",
    "BaseStrategy",
    "BullishKicker",
    "BullishOutsideBar",
    "MacdRsiSwing",
    "MovingAverageStochastic",
]
