"""Strategies package containing base strategy definitions and implementations."""

from strategies.adx_ema_swing import AdxEmaSwingStrategy
from strategies.base_strategy import BaseStrategy
from strategies.bollinger_stoch_rsi import BollingerStochRsi
from strategies.bullish_kicker import BullishKicker
from strategies.bullish_outside_bar import BullishOutsideBar
from strategies.dual_moving_average_adx import DualMovingAverageAdx
from strategies.moving_average_stochastic import MovingAverageStochastic
from strategies.nifty_dual_momentum_breakout import NiftyDualMomentumBreakout
from strategies.rsi_bull_trend_pullback import RsiBullTrendPullback

STRATEGY_REGISTRY = {
    "Moving Average + Stochastic (200 MA, 8,3,3, 10% Target)": MovingAverageStochastic,
    "Bullish Kicker Pattern (Daily, 10% Target)": BullishKicker,
    "Bullish Outside Bar (Daily, 20% Target, 2-3 Weeks)": BullishOutsideBar,
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
    "Nifty Dual Momentum Breakout (Hourly, 200 EMA, 20D High, 1:2 RRR)": (
        NiftyDualMomentumBreakout
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
    "MovingAverageStochastic",
    "NiftyDualMomentumBreakout",
    "RsiBullTrendPullback",
]
