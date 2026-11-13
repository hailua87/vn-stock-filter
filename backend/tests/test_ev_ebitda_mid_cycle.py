"""
Canh nhánh CYCLICAL của `methods_ev_ebitda` không phóng EBITDA lên một chiều.

Lỗi gốc: `ebitda_used = max(ba ứng viên)`, trong đó ứng viên thứ ba là
`revenue × normalized_ebitda_margin` với margin lấy từ
`data['cyclical_info']['normalized_ebitda_margin']` — một khoá KHÔNG module nào
gán, nên nó luôn rơi về hằng số mặc định 0,10.

Hệ quả đo trên rổ cache 16/10/2026 (35 mã cyclical): 19 mã lấy
`doanh thu × 10%` làm `ebitda_used`, và 19 mã đó trùng khớp hoàn toàn với 19 mã
có biên EBITDA thật dưới 10%. Biên thật càng mỏng thì phóng càng mạnh —
DHM biên 0,45% được định giá trên EBITDA gấp 22,45 lần số thật; TTF biên 2,91%
gấp 3,44 lần, và TTF có upside công bố +243,7% với EV/EBITDA trọng số 50%.

Nặng hơn cả phóng: hai mã EBITDA ÂM (ABS −513,6 tỷ, DTL −79,3 tỷ) được ứng viên
doanh thu kéo lên dương nên LỌT qua cổng `ebitda_used <= 0`, và vẫn ra một mức
giá hợp lý cho doanh nghiệp đang lỗ ở mức EBITDA.

Bản sửa: `ebitda_used = 0,50 × ebitda_5y_avg + 0,50 × ebitda_ttm`. Tổ hợp lồi
của hai ước lượng từ BCTC nên luôn nằm giữa chúng, không lệch một chiều, và giữ
dấu âm.

Mọi phép kiểm đi qua entrypoint `calculate_ev_ebitda_valuation` (CLAUDE.md §6),
KHÔNG gọi hàm nội bộ nào. Các khoản mục BCTC đều TỶ ĐỒNG (§2); giá là ĐỒNG.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner import peer_database
from scanner.strategies.valuation.normalizer import normalize_fundamentals
from scanner.strategies.valuation.methods_ev_ebitda import (
    calculate_ev_ebitda_valuation,
)

SHARES = 1_000_000_000  # tròn 1 tỷ cp

# Hình TTF, đã làm tròn: doanh thu lớn, EBITDA mỏng.
# Biên EBITDA thật = 300/12.000 = 2,5% ⇒ `doanh thu × 10%` = 1.200 tỷ, tức gấp
# 4 lần EBITDA thật. Đây là hình mà bản cũ phóng mạnh nhất.
BIEN_MONG = dict(revenue=12_000.0, operating_profit=200.0, loi_nhuan=150.0)

# Hình HPG: biên dày, `doanh thu × 10%` nằm DƯỚI EBITDA thật nên bản cũ không
# nhả. Giữ để chứng minh bản sửa không làm xáo trộn nhóm này.
BIEN_DAY = dict(revenue=10_000.0, operating_profit=2_400.0, loi_nhuan=2_000.0)

# EBITDA âm cả ở kỳ gần nhất và trung bình 5 năm — phải bị TỪ CHỐI định giá.
EBITDA_AM = dict(revenue=2_000.0, operating_profit=-700.0, loi_nhuan=-600.0)

DEP = 100.0  # khấu hao, tỷ đồng


def _raw(hinh, loi_nhuan_5y=None, current_price=20_000):
    """BCTC tối thiểu đủ cho `normalize_fundamentals`. Khoản mục: TỶ ĐỒNG.

    `ebitda_ttm` = operating_profit + khấu hao (normalizer.py:455).
    `ebitda_5y_avg` = trung bình lợi nhuận cổ đông mẹ 5 năm + khấu hao
    (normalizer.py:460-463) — công thức khác, xem ghi chú trong PR.
    """
    lai = list(loi_nhuan_5y) if loi_nhuan_5y is not None else [hinh['loi_nhuan']] * 5
    return {
        'ticker': 'TEST',
        'current_price': current_price,
        'overview': {'industry': 'Thép', 'outstanding_share': SHARES},
        'balance_sheet': [{
            'owner_s_equity': 8_000, 'total_assets': 16_000,
            'cash': 1_000, 'short_term_borrowings': 2_000,
            'long_term_borrowings': 3_000, 'minority_interests': 0,
        }],
        'income': [
            {'net_profit_for_the_year': p, 'revenue': hinh['revenue'],
             'operating_profit': hinh['operating_profit'],
             'attributable_to_parent_company': p}
            for p in lai
        ],
        'cash_flow': [{
            'depreciation_and_amortisation': DEP,
            'net_cash_inflows_outflows_from_operating_activities': 1_000,
            'purchase_of_fixed_assets': -500,
            'dividends_paid': -100,
        } for _ in range(5)],
        'ratio': [],
    }


def _data(hinh, loi_nhuan_5y=None, current_price=20_000, industry='Steel_Metals'):
    d = normalize_fundamentals(_raw(hinh, loi_nhuan_5y, current_price))
    assert d is not None
    d['_industry'] = industry
    return d


@pytest.fixture(autouse=True)
def _peer_on_dinh(monkeypatch):
    """Ghim bội số MỤC TIÊU để mọi phép kiểm dưới đây chỉ đo phía MẪU SỐ.

    Không ghim thì bội số đến từ `peer_multiples.json` (conftest đã trỏ sang
    tmp_path, nên rỗng) và rơi về bảng mặc định theo ngành — vẫn chạy được,
    nhưng khi ai đó đổi bảng mặc định thì các phép kiểm này đổi theo mà lỗi
    chẳng liên quan gì tới EBITDA.
    """
    monkeypatch.setattr(
        peer_database, 'get_peer_band',
        lambda industry, metric: ({'median': 6.0, 'p25': 5.0, 'p75': 7.0, 'n': 8}
                                  if metric == 'ev_ebitda' else None))


# ── 1. Tiền đề: fixture thật sự dựng được hình "biên mỏng" ───────────────
# Không có phép kiểm này thì các phép kiểm dưới chỉ chứng minh "biên dày thì
# không phóng" và xanh rỗng.
def test_fixture_dung_duoc_bien_mong():
    cf = _data(BIEN_MONG)['cash_flow']
    rev = _data(BIEN_MONG)['income']['revenue']
    assert cf['ebitda_ttm'] == pytest.approx(300.0)      # 200 + 100
    assert cf['ebitda_5y_avg'] == pytest.approx(250.0)   # 150 + 100
    # Biên thật 2,5% — dưới hằng số 0,10, tức nằm đúng vùng bản cũ nhả.
    assert cf['ebitda_ttm'] / rev < 0.10
    # Và `doanh thu × 10%` phải CAO hơn cả hai ước lượng từ BCTC, nếu không
    # thì `max` của bản cũ cũng không chọn nó và phép kiểm 2 xanh rỗng.
    assert rev * 0.10 > max(cf['ebitda_ttm'], cf['ebitda_5y_avg'])


# ── 2. Phép kiểm chính: EBITDA dùng để định giá không bị doanh thu phóng ──
def test_bien_mong_khong_bi_nhanh_doanh_thu_phong():
    """`ebitda_used` phải nằm GIỮA hai ước lượng từ BCTC, không theo doanh thu.

    Bản cũ: max(250, 275, 1.200) = 1.200 (= doanh thu × 10%).
    Bản sửa: 0,5 × 250 + 0,5 × 300 = 275.
    """
    data = _data(BIEN_MONG)
    r = calculate_ev_ebitda_valuation(data, is_cyclical=True)

    ttm = data['cash_flow']['ebitda_ttm']
    avg5 = data['cash_flow']['ebitda_5y_avg']
    used = r.key_inputs['ebitda_used']

    assert used == pytest.approx(0.50 * avg5 + 0.50 * ttm)
    assert used == pytest.approx(275.0)
    # Chốt chặn độc lập với công thức: không được vượt ước lượng cao nhất từ
    # BCTC. Bản cũ ra 1.200 nên đỏ ở đây kể cả khi công thức trộn đổi sau này.
    assert used <= max(ttm, avg5) + 1e-9, (
        f"ebitda_used {used:,.1f} vượt cả hai ước lượng từ BCTC "
        f"(ttm {ttm:,.1f}, 5y {avg5:,.1f}) → đang bị một nhánh khác phóng lên")
    # Và doanh thu × 10% không được là câu trả lời.
    assert used != pytest.approx(data['income']['revenue'] * 0.10)


def test_he_so_phong_so_voi_ebitda_that_bi_chan():
    """Hệ số `ebitda_used / ebitda_ttm` phải quanh 1, không phải 4x.

    Đo cùng một thước trước/sau trên cùng fixture: bản cũ 4,00x, bản sửa 0,92x.
    """
    data = _data(BIEN_MONG)
    r = calculate_ev_ebitda_valuation(data, is_cyclical=True)
    he_so = r.key_inputs['ebitda_used'] / data['cash_flow']['ebitda_ttm']
    assert he_so < 1.25, f"EBITDA định giá gấp {he_so:.2f}x EBITDA thật"


def test_fair_value_bien_mong_khong_bi_thoi():
    """Hệ quả cuối: fair value và upside phải xuống theo.

    Bản cũ với fixture này: EV = 6,0 × 1.200 = 7.200 tỷ → FV 3.200 đ/cp.
    Bản sửa:               EV = 6,0 × 275  = 1.650 tỷ → FV âm, tức mã này
    không có giá trị vốn chủ sau khi trừ nợ ròng — và đó là câu trả lời đúng
    cho một doanh nghiệp EBITDA 300 tỷ đang nợ ròng 4.000 tỷ.
    """
    data = _data(BIEN_MONG)
    r = calculate_ev_ebitda_valuation(data, is_cyclical=True)
    ev = r.key_outputs['enterprise_value']
    assert ev == pytest.approx(6.0 * 275.0)
    # Nợ ròng 4.000 tỷ (2.000 + 3.000 − 1.000) lớn hơn EV ⇒ equity âm.
    assert r.key_outputs['equity_value'] < 0
    assert r.fair_value_per_share < data['market']['current_price']


# ── 3. EBITDA âm phải bị TỪ CHỐI, không được nhánh doanh thu hồi sinh ────
def test_ebitda_am_bi_tu_choi_dinh_gia():
    """ABS/DTL: EBITDA âm cả hai kỳ ⇒ không định giá được bằng EV/EBITDA.

    Bản cũ: max(−500, −550, 200) = 200 ⇒ lọt cổng, ra một mức giá hợp lý cho
    doanh nghiệp đang lỗ ở mức EBITDA.
    """
    data = _data(EBITDA_AM)
    assert data['cash_flow']['ebitda_ttm'] < 0        # tiền đề
    assert data['cash_flow']['ebitda_5y_avg'] < 0
    assert data['income']['revenue'] * 0.10 > 0       # nhánh cũ sẽ ra số dương

    r = calculate_ev_ebitda_valuation(data, is_cyclical=True)
    assert r.fair_value_per_share == 0
    assert r.confidence == 0.0
    assert any('EBITDA <= 0' in w for w in r.warnings)


# ── 4. Không xáo trộn nhóm biên dày và nhánh stable ─────────────────────
def test_bien_day_khong_doi():
    """Biên dày: `doanh thu × 10%` vốn đã nằm dưới, nên nhóm này không đổi."""
    data = _data(BIEN_DAY)
    ttm = data['cash_flow']['ebitda_ttm']        # 2.500
    avg5 = data['cash_flow']['ebitda_5y_avg']    # 2.100
    assert data['income']['revenue'] * 0.10 < min(ttm, avg5)   # tiền đề

    r = calculate_ev_ebitda_valuation(data, is_cyclical=True)
    # Bản cũ cũng ra bản trộn ở đây (max chọn ttm_blended), nên con số TRÙNG.
    assert r.key_inputs['ebitda_used'] == pytest.approx(0.50 * avg5 + 0.50 * ttm)
    assert r.key_inputs['ebitda_used'] == pytest.approx(2_300.0)


def test_nhanh_stable_van_dung_ebitda_ky_gan_nhat():
    """`is_cyclical=False` không đi qua chỗ sửa — phải vẫn là EBITDA kỳ gần nhất."""
    data = _data(BIEN_MONG)
    r = calculate_ev_ebitda_valuation(data, is_cyclical=False)
    assert r.key_inputs['ebitda_used'] == pytest.approx(
        data['cash_flow']['ebitda_ttm'])


# ── 5. Khoá cấu hình chết đã bị bỏ, không âm thầm sống lại ──────────────
def test_khong_con_doc_normalized_ebitda_margin():
    """`cyclical_info.normalized_ebitda_margin` không còn ảnh hưởng kết quả.

    Chính một khoá không ai gán đã để hằng số 0,10 sống im lặng. Nếu ai đó đưa
    lại nhánh `doanh thu × margin`, phép kiểm này đỏ — kể cả khi họ đặt margin
    "hợp lý".
    """
    data = _data(BIEN_MONG)
    khong_co = calculate_ev_ebitda_valuation(data, is_cyclical=True)

    data_co = _data(BIEN_MONG)
    data_co['cyclical_info'] = {'normalized_ebitda_margin': 0.25}
    co = calculate_ev_ebitda_valuation(data_co, is_cyclical=True)

    assert (co.key_inputs['ebitda_used']
            == pytest.approx(khong_co.key_inputs['ebitda_used']))


def test_ghi_chu_noi_dung_mid_cycle_la_tron_khong_phai_max():
    """`notes` là chỗ duy nhất người đọc thấy EBITDA nào đã được dùng."""
    r = calculate_ev_ebitda_valuation(_data(BIEN_MONG), is_cyclical=True)
    ghi_chu = ' | '.join(r.notes)
    assert 'mid-cycle' in ghi_chu
    assert 'Chọn max' not in ghi_chu
    assert 'rev×margin' not in ghi_chu
