"""Average Directional Index (ADX) and Directional Movement System module."""

import numpy as np
import pandas as pd


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate the Average Directional Index (ADX), +DI, -DI, and ATR.

    Uses Wilder's Exponential Smoothing technique for True Range and Directional Movement.

    Args:
        df (pd.DataFrame): OHLCV DataFrame containing 'high', 'low', and 'close' columns.
        period (int): Lookback smoothing period. Defaults to 14.

    Returns:
        pd.DataFrame: DataFrame containing 'ADX', '+DI', '-DI', 'DX', and 'ATR'.
    """
    required_cols = {'high', 'low', 'close'}
    if df.empty or not required_cols.issubset(df.columns) or len(df) < period:
        return pd.DataFrame(
            index=df.index,
            columns=['ADX', '+DI', '-DI', 'DX', 'ATR'],
            dtype=float,
        )

    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)

    # 1. Calculate True Range (TR)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # 2. Calculate Directional Movements (+DM, -DM)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    pos_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    neg_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    # 3. Wilder's Exponential Smoothing (alpha = 1 / period)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    smooth_pos_dm = pos_dm.ewm(
        alpha=1.0 / period, min_periods=period, adjust=False,
    ).mean()
    smooth_neg_dm = neg_dm.ewm(
        alpha=1.0 / period, min_periods=period, adjust=False,
    ).mean()

    # 4. Calculate Directional Indicators (+DI, -DI)
    # Avoid division by zero when ATR is zero
    pos_di = 100.0 * (smooth_pos_dm / atr.replace(0, np.nan))
    neg_di = 100.0 * (smooth_neg_dm / atr.replace(0, np.nan))
    pos_di = pos_di.fillna(0.0)
    neg_di = neg_di.fillna(0.0)

    # 5. Calculate Directional Index (DX)
    di_diff = (pos_di - neg_di).abs()
    di_sum = pos_di + neg_di
    dx = 100.0 * (di_diff / di_sum.replace(0, np.nan))
    dx = dx.fillna(0.0)

    # 6. Calculate Average Directional Index (ADX)
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    return pd.DataFrame(
        {
            'ADX': adx,
            '+DI': pos_di,
            '-DI': neg_di,
            'DX': dx,
            'ATR': atr,
        },
        index=df.index,
    )


def analyze_adx(
    df: pd.DataFrame,
    period: int = 14,
    threshold: int = 25,
) -> dict:
    """Analyze current trend strength and directional bias from ADX, +DI, and -DI.

    Args:
        df (pd.DataFrame): OHLCV DataFrame containing 'high', 'low', 'close'.
        period (int): Lookback smoothing period. Defaults to 14.
        threshold (int): Trend strength threshold. Defaults to 25.

    Returns:
        dict: Summary containing 'current_adx', 'current_pos_di', 'current_neg_di',
              'trend_strength', 'directional_bias', 'period', and 'threshold'.
    """
    adx_df = calculate_adx(df, period=period)
    valid_adx = adx_df['ADX'].dropna()

    if valid_adx.empty:
        return {
            'current_adx': None,
            'current_pos_di': None,
            'current_neg_di': None,
            'trend_strength': 'Insufficient Data',
            'directional_bias': 'Neutral',
            'period': period,
            'threshold': threshold,
        }

    latest_adx = float(valid_adx.iloc[-1])
    latest_pos_di = float(adx_df['+DI'].iloc[-1])
    latest_neg_di = float(adx_df['-DI'].iloc[-1])

    # Classify trend strength based on ADX level
    if latest_adx >= 50:
        trend_strength = "Very Strong Trend"
    elif latest_adx >= threshold:
        trend_strength = "Strong Trend"
    elif latest_adx >= 20:
        trend_strength = "Moderate Trend"
    else:
        trend_strength = "Weak / Ranging"

    # Classify directional bias based on +DI vs -DI
    if latest_pos_di > latest_neg_di:
        directional_bias = "Bullish (+DI > -DI)"
    elif latest_neg_di > latest_pos_di:
        directional_bias = "Bearish (-DI > +DI)"
    else:
        directional_bias = "Neutral"

    return {
        'current_adx': round(latest_adx, 2),
        'current_pos_di': round(latest_pos_di, 2),
        'current_neg_di': round(latest_neg_di, 2),
        'trend_strength': trend_strength,
        'directional_bias': directional_bias,
        'period': period,
        'threshold': threshold,
    }
