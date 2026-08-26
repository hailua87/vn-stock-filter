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

    Returns dict with series: tenkan, kijun, senkou_a, senkou_b, chikou,
    future_senkou_a, future_senkou_b.
    All series are aligned to the dataframe's index.
    """
    tk = tenkan_sen(df, period=9)
    kj = kijun_sen(df, period=26)
    sa = senkou_span_a(tk, kj, shift=26)
    sb = senkou_span_b(df, period=52, shift=26)
    ch = chikou_span(df['Close'], shift=26)

    # MÂY TƯƠNG LAI (Kumo phía trước) = senkou A/B TRƯỚC khi dịch 26 bar.
    # Đây là thành phần dự báo đặc trưng nhất của Ichimoku, và độc lập với trạng
    # thái TK hiện tại — dùng nó để chấm điểm thay vì đếm hai lần cùng một sự
    # kiện TK cross (xem ichimoku.py).
    future_sa = (tk + kj) / 2
    future_sb = (df['High'].rolling(window=52).max()
                 + df['Low'].rolling(window=52).min()) / 2

    return {
        'tenkan': tk,
        'kijun': kj,
        'senkou_a': sa,
        'senkou_b': sb,
        'chikou': ch,
        'future_senkou_a': future_sa,
        'future_senkou_b': future_sb,
    }


# ---------- Helpers for cross detection ----------

def detect_recent_cross_up(fast: pd.Series, slow: pd.Series, lookback: int = 5) -> dict:
    """
    Phát hiện `fast` cắt lên `slow` trong `lookback` phiên gần nhất.

    HAI LỖI ĐÃ SỬA:
      1. Bản cũ quét XUÔI và `break` ở lần cắt ĐẦU TIÊN (tức lần CŨ NHẤT) trong
         cửa sổ. Khi có whipsaw (cắt lên → cắt xuống → cắt lên) trong 5 phiên,
         hệ thống báo lần cắt cũ và bỏ qua lần cắt mới. Nay quét NGƯỢC để lấy
         lần cắt gần nhất.
      2. Bản cũ không kiểm tra trạng thái hiện tại: mã cắt lên ở T-5 rồi cắt
         xuống lại ở T-1 vẫn được tính `crossed = True` và lọt vào danh sách
         Golden Cross. Nay `crossed` yêu cầu fast vẫn đang nằm trên slow.

    Returns:
        {
            'crossed': bool,        # cắt lên gần đây VÀ hiện vẫn còn hiệu lực
            'crossed_raw': bool,    # có xảy ra cắt lên trong cửa sổ (kể cả đã đảo)
            'reverted': bool,       # đã cắt lên nhưng nay fast <= slow
            'days_ago': int|None,   # 0 = hôm nay, 1 = phiên trước...
            'fast_current': float,
            'slow_current': float,
            'spread_pct': float,    # fast đang trên slow bao nhiêu %
        }
    """
    empty = {'crossed': False, 'crossed_raw': False, 'reverted': False,
             'days_ago': None, 'fast_current': None, 'slow_current': None,
             'spread_pct': 0}
    if len(fast) < lookback + 1 or len(slow) < lookback + 1:
        return empty

    # Cửa sổ (lookback+1) bar để có đủ các cặp (i-1, i)
    recent_fast = fast.iloc[-(lookback + 1):].to_numpy(dtype=float)
    recent_slow = slow.iloc[-(lookback + 1):].to_numpy(dtype=float)

    # Quét NGƯỢC: lấy lần cắt lên gần nhất.
    crossed_at = None
    for i in range(len(recent_fast) - 1, 0, -1):
        if recent_fast[i - 1] <= recent_slow[i - 1] and recent_fast[i] > recent_slow[i]:
            crossed_at = lookback - i   # đổi vị trí mảng → số phiên trước
            break

    fast_current = float(recent_fast[-1])
    slow_current = float(recent_slow[-1])
    if pd.isna(fast_current) or pd.isna(slow_current):
        return empty

    still_above = fast_current > slow_current
    spread_pct = ((fast_current - slow_current) / slow_current * 100) if slow_current > 0 else 0

    return {
        'crossed': crossed_at is not None and still_above,
        'crossed_raw': crossed_at is not None,
        'reverted': crossed_at is not None and not still_above,
        'days_ago': crossed_at,
        'fast_current': round(fast_current, 2),
        'slow_current': round(slow_current, 2),
        'spread_pct': round(spread_pct, 2),
    }
