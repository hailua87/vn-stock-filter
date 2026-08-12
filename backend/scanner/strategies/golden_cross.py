"""
Golden Cross strategy — supports two MA presets.

Presets:
  - 'long'  (MA50 × MA200): classic golden cross, position-trade signal (3-12 months)
  - 'short' (MA10 × MA20): short-term swing signal (2-4 weeks)

Both are computed for every stock. The web UI lets users pick which preset
to view via a chip.

Strategy criteria (5 sub-checks per preset, score 0-5):

  1. RECENT_CROSS: fast MA crossed above slow MA within last N bars (mandatory)
  2. PRICE_ABOVE_FAST: Current close > fast MA
  3. MA_STACKING: short-term MAs stacked bullishly
       - For long preset: MA10 > MA20 > MA50
       - For short preset: MA5 > MA10 > MA20
  4. SLOW_RISING: slow MA today > slow MA N bars ago
  5. VOLUME_CONFIRM: volume on cross day > 1.5 × MA20

Ratings:
  - A+ : 5/5
  - A  : 4/5
  - B  : 3/5
  - C  : <3 (filtered out)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from .indicators_ext import ma, detect_recent_cross_up
from ..indicators import rsi_last

log = logging.getLogger(__name__)


# Two presets, each defining the MAs and minimum history required.
PRESETS = {
    'long': {
        'name': 'MA50×MA200',
        'description': 'Cổ điển — position trade 3-12 tháng',
        'fast_period': 50,
        'slow_period': 200,
        'min_history': 220,
        'cross_lookback': 5,        # window to detect cross
        'slow_rising_lookback': 5,
        'stacking_periods': [10, 20, 50],
    },
    'short': {
        'name': 'MA10×MA20',
        'description': 'Ngắn hạn — swing 2-4 tuần',
        'fast_period': 10,
        'slow_period': 20,
        'min_history': 40,
        'cross_lookback': 5,        # tìm cross trong 5 phiên gần nhất
        'slow_rising_lookback': 3,
        'stacking_periods': [5, 10, 20],
    },
}


DEFAULT_CONFIG = {
    'min_avg_volume': 10_000,
    'volume_surge_ratio': 1.5,
    'corporate_action_lookback_days': 5,
    'corporate_action_lookahead_days': 5,
    'sanity_max_single_day_drop': 0.15,
}


@dataclass
class GoldenCrossResult:
    ticker: str
    exchange: str
    date: pd.Timestamp
    close: float
    volume: int
    preset: str        # 'long' or 'short'
    scores: dict
    metrics: dict

    @property
    def total_score(self) -> int:
        return sum(self.scores.values())

    @property
    def rating(self) -> str:
        s = self.total_score
        if s == 5: return 'A+'
        if s == 4: return 'A'
        if s == 3: return 'B'
        return 'C'

    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'exchange': self.exchange,
            'date': self.date.isoformat() if hasattr(self.date, 'isoformat') else str(self.date),
            'close': self.close,
            'volume': self.volume,
            'preset': self.preset,
            'total_score': self.total_score,
            'rating': self.rating,
            **{f'gc_{k}': v for k, v in self.scores.items()},
            **{f'm_{k}': v for k, v in self.metrics.items()},
        }


def evaluate(df: pd.DataFrame, ticker: str, preset: str = 'long',
             config: Optional[dict] = None,
             events: Optional[list] = None) -> Optional[GoldenCrossResult]:
    """
    Evaluate a stock against Golden Cross criteria for the given preset.

    Args:
        preset: 'long' (MA50×MA200) or 'short' (MA10×MA20)

    Returns None if:
      - Insufficient history for the preset
      - Low avg volume
      - Recent dilutive corporate action
      - No cross detected within lookback
      - Score < 3 (filtered out as too weak)
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}. Use 'long' or 'short'.")

    p = PRESETS[preset]
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if len(df) < p['min_history']:
        return None
    if df['Volume'].tail(20).mean() < cfg['min_avg_volume']:
        return None

    # FIX: Reject stale-cache rows (xem giải thích trong ichimoku.evaluate).
    if 'StaleCache' in df.columns and bool(df['StaleCache'].iloc[-1]):
        return None

    # Sanity check for un-adjusted prices
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

    close = df['Close']

    # Compute the MAs for this preset
    fast_ma = ma(close, p['fast_period'])
    slow_ma = ma(close, p['slow_period'])

    # Also compute stacking MAs (3 short-term levels)
    stack_mas = [ma(close, period) for period in p['stacking_periods']]

    # Validate latest values
    if pd.isna(slow_ma.iloc[-1]) or pd.isna(fast_ma.iloc[-1]):
        return None

    # 1. Detect cross within lookback
    cross_info = detect_recent_cross_up(fast_ma, slow_ma, lookback=p['cross_lookback'])
    if not cross_info['crossed']:
        return None

    scores = {'recent_cross': 1}

    last_close = float(close.iloc[-1])
    last_volume = int(df['Volume'].iloc[-1])

    # 2. Price above fast MA
    scores['price_above_fast'] = int(last_close > float(fast_ma.iloc[-1]))

    # 3. MA stacking (3 short-term MAs)
    stack_values = [float(m.iloc[-1]) for m in stack_mas if not pd.isna(m.iloc[-1])]
    if len(stack_values) == 3:
        scores['ma_stacking'] = int(stack_values[0] > stack_values[1] > stack_values[2])
    else:
        scores['ma_stacking'] = 0

    # 4. Slow MA rising
    slow_now = float(slow_ma.iloc[-1])
    slow_past = float(slow_ma.iloc[-1 - p['slow_rising_lookback']]) \
        if len(slow_ma) > p['slow_rising_lookback'] else slow_now
    scores['slow_rising'] = int(slow_now > slow_past)

    # 5. Volume confirmation on cross day
    if cross_info['days_ago'] is not None:
        cross_day_idx = len(df) - 1 - cross_info['days_ago']
        if cross_day_idx >= 20:
            cross_vol = float(df['Volume'].iloc[cross_day_idx])
            avg_vol = float(df['Volume'].iloc[cross_day_idx - 20:cross_day_idx].mean())
            scores['volume_confirm'] = int(cross_vol > avg_vol * cfg['volume_surge_ratio'])
        else:
            scores['volume_confirm'] = 0
    else:
        scores['volume_confirm'] = 0

    # Filter out weak signals (score < 3)
    if sum(scores.values()) < 3:
        return None

    # Common metrics
    rsi14_val = rsi_last(close, 14)
    vol_ma20 = float(df['Volume'].tail(20).mean())
    vol_ratio = last_volume / vol_ma20 if vol_ma20 > 0 else 0

    # Fibonacci S/R
    try:
        from ..support_resistance import get_fibo_support_resistance
        sr = get_fibo_support_resistance(df, current_price=last_close,
                                          lookback=60, n_levels=3)
    except Exception:
        sr = {'supports': [], 'resistances': [], 'swing': None}

    metrics = {
        'preset_name': p['name'],
        'cross_days_ago': cross_info['days_ago'],
        'fast_ma': round(float(fast_ma.iloc[-1]), 2),
        'slow_ma': round(slow_now, 2),
        'slow_spread_pct': cross_info['spread_pct'],
        'change_5d_pct': round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2),
        'vol_ratio': round(vol_ratio, 2),
        'rsi14': round(rsi14_val, 1),
        'suspicious_data': bool(suspicious_data),
        'upcoming_event': event_warning,
        'supports': sr['supports'],
        'resistances': sr['resistances'],
        'fibo_swing': sr.get('swing'),
    }

    return GoldenCrossResult(
        ticker=ticker,
        exchange=df['Exchange'].iloc[-1] if 'Exchange' in df.columns else '',
        date=df['Date'].iloc[-1],
        close=round(last_close, 2),
        volume=last_volume,
        preset=preset,
        scores=scores,
        metrics=metrics,
    )
