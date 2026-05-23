"""Tests for ichimoku strategy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import pytest

from scanner.strategies import ichimoku
from scanner.strategies.indicators_ext import (
    tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span, compute_ichimoku
)


def make_strong_uptrend_df(days=120, seed=42):
    """Build OHLCV with strong uptrend (price > cloud, cloud bullish)."""
    np.random.seed(seed)
    close = np.linspace(40, 70, days) + np.random.randn(days) * 0.5
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    return pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': np.random.randint(100000, 800000, days),
        'Exchange': 'HOSE',
    })


def make_downtrend_df(days=120, seed=42):
    """Build OHLCV with downtrend (price < cloud)."""
    np.random.seed(seed)
    close = np.linspace(70, 40, days) + np.random.randn(days) * 0.5
    dates = pd.date_range('2025-01-01', periods=days, freq='D')
    return pd.DataFrame({
        'Date': dates,
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close,
        'Volume': np.random.randint(100000, 800000, days),
        'Exchange': 'HOSE',
    })


# ---------- Ichimoku components ----------

def test_tenkan_sen_formula():
    """Tenkan = (max(High,9) + min(Low,9)) / 2."""
    df = make_strong_uptrend_df()
    tk = tenkan_sen(df, period=9)
    # Manually verify last value
    last_9_high = df['High'].tail(9).max()
    last_9_low = df['Low'].tail(9).min()
    expected = (last_9_high + last_9_low) / 2
    assert abs(tk.iloc[-1] - expected) < 0.01


def test_kijun_sen_formula():
    df = make_strong_uptrend_df()
    kj = kijun_sen(df, period=26)
    last_26_high = df['High'].tail(26).max()
    last_26_low = df['Low'].tail(26).min()
    expected = (last_26_high + last_26_low) / 2
    assert abs(kj.iloc[-1] - expected) < 0.01


def test_compute_ichimoku_returns_all_components():
    df = make_strong_uptrend_df()
    ich = compute_ichimoku(df)
    assert set(ich.keys()) == {'tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou'}
    # All should be Series of same length
    for k, v in ich.items():
        assert len(v) == len(df)


def test_senkou_a_is_shifted_forward():
    """Senkou A is shifted forward by 26 — meaning index -1 has values from 26 bars ago."""
    df = make_strong_uptrend_df()
    tk = tenkan_sen(df)
    kj = kijun_sen(df)
    sa = senkou_span_a(tk, kj, shift=26)
    # The value at position -1 should equal (tk + kj) / 2 from position -27
    expected = (tk.iloc[-27] + kj.iloc[-27]) / 2
    assert abs(sa.iloc[-1] - expected) < 0.01


# ---------- Strategy acceptance ----------

def test_short_history_returns_none():
    df = make_strong_uptrend_df(days=50)  # < 80 days
    res = ichimoku.evaluate(df, 'TEST')
    assert res is None


def test_low_volume_returns_none():
    df = make_strong_uptrend_df()
    df['Volume'] = 100
    res = ichimoku.evaluate(df, 'TEST')
    assert res is None


def test_strong_uptrend_detected():
    """Strong uptrend should hit all 4 Ichimoku bullish criteria."""
    df = make_strong_uptrend_df()
    res = ichimoku.evaluate(df, 'TEST')
    assert res is not None
    assert res.total_score == 4
    assert res.rating == 'A+'
    assert res.scores['tk_bullish'] == 1
    assert res.scores['price_above_cloud'] == 1
    assert res.scores['cloud_bullish'] == 1
    assert res.scores['chikou_free'] == 1


def test_downtrend_rejected_by_flexible_filter():
    """Downtrend has score < 3 → filtered out (flexible mode requires >= 3)."""
    df = make_downtrend_df()
    res = ichimoku.evaluate(df, 'TEST')
    assert res is None


# ---------- Result structure ----------

def test_result_to_dict_has_expected_keys():
    df = make_strong_uptrend_df()
    res = ichimoku.evaluate(df, 'TEST')
    assert res is not None
    d = res.to_dict()
    assert 'ticker' in d
    assert 'total_score' in d
    assert 'rating' in d
    assert 'ich_tk_bullish' in d
    assert 'ich_price_above_cloud' in d
    assert 'ich_cloud_bullish' in d
    assert 'ich_chikou_free' in d
    assert 'm_tenkan' in d
    assert 'm_kijun' in d
    assert 'm_cloud_top' in d
    assert 'm_cloud_bottom' in d


def test_rating_scale():
    """Score 4 → A+, 3 → A (only these two possible with flexible filter)."""
    df = make_strong_uptrend_df()
    res = ichimoku.evaluate(df, 'TEST')
    if res:
        if res.total_score == 4:
            assert res.rating == 'A+'
        elif res.total_score == 3:
            assert res.rating == 'A'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
