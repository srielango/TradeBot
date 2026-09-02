"""Relative Strength Index (RSI) indicator calculation and analysis module."""

import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate the Relative Strength Index (RSI) using Wilder's exponential smoothing.

    Args:
        series (pd.Series): Price series (typically close prices).
        period (int): Lookback period for RSI calculation. Defaults to 14.

    Returns:
        pd.Series: Calculated RSI values ranging from 0.0 to 100.0.
    """
    if series.empty or len(series) < period:
        return pd.Series(index=series.index, dtype=float)

    # Compute daily price difference
    delta = series.diff()

    # Isolate upward and downward price movements
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's Exponential Moving Average smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Relative Strength (RS) ratio calculation
    # When avg_loss is 0, RS is infinite (RSI = 100)
    rs = avg_gain / avg_loss

    # Compute RSI bounded between 0 and 100
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Clean edge cases where avg_loss is 0
    rsi = rsi.where(avg_loss != 0, 100.0)
    # When both avg_gain and avg_loss are 0 (flat price), RSI is neutral (50.0)
    rsi = rsi.where((avg_gain != 0) | (avg_loss != 0), 50.0)

    return rsi


def analyze_rsi(
    df: pd.DataFrame,
    period: int = 14,
    overbought: int = 70,
    oversold: int = 30,
    price_col: str = "close",
) -> dict:
    """Analyze current RSI momentum and condition status for a given OHLCV dataset.

    Args:
        df (pd.DataFrame): OHLCV DataFrame containing price data.
        period (int): RSI calculation lookback period. Defaults to 14.
        overbought (int): Overbought threshold level. Defaults to 70.
        oversold (int): Oversold threshold level. Defaults to 30.
        price_col (str): Column name representing close prices. Defaults to "close".

    Returns:
        dict: Summary dictionary containing 'current_rsi', 'status', 'period',
              'overbought', and 'oversold'.
    """
    if df.empty or price_col not in df.columns:
        return {
            "current_rsi": None,
            "status": "No Data",
            "period": period,
            "overbought": overbought,
            "oversold": oversold,
        }

    rsi_series = calculate_rsi(df[price_col], period=period)
    valid_rsi = rsi_series.dropna()

    if valid_rsi.empty:
        return {
            "current_rsi": None,
            "status": "Insufficient Data",
            "period": period,
            "overbought": overbought,
            "oversold": oversold,
        }

    latest_rsi = float(valid_rsi.iloc[-1])

    if latest_rsi >= overbought:
        status = "Overbought"
    elif latest_rsi <= oversold:
        status = "Oversold"
    else:
        status = "Neutral"

    return {
        "current_rsi": round(latest_rsi, 2),
        "status": status,
        "period": period,
        "overbought": overbought,
        "oversold": oversold,
    }
