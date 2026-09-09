"""Bollinger Bands volatility indicator calculation and analysis module."""

import pandas as pd


def calculate_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Calculate Bollinger Bands (Middle, Upper, Lower, Bandwidth, and %B).

    Args:
        series (pd.Series): Price series (typically close prices).
        period (int): Lookback period for simple moving average. Defaults to 20.
        num_std (float): Number of standard deviations for bands. Defaults to 2.0.

    Returns:
        pd.DataFrame: DataFrame containing 'BB_Middle', 'BB_Upper', 'BB_Lower',
            'BB_Bandwidth', and '%B'.
    """
    if series.empty or len(series) < period:
        return pd.DataFrame(
            index=series.index,
            columns=["BB_Middle", "BB_Upper", "BB_Lower", "BB_Bandwidth", "%B"],
            dtype=float,
        )

    # 1. Middle Band = N-period Simple Moving Average
    middle = series.rolling(window=period, min_periods=period).mean()

    # 2. Rolling Standard Deviation
    rolling_std = series.rolling(window=period, min_periods=period).std()

    # 3. Upper & Lower Bands
    upper = middle + (num_std * rolling_std)
    lower = middle - (num_std * rolling_std)

    # 4. Bandwidth & %B Indicators
    bandwidth = (upper - lower) / middle.replace(0, float("nan"))
    channel_range = (upper - lower).replace(0, float("nan"))
    pct_b = (series - lower) / channel_range

    return pd.DataFrame(
        {
            "BB_Middle": middle,
            "BB_Upper": upper,
            "BB_Lower": lower,
            "BB_Bandwidth": bandwidth,
            "%B": pct_b,
        },
        index=series.index,
    )


def analyze_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> dict:
    """Analyze current Bollinger Bands status, band squeeze, and relative position.

    Args:
        series (pd.Series): Price series (typically close prices).
        period (int): Lookback period for SMA. Defaults to 20.
        num_std (float): Standard deviations for bands. Defaults to 2.0.

    Returns:
        dict: Summary containing 'current_price', 'upper_band', 'middle_band',
            'lower_band', 'percent_b', 'bandwidth', and 'band_position'.
    """
    bb_df = calculate_bollinger_bands(series, period=period, num_std=num_std)
    valid_bb = bb_df.dropna()

    if valid_bb.empty:
        return {
            "current_price": None,
            "upper_band": None,
            "middle_band": None,
            "lower_band": None,
            "percent_b": None,
            "bandwidth": None,
            "band_position": "Insufficient Data",
        }

    curr_price = float(series.iloc[-1])
    upper_val = float(valid_bb["BB_Upper"].iloc[-1])
    middle_val = float(valid_bb["BB_Middle"].iloc[-1])
    lower_val = float(valid_bb["BB_Lower"].iloc[-1])
    pct_b_val = float(valid_bb["%B"].iloc[-1])
    bw_val = float(valid_bb["BB_Bandwidth"].iloc[-1])

    if curr_price >= upper_val:
        band_position = "Above Upper Band (Overbought)"
    elif curr_price <= lower_val:
        band_position = "Below Lower Band (Oversold)"
    elif curr_price >= middle_val:
        band_position = "Upper Half (Bullish Bias)"
    else:
        band_position = "Lower Half (Bearish Bias)"

    return {
        "current_price": round(curr_price, 2),
        "upper_band": round(upper_val, 2),
        "middle_band": round(middle_val, 2),
        "lower_band": round(lower_val, 2),
        "percent_b": round(pct_b_val, 3),
        "bandwidth": round(bw_val, 4),
        "band_position": band_position,
    }
