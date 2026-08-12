"""
Test các sửa lỗi logic của valuation engine.

Trọng tâm là chống TÁI PHÁT ba lỗi tư duy đã làm "fair value" mất ý nghĩa:
  1. Circularity — fair value tự kéo về giá thị trường
  2. Bội số mục tiêu là hằng số ẩn (EV/EBITDA luôn 6.0x)
  3. Cắt fair value về bội số của giá rồi vẫn coi là ý kiến độc lập
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner.strategies.valuation.normalizer import normalize_fundamentals
from scanner.strategies.valuation.engine import (
    _determine_verdict,
    _method_dispersion,
    MARGIN_OF_SAFETY,
    MAX_METHOD_DISPERSION,
)
from scanner.strategies.valuation.methods_pe import calculate_pe_valuation, PE_FLOOR, PE_CEILING
from scanner.strategies.valuation.methods_ev_ebitda import INDUSTRY_DEFAULT_EV_EBITDA


def _raw(current_price=30_000, dividend_yield=5.0, with_history=False):
    raw = {
        'ticker': 'TEST',
        'current_price': current_price,
        'overview': {'industry': 'Công nghệ', 'outstanding_share': 1_000_000_000},
        'balance_sheet': [{
            'owner_s_equity': 30_000, 'total_assets': 60_000,
            'cash': 5_000, 'short_term_borrowings': 3_000,
            'long_term_borrowings': 7_000, 'minority_interests': 500,
        }],
        'income': [
            {'net_profit_for_the_year': 5_000, 'revenue': 40_000, 'operating_profit': 6_000},
            {'net_profit_for_the_year': 4_500, 'revenue': 36_000, 'operating_profit': 5_400},
            {'net_profit_for_the_year': 4_000, 'revenue': 33_000, 'operating_profit': 4_800},
            {'net_profit_for_the_year': 3_600, 'revenue': 30_000, 'operating_profit': 4_300},
            {'net_profit_for_the_year': 3_200, 'revenue': 27_000, 'operating_profit': 3_900},
        ],
        'cash_flow': [{'depreciation_and_amortisation': 1_200,
                       'net_cash_inflows_outflows_from_operating_activities': 6_000,
                       'purchase_of_fixed_assets': -2_000}],
        'ratio': [{'eps': 5_000, 'bvps': 30_000, 'roe': 17.0, 'pb': 1.0, 'pe': 6.0,
                   'dividend_yield': dividend_yield, 'payout_ratio': 30.0}],
    }
    if with_history:
        raw['historical_multiples'] = {
            'fallback': False,
            'pe_5y_median': 12.0, 'pe_5y_p25': 10.0, 'pe_5y_p75': 15.0,
            'pb_5y_median': 1.8, 'pb_5y_p25': 1.4, 'pb_5y_p75': 2.2,
        }
    return raw


# ── 1. CIRCULARITY ────────────────────────────────────────────────────────
def test_no_historical_proxy_from_current_multiple():
    """
    Thiếu historical thật ⇒ pe_5y_median phải là None, KHÔNG được gán = pe_ttm.
    Gán như bản cũ khiến 'Historical Multiple' cho fair value đúng bằng giá
    thị trường (42.215 vs 42.000 trong output demo).
    """
    data = normalize_fundamentals(_raw())
    assert data['ratios']['pe_5y_median'] is None
    assert data['ratios']['pb_5y_median'] is None
    assert data['ratios']['_historical_multiples_source'] == 'unavailable'


def test_historical_used_when_real():
    data = normalize_fundamentals(_raw(with_history=True))
    assert data['ratios']['pe_5y_median'] == 12.0
    assert data['ratios']['_historical_multiples_source'] == 'computed'


def test_dps_not_derived_from_price():
    """
    DPS phải độc lập với giá. Bản cũ dùng `price × dividend_yield` nên DDM cho
    fair value tỷ lệ thuận với giá ⇒ upside gần như hằng số.
    """
    low = normalize_fundamentals(_raw(current_price=10_000))
    high = normalize_fundamentals(_raw(current_price=90_000))
    assert low['per_share']['dps_ttm'] == high['per_share']['dps_ttm']
    assert low['per_share']['dps_ttm'] > 0
    assert low['per_share']['dps_source'] == 'eps_x_payout'


def test_pe_fair_value_independent_of_price():
    """Fair value của P/E method không được đổi khi giá thị trường đổi."""
    cheap = calculate_pe_valuation(normalize_fundamentals(_raw(current_price=10_000)))
    rich = calculate_pe_valuation(normalize_fundamentals(_raw(current_price=90_000)))
    assert cheap.fair_value_per_share == pytest.approx(rich.fair_value_per_share, rel=1e-9)
    # ...nhưng upside thì phải khác nhau rõ rệt
    assert cheap.upside_pct > rich.upside_pct


# ── 2. EV/EBITDA không còn là hằng số ─────────────────────────────────────
def test_ev_ebitda_is_computed():
    data = normalize_fundamentals(_raw())
    ev_ebitda = data['ratios']['ev_ebitda']
    assert ev_ebitda is not None
    # EV = 30.000 (cap) + 5.000 (net debt) + 500 (MI) = 35.500; EBITDA = 7.200
    assert ev_ebitda == pytest.approx(35_500 / 7_200, rel=1e-6)


def test_ev_ebitda_feeds_peer_database():
    """peer_database.extract_peer_input trước đây luôn lấy None cho ev_ebitda."""
    from scanner.peer_database import extract_peer_input
    data = normalize_fundamentals(_raw())
    data['_industry'] = 'Technology'
    peer_input = extract_peer_input(data)
    assert peer_input['ev_ebitda'] is not None


def test_industry_defaults_differ():
    """Bội số mặc định phải khác nhau theo ngành, không phải 6.0x cho tất cả."""
    assert INDUSTRY_DEFAULT_EV_EBITDA['Technology'] > INDUSTRY_DEFAULT_EV_EBITDA['Steel_Metals']
    assert len(set(INDUSTRY_DEFAULT_EV_EBITDA.values())) > 5


# ── 3. Forward P/E không còn điểm gián đoạn ───────────────────────────────
def test_forward_pe_clamped():
    """
    Tăng trưởng 0,5% từng cho forward P/E = 0,4x rồi nhảy lên ~10x khi g = 0.
    Nay phải nằm trong dải hợp lý.
    """
    result = calculate_pe_valuation(normalize_fundamentals(_raw()))
    fwd_pe = result.key_outputs['forward_pe_peg']
    assert PE_FLOOR <= fwd_pe <= PE_CEILING


def test_peer_pe_is_in_the_blend():
    """
    peer_pe trước đây được tính đầy đủ rồi chỉ ghi vào key_outputs, không vào
    công thức target_pe. Kiểm tra bằng cách xác nhận target nằm trong bao lồi
    của các cấu phần và note có nhắc tới peer.
    """
    result = calculate_pe_valuation(normalize_fundamentals(_raw()))
    out = result.key_outputs
    parts = [out['justified_pe'], out['peer_pe'], out['forward_pe_peg']]
    assert min(parts) - 1e-6 <= out['target_pe'] <= max(parts) + 1e-6
    assert any('peer' in n.lower() for n in result.notes)


# ── 4. Verdict: biên an toàn + mâu thuẫn phương pháp ──────────────────────
def test_margin_of_safety_required_for_buy():
    """Upside 12% không đủ để khuyến nghị MUA — nằm trong sai số mô hình."""
    assert _determine_verdict(0.12) == 'HOLD'
    assert _determine_verdict(MARGIN_OF_SAFETY + 0.01) == 'BUY'
    assert _determine_verdict(0.50) == 'STRONG BUY'


def test_confidence_not_double_counted():
    """
    _determine_verdict không còn nhận confidence: nó đã được dùng làm trọng số
    khi tổng hợp fair value.
    """
    import inspect
    params = inspect.signature(_determine_verdict).parameters
    assert 'confidence' not in params


def test_dispersion_blocks_recommendation():
    """VHM demo: RNAV 115.870 vs P/E 27.878 → không được ra STRONG BUY."""
    dispersion = _method_dispersion([115_870, 81_752, 27_878, 42_215])
    assert dispersion > MAX_METHOD_DISPERSION
    assert _determine_verdict(0.86, dispersion) == 'HOLD'


def test_dispersion_zero_for_single_method():
    assert _method_dispersion([50_000]) == 0.0
    assert _method_dispersion([]) == 0.0


def test_consistent_methods_allow_buy():
    dispersion = _method_dispersion([50_000, 52_000, 48_000])
    assert dispersion < MAX_METHOD_DISPERSION
    assert _determine_verdict(0.30, dispersion) == 'BUY'
