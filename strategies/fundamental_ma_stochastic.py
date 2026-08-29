"""Fundamental Moving Average Stochastic alias pointing to unified MovingAverageStochastic."""

from strategies.moving_average_stochastic import MovingAverageStochastic

# Backward compatibility alias
FundamentalMovingAverageStochastic = MovingAverageStochastic

__all__ = ["FundamentalMovingAverageStochastic", "MovingAverageStochastic"]
