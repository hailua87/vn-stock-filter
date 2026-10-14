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


# ── Invariant ở cấp BÁO CÁO, tức đi qua `value_ticker` ─────────────────────
#
# Phép kiểm `test_pb_implied_by_fair_value_is_sane` ở trên canh đúng chuyện này
# nhưng chỉ đọc `normalize_fundamentals(...)` — nó KHÔNG BAO GIỜ đi qua
# `value_ticker`, nên mọi lỗi đơn vị phát sinh TRONG engine đều lọt.
#
# Và mọi assert về upside ở cấp báo cáo trong kho đều MỘT CHIỀU
# (`test_valuation_quality_fixes.py:194` và `:211` là `assert upside_pct > 0.5`).
# Một upside phồng 1.431 lần vẫn thoả `> 0.5`.
#
# Đo thật 14/10/2026: bọc `vnd_to_quote()` quanh `current_price` ở
# `engine.py` — đúng dạng lỗi đã gây `+98.600%` ghi trong docstring
# `price_units.py` — thì 60 phép kiểm của bốn tệp test định giá VẪN XANH, trong
# khi `upside_pct` ra `+331.475,9%` thay vì `+231,6%`.

def _bao_cao_FPT():
    """Fixture phi tài chính có sẵn, đủ khoản mục để nhiều phương pháp chạy."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_valuation_quality_fixes import _raw
    from scanner.strategies.valuation import value_ticker
    raw = _raw('FPT', overview={'industry': 'Computer Services',
                                'outstanding_share': 1_000_000_000})
    raw['current_price'] = 66_400.0
    return value_ticker('FPT', raw_fundamentals=raw, enrich_market_metrics=False)


def test_upside_tong_hop_nam_TRONG_dai_upside_cua_tung_phuong_phap():
    """
    `fair_value` là trung bình CÓ TRỌNG SỐ của fair value từng phương pháp, nên
    nó nằm trong [min, max] của chúng. `upside = (fv − cp) / cp` đơn điệu theo
    `fv`, nên upside tổng hợp cũng phải nằm trong dải upside của các phương
    pháp — VỚI ĐIỀU KIỆN mọi bên dùng CÙNG MỘT `current_price`.

    Đó chính là điều kiện bị phá khi đơn vị lệch: upside cấp phương pháp tính
    bằng đồng (`methods_pb_roe.py` dùng `market["current_price"]` trực tiếp),
    còn upside tổng hợp tính bằng nghìn đồng. Phép kiểm HAI CHIỀU này đỏ ngay,
    còn `> 0.5` thì không.
    """
    r = _bao_cao_FPT()
    d = r.to_dict()
    ups = [m['upside_pct'] for m in d['method_details']]
    assert len(ups) >= 2, (
        f'fixture chỉ có {len(ups)} phương pháp — phép kiểm này cần ít nhất 2 '
        f'để có dải, nếu không nó xanh rỗng')
    # Biên 0,5 điểm phần trăm cho việc làm tròn trong `to_dict`.
    assert min(ups) - 0.5 <= d['upside_pct'] <= max(ups) + 0.5, (
        f"upside tổng hợp {d['upside_pct']}% nằm NGOÀI dải của các phương pháp "
        f"[{min(ups)}%, {max(ups)}%] — dấu hiệu `current_price` ở engine lệch "
        f"đơn vị so với `current_price` mà từng phương pháp dùng")


def test_bao_cao_phat_ra_fair_value_va_gia_CUNG_thang():
    """
    Bốn trường tiền trong `to_dict` phải cùng đơn vị đồng. Phát `current_price`
    bằng nghìn đồng cạnh `fair_value` bằng đồng là phá hợp đồng dữ liệu với
    `web/valuation/valuation.js` — nó in hai số đó trong CÙNG một bảng.
    """
    from scanner.price_units import MAX_PLAUSIBLE_PRICE_VND, MIN_PLAUSIBLE_PRICE_VND
    d = _bao_cao_FPT().to_dict()
    for truong in ('current_price', 'fair_value', 'fair_value_low', 'fair_value_high'):
        v = d[truong]
        assert MIN_PLAUSIBLE_PRICE_VND <= v <= MAX_PLAUSIBLE_PRICE_VND, (
            f'{truong}={v:,.0f} ngoài dải hợp lý cho đồng/cp '
            f'[{MIN_PLAUSIBLE_PRICE_VND}, {MAX_PLAUSIBLE_PRICE_VND}] — '
            f'nhiều khả năng quên hoặc lặp phép quy đổi 1.000')
    # Tỷ lệ giữa fair value và giá phải hợp lý: lệch 1000 lần thì không.
    ty = d['fair_value'] / d['current_price']
    assert 0.01 < ty < 100, f'fair_value / current_price = {ty:,.1f} — sai đơn vị'


def test_upside_tung_phuong_phap_tinh_LAI_DUOC_tu_chinh_bao_cao():
    """
    Phép kiểm chứa-trong-dải ở trên CÓ GIỚI HẠN, và giới hạn đó tìm ra bằng
    cách phá: nếu MỘT phương pháp báo upside lệch đơn vị thì nó chỉ làm DẢI NỞ
    RA, không đẩy upside tổng hợp ra ngoài dải — nên phép kiểm kia vẫn xanh.

    Chỗ này so chéo: `upside_pct` của từng phương pháp phải tính lại được từ
    `fair_value` của chính nó và `current_price` của báo cáo. Ba số đều có trong
    cùng một `to_dict()`, nên không cần biết đơn vị là gì — chỉ cần chúng NHẤT
    QUÁN với nhau. Một phép quy đổi lẻ ở bất kỳ đâu trong chuỗi đều phá đẳng
    thức này.
    """
    d = _bao_cao_FPT().to_dict()
    cp = d['current_price']
    assert cp > 0
    for m in d['method_details']:
        mong = (m['fair_value'] - cp) / cp * 100
        assert m['upside_pct'] == pytest.approx(mong, abs=0.6), (
            f"{m['method']}: upside_pct={m['upside_pct']}% nhưng tính lại từ "
            f"fair_value={m['fair_value']:,.0f} và current_price={cp:,.0f} ra "
            f"{mong:.1f}% — ba số này không nhất quán, dấu hiệu quy đổi lẻ")
