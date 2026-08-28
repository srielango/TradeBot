"""Strategies package containing base strategy definitions and implementations."""

from strategies.base_strategy import BaseStrategy
from strategies.macd_rsi_swing import MacdRsiSwing
from strategies.moving_average_stochastic import MovingAverageStochastic

STRATEGY_REGISTRY = {
    "Moving Average + Stochastic (200 MA, 8,3,3)": MovingAverageStochastic,
    "MACD RSI Swing (12, 26, 9)": MacdRsiSwing,
}

__all__ = [
    "STRATEGY_REGISTRY",
    "BaseStrategy",
    "MacdRsiSwing",
    "MovingAverageStochastic",
]
