"""Tests for Fibonacci support_resistance module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import pytest

from scanner.support_resistance import (
    find_swing_extremes, compute_fibo_levels, get_fibo_support_resistance,
    FIBO_RATIOS,
)


def make_df(closes, highs=None, lows=None):
    n = len(closes)
    dates = pd.date_range('2026-01-01', periods=n, freq='D')
    if highs is None: highs = [c * 1.01 for c in closes]
    if lows is None: lows = [c * 0.99 for c in closes]
    return pd.DataFrame({
        'Date': dates,
        'Open': closes,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': [100000] * n,
    })


# ---------- find_swing_extremes ----------

def test_find_uptrend_swing():
    # Low at start (40), high at end (60) → uptrend
    closes = list(np.linspace(40, 60, 30))
    df = make_df(closes)
    swing = find_swing_extremes(df, lookback=30)
    assert swing['direction'] == 'up'
    assert swing['low'] < 41
    assert swing['high'] > 59
    assert swing['range'] > 18


def test_find_downtrend_swing():
    # High at start (60), low at end (40) → downtrend
    closes = list(np.linspace(60, 40, 30))
    df = make_df(closes)
    swing = find_swing_extremes(df, lookback=30)
    assert swing['direction'] == 'down'


def test_swing_returns_none_for_short_data():
    closes = [50, 51, 52]  # only 3 bars
    df = make_df(closes)
    swing = find_swing_extremes(df, lookback=60)
    assert swing is None


# ---------- compute_fibo_levels ----------

def test_fibo_levels_count():
    """Should return exactly 7 Fibo levels (0, 23.6, 38.2, 50, 61.8, 78.6, 100)."""
    swing = {
        'high': 100, 'low': 50, 'range': 50, 'direction': 'up',
        'high_idx': 30, 'low_idx': 0, 'high_date': '2026-02-01', 'low_date': '2026-01-01',
    }
    levels = compute_fibo_levels(swing)
    assert len(levels) == 7


def test_fibo_levels_uptrend_calculations():
    """For uptrend: 0% = high, 100% = low, 61.8% = high - 61.8% * range."""
    swing = {
        'high': 100, 'low': 50, 'range': 50, 'direction': 'up',
        'high_idx': 30, 'low_idx': 0, 'high_date': '2026-02-01', 'low_date': '2026-01-01',
    }
    levels = compute_fibo_levels(swing)
    by_ratio = {lv['ratio']: lv['price'] for lv in levels}
    assert abs(by_ratio[0.0] - 100) < 0.01      # 0% = high
    assert abs(by_ratio[1.0] - 50) < 0.01       # 100% = low
    assert abs(by_ratio[0.5] - 75) < 0.01       # 50% = midpoint
    assert abs(by_ratio[0.618] - (100 - 50 * 0.618)) < 0.01   # 61.8% golden


def test_fibo_levels_downtrend_calculations():
    """For downtrend: 0% = low, 100% = high (inverted)."""
    swing = {
        'high': 100, 'low': 50, 'range': 50, 'direction': 'down',
        'high_idx': 0, 'low_idx': 30, 'high_date': '2026-01-01', 'low_date': '2026-02-01',
    }
    levels = compute_fibo_levels(swing)
    by_ratio = {lv['ratio']: lv['price'] for lv in levels}
    assert abs(by_ratio[0.0] - 50) < 0.01       # 0% = low (starting point)
    assert abs(by_ratio[1.0] - 100) < 0.01      # 100% = high (target)


def test_fibo_levels_sorted_ascending():
    swing = {
        'high': 100, 'low': 50, 'range': 50, 'direction': 'up',
        'high_idx': 30, 'low_idx': 0, 'high_date': '2026-02-01', 'low_date': '2026-01-01',
    }
    levels = compute_fibo_levels(swing)
    prices = [lv['price'] for lv in levels]
    assert prices == sorted(prices)


def test_golden_ratio_flagged():
    swing = {
        'high': 100, 'low': 50, 'range': 50, 'direction': 'up',
        'high_idx': 30, 'low_idx': 0, 'high_date': '2026-02-01', 'low_date': '2026-01-01',
    }
    levels = compute_fibo_levels(swing)
    golden = [lv for lv in levels if lv['is_golden']]
    assert len(golden) == 1
    assert golden[0]['ratio'] == 0.618


# ---------- get_fibo_support_resistance ----------

def test_get_sr_returns_correct_structure():
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60, n_levels=3)

    assert 'current' in sr
    assert 'swing' in sr
    assert 'supports' in sr
    assert 'resistances' in sr
    assert 'all_levels' in sr


def test_supports_below_current_resistances_above():
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)

    for s in sr['supports']:
        assert s['price'] < sr['current']
    for r in sr['resistances']:
        assert r['price'] > sr['current']


def test_supports_sorted_nearest_first():
    """Supports should be ordered descending (nearest = highest = first)."""
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)

    if len(sr['supports']) >= 2:
        for i in range(len(sr['supports']) - 1):
            assert sr['supports'][i]['price'] >= sr['supports'][i+1]['price']


def test_resistances_sorted_nearest_first():
    """Resistances should be ordered ascending (nearest = lowest = first)."""
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)

    if len(sr['resistances']) >= 2:
        for i in range(len(sr['resistances']) - 1):
            assert sr['resistances'][i]['price'] <= sr['resistances'][i+1]['price']


def test_distance_pct_correct():
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)

    for s in sr['supports']:
        expected = (sr['current'] - s['price']) / sr['current'] * 100
        assert abs(s['distance_pct'] - expected) < 0.1
    for r in sr['resistances']:
        expected = (r['price'] - sr['current']) / sr['current'] * 100
        assert abs(r['distance_pct'] - expected) < 0.1


def test_all_levels_returned():
    """all_levels should contain all 7 Fibo levels."""
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)
    assert len(sr['all_levels']) == 7


def test_n_levels_limit_respected():
    """supports/resistances lists should not exceed n_levels."""
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60, n_levels=2)
    assert len(sr['supports']) <= 2
    assert len(sr['resistances']) <= 2


def test_label_present():
    closes = list(np.linspace(40, 60, 70))
    df = make_df(closes)
    sr = get_fibo_support_resistance(df, lookback=60)
    for s in sr['supports']:
        assert 'label' in s
        assert s['label'] in ['0%', '23.6%', '38.2%', '50%', '61.8%', '78.6%', '100%']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
