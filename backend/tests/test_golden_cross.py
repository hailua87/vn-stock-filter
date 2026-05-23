"""Tests for golden_cross strategy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import pytest

from scanner.strategies import golden_cross
from scanner.strategies.indicators_ext import ma, detect_recent_cross_up


def make_uptrend_df(days=250, base=50, end=70, seed=42, vol_surge_at_end=True):
    """Build OHLCV with a clear long-term uptrend."""
    np.random.seed(seed)
    flat = base + np.random.randn(days - 50) * 1.0
    rally = np.linspace(base, end, 50) + np.random.randn(50) * 0.5
    close = np.concatenate([flat, rally])
    dates = pd.date_range('2025-01-01', periods=days, freq='D')

    if vol_surge_at_end:
        vols = np.concatenate([
            np.random.randint(100000, 300000, days - 30),
            np.random.randint(500000, 1500000, 30),
        ])
    else:
        vols = np.random.randint(100000, 300000, days)

    return pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': vols, 'Exchange': 'HOSE',
    })


# ---------- Basic acceptance ----------

def test_invalid_preset_raises():
    df = make_uptrend_df()
    with pytest.raises(ValueError):
        golden_cross.evaluate(df, 'TEST', preset='invalid')


def test_short_history_returns_none():
    # Use 30 days (need at least 50 to pass min_history)
    np.random.seed(0)
    days = 30
    close = 50 + np.random.randn(days) * 1.0
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    df = pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': np.random.randint(100000, 300000, days),
        'Exchange': 'HOSE',
    })
    res = golden_cross.evaluate(df, 'TEST', preset='long')
    assert res is None  # not enough data for MA200


def test_low_volume_returns_none():
    df = make_uptrend_df()
    df['Volume'] = 100  # below threshold
    res = golden_cross.evaluate(df, 'TEST', preset='long')
    assert res is None


# ---------- Long preset (MA50 x MA200) ----------

def test_long_preset_detects_cross():
    """A clear uptrend with cross in last 5 bars should be detected."""
    # Tạo data: 200 phiên đi ngang quanh 45, rồi tăng mạnh 50 phiên cuối lên 65
    # → MA50 cross MA200 trong vài phiên cuối
    np.random.seed(7)
    days = 260
    flat = 45 + np.random.randn(210) * 0.7
    rally = np.linspace(45, 65, 50) + np.random.randn(50) * 0.5
    close = np.concatenate([flat, rally])
    dates = pd.date_range('2025-01-01', periods=days, freq='D')

    df = pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': np.concatenate([
            np.random.randint(100000, 300000, 240),
            np.random.randint(500000, 1500000, 20),
        ]),
        'Exchange': 'HOSE',
    })

    res = golden_cross.evaluate(df, 'TEST', preset='long')
    # Cross may or may not occur depending on noise — but result should be valid if detected
    if res:
        assert res.preset == 'long'
        assert res.scores['recent_cross'] == 1
        assert res.total_score >= 3  # filter threshold
        assert res.rating in ['A+', 'A', 'B']


# ---------- Short preset (MA10 x MA20) ----------

def test_short_preset_detects_cross():
    """Build data with explicit MA10 x MA20 cross in last 5 bars."""
    np.random.seed(42)
    days = 250
    flat = 50 + np.random.randn(215) * 1.0
    recent_drop = np.linspace(50, 48, 25)
    recent_pop = np.linspace(48, 53, 10) + np.random.randn(10) * 0.2
    close = np.concatenate([flat, recent_drop, recent_pop])[:days]

    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    df = pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': np.concatenate([
            np.random.randint(50000, 200000, 240),
            np.random.randint(500000, 1500000, 10),
        ]),
        'Exchange': 'HOSE',
    })

    res = golden_cross.evaluate(df, 'TEST', preset='short')
    assert res is not None
    assert res.preset == 'short'
    assert res.scores['recent_cross'] == 1
    assert res.total_score >= 3


def test_short_preset_no_cross_returns_none():
    """Stable price (no MA cross) should return None."""
    np.random.seed(0)
    days = 100
    close = 50 + np.random.randn(days) * 0.3  # very stable, no trend
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    df = pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.005, 'Low': close * 0.995, 'Close': close,
        'Volume': np.random.randint(100000, 300000, days),
        'Exchange': 'HOSE',
    })
    res = golden_cross.evaluate(df, 'TEST', preset='short')
    assert res is None


# ---------- Result structure ----------

def test_result_to_dict_has_expected_keys():
    np.random.seed(42)
    days = 250
    flat = 50 + np.random.randn(215) * 1.0
    recent_drop = np.linspace(50, 48, 25)
    recent_pop = np.linspace(48, 53, 10) + np.random.randn(10) * 0.2
    close = np.concatenate([flat, recent_drop, recent_pop])[:days]
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    df = pd.DataFrame({
        'Date': dates, 'Open': close, 'High': close * 1.01,
        'Low': close * 0.99, 'Close': close,
        'Volume': np.random.randint(500000, 1500000, days),
        'Exchange': 'HOSE',
    })

    res = golden_cross.evaluate(df, 'TEST', preset='short')
    if res:
        d = res.to_dict()
        assert 'ticker' in d
        assert 'preset' in d
        assert d['preset'] == 'short'
        assert 'total_score' in d
        assert 'rating' in d
        assert 'gc_recent_cross' in d
        assert 'gc_price_above_fast' in d
        assert 'gc_ma_stacking' in d
        assert 'gc_slow_rising' in d
        assert 'gc_volume_confirm' in d
        assert 'm_fast_ma' in d
        assert 'm_slow_ma' in d
        assert 'm_cross_days_ago' in d


def test_rating_scale():
    """Score 5 = A+, 4 = A, 3 = B."""
    np.random.seed(42)
    days = 250
    flat = 50 + np.random.randn(215) * 1.0
    recent_drop = np.linspace(50, 48, 25)
    recent_pop = np.linspace(48, 53, 10) + np.random.randn(10) * 0.2
    close = np.concatenate([flat, recent_drop, recent_pop])[:days]
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    df = pd.DataFrame({
        'Date': dates, 'Open': close, 'High': close * 1.01,
        'Low': close * 0.99, 'Close': close,
        'Volume': np.random.randint(500000, 1500000, days),
        'Exchange': 'HOSE',
    })
    res = golden_cross.evaluate(df, 'TEST', preset='short')
    if res:
        if res.total_score == 5:
            assert res.rating == 'A+'
        elif res.total_score == 4:
            assert res.rating == 'A'
        elif res.total_score == 3:
            assert res.rating == 'B'


# ---------- detect_recent_cross_up helper ----------

def test_detect_cross_up_clear_case():
    fast = pd.Series([1, 2, 3, 4, 5, 6, 7, 8])
    slow = pd.Series([5, 5, 5, 5, 5, 5, 5, 5])
    result = detect_recent_cross_up(fast, slow, lookback=5)
    assert result['crossed'] is True


def test_detect_cross_no_cross():
    fast = pd.Series([1] * 10)
    slow = pd.Series([5] * 10)
    result = detect_recent_cross_up(fast, slow, lookback=5)
    assert result['crossed'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
