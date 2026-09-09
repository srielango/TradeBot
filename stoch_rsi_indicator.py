"""Stochastic Relative Strength Index (StochRSI) calculation and analysis module."""

import pandas as pd

from rsi_indicator import calculate_rsi


def calculate_stoch_rsi(
    series: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> pd.DataFrame:
    """Calculate the Stochastic RSI oscillator (%K and %D).

    Applies the Stochastic Oscillator formula to RSI values rather than raw prices,
    producing an indicator oscillating between 0.0 and 100.0 that identifies
    extreme momentum exhaustion much earlier than standard RSI.

    Args:
        series (pd.Series): Price series (typically close prices).
        rsi_period (int): Lookback smoothing window for RSI. Defaults to 14.
        stoch_period (int): Lookback window for min/max RSI. Defaults to 14.
        k_period (int): Smoothing factor for %K line. Defaults to 3.
        d_period (int): Smoothing factor for %D signal line. Defaults to 3.

    Returns:
        pd.DataFrame: DataFrame containing 'RSI', 'StochRSI_Raw', 'StochRSI_K',
            and 'StochRSI_D'.
    """
    min_required = rsi_period + stoch_period + k_period
    if series.empty or len(series) < min_required:
        return pd.DataFrame(
            index=series.index,
            columns=["RSI", "StochRSI_Raw", "StochRSI_K", "StochRSI_D"],
            dtype=float,
        )

    # 1. Calculate base RSI series
    rsi = calculate_rsi(series, period=rsi_period)

    # 2. Find min and max RSI over Stochastic lookback window
    min_rsi = rsi.rolling(window=stoch_period, min_periods=stoch_period).min()
    max_rsi = rsi.rolling(window=stoch_period, min_periods=stoch_period).max()

    # 3. Compute raw StochRSI bounded between 0 and 100
    rsi_range = (max_rsi - min_rsi).replace(0, float("nan"))
    raw_stoch_rsi = 100.0 * (rsi - min_rsi) / rsi_range
    # When min_rsi == max_rsi (flat RSI), neutral is 50.0
    raw_stoch_rsi = raw_stoch_rsi.fillna(50.0)

    # 4. Smooth %K and %D moving averages
    stoch_k = raw_stoch_rsi.rolling(window=k_period, min_periods=k_period).mean()
    stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean()

    return pd.DataFrame(
        {
            "RSI": rsi,
            "StochRSI_Raw": raw_stoch_rsi,
            "StochRSI_K": stoch_k,
            "StochRSI_D": stoch_d,
        },
        index=series.index,
    )


def analyze_stoch_rsi(
    series: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
    overbought: float = 80.0,
    oversold: float = 20.0,
) -> dict:
    """Analyze current Stochastic RSI momentum and crossover status.

    Args:
        series (pd.Series): Price series (typically close prices).
        rsi_period (int): Lookback smoothing window for RSI. Defaults to 14.
        stoch_period (int): Lookback window for StochRSI. Defaults to 14.
        k_period (int): %K smoothing window. Defaults to 3.
        d_period (int): %D smoothing window. Defaults to 3.
        overbought (float): Overbought boundary level. Defaults to 80.0.
        oversold (float): Oversold boundary level. Defaults to 20.0.

    Returns:
        dict: Summary containing 'current_k', 'current_d', 'status', and 'crossover'.
    """
    df_stoch = calculate_stoch_rsi(
        series,
        rsi_period=rsi_period,
        stoch_period=stoch_period,
        k_period=k_period,
        d_period=d_period,
    )
    valid_k = df_stoch["StochRSI_K"].dropna()
    valid_d = df_stoch["StochRSI_D"].dropna()

    if valid_k.empty or valid_d.empty or len(valid_k) < 2:
        return {
            "current_k": None,
            "current_d": None,
            "status": "Insufficient Data",
            "crossover": "None",
        }

    k_curr = float(valid_k.iloc[-1])
    d_curr = float(valid_d.iloc[-1])
    k_prev = float(valid_k.iloc[-2])
    d_prev = float(valid_d.iloc[-2])

    if k_curr >= overbought:
        status = "Overbought"
    elif k_curr <= oversold:
        status = "Oversold"
    else:
        status = "Neutral"

    if k_prev <= d_prev and k_curr > d_curr:
        crossover = "Bullish Crossover (%K > %D)"
    elif k_prev >= d_prev and k_curr < d_curr:
        crossover = "Bearish Crossover (%K < %D)"
    else:
        crossover = "No Crossover"

    return {
        "current_k": round(k_curr, 2),
        "current_d": round(d_curr, 2),
        "status": status,
        "crossover": crossover,
    }
