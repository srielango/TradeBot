"""Strategies package containing base strategy definitions and implementations."""

from strategies.adx_ema_swing import AdxEmaSwingStrategy
from strategies.base_strategy import BaseStrategy
from strategies.bollinger_stoch_rsi import BollingerStochRsi
from strategies.bullish_kicker import BullishKicker
from strategies.bullish_outside_bar import BullishOutsideBar
from strategies.dual_moving_average_adx import DualMovingAverageAdx
from strategies.macd_rsi_swing import MacdRsiSwing
from strategies.moving_average_stochastic import MovingAverageStochastic
from strategies.rsi_bull_trend_pullback import RsiBullTrendPullback

STRATEGY_REGISTRY = {
    "Moving Average + Stochastic (200 MA, 8,3,3, 15% Target)": MovingAverageStochastic,
    "MACD RSI Swing (12, 26, 9)": MacdRsiSwing,
    "Bullish Kicker Pattern (Daily, 9% Target)": BullishKicker,
    "Bullish Outside Bar (Weekly, 10% Target)": BullishOutsideBar,
    "Linda Raschke ADX + 20 EMA Swing (The Holy Grail)": AdxEmaSwingStrategy,
    "Dual Moving Average & Volatility Filter (Daily, 20/50 EMA, ADX > 20)": (
        DualMovingAverageAdx
    ),
    "RSI Pullback in Bull Trend (Daily, 200 SMA, RSI 40-70, 15d Max)": (
        RsiBullTrendPullback
    ),
    "Mean Reversion Bollinger Bands + Stoch RSI (Daily, 20/2 BB, 14 Stoch RSI)": (
        BollingerStochRsi
    ),
}

__all__ = [
    "STRATEGY_REGISTRY",
    "AdxEmaSwingStrategy",
    "BaseStrategy",
    "BollingerStochRsi",
    "BullishKicker",
    "BullishOutsideBar",
    "DualMovingAverageAdx",
    "MacdRsiSwing",
    "MovingAverageStochastic",
    "RsiBullTrendPullback",
]
