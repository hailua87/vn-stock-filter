"""
Additional technical indicators for Golden Cross and Ichimoku strategies.

Re-exports basic indicators from main indicators.py and adds:
- MA50, MA200 (for Golden Cross)
- Ichimoku 5 components: Tenkan, Kijun, Senkou A, Senkou B, Chikou
"""
from __future__ import annotations
import pandas as pd
import numpy as np


# ---------- Moving Averages (for Golden Cross) ----------
def ma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


# ---------- Ichimoku Components ----------

def tenkan_sen(df: pd.DataFrame, period: int = 9) -> pd.Series:
    """
    Tenkan-sen (Conversion line) = (Highest High + Lowest Low) / 2 over `period` bars.
    Default period: 9.
    """
    high_9 = df['High'].rolling(window=period).max()
    low_9 = df['Low'].rolling(window=period).min()
    return (high_9 + low_9) / 2


def kijun_sen(df: pd.DataFrame, period: int = 26) -> pd.Series:
    """
    Kijun-sen (Base line) = (Highest High + Lowest Low) / 2 over `period` bars.
    Default period: 26.
    """
    high_26 = df['High'].rolling(window=period).max()
    low_26 = df['Low'].rolling(window=period).min()
    return (high_26 + low_26) / 2


def senkou_span_a(tenkan: pd.Series, kijun: pd.Series, shift: int = 26) -> pd.Series:
    """
    Senkou Span A (Leading Span A) = (Tenkan + Kijun) / 2, shifted forward by 26.
    This forms the top/bottom of the Kumo (cloud).
    """
    return ((tenkan + kijun) / 2).shift(shift)


def senkou_span_b(df: pd.DataFrame, period: int = 52, shift: int = 26) -> pd.Series:
    """
    Senkou Span B (Leading Span B) = (Highest High + Lowest Low) / 2 over 52 bars,
    shifted forward by 26. Forms the other edge of the cloud.
    """
    high_52 = df['High'].rolling(window=period).max()
    low_52 = df['Low'].rolling(window=period).min()
    return ((high_52 + low_52) / 2).shift(shift)


def chikou_span(close: pd.Series, shift: int = 26) -> pd.Series:
    """
    Chikou Span (Lagging Span) = Close, shifted BACKWARD by 26.
    Used to confirm momentum: compare to past price action.
    """
    return close.shift(-shift)


def compute_ichimoku(df: pd.DataFrame) -> dict:
    """
    Compute all Ichimoku components for a price dataframe.

    Returns dict with series: tenkan, kijun, senkou_a, senkou_b, chikou
    All series are aligned to the dataframe's index.
    """
    tk = tenkan_sen(df, period=9)
    kj = kijun_sen(df, period=26)
    sa = senkou_span_a(tk, kj, shift=26)
    sb = senkou_span_b(df, period=52, shift=26)
    ch = chikou_span(df['Close'], shift=26)

    return {
        'tenkan': tk,
        'kijun': kj,
        'senkou_a': sa,
        'senkou_b': sb,
        'chikou': ch,
    }


# ---------- Helpers for cross detection ----------

def detect_recent_cross_up(fast: pd.Series, slow: pd.Series, lookback: int = 5) -> dict:
    """
    Detect if `fast` crossed above `slow` within the last `lookback` bars.

    Returns:
        {
            'crossed': bool,
            'days_ago': int or None,  # 0 = today, 1 = yesterday, ...
            'fast_current': float,
            'slow_current': float,
            'spread_pct': float,       # how far fast is above slow now
        }
    """
    if len(fast) < lookback + 1 or len(slow) < lookback + 1:
        return {'crossed': False, 'days_ago': None,
                'fast_current': None, 'slow_current': None, 'spread_pct': 0}

    # Look at last (lookback+1) bars; we need pairs (i-1, i)
    recent_fast = fast.iloc[-(lookback + 1):].values
    recent_slow = slow.iloc[-(lookback + 1):].values

    crossed_at = None
    for i in range(1, len(recent_fast)):
        if recent_fast[i - 1] <= recent_slow[i - 1] and recent_fast[i] > recent_slow[i]:
            # Cross happened at position i (counting from -(lookback+1))
            crossed_at = lookback - i  # days_ago from current
            break

    fast_current = float(recent_fast[-1])
    slow_current = float(recent_slow[-1])
    spread_pct = ((fast_current - slow_current) / slow_current * 100) if slow_current > 0 else 0

    return {
        'crossed': crossed_at is not None,
        'days_ago': crossed_at,
        'fast_current': round(fast_current, 2),
        'slow_current': round(slow_current, 2),
        'spread_pct': round(spread_pct, 2),
    }
