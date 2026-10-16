"""
Canh lỗi SỐ PHỨC khi ROE âm trong `methods_pe`.

Lỗi gốc: `quality_factor = (sustainable_roe / peer_roe) ** 0.5`. Trong Python
luỹ thừa 0,5 của một số âm KHÔNG raise — nó trả về số phức:

    (-2.0) ** 0.5  ==  (8.6e-17+1.414j)

Số phức đó đi tiếp vào `peer_pe`, rồi nổ ở bước blend tại phép so sánh
`if v and v > 0` với `TypeError: '>' not supported between instances of
'complex' and 'int'`. Engine bọc từng method trong try/except nên ngoại lệ
không làm cả lượt chạy chết — nó chỉ LẶNG LẼ bỏ cấu phần P/E khỏi fair value,
để lại một dòng `✗ P/E Multiple failed` lẫn trong tối đa 8 `notes` của mã đó.

`sustainable_roe` âm khi doanh nghiệp lỗ: nó là trung bình trimmed của
`income['roe_5y']`, hoặc `ratios['roe_ttm']` khi chưa đủ 3 năm.

Bộ kiểm này canh HAI nhánh — nhánh có peer DB (quality vs peer ROE) và nhánh
VN-Index fallback (quality vs 15%) — vì nhánh nào chạy phụ thuộc vào việc
`backend/data/peer_multiples.json` có tồn tại hay không, tức một lượt chạy
thật có thể đi đường khác hẳn lượt chạy test.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner import peer_database
from scanner.strategies.valuation.normalizer import normalize_fundamentals
from scanner.strategies.valuation.methods_pe import (
    calculate_pe_valuation, quality_factor_roe,
)
from scanner.strategies.valuation.methods_pb_roe import calculate_pb_roe_valuation

SHARES = 1_000_000_000  # tròn 1 tỷ cp → eps = lợi nhuận(tỷ)×1e9/1e9 ra số tròn

# Lợi nhuận 5 năm, TỶ ĐỒNG (CLAUDE.md §2), mới nhất trước.
LAI = [5_000.0, 4_500.0, 4_000.0, 3_600.0, 3_200.0]
LO = [-50.0, -120.0, -80.0, -200.0, -60.0]            # lỗ cả 5 năm → ROE 5y < 0
LO_ROI_LAI = [5_000.0, -120.0, -80.0, -200.0, -60.0]  # mới hồi: EPS TTM > 0


def _raw(profits=None, current_price=30_000):
    """BCTC tối thiểu đủ cho normalize + định giá. Khoản mục: TỶ ĐỒNG.

    Một dòng balance sheet là đủ: `roe_history_from_statements` ghép theo khoá
    `period`, mà cả hai bảng ở đây đều không có khoá đó → cùng khớp `None`, nên
    mọi năm dùng chung vốn chủ sở hữu 30.000 tỷ. ROE từng năm = lợi nhuận/30.000.
    """
    lai = list(profits) if profits is not None else list(LAI)
    return {
        'ticker': 'TEST',
        'current_price': current_price,
        'overview': {'industry': 'Công nghệ', 'outstanding_share': SHARES},
        'balance_sheet': [{
            'owner_s_equity': 30_000, 'total_assets': 60_000,
            'cash': 5_000, 'short_term_borrowings': 3_000,
            'long_term_borrowings': 7_000, 'minority_interests': 500,
        }],
        'income': [
            {'net_profit_for_the_year': p, 'revenue': 40_000,
             'operating_profit': 6_000, 'attributable_to_parent_company': p}
            for p in lai
        ],
        'cash_flow': [{
            'depreciation_and_amortisation': 1_200,
            'net_cash_inflows_outflows_from_operating_activities': 6_000,
            'purchase_of_fixed_assets': -2_000,
            'dividends_paid': -1_500,
        } for _ in range(5)],
        'ratio': [],   # bảng ratio của VCI không còn được lấy từ 26/09/2026
    }


def _data(profits=None, industry='Technology'):
    d = normalize_fundamentals(_raw(profits))
    assert d is not None
    d['_industry'] = industry
    return d


def _co_peer_db(monkeypatch, pe_median=14.0, roe_median=0.18):
    """Giả lập `peer_multiples.json` có dữ liệu → nhánh peer DB được chạy.

    Phải vá trên `scanner.peer_database` (không phải trên module methods_pe),
    vì `methods_pe` import `get_peer_band` BÊN TRONG hàm mỗi lượt gọi.
    """
    def fake(industry, metric):
        if metric == 'pe':
            return {'median': pe_median, 'p25': 10.0, 'p75': 18.0, 'n': 12}
        if metric == 'roe':
            return {'median': roe_median, 'p25': 0.12, 'p75': 0.22, 'n': 12}
        return None
    monkeypatch.setattr(peer_database, 'get_peer_band', fake)


def _khong_peer_db(monkeypatch):
    """Không có peer DB → `methods_pe` rơi vào nhánh VN-Index fallback."""
    monkeypatch.setattr(peer_database, 'get_peer_band', lambda i, m: None)


# ── 1. Tiền đề: fixture thật sự dựng được sustainable_roe âm ─────────────
# Không có nó thì mọi phép kiểm dưới đây xanh rỗng — chúng sẽ chỉ chứng minh
# "ROE dương thì không nổ".
@pytest.mark.parametrize('profits,am', [
    (LAI, False), (LO, True), (LO_ROI_LAI, True),
])
def test_fixture_dung_duoc_roe_am(profits, am):
    roe_5y = _data(profits)['income']['roe_5y']
    assert len(roe_5y) >= 3, f"chỉ có {len(roe_5y)} năm ROE, trimmed mean không chạy"
    s = sorted(roe_5y)
    trimmed = s[1:-1] if len(s) >= 5 else s
    sustainable_roe = sum(trimmed) / len(trimmed)
    assert (sustainable_roe < 0) is am, f"sustainable_roe = {sustainable_roe}"


def test_fixture_lo_roi_lai_co_eps_ttm_duong():
    """Mã mới hồi phục: ROE 5y âm NHƯNG EPS TTM dương.

    Quan trọng vì nếu EPS TTM <= 0 thì `confidence` bị ép về 0 và cấu phần P/E
    rụng khỏi phép trộn dù sao — lúc đó lỗi số phức không đổi fair value, và
    phép kiểm không nói được gì về hậu quả thật.
    """
    d = _data(LO_ROI_LAI)
    assert d['per_share']['eps_ttm'] > 0


# ── 2. ROE âm không được làm hàm nổ, và không được ra số phức ───────────
@pytest.mark.parametrize('co_peer', [True, False], ids=['peer_db', 'vnindex'])
@pytest.mark.parametrize('profits', [LO, LO_ROI_LAI], ids=['lo_5y', 'lo_roi_lai'])
def test_roe_am_khong_no(monkeypatch, co_peer, profits):
    if co_peer:
        _co_peer_db(monkeypatch)
    else:
        _khong_peer_db(monkeypatch)

    r = calculate_pe_valuation(_data(profits))   # bản cũ: TypeError ở đây

    for ten, v in r.key_outputs.items():
        assert not isinstance(v, complex), f"key_outputs[{ten}] là số phức: {v!r}"
    for ten, v in r.key_inputs.items():
        assert not isinstance(v, complex), f"key_inputs[{ten}] là số phức: {v!r}"
    assert not isinstance(r.fair_value_per_share, complex)
    assert not isinstance(r.upside_pct, complex)


@pytest.mark.parametrize('co_peer', [True, False], ids=['peer_db', 'vnindex'])
def test_roe_am_loai_cau_phan_peer(monkeypatch, co_peer):
    """Loại tường minh, KHÔNG bịa số.

    `peer_pe` phải là None — không phải 0 (một "P/E mục tiêu 0x" lọt vào
    `key_outputs` và `notes` thì người đọc không phân biệt được "không tính
    được" với "tính ra bằng 0"), và dĩ nhiên không phải `abs()` (ROE −20% hoá
    chất lượng y như +20%).
    """
    if co_peer:
        _co_peer_db(monkeypatch)
    else:
        _khong_peer_db(monkeypatch)

    r = calculate_pe_valuation(_data(LO_ROI_LAI))
    assert r.key_outputs['peer_pe'] is None
    assert any('ROE' in w and 'peer' in w.lower() for w in r.warnings), r.warnings
    # Phần còn lại của blend vẫn phải chạy, không rụng theo
    assert r.key_outputs['target_pe'] > 0
    assert r.fair_value_per_share > 0


# ── 3. Chặn sửa quá tay: ROE dương vẫn phải được điều chỉnh chất lượng ──
def test_roe_duong_van_dieu_chinh_chat_luong(monkeypatch):
    """Nếu ai đó "sửa" bằng cách kẹp quality_factor về 1,0 cho mọi mã thì
    peer_pe hoá bằng đúng peer median — phép kiểm này đỏ."""
    _co_peer_db(monkeypatch, pe_median=14.0, roe_median=0.18)
    r = calculate_pe_valuation(_data(LAI))
    sroe = r.key_inputs['sustainable_roe']
    assert sroe > 0
    cho_doi = 14.0 * (sroe / 0.18) ** 0.5
    assert r.key_outputs['peer_pe'] == pytest.approx(cho_doi, rel=1e-9)
    assert r.key_outputs['peer_pe'] != pytest.approx(14.0, rel=1e-6)


# ── 4. Hàm trợ giúp, kiểm trực tiếp ─────────────────────────────────────
@pytest.mark.parametrize('roe,benchmark,cho_doi', [
    (0.18, 0.18, 1.0),              # ngang ngành
    (0.36, 0.09, 2.0),              # ROE gấp 4 lần → quality 2x
    (-0.05, 0.18, None),            # ROE âm → không tính được
    (0.0, 0.18, None),              # ROE 0 → cũng không
    (None, 0.18, None),             # thiếu dữ liệu
    (0.18, 0.0, 1.0),               # thiếu mốc tham chiếu → không điều chỉnh
    (0.18, None, 1.0),
    (0.18, -0.05, 1.0),             # mốc tham chiếu âm → cũng không điều chỉnh
])
def test_quality_factor_roe(roe, benchmark, cho_doi):
    ket_qua = quality_factor_roe(roe, benchmark)
    if cho_doi is None:
        assert ket_qua is None
    else:
        assert not isinstance(ket_qua, complex)
        assert ket_qua == pytest.approx(cho_doi)


# ── 5. Mã chị em: `methods_pb_roe` cũng dùng sustainable_roe ────────────
def test_pb_roe_khong_no_khi_roe_am():
    """`methods_pb_roe` đã có floor 3% nên không ra số phức — phép kiểm này
    canh để floor đó không bị bỏ đi mà không ai biết."""
    r = calculate_pb_roe_valuation(_data(LO))
    assert not isinstance(r.fair_value_per_share, complex)
    for ten, v in r.key_outputs.items():
        assert not isinstance(v, complex), f"key_outputs[{ten}] là số phức: {v!r}"
