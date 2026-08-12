"""
Invariant test cho đơn vị giá — chặn tái phát lỗi 1000× của valuation engine.

Bối cảnh: vnstock trả OHLCV theo nghìn VND (ACB = 24.30) còn EPS/BVPS theo VND
(EPS = 3.500). Trước fix, fair_value (VND) bị so với current_price (nghìn VND)
→ upside +98.600%.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner.price_units import (
    VND_PER_QUOTE_UNIT,
    quote_to_vnd,
    vnd_to_quote,
    assert_price_is_vnd,
)
from scanner.strategies.valuation.normalizer import normalize_fundamentals


def _raw_fundamentals(current_price):
    """Bộ fundamentals tối thiểu để normalize_fundamentals chạy được."""
    return {
        'ticker': 'TEST',
        'current_price': current_price,
        'overview': {'industry': 'Ngân hàng', 'outstanding_share': 1_000_000_000},
        'balance_sheet': [{'owner_s_equity': 30_000, 'total_assets': 300_000,
                           'cash': 5_000, 'short_term_borrowings': 1_000,
                           'long_term_borrowings': 2_000}],
        'income': [{'net_profit_for_the_year': 5_000, 'revenue': 20_000,
                    'operating_profit': 6_000}],
        'cash_flow': [{'depreciation_and_amortisation': 500}],
        'ratio': [{'eps': 5_000, 'bvps': 30_000, 'roe': 18.0, 'pb': 1.2}],
    }


# ── Quy đổi cơ bản ────────────────────────────────────────────────────────
def test_quote_to_vnd():
    assert quote_to_vnd(24.3) == 24_300
    assert quote_to_vnd(137.3) == 137_300
    assert quote_to_vnd(None) is None


def test_roundtrip():
    assert vnd_to_quote(quote_to_vnd(24.3)) == pytest.approx(24.3)
    assert VND_PER_QUOTE_UNIT == 1_000


# ── Guard tại biên ────────────────────────────────────────────────────────
def test_assert_rejects_quote_units():
    """24.3 là giá nghìn VND — phải bị chặn, không được lọt vào engine."""
    with pytest.raises(ValueError, match='quote'):
        assert_price_is_vnd(24.3, 'ACB')


def test_assert_accepts_vnd():
    assert assert_price_is_vnd(24_300, 'ACB') == 24_300
    assert assert_price_is_vnd(1_050_000, 'VCF') == 1_050_000


def test_assert_rejects_absurdly_high():
    with pytest.raises(ValueError):
        assert_price_is_vnd(24_300_000, 'BUG')


# ── Invariant xuyên suốt normalizer ───────────────────────────────────────
def test_normalizer_rejects_quote_price():
    with pytest.raises(ValueError):
        normalize_fundamentals(_raw_fundamentals(24.3))


def test_normalizer_accepts_vnd_price():
    data = normalize_fundamentals(_raw_fundamentals(24_300))
    assert data is not None
    assert data['market']['current_price'] == 24_300


def test_market_cap_in_billion_vnd_is_sane():
    """1 tỷ cp × 24.300đ = 24.300 tỷ. Trước fix con số này ra 24,3 tỷ."""
    data = normalize_fundamentals(_raw_fundamentals(24_300))
    assert data['market']['market_cap'] == pytest.approx(24_300, rel=1e-6)


def test_pb_implied_by_fair_value_is_sane():
    """
    fair_value tính từ BVPS (VND) phải cùng thang với current_price.
    Đây chính là phép so sánh đã sai 1000× trước fix.
    """
    data = normalize_fundamentals(_raw_fundamentals(24_300))
    bvps = data['per_share']['bvps']
    price = data['market']['current_price']
    implied_pb = price / bvps
    assert 0.05 < implied_pb < 20, f"P/B ngụ ý {implied_pb} — sai đơn vị"
