"""
Ichimoku Kinko Hyo strategy — comprehensive trend analysis.

Theory:
  Ichimoku is a Japanese charting system with 5 components that together
  visualize trend, momentum, support/resistance, and future projection.

  Components:
    - Tenkan-sen (9-period, "Conversion line"): short-term momentum
    - Kijun-sen (26-period, "Base line"): mid-term equilibrium
    - Senkou Span A: midpoint of Tenkan+Kijun, plotted 26 bars AHEAD
    - Senkou Span B: 52-period midpoint, plotted 26 bars AHEAD
    - Kumo (Cloud): area between Senkou A and B — primary support/resistance
    - Chikou Span (Lagging): current close plotted 26 bars BEHIND

Strategy criteria (5 bullish signals, score 0-5):

  1. TK_BULLISH: Tenkan > Kijun (short-term momentum bullish, current state).

  1b. RECENT_TK_CROSS: Tenkan VỪA cắt lên Kijun trong 5 phiên gần nhất.
       Đây là tín hiệu MẠNH NHẤT — entry sớm trước khi trend lớn xuất hiện.

  2. PRICE_ABOVE_CLOUD: Close > max(Senkou A, Senkou B)
       Price is above the cloud → bullish bias.

  3. CLOUD_BULLISH: Senkou A > Senkou B
       Cloud is "green" (bullish), narrowing or widening upward.

  4. CHIKOU_FREE: Chikou Span (close shifted back 26) > price 26 bars ago
       Momentum confirmed — no resistance from past price.

Ratings:
  - A+ : 4-5/5 — strong bullish setup (rare with recent cross = entry điểm)
  - A  : 3/5 — bullish
  - C  : <3 — filtered out (not bullish enough)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from .indicators_ext import compute_ichimoku, detect_recent_cross_up

log = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    'min_history_days': 80,        # need 52 + 26 = 78 + buffer for Senkou B
    'min_avg_volume': 10_000,
    'tk_cross_lookback': 5,
    'corporate_action_lookback_days': 5,
    'corporate_action_lookahead_days': 5,
    'sanity_max_single_day_drop': 0.15,
}


@dataclass
class IchimokuResult:
    ticker: str
    exchange: str
    date: pd.Timestamp
    close: float
    volume: int
    scores: dict
    metrics: dict

    @property
    def total_score(self) -> int:
        return sum(self.scores.values())

    @property
    def rating(self) -> str:
        # 5 criteria total. Recent TK cross is bonus.
        s = self.total_score
        if s >= 5: return 'A+'    # 5/5 — full setup + just crossed
        if s == 4: return 'A+'    # 4/5 — strong
        if s == 3: return 'A'     # 3/5 — bullish
        return 'C'  # filtered out

    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'exchange': self.exchange,
            'date': self.date.isoformat() if hasattr(self.date, 'isoformat') else str(self.date),
            'close': self.close,
            'volume': self.volume,
            'total_score': self.total_score,
            'rating': self.rating,
            **{f'ich_{k}': v for k, v in self.scores.items()},
            **{f'm_{k}': v for k, v in self.metrics.items()},
        }


def evaluate(df: pd.DataFrame, ticker: str,
             config: Optional[dict] = None,
             events: Optional[list] = None) -> Optional[IchimokuResult]:
    """
    Evaluate a stock's OHLCV against Ichimoku criteria.

    Returns None if:
      - Insufficient history
      - Low avg volume
      - Recent dilutive corporate action
      - Stale cache (phiên cuối không khớp phiên giao dịch gần nhất)
      - Score < 2 (not even mildly bullish)
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if len(df) < cfg['min_history_days']:
        return None
    if df['Volume'].tail(20).mean() < cfg['min_avg_volume']:
        return None

    # FIX: Reject stale-cache rows. fetch_with_cache đánh dấu cột 'StaleCache'=True
    # khi refetch thất bại và phải dùng dữ liệu cũ. Trả về None để mã không lọt
    # vào kết quả scan với giá/KL của phiên không khớp ngày hiển thị.
    if 'StaleCache' in df.columns and bool(df['StaleCache'].iloc[-1]):
        log.debug(f"  {ticker}: skipped (stale cache)")
        return None

    # Sanity check
    recent = df.tail(30)
    overnight_change = recent['Close'].pct_change()
    suspicious_data = (overnight_change < -cfg['sanity_max_single_day_drop']).any()

    # Corporate action filter
    event_warning = None
    if events:
        from ..corporate_actions import has_recent_event, has_upcoming_event
        recent_event = has_recent_event(events, days=cfg['corporate_action_lookback_days'])
        if recent_event:
            return None
        upcoming = has_upcoming_event(events, days=cfg['corporate_action_lookahead_days'])
        if upcoming:
            event_warning = {
                'type': upcoming.event_type,
                'ex_date': upcoming.ex_date,
                'ratio': upcoming.ratio,
            }

    # Compute Ichimoku components
    ich = compute_ichimoku(df)
    tenkan = ich['tenkan']
    kijun = ich['kijun']
    senkou_a = ich['senkou_a']
    senkou_b = ich['senkou_b']

    # Get most recent values (excluding NaN for cloud projection)
    last_close = float(df['Close'].iloc[-1])
    last_volume = int(df['Volume'].iloc[-1])
    last_idx = len(df) - 1

    last_tenkan = float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else None
    last_kijun = float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else None

    # Cloud values AT current position (not future projection)
    # senkou_a/b at index -1 are values projected from 26 bars ago
    last_senkou_a = float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else None
    last_senkou_b = float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else None

    if any(v is None for v in [last_tenkan, last_kijun, last_senkou_a, last_senkou_b]):
        return None

    scores = {}

    # 1. Tenkan > Kijun (current TK state bullish)
    scores['tk_bullish'] = int(last_tenkan > last_kijun)

    # 1b. RECENT TK CROSS — Tenkan vừa cắt lên Kijun trong N phiên gần nhất.
    # Đây là tín hiệu mạnh nhất trong Ichimoku — entry sớm.
    tk_cross = detect_recent_cross_up(tenkan, kijun, lookback=cfg['tk_cross_lookback'])
    scores['recent_tk_cross'] = int(tk_cross['crossed'])

    # 2. Price above cloud (both Senkou A and B)
    cloud_top = max(last_senkou_a, last_senkou_b)
    cloud_bottom = min(last_senkou_a, last_senkou_b)
    scores['price_above_cloud'] = int(last_close > cloud_top)

    # 3. Cloud bullish (Senkou A > Senkou B)
    scores['cloud_bullish'] = int(last_senkou_a > last_senkou_b)

    # 4. Chikou span free — current close > price 26 bars ago (positive momentum)
    if len(df) >= 27:
        price_26_ago = float(df['Close'].iloc[-27])
        scores['chikou_free'] = int(last_close > price_26_ago)
    else:
        scores['chikou_free'] = 0

    # Filter: must have at least 3 of 5 bullish signals (flexible mode)
    if sum(scores.values()) < 3:
        return None

    # Common metrics
    rsi14_val = _compute_rsi(df['Close'], 14)
    vol_ma20 = float(df['Volume'].tail(20).mean())
    vol_ratio = last_volume / vol_ma20 if vol_ma20 > 0 else 0

    # Fibonacci S/R
    try:
        from ..support_resistance import get_fibo_support_resistance
        sr = get_fibo_support_resistance(df, current_price=last_close,
                                          lookback=60, n_levels=3)
    except Exception:
        sr = {'supports': [], 'resistances': [], 'swing': None}

    # Distance to cloud (helpful info)
    cloud_distance_pct = 0
    if last_close > cloud_top:
        cloud_distance_pct = (last_close - cloud_top) / cloud_top * 100
    elif last_close < cloud_bottom:
        cloud_distance_pct = (last_close - cloud_bottom) / cloud_bottom * 100

    # ════════════════════════════════════════════════════
    # TURNAROUND SIGNAL DETECTION (đảo chiều sớm — STRICT MODE)
    # ════════════════════════════════════════════════════
    # Đặc trưng: TK vừa cắt KJ + giá đang break từ DƯỚI/TRONG cloud lên
    # + volume mạnh + đà tăng rõ. Setup early-reversal cao cấp.
    #
    # Điều kiện CHẶT (high quality, ít tín hiệu):
    #   1. TK cross trong ≤2 phiên (very recent, T-1 hoặc T-2)
    #   2. Giá CHUẨN BỊ break cloud: dưới hoặc vừa vượt nhẹ
    #      → close < cloud_top * 1.01 (chỉ 1% trên cloud_top)
    #   3. Đà tăng 3 phiên ≥ 2.5% (rõ ràng đảo chiều)
    #   4. Volume ratio ≥ 1.5× MA20 (xác nhận dòng tiền lớn)
    is_turnaround = False
    turnaround_reasons = []
    if tk_cross['crossed'] and tk_cross['days_ago'] is not None and tk_cross['days_ago'] <= 2:
        turnaround_reasons.append(f"TK cross {tk_cross['days_ago']} phiên trước")
        # Check position vs cloud (chuẩn bị break)
        if last_close < cloud_top * 1.01:
            turnaround_reasons.append('Giá chuẩn bị break cloud')
            # 3-day momentum (≥ 2.5%)
            if len(df) >= 4:
                change_3d_pct = (last_close / float(df['Close'].iloc[-4]) - 1) * 100
                if change_3d_pct >= 2.5:
                    turnaround_reasons.append(f'Nến tăng {change_3d_pct:.1f}% trong 3 phiên')
                    if vol_ratio >= 1.5:
                        turnaround_reasons.append(f'Volume {vol_ratio:.1f}× MA20')
                        is_turnaround = True

    metrics = {
        'tenkan': round(last_tenkan, 2),
        'kijun': round(last_kijun, 2),
        'senkou_a': round(last_senkou_a, 2),
        'senkou_b': round(last_senkou_b, 2),
        'cloud_top': round(cloud_top, 2),
        'cloud_bottom': round(cloud_bottom, 2),
        'cloud_distance_pct': round(cloud_distance_pct, 2),
        'tk_cross_days_ago': tk_cross['days_ago'],
        'is_turnaround': bool(is_turnaround),
        'turnaround_reasons': turnaround_reasons,
        'change_5d_pct': round((df['Close'].iloc[-1] / df['Close'].iloc[-6] - 1) * 100, 2),
        'vol_ratio': round(vol_ratio, 2),
        'rsi14': round(rsi14_val, 1),
        'suspicious_data': bool(suspicious_data),
        'upcoming_event': event_warning,
        'supports': sr['supports'],
        'resistances': sr['resistances'],
        'fibo_swing': sr.get('swing'),
    }

    return IchimokuResult(
        ticker=ticker,
        exchange=df['Exchange'].iloc[-1] if 'Exchange' in df.columns else '',
        date=df['Date'].iloc[-1],
        close=round(last_close, 2),
        volume=last_volume,
        scores=scores,
        metrics=metrics,
    )


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gains = delta.where(delta > 0, 0).rolling(period).mean()
    losses = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gains / losses
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty and rsi.iloc[-1] == rsi.iloc[-1] else 50.0
