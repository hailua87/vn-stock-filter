"""
Trình bày KHOẢNG khi các phương pháp định giá mâu thuẫn.

Nhóm mâu thuẫn (54/200 mã sau khi backfill OHLCV, 01/10/2026) không mở được:
dispersion trung vị 80%, engine nhân độ tin cậy với 0.5 nên 0/54 mã chạm ngưỡng
50%. Hạ ngưỡng để mở là gian. Việc làm được là NÓI RA bốn phương pháp cho khoảng
nào, thay vì chỉ in "Chưa có" rồi im lặng.

Hai điều test này giữ:
  1. Khoảng lấy min–max của `method_details`, KHÔNG lấy `fair_value_low/high`
     của engine — cái đó là phân vị 25/75 nên với 4 phương pháp nó cắt mất
     phương pháp thấp nhất, tức là che đúng cái cần cho thấy.
  2. Mức định giá vẫn là NOT_AVAILABLE. Đây là thay đổi trình bày, không phải
     thay đổi ngưỡng: khoảng rộng vẫn không chốt được một mức.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.quality.status import valuation_band
from test_quality_pipeline import _run, universe  # noqa: F401 (fixture)


def _conflict(fvs, dispersion=138.0, **extra):
    """Tín hiệu mâu thuẫn với fair value từng phương pháp (đơn vị đồng)."""
    return {'upside_pct': 12.0, 'confidence': 31.0, 'methods_conflict': True,
            'method_dispersion_pct': dispersion,
            'method_details': [{'method': f'M{i}', 'weight': 25, 'fair_value': v}
                               for i, v in enumerate(fvs)],
            **extra}


# --- Khoảng lấy từ đâu -------------------------------------------------------

def test_range_is_full_span_of_methods():
    # HPG 01/10: bốn phương pháp 11.300 / 17.800 / 18.300 / 36.400.
    b = valuation_band(_conflict([17_800, 11_300, 36_400, 18_300]))
    assert (b['range_low'], b['range_high']) == (11_300, 36_400)
    assert b['dispersion_pct'] == 138.0


def test_range_ignores_engine_quartile_band():
    # fair_value_low/high của engine là phân vị 25/75 — với 4 phương pháp thì
    # low = phần tử thứ hai, nên 11.300 bị cắt. Nếu lớp trình bày đọc hai
    # trường đó thì nó in 17.800–36.400 và người đọc tưởng không ai định giá
    # dưới 17.800.
    b = valuation_band(_conflict([17_800, 11_300, 36_400, 18_300],
                                 fair_value_low=17_800, fair_value_high=36_400))
    assert b['range_low'] == 11_300, 'khoảng phải là min các phương pháp, không phải phân vị 25'


def test_reason_states_both_ends_and_dispersion():
    b = valuation_band(_conflict([11_300, 36_400], dispersion=138.0))
    assert '11.300' in b['reason'] and '36.400' in b['reason']
    assert '138%' in b['reason']
    assert 'Chưa có' not in b['reason']


# --- Khoảng KHÔNG được tràn ra chỗ khác --------------------------------------

def test_band_stays_not_available_on_conflict():
    b = valuation_band(_conflict([11_300, 36_400]))
    assert b['band'] == 'NOT_AVAILABLE' and b['label'] == 'Chưa có'


def test_no_range_when_methods_agree():
    # Mã đã chốt được mức thì khoảng là nhiễu: nó sẽ làm "Hấp dẫn" trông như
    # còn tranh chấp.
    sig = {'upside_pct': 25.0, 'confidence': 70.0, 'methods_conflict': False,
           'method_details': [{'method': 'P/E Multiple', 'weight': 40, 'fair_value': 30_000},
                              {'method': 'DCF', 'weight': 60, 'fair_value': 34_000}]}
    b = valuation_band(sig)
    assert b['band'] == 'ATTRACTIVE'
    assert b['range_low'] is None and b['range_high'] is None


def test_keys_exist_even_without_signal():
    # Shape của JSON phải ổn định: web đọc v.range_low trên MỌI mã.
    for k in ('range_low', 'range_high', 'dispersion_pct'):
        assert k in valuation_band(None)


def test_falls_back_when_method_values_unusable():
    # fair_value = 0 nghĩa là phương pháp không ra được gì. Một giá trị dùng
    # được thì không thành khoảng.
    b = valuation_band(_conflict([0, 24_000]))
    assert b['range_low'] is None
    assert b['reason'] == 'Các phương pháp định giá mâu thuẫn'


# --- Đi tới được tệp chất lượng ---------------------------------------------

def test_quality_output_carries_the_range(universe):  # noqa: F811
    items, _, _ = _run(universe, valuation={'T01': _conflict([11_300, 36_400])})
    v = items['T01']['valuation']
    assert (v['range_low'], v['range_high']) == (11_300, 36_400)
    assert v['dispersion_pct'] == 138.0
    assert v['band'] == 'NOT_AVAILABLE'
