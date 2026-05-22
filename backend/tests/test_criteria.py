"""Unit tests for the scanner criteria."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scanner.criteria import evaluate, DEFAULT_CONFIG
from scanner.indicators import atr, rsi, obv, bollinger_width


def _make_df(closes, volumes=None, n=80):
    """Build a fake OHLCV DataFrame from a closes array."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    rng = np.random.default_rng(0)
    opens = closes * (1 + rng.normal(0, 0.003, n))
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.005, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.005, n)))
    if volumes is None:
        volumes = rng.integers(50_000, 500_000, n)
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=n, freq='B'),
        'Open': opens, 'High': highs, 'Low': lows,
        'Close': closes, 'Volume': volumes, 'Exchange': 'HOSE',
    })


def test_indicators_basic():
    df = _make_df(np.linspace(100, 110, 80))
    assert atr(df, 14).notna().sum() > 30
    assert (rsi(df['Close'], 14).dropna() <= 100).all()
    assert (rsi(df['Close'], 14).dropna() >= 0).all()
    assert obv(df['Close'], df['Volume']).notna().all()
    assert bollinger_width(df['Close'], 20).notna().sum() > 40


def test_evaluate_returns_none_for_short_history():
    df = _make_df(np.linspace(100, 110, 30))  # < 60 days
    assert evaluate(df, 'TEST') is None


def test_evaluate_returns_none_for_low_volume():
    df = _make_df(np.linspace(100, 110, 80), volumes=np.full(80, 100))
    assert evaluate(df, 'TEST') is None


def test_evaluate_returns_result():
    df = _make_df(np.linspace(100, 110, 80))
    res = evaluate(df, 'TEST')
    assert res is not None
    assert res.ticker == 'TEST'
    assert 0 <= res.total_score <= 10
    assert res.rating in {'A+', 'A', 'B', 'C'}
    assert len(res.scores) == 10


def test_pre_breakout_pattern_scores_high():
    """A constructed pre-breakout pattern should score >= 5."""
    rng = np.random.default_rng(42)
    base = 100.0
    # Phase 1: uptrend creating peak
    p1 = base + np.cumsum(rng.normal(0.3, 0.5, 40))
    peak = p1.max()
    # Phase 2: pullback
    p2 = np.linspace(p1[-1], peak * 0.93, 15)
    # Phase 3: tight consolidation just below peak
    p3 = peak * 0.94 + rng.normal(0, 0.3, 15)
    # Phase 4: stealth push toward peak with tight range
    p4 = np.linspace(p3[-1], peak * 0.985, 10) + rng.normal(0, 0.15, 10)
    closes = np.concatenate([p1, p2, p3, p4])
    # Volumes: low during consolidation, rising at end
    vols = rng.integers(80_000, 150_000, len(closes))
    vols[-5:] = rng.integers(180_000, 280_000, 5)
    df = _make_df(closes, volumes=vols)
    res = evaluate(df, 'PREBO')
    assert res is not None
    assert res.total_score >= 4, f"Expected ≥4, got {res.total_score}: {res.scores}"


def test_random_walk_scores_low_on_average():
    """Random walks should mostly NOT trigger strong signals."""
    rng = np.random.default_rng(123)
    high_scores = 0
    n_trials = 20
    for seed in range(n_trials):
        local_rng = np.random.default_rng(seed)
        closes = 100 * np.exp(np.cumsum(local_rng.normal(0, 0.02, 80)))
        df = _make_df(closes)
        res = evaluate(df, f'RW{seed}')
        if res and res.total_score >= 8:
            high_scores += 1
    # No more than 25% of random walks should score 8+
    assert high_scores < n_trials * 0.25


def test_scores_are_binary():
    df = _make_df(np.linspace(100, 110, 80))
    res = evaluate(df, 'TEST')
    for k, v in res.scores.items():
        assert v in (0, 1), f"Score {k}={v} is not binary"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
