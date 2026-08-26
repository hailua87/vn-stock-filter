"""
Technical indicators used by the pre-breakout scanner.
All functions accept pandas Series/DataFrame and return Series.
"""
import numpy as np
import pandas as pd


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """
    Làm mượt kiểu Wilder (RMA): alpha = 1/period, seed bằng SMA của `period` giá
    trị đầu tiên. Đây là cách TradingView / Amibroker / MetaStock tính RSI và ATR.

    Lưu ý: `ewm(alpha=1/period)` thuần tuý sẽ cho seed khác (giá trị đầu tiên),
    lệch vài điểm ở đoạn đầu chuỗi; dùng adjust=False sau khi seed bằng SMA cho
    kết quả khớp với bảng điện.
    """
    series = series.astype(float)
    return series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range = max(H-L, |H-C_prev|, |L-C_prev|)."""
    h_l = df['High'] - df['Low']
    h_c = (df['High'] - df['Close'].shift()).abs()
    l_c = (df['Low'] - df['Close'].shift()).abs()
    return pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range theo Wilder (RMA), khớp với TradingView/Amibroker.

    FIX: bản cũ dùng SMA của TR nên ATR% lệch so với bảng điện của người dùng —
    trong khi tiêu chí C1 lại so ATR hiện tại với trung bình 20 phiên, sai số
    smoothing ảnh hưởng trực tiếp tới kết quả lọc.
    """
    return _wilder_smooth(true_range(df), period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI theo đúng công thức Wilder (RMA), không phải SMA.

    FIX: bản cũ dùng SMA → lệch 3-7 điểm ở vùng biến động mạnh so với
    TradingView. Với bộ lọc `50 <= RSI <= 65`, sai số này đủ để đổi kết quả scan
    và làm người dùng mất niềm tin khi đối chiếu bảng điện.
    """
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # avg_loss == 0 (chuỗi tăng liên tục) → RSI = 100 theo định nghĩa,
    # nhưng chỉ ở những bar đã đủ dữ liệu để tính (tránh biến NaN warmup thành 100).
    out = out.where(~((avg_loss == 0) & avg_gain.notna()), 100.0)
    return out


def rsi_last(close: pd.Series, period: int = 14, default: float = 50.0) -> float:
    """
    Giá trị RSI của bar cuối, an toàn với NaN/chuỗi ngắn.

    Tồn tại để các strategy không tự cài lại RSI — trước đây có 3 bản cài đặt
    khác nhau (indicators.py, golden_cross.py, ichimoku.py) và 2 trong số đó
    chia cho 0 không guard.
    """
    if close is None or len(close) < period + 1:
        return default
    series = rsi(close, period)
    if series.empty:
        return default
    last = series.iloc[-1]
    return float(last) if pd.notna(last) else default


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — cumulative money flow."""
    direction = np.where(close > close.shift(), 1,
                np.where(close < close.shift(), -1, 0))
    return (direction * volume).cumsum()


def obv_normalized_change(obv_series: pd.Series, volume: pd.Series,
                          lookback: int = 10, vol_ma: int = 20) -> float:
    """
    Biến động OBV trong `lookback` phiên, chuẩn hoá theo khối lượng trung bình.

    Đơn vị đầu ra: "số phiên khối lượng ròng" đã tích luỹ.
      +2.0  ⇒ dòng tiền ròng mua vào tương đương 2 phiên giao dịch trung bình.

    FIX: bản cũ chia cho `abs(OBV[-11]) + 1`. OBV là cumsum tính từ điểm bắt đầu
    tuỳ ý của cửa sổ fetch (180 hay 400 phiên) nên mẫu số đó không có ý nghĩa
    kinh tế: mã tích luỹ lâu → mẫu số khổng lồ → tỷ lệ luôn ≈ 0; mã có OBV gần 0
    → tỷ lệ bùng nổ. Ngoài ra kết quả còn bị đem so trực tiếp với % thay đổi giá
    (khác đơn vị hoàn toàn).
    """
    if obv_series is None or len(obv_series) < lookback + 1:
        return 0.0
    avg_vol = float(volume.tail(vol_ma).mean()) if len(volume) else 0.0
    if not avg_vol or avg_vol <= 0 or pd.isna(avg_vol):
        return 0.0
    delta = float(obv_series.iloc[-1] - obv_series.iloc[-(lookback + 1)])
    return delta / avg_vol


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
