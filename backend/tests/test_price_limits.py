"""
Test biên độ trần/sàn — thông tin quyết định lệnh có khớp được hay không.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner.price_limits import band_for, classify_price_limit


def _df(prev_close, close, high=None, low=None):
    high = high if high is not None else max(prev_close, close) * 1.001
    low = low if low is not None else min(prev_close, close) * 0.999
    return pd.DataFrame({
        'Date': pd.to_datetime(['2026-08-11', '2026-08-12']),
        'Open': [prev_close, close], 'High': [prev_close, high],
        'Low': [prev_close, low], 'Close': [prev_close, close],
        'Volume': [1_000_000, 1_000_000],
    })


# ── Biên độ theo sàn ──────────────────────────────────────────────────────
def test_bands():
    assert band_for('HOSE') == 0.07
    assert band_for('HNX') == 0.10
    assert band_for('UPCOM') == 0.15
    assert band_for('upcom') == 0.15       # không phân biệt hoa thường
    assert band_for(None) == 0.07          # không rõ sàn → dùng mức chặt nhất


# ── Trần ──────────────────────────────────────────────────────────────────
def test_hose_ceiling():
    r = classify_price_limit(_df(100, 107), 'HOSE')
    assert r['limit_status'] == 'ceiling'
    assert r['change_1d_pct'] == pytest.approx(7.0, abs=0.01)
    assert 'TRẦN' in r['tradable_warning']


def test_hose_ceiling_with_tick_rounding():
    """Giá khớp làm tròn theo bước giá nên hiếm khi đúng 7,00%."""
    r = classify_price_limit(_df(100, 106.8), 'HOSE')
    assert r['limit_status'] == 'ceiling'


def test_locked_ceiling_detected():
    """Trần CỨNG: cả phiên chỉ khớp một mức giá → gần như chắc chắn không mua được."""
    r = classify_price_limit(_df(100, 107, high=107, low=107), 'HOSE')
    assert r['limit_status'] == 'ceiling'
    assert r['limit_locked'] is True
    assert 'khoá cứng' in r['tradable_warning']


def test_hnx_ceiling_is_10pct_not_7():
    """+8% trên HNX chưa phải trần (biên 10%), nhưng trên HOSE thì vượt trần."""
    assert classify_price_limit(_df(100, 108), 'HNX')['limit_status'] != 'ceiling'
    assert classify_price_limit(_df(100, 108), 'HOSE')['limit_status'] == 'ceiling'


def test_upcom_band_15pct():
    assert classify_price_limit(_df(100, 112), 'UPCOM')['limit_status'] != 'ceiling'
    assert classify_price_limit(_df(100, 115), 'UPCOM')['limit_status'] == 'ceiling'


# ── Sàn ───────────────────────────────────────────────────────────────────
def test_floor():
    r = classify_price_limit(_df(100, 93), 'HOSE')
    assert r['limit_status'] == 'floor'
    assert 'SÀN' in r['tradable_warning']
    assert 'không thoát được hàng' in r['tradable_warning']


# ── Các trạng thái khác ───────────────────────────────────────────────────
def test_near_ceiling_warns_about_liquidity():
    r = classify_price_limit(_df(100, 105.5), 'HOSE')   # +5,5% ≈ 79% biên độ
    assert r['limit_status'] == 'near_ceiling'
    assert 'Sát giá trần' in r['tradable_warning']


def test_reference_price():
    r = classify_price_limit(_df(100, 100), 'HOSE')
    assert r['limit_status'] == 'reference'
    assert r['tradable_warning'] is None


def test_normal_has_no_warning():
    r = classify_price_limit(_df(100, 102), 'HOSE')
    assert r['limit_status'] == 'normal'
    assert r['tradable_warning'] is None
    assert r['change_1d_pct'] == pytest.approx(2.0, abs=0.01)


# ── Trường hợp biên ───────────────────────────────────────────────────────
def test_insufficient_history():
    df = _df(100, 105).head(1)
    assert classify_price_limit(df, 'HOSE')['limit_status'] == 'unknown'


def test_none_dataframe():
    assert classify_price_limit(None, 'HOSE')['limit_status'] == 'unknown'


def test_zero_prev_close_does_not_crash():
    assert classify_price_limit(_df(0, 10), 'HOSE')['limit_status'] == 'unknown'


# ── Tích hợp với strategy ─────────────────────────────────────────────────
def test_criteria_exposes_limit_status():
    """Tín hiệu Pre-Breakout phải mang theo trạng thái trần/sàn."""
    import numpy as np
    from scanner.criteria import evaluate

    n = 120
    rng = np.random.default_rng(0)
    close = 20 * np.cumprod(1 + 0.001 + rng.normal(0, 0.01, n))
    df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=n, freq='B'),
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99,
        'Close': close, 'Volume': np.full(n, 500_000), 'Exchange': 'HOSE',
    })
    res = evaluate(df, 'TEST')
    assert res is not None
    assert 'limit_status' in res.metrics
    assert 'change_1d_pct' in res.metrics
    assert 'm_limit_status' in res.to_dict()
