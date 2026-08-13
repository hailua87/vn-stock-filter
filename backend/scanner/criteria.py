"""
Pre-breakout detection criteria.
Each criterion returns a binary (0/1) score + optional metadata.
Final composite score is a weighted sum (default weights = 1).
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np

from .indicators import atr, rsi, obv, bollinger_width, obv_normalized_change

log = logging.getLogger(__name__)


# Trọng số từng tiêu chí. Mặc định = 1.0 cho cả 10 tiêu chí (giữ nguyên thang
# 0-10 và toàn bộ dữ liệu archive đã sinh ra trước đây).
#
# Điểm cần biết trước khi hiệu chỉnh: các tiêu chí KHÔNG độc lập.
#   - atr_squeeze và bb_squeeze đo gần như cùng một hiện tượng (nén biến động)
#     → hiện đang được cộng 2 điểm cho 1 thông tin.
#   - near_high20 và ma_align tương quan mạnh.
#   - no_gap_down là tiêu chí "vắng mặt điều xấu", ~95% mã đạt → gần như +1 miễn
#     phí, làm lạm phát điểm và giảm khả năng phân biệt A với B.
# Trọng số đúng phải đến từ dữ liệu (information coefficient của từng tiêu chí),
# không phải đặt tay — xem backend/scanner/weight_calibration.py và
# backend/run_weight_calibration.py.
DEFAULT_CRITERIA_WEIGHTS = {
    'atr_squeeze': 1.0,
    'bb_squeeze': 1.0,
    'near_high20': 1.0,
    'stealth_accum': 1.0,
    'vol_surge': 1.0,
    'upper_close': 1.0,
    'ma_align': 1.0,
    'rsi_zone': 1.0,
    'pocket_pivot': 1.0,
    'no_gap_down': 1.0,
}

# Trọng số đã hiệu chỉnh, do `run_weight_calibration.py --apply` sinh ra.
# KHÔNG sửa tay file này: nó chỉ được ghi khi kiểm định NGOÀI MẪU đạt ngưỡng.
ACTIVE_WEIGHTS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'criteria_weights.json'


def load_active_weights() -> tuple[dict, str]:
    """
    Đọc trọng số đang dùng. Trả về (weights, version).

    Không có file → trọng số đều, version 'default'. Đây là trạng thái ĐÚNG khi
    chưa đủ dữ liệu lịch sử: trọng số đều là một prior trung thực, còn trọng số
    fit trên 1,6 năm dữ liệu chỉ là nhiễu được đóng gói cho đẹp.

    `version` được ghi vào mọi file output để tín hiệu quá khứ tái lập được —
    thiếu nó thì backtest trên archive về sau vô nghĩa, vì không biết điểm số
    ngày đó được sinh ra bằng bộ trọng số nào.
    """
    if not ACTIVE_WEIGHTS_PATH.exists():
        return dict(DEFAULT_CRITERIA_WEIGHTS), 'default'
    try:
        import json
        data = json.loads(ACTIVE_WEIGHTS_PATH.read_text(encoding='utf-8'))
        raw = data.get('weights') or {}
        # Chỉ nhận key đã biết — phòng file bị sửa tay sai
        merged = {k: float(raw.get(k, 0.0)) for k in DEFAULT_CRITERIA_WEIGHTS}
        if sum(merged.values()) <= 0:
            log.warning("  criteria_weights.json có tổng trọng số = 0 → dùng mặc định")
            return dict(DEFAULT_CRITERIA_WEIGHTS), 'default'
        return merged, str(data.get('version', 'unknown'))
    except Exception as e:
        log.warning(f"  Đọc criteria_weights.json thất bại ({e}) → dùng mặc định")
        return dict(DEFAULT_CRITERIA_WEIGHTS), 'default'


ACTIVE_WEIGHTS, ACTIVE_WEIGHTS_VERSION = load_active_weights()


@dataclass
class CriteriaResult:
    ticker: str
    exchange: str
    date: pd.Timestamp
    close: float
    volume: int
    scores: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    weights: dict = field(default_factory=lambda: dict(ACTIVE_WEIGHTS))
    weights_version: str = ACTIVE_WEIGHTS_VERSION

    @property
    def total_score(self) -> float:
        total = sum(self.scores[k] * self.weights.get(k, 1.0) for k in self.scores)
        # Trọng số mặc định đều là 1.0 → tổng là số nguyên; round() giữ cho
        # JSON output và so sánh `>= min_score` không bị nhiễu dấu phẩy động.
        return round(total, 2)

    @property
    def max_score(self) -> float:
        return round(sum(self.weights.get(k, 1.0) for k in self.scores), 2)

    @property
    def rating(self) -> str:
        # Ngưỡng theo TỶ LỆ để không phụ thuộc thang điểm khi trọng số thay đổi.
        # 8/10, 6/10, 4/10 — giữ đúng hành vi cũ khi mọi trọng số = 1.
        mx = self.max_score or 1
        pct = self.total_score / mx
        if pct >= 0.8: return 'A+'
        if pct >= 0.6: return 'A'
        if pct >= 0.4: return 'B'
        return 'C'

    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'exchange': self.exchange,
            'date': self.date.isoformat() if hasattr(self.date, 'isoformat') else str(self.date),
            'close': self.close,
            'volume': self.volume,
            'total_score': self.total_score,
            'max_score': self.max_score,
            'rating': self.rating,
            'weights_version': self.weights_version,
            **{f'c{i+1}_{k}': v for i, (k, v) in enumerate(self.scores.items())},
            **{f'm_{k}': v for k, v in self.metrics.items()},
        }


# ----- Configuration -----
DEFAULT_CONFIG = {
    'min_history_days': 60,
    'min_avg_volume': 10_000,
    'atr_squeeze_ratio': 0.85,        # current ATR% < 85% of 20d average
    'bbw_squeeze_quantile': 0.25,     # current BBW in bottom 25% of 60d
    'near_high_pct': 3.0,             # within 3% of 20d high
    'stealth_obv_chg_min': 0.05,      # OBV change > 5%
    'stealth_price_chg_max': 0.03,    # price change < 3%
    'vol_surge_ratio': 1.15,          # 5d avg vol > 1.15 * 20d MA vol
    'upper_close_threshold': 0.6,     # close in top 40% of day's range
    'upper_close_min_days': 3,        # at least 3 out of 5 days
    'rsi_lower': 50,
    'rsi_upper': 65,
    'gap_down_threshold': 0.04,       # 4% gap down disqualifies
    'corporate_action_lookback_days': 5,  # skip signal if dilutive event in last N days
    'corporate_action_lookahead_days': 5, # warn if upcoming ex-rights in next N days
    'sanity_max_single_day_drop': 0.15,   # >15% drop in 1 day → suspect un-adjusted data
    'stealth_obv_days_min': 1.0,          # OBV ròng >= 1 phiên khối lượng TB
    'criteria_weights': ACTIVE_WEIGHTS,
}


def evaluate(df: pd.DataFrame, ticker: str,
             config: Optional[dict] = None,
             events: Optional[list] = None) -> Optional[CriteriaResult]:
    """
    Evaluate a stock's daily OHLCV DataFrame against all 10 pre-breakout criteria.

    Args:
        df: must be sorted ascending by Date with columns
            Date, Open, High, Low, Close, Volume, Exchange
        events: optional list of CorporateAction objects for this ticker.
            If provided, signals will be suppressed when a dilutive event
            occurred recently (data may still be inconsistent).
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if len(df) < cfg['min_history_days']:
        return None
    if df['Volume'].tail(20).mean() < cfg['min_avg_volume']:
        return None

    # FIX: reject stale-cache rows — giống golden_cross.evaluate và
    # ichimoku.evaluate. Trước đây Pre-Breakout (strategy chính, ghi ra
    # web/data/latest.json) là strategy DUY NHẤT thiếu guard này, nên đúng lỗi
    # "giá phiên cũ hiển thị dưới ngày mới" đã fix ở 2 strategy kia vẫn còn.
    if 'StaleCache' in df.columns and bool(df['StaleCache'].iloc[-1]):
        log.debug(f"  {ticker}: skipped (stale cache)")
        return None

    # Sanity check: detect un-adjusted prices via implausibly large overnight drops
    # in the last 30 days. A real >15% gap is rare; usually it's a corporate action
    # we failed to adjust for.
    recent = df.tail(30)
    overnight_change = recent['Close'].pct_change()
    if (overnight_change < -cfg['sanity_max_single_day_drop']).any():
        log.warning(f"  {ticker}: detected suspicious drop > {cfg['sanity_max_single_day_drop']*100:.0f}% — possible un-adjusted corporate action")
        # Don't refuse outright; flag in metadata so UI can warn
        suspicious_data = True
    else:
        suspicious_data = False

    # Corporate action filter: skip if dilutive event happened recently
    event_warning = None
    if events:
        from .corporate_actions import has_recent_event, has_upcoming_event
        recent_event = has_recent_event(events, days=cfg['corporate_action_lookback_days'])
        if recent_event:
            # Recent split/stock dividend → indicators distorted, skip
            return None
        upcoming = has_upcoming_event(events, days=cfg['corporate_action_lookahead_days'])
        if upcoming:
            event_warning = {
                'type': upcoming.event_type,
                'ex_date': upcoming.ex_date,
                'ratio': upcoming.ratio,
            }

    df = df.copy().reset_index(drop=True)
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    # Indicators
    df['MA10'] = close.rolling(10).mean()
    df['MA20'] = close.rolling(20).mean()
    df['VolMA20'] = vol.rolling(20).mean()
    df['ATR14'] = atr(df, 14)
    df['ATR_pct'] = df['ATR14'] / close * 100
    df['RSI14'] = rsi(close, 14)
    df['OBV'] = obv(close, vol)
    df['BBW'] = bollinger_width(close, 20)
    df['High20'] = high.rolling(20).max()

    last = df.iloc[-1]
    scores = {}

    # ── C1: ATR squeeze ──────────────────────────────────────────────
    atr_avg20 = df['ATR_pct'].iloc[-21:-1].mean()
    scores['atr_squeeze'] = int(last['ATR_pct'] < atr_avg20 * cfg['atr_squeeze_ratio'])

    # ── C2: Bollinger width in bottom quartile of 60d ────────────────
    bbw_q = df['BBW'].iloc[-60:].quantile(cfg['bbw_squeeze_quantile'])
    scores['bb_squeeze'] = int(last['BBW'] <= bbw_q)

    # ── C3: Within 3% of 20-day high but not above ───────────────────
    dist_high = (last['High20'] - last['Close']) / last['High20'] * 100
    scores['near_high20'] = int(0 < dist_high <= cfg['near_high_pct'])

    # ── C4: Stealth accumulation (dòng tiền vào nhưng giá chưa chạy) ──
    # obv_days = khối lượng ròng 10 phiên qua, tính bằng "số phiên khối lượng TB".
    # So sánh với price_chg (đơn vị %) đã bị bỏ: hai đại lượng khác đơn vị nên
    # điều kiện `obv_chg > price_chg * 2` cũ không có ý nghĩa toán học.
    obv_days = obv_normalized_change(df['OBV'], vol, lookback=10, vol_ma=20)
    price_chg = (close.iloc[-1] - close.iloc[-11]) / close.iloc[-11]
    scores['stealth_accum'] = int(
        obv_days >= cfg['stealth_obv_days_min']
        and price_chg < cfg['stealth_price_chg_max']
    )

    # ── C5: Volume surge (5d avg > 20d MA * 1.15) ────────────────────
    vol5 = vol.iloc[-5:].mean()
    scores['vol_surge'] = int(vol5 > last['VolMA20'] * cfg['vol_surge_ratio'])

    # ── C6: Upper-half close ≥ 3 of last 5 days ──────────────────────
    upper_days = 0
    for _, r in df.iloc[-5:].iterrows():
        rng = r['High'] - r['Low']
        if rng > 0 and (r['Close'] - r['Low']) / rng >= cfg['upper_close_threshold']:
            upper_days += 1
    scores['upper_close'] = int(upper_days >= cfg['upper_close_min_days'])

    # ── C7: MA10 > MA20 and MA20 rising ──────────────────────────────
    scores['ma_align'] = int(
        last['MA10'] > last['MA20']
        and last['MA20'] >= df['MA20'].iloc[-6]
    )

    # ── C8: RSI in healthy zone 50-65 ────────────────────────────────
    scores['rsi_zone'] = int(cfg['rsi_lower'] <= last['RSI14'] <= cfg['rsi_upper'])

    # ── C9: Pocket Pivot (Chris Kacher) ──────────────────────────────
    last10 = df.iloc[-11:-1]
    down_days = last10[last10['Close'] < last10['Close'].shift()]
    pocket = False
    if len(down_days) > 0 and last['Close'] > df.iloc[-2]['Close']:
        if last['Volume'] > down_days['Volume'].max():
            pocket = True
    scores['pocket_pivot'] = int(pocket)

    # ── C10: No major gap down in last 5 days ────────────────────────
    no_gap = True
    for i in range(-5, 0):
        if df.iloc[i]['Open'] < df.iloc[i-1]['Close'] * (1 - cfg['gap_down_threshold']):
            no_gap = False
            break
    scores['no_gap_down'] = int(no_gap)

    # Calculate Fibonacci-based support/resistance levels
    try:
        from .support_resistance import get_fibo_support_resistance
        sr = get_fibo_support_resistance(df, current_price=float(last['Close']),
                                         lookback=60, n_levels=3)
    except Exception as e:
        log.warning(f"  {ticker}: Fibo SR calculation failed: {e}")
        sr = {'supports': [], 'resistances': [], 'swing': None}

    # Trạng thái trần/sàn: mã đang dư mua trần thì KHÔNG MUA ĐƯỢC, nên một
    # "tín hiệu breakout" ở đó là tín hiệu không thực hiện được.
    from .price_limits import classify_price_limit
    exchange_val = df['Exchange'].iloc[-1] if 'Exchange' in df.columns else None
    limit_info = classify_price_limit(df, exchange_val)

    metrics = {
        'change_1d_pct': limit_info['change_1d_pct'],
        'limit_status': limit_info['limit_status'],
        'limit_locked': limit_info['limit_locked'],
        'tradable_warning': limit_info['tradable_warning'],
        'change_5d_pct': round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2),
        'vol_ratio': round(last['Volume'] / last['VolMA20'], 2) if last['VolMA20'] > 0 else 0,
        'rsi14': round(last['RSI14'], 1),
        'atr_pct': round(last['ATR_pct'], 2),
        'obv_days_10d': round(obv_days, 2),
        'dist_to_high20_pct': round(dist_high, 2),
        'high20': round(last['High20'], 2),
        'ma10': round(last['MA10'], 2),
        'ma20': round(last['MA20'], 2),
        'suspicious_data': suspicious_data,
        'upcoming_event': event_warning,
        'supports': sr['supports'],          # Fibo levels below current
        'resistances': sr['resistances'],    # Fibo levels above current
        'fibo_swing': sr.get('swing'),       # {high, low, direction, range, dates}
    }

    return CriteriaResult(
        ticker=ticker,
        exchange=df['Exchange'].iloc[-1] if 'Exchange' in df.columns else '',
        date=df['Date'].iloc[-1],
        close=round(last['Close'], 2),
        volume=int(last['Volume']),
        scores=scores,
        metrics=metrics,
        weights=dict(cfg.get('criteria_weights') or ACTIVE_WEIGHTS),
    )
