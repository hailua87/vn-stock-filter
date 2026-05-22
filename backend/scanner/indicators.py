"""
Technical indicators used by the pre-breakout scanner.
All functions accept pandas Series/DataFrame and return Series.
"""
import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — volatility measure."""
    h_l = df['High'] - df['Low']
    h_c = (df['High'] - df['Close'].shift()).abs()
    l_c = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing approximated by SMA)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — cumulative money flow."""
    direction = np.where(close > close.shift(), 1,
                np.where(close < close.shift(), -1, 0))
    return (direction * volume).cumsum()


def bollinger_width(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    """Bollinger Band width normalised by MA — squeeze detector."""
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return (2 * k * sd) / ma


def relative_strength(stock_close: pd.Series, index_close: pd.Series,
                      period: int = 20) -> pd.Series:
    """Relative strength vs benchmark over `period` days."""
    stock_ret = stock_close.pct_change(period)
    index_ret = index_close.pct_change(period)
    return stock_ret - index_ret


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price (per-day, intraday version would differ)."""
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    return (typical * df['Volume']).cumsum() / df['Volume'].cumsum()


def keltner_channel(df: pd.DataFrame, period: int = 20, mult: float = 1.5):
    """Returns (upper, middle, lower) Keltner channel for squeeze comparison."""
    ema = df['Close'].ewm(span=period).mean()
    a = atr(df, period)
    return ema + mult * a, ema, ema - mult * a
