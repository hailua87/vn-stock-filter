"""
Test market regime + relative strength — hai thứ quyết định alpha mà scanner
trước đây hoàn toàn không có (fetch_vnindex và relative_strength đều là dead code).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from scanner.market_regime import (
    compute_regime,
    compute_breadth,
    compute_relative_strength,
    annotate_results,
)


def _index_df(trend: float, days: int = 300, start: float = 1000.0):
    """Chuỗi index với xu hướng tuyến tính `trend` %/phiên."""
    dates = pd.date_range('2025-01-01', periods=days, freq='B')
    close = start * (1 + trend) ** np.arange(days)
    return pd.DataFrame({'Date': dates, 'Close': close})


def _stock_df(trend: float, days: int = 300, start: float = 20.0):
    dates = pd.date_range('2025-01-01', periods=days, freq='B')
    close = start * (1 + trend) ** np.arange(days)
    return pd.DataFrame({
        'Date': dates, 'Open': close, 'High': close * 1.01,
        'Low': close * 0.99, 'Close': close,
        'Volume': np.full(days, 500_000),
    })


# ── Regime ────────────────────────────────────────────────────────────────
def test_uptrend_is_risk_on():
    regime = compute_regime(_index_df(0.001))
    assert regime['available'] is True
    assert regime['regime'] == 'risk_on'
    assert regime['above_ma50'] and regime['above_ma200'] and regime['ma50_rising']
    assert regime['position_size_multiplier'] == 1.0


def test_downtrend_is_risk_off():
    regime = compute_regime(_index_df(-0.001))
    assert regime['regime'] == 'risk_off'
    assert not regime['above_ma50']
    # Gợi ý co mạnh tỷ trọng — đây là điểm cả hệ thống đang thiếu
    assert regime['position_size_multiplier'] < 0.5


def test_missing_index_is_handled():
    regime = compute_regime(None)
    assert regime['available'] is False
    assert regime['regime'] == 'unknown'
    assert regime['position_size_multiplier'] == 1.0    # không tự ý phạt khi thiếu dữ liệu


def test_drawdown_reported():
    regime = compute_regime(_index_df(-0.001))
    assert regime['drawdown_from_high_pct'] < 0


# ── Breadth ───────────────────────────────────────────────────────────────
def test_breadth_all_above():
    by_ticker = {f'T{i}': _stock_df(0.002) for i in range(5)}
    breadth = compute_breadth(by_ticker)
    assert breadth['pct_above_ma50'] == 100.0
    assert breadth['sample_size'] == 5


def test_breadth_mixed():
    by_ticker = {'UP1': _stock_df(0.002), 'UP2': _stock_df(0.002),
                 'DOWN1': _stock_df(-0.002), 'DOWN2': _stock_df(-0.002)}
    breadth = compute_breadth(by_ticker)
    assert breadth['pct_above_ma50'] == 50.0


def test_breadth_skips_short_history():
    by_ticker = {'SHORT': _stock_df(0.002, days=10)}
    breadth = compute_breadth(by_ticker)
    assert breadth['sample_size'] == 0


# ── Relative strength ─────────────────────────────────────────────────────
def test_leader_beats_laggard():
    index_df = _index_df(0.0005)
    by_ticker = {'LEADER': _stock_df(0.002), 'LAGGARD': _stock_df(-0.001)}
    rs = compute_relative_strength(by_ticker, index_df)

    assert rs['LEADER']['rs_score'] > 0     # khoẻ hơn thị trường
    assert rs['LAGGARD']['rs_score'] < 0    # yếu hơn thị trường
    assert rs['LEADER']['rs_rank'] > rs['LAGGARD']['rs_rank']


def test_rs_rank_within_1_99():
    index_df = _index_df(0.0005)
    by_ticker = {f'T{i}': _stock_df(0.0005 + i * 0.0003) for i in range(10)}
    rs = compute_relative_strength(by_ticker, index_df)
    for v in rs.values():
        assert 1 <= v['rs_rank'] <= 99


def test_rs_empty_without_index():
    assert compute_relative_strength({'A': _stock_df(0.001)}, None) == {}


def test_annotate_results_attaches_rs():
    class FakeResult:
        def __init__(self, ticker):
            self.ticker = ticker
            self.metrics = {}

    results = [FakeResult('LEADER'), FakeResult('UNKNOWN')]
    rs_map = {'LEADER': {'rs_score': 12.3, 'rs_rank': 88, 'rs_63d': 9.1}}
    annotate_results(results, rs_map)

    assert results[0].metrics['rs_rank'] == 88
    assert 'rs_rank' not in results[1].metrics    # không bịa dữ liệu cho mã thiếu
