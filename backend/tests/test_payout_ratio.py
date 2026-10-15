"""
Canh `payout_ratio` — khoá từng im lặng bằng 0,0 cho 100% rổ.

Lỗi gốc: `normalizer` có `ratios.setdefault('payout_ratio', 0.30)`, nhưng vòng
lặp ratio ngay trên đã gán khoá này cho MỌI mã (thiếu dữ liệu thì `_safe_float`
trả 0.0), nên `setdefault` là MÃ CHẾT — không bao giờ chạy. Cộng thêm việc bảng
`ratio` của VCI không còn được lấy từ 26/09/2026, payout_ratio là 0,0 ở mọi mã.

Hệ quả đã đo (15/10/2026, 200 mã): `justified_pe = payout/(coe-g) = 0` nên cấu
phần 30% trọng số bị loại khỏi blend P/E ở TOÀN BỘ rổ, và `dps = eps × 0 = 0`.

Trọng tâm của bộ kiểm này là PHÂN BIỆT hai thứ mà bản cũ gộp làm một:
  - "không trả cổ tức"  → payout = 0,0 là ĐÚNG
  - "thiếu dữ liệu"     → payout = 0,0 là SAI, phải là None
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner.strategies.valuation.normalizer import normalize_fundamentals
from scanner.strategies.valuation.methods_pe import calculate_pe_valuation
from scanner.strategies.valuation.methods_pb_roe import calculate_pb_roe_valuation
from scanner.strategies.valuation.methods_dcf_ddm import calculate_ddm

# Số cổ phiếu tròn 1 tỷ để eps/dps ra số tròn: lợi nhuận (tỷ đồng) × 1e9 / 1e9
SHARES = 1_000_000_000


def _raw(net_profit=5_000.0, dividends_paid=-1_500.0, no_cash_flow=False,
         ratio_payout=None, current_price=30_000, profits=None):
    """
    Mọi khoản mục BCTC ở đây là TỶ ĐỒNG (CLAUDE.md §2), giá là ĐỒNG/cp.

    `dividends_paid=None` = bảng lưu chuyển tiền tệ KHÔNG có dòng cổ tức.
    `no_cash_flow=True`   = không có bảng lưu chuyển tiền tệ nào cả.
    `profits`             = chuỗi lợi nhuận 5 năm (mới nhất trước); mặc định
                            PHẲNG để payout = |cổ tức| / lợi nhuận ra số tròn.

    NĂM KỲ ở CẢ HAI bảng, vì payout nay tính trên TỔNG nhiều năm: số kỳ dùng
    được là `min(len(lưu chuyển), len(kết quả))`, nên bảng lưu chuyển chỉ có
    một dòng sẽ âm thầm biến phép kiểm "nhiều năm" thành phép kiểm một năm.
    Đã mắc đúng bẫy này khi viết bộ kiểm.
    """
    cf = {
        'depreciation_and_amortisation': 1_200,
        'net_cash_inflows_outflows_from_operating_activities': 6_000,
        'purchase_of_fixed_assets': -2_000,
    }
    if dividends_paid is not None:
        cf['dividends_paid'] = dividends_paid

    ratio_row = {'eps': 5_000, 'bvps': 30_000, 'roe': 17.0, 'pb': 1.0, 'pe': 6.0}
    if ratio_payout is not None:
        ratio_row['payout_ratio'] = ratio_payout

    lai = list(profits) if profits else [net_profit] * 5
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
        'cash_flow': [] if no_cash_flow else [dict(cf) for _ in range(5)],
        # Bảng ratio rỗng = đúng thực tế production từ 26/09/2026
        'ratio': [ratio_row] if ratio_payout is not None else [],
    }


# Chuỗi lợi nhuận TĂNG TRƯỞNG — cần cho các phép kiểm mà payout chỉ đổi được
# kết quả khi g > 0 (xem test_pb_roe_khong_bia_payout_khi_thieu).
PROFITS_TANG = [5_000.0, 4_500.0, 4_000.0, 3_600.0, 3_200.0]


# ── 1. Suy từ dữ liệu thật, không phải 0,0 cũng không phải 0,30 ──────────
def test_payout_suy_tu_luu_chuyen_tien_te():
    """
    Cổ tức đã trả 1.500 tỷ / lợi nhuận cổ đông mẹ 5.000 tỷ = 30%.

    Bản cũ cho 0,0 ở đây vì bảng ratio rỗng — và `setdefault(0.30)` không cứu
    được vì khoá đã tồn tại.
    """
    d = normalize_fundamentals(_raw())
    assert d['ratios']['payout_ratio'] == pytest.approx(0.30)
    assert d['ratios']['payout_source'] == 'cash_flow_5y'


def test_payout_khong_bao_gio_la_mac_dinh_0_30():
    """
    0,30 phải không xuất hiện như một mặc định âm thầm. Mã thật trả 20% thì
    payout là 0,20 — nếu thấy đúng 0,30 nghĩa là mặc định đã lẻn vào.
    """
    d = normalize_fundamentals(_raw(dividends_paid=-1_000.0))
    assert d['ratios']['payout_ratio'] == pytest.approx(0.20)
    assert d['ratios']['payout_ratio'] != 0.30


# ── 2. PHÂN BIỆT: không trả cổ tức ≠ thiếu dữ liệu ───────────────────────
def test_khong_tra_co_tuc_thi_0_la_so_that():
    """
    Bảng lưu chuyển tiền tệ luôn materialize dòng `dividends_paid` (ô trống =
    0), nên mã không trả cổ tức TIỀN MẶT cho 0 đúng nghĩa — kèm nguồn
    'cash_flow_5y' để phân biệt với thiếu dữ liệu.
    """
    d = normalize_fundamentals(_raw(dividends_paid=0.0))
    assert d['ratios']['payout_ratio'] == 0.0
    assert d['ratios']['payout_source'] == 'cash_flow_5y'


@pytest.mark.parametrize('kw, vi_sao', [
    ({'net_profit': -500.0}, 'lỗ: mẫu số âm làm payout vô nghĩa'),
    ({'no_cash_flow': True}, 'không có bảng lưu chuyển tiền tệ'),
])
def test_thieu_du_lieu_thi_None_chu_khong_phai_0(kw, vi_sao):
    """
    Thiếu dữ liệu KHÔNG được thành 0,0 — vì 0,0 là một phát biểu THẬT ("không
    trả cổ tức") mà ta không có cơ sở để nói. Và cũng không được thành 0,30.
    """
    d = normalize_fundamentals(_raw(**kw))
    assert d['ratios']['payout_ratio'] is None, vi_sao
    assert d['ratios']['payout_source'] == 'unavailable', vi_sao


def test_bang_ratio_co_payout_thi_uu_tien_bang_ratio():
    """Bảng ratio trả về (hiện không xảy ra ở production) thì vẫn phải thắng."""
    d = normalize_fundamentals(_raw(ratio_payout=45.0))
    assert d['ratios']['payout_ratio'] == pytest.approx(0.45)
    assert d['ratios']['payout_source'] == 'reported'


# ── 2b. Lấy NHIỀU NĂM, không lấy một năm ─────────────────────────────────
def _raw_nam_xau_cuoi():
    """
    Lợi nhuận năm gần nhất sụt còn 100 tỷ nhưng cổ tức vẫn trả 1.500 tỷ từ lợi
    nhuận giữ lại — payout MỘT NĂM = 15,0 (1.500%).

    Đây là HAX thật: đo 15/10/2026 cho payout một năm 23,18 và justified_pe
    207x. Một con số như vậy vào blend với 30% trọng số còn tệ hơn bị loại.
    """
    r = _raw()
    r['income'][0]['net_profit_for_the_year'] = 100.0
    r['income'][0]['attributable_to_parent_company'] = 100.0
    return r


def test_payout_lay_nhieu_nam_nen_mot_nam_xau_khong_lam_no():
    d = normalize_fundamentals(_raw_nam_xau_cuoi())
    p = d['ratios']['payout_ratio']
    # Một năm sẽ là 1.500/100 = 15,0. Tổng 5 năm thì mẫu số còn các năm lành.
    assert p < 1.0, f'payout {p} — có vẻ đang tính một năm thay vì nhiều năm'
    assert d['ratios']['payout_source'] == 'cash_flow_5y'


def test_justified_pe_khong_bi_mot_nam_xau_keo_len_vo_ly():
    """Hệ quả thật của việc lấy một năm: justified P/E 207x."""
    res = calculate_pe_valuation(normalize_fundamentals(_raw_nam_xau_cuoi()))
    assert res.key_outputs['justified_pe'] < 30


def test_payout_vuot_100_phan_tram_bi_chan_tran_va_ghi_ra():
    """
    payout > 100% không duy trì được vĩnh viễn, mà Gordon là mô hình vĩnh viễn.
    Chặn về 1,0 — nhưng PHẢI ghi vào nguồn, trần tàng hình là trần không kiểm
    được. Còn 10/200 mã vượt 1,0 kể cả sau khi tính 5 năm (cao nhất 2,10).
    """
    r = _raw()
    for row in r['cash_flow']:
        row['dividends_paid'] = -9_000.0      # 9.000 tỷ cổ tức / 5.000 tỷ lợi nhuận
    d = normalize_fundamentals(r)
    assert d['ratios']['payout_ratio'] == 1.0
    assert d['ratios']['payout_source'] == 'cash_flow_5y_capped'


# ── 3. Bẫy đơn vị (CLAUDE.md §2) ─────────────────────────────────────────
def test_hai_duong_suy_payout_khong_lech_nhau():
    """
    payout tính bằng TỶ ĐỒNG (cổ tức/lợi nhuận) phải bằng payout tính bằng
    ĐỒNG/CP (dps/eps), vì hai vế cùng chia cho số cổ phiếu.

    Lệch nhau = có người đổi đơn vị một vế mà quên vế kia — đúng loại lỗi
    không làm test đỏ ở kho này.
    """
    d = normalize_fundamentals(_raw())
    tu_ty_dong = d['ratios']['payout_ratio']
    tu_dong_tren_cp = d['per_share']['dps_ttm'] / d['per_share']['eps_ttm']
    assert tu_ty_dong == pytest.approx(tu_dong_tren_cp, rel=1e-9)


# ── 4. Hạ nguồn: justified P/E ───────────────────────────────────────────
def test_justified_pe_co_mat_khi_suy_duoc_payout():
    """
    Đây là phép kiểm chính của lỗi: bản cũ cho justified_pe = 0 ở MỌI mã nên
    cấu phần 30% trọng số bị loại khỏi blend mà không ai thấy.
    """
    res = calculate_pe_valuation(normalize_fundamentals(_raw()))
    assert res.key_outputs['justified_pe'] > 0
    assert any('justified' in n.lower() for n in res.notes)


def test_justified_pe_bi_loai_khi_thieu_payout():
    """Thiếu payout thì cấu phần phải VẮNG MẶT (None), không phải bằng 0."""
    res = calculate_pe_valuation(normalize_fundamentals(_raw(no_cash_flow=True)))
    assert res.key_outputs['justified_pe'] is None
    assert any('loại cấu phần justified' in n for n in res.notes)


def test_payout_doi_thi_fair_value_pe_doi():
    """
    Nếu payout không thật sự đi vào kết quả thì hai mức chi trả rất khác nhau
    vẫn cho cùng một fair value — đúng như bản cũ (0,0 ở cả hai).
    """
    it = calculate_pe_valuation(normalize_fundamentals(_raw(dividends_paid=-500.0)))
    nhieu = calculate_pe_valuation(normalize_fundamentals(_raw(dividends_paid=-3_000.0)))
    assert it.fair_value_per_share != pytest.approx(nhieu.fair_value_per_share, rel=1e-6)


# ── 5. payout None không được làm nổ method nào ──────────────────────────
@pytest.mark.parametrize('ten, fn', [
    ('pe', calculate_pe_valuation),
    ('pb_roe', calculate_pb_roe_valuation),
    ('ddm', calculate_ddm),
])
def test_method_khong_no_khi_payout_None(ten, fn):
    """
    payout None đi qua số học (so sánh, format %, `.get(..., g)`) là nổ ngay.
    Đã bắt được UnboundLocalError thật ở `methods_pe` khi viết bộ kiểm này.
    """
    d = normalize_fundamentals(_raw(no_cash_flow=True))
    res = fn(d)   # không được raise
    assert res.fair_value_per_share >= 0


def test_pb_roe_khong_bia_payout_khi_thieu():
    """
    Mô hình 2-stage của P/B KHÔNG loại được cấu phần cổ tức (nó là cấu trúc của
    công thức), nên nó phải dùng payout NGỤ Ý suy từ g và ROE — chứ không lẳng
    lặng thay bằng 0,30.

    Lỗ hổng thật: khi viết bộ kiểm này, `payout = ratios.get(...) or 0.30` ở
    `methods_pb_roe` làm cả 14 phép kiểm vẫn XANH. `key_inputs` là chỗ duy nhất
    đọc được payout mà method thật sự đã dùng, nên phải chốt ở đó.
    """
    thieu = calculate_pb_roe_valuation(normalize_fundamentals(
        _raw(no_cash_flow=True, profits=PROFITS_TANG)))
    assert thieu.key_inputs['payout_ratio'] is None

    # ...và payout phải THẬT SỰ đi vào kết quả khi nó CHẶN được payout ngụ ý.
    #
    # HAI cái bẫy xanh-rỗng ở phép kiểm này, cả hai đều đã mắc khi viết nó:
    #
    # 1. `payout_implied = max(payout, 1 - g1/ROE)`, nên payout CHỈ đổi được
    #    kết quả khi nó vượt đẳng thức. Với bộ số tăng trưởng này đẳng thức cho
    #    ~55%: đo được cả ba trường hợp None/0,20/0,50 đều ra đúng 40.678,80.
    # 2. Chuỗi lợi nhuận PHẲNG cho g = 0 ⇒ đẳng thức = 1 - 0/ROE = 1,0, tức
    #    payout không bao giờ vượt được. Phải dùng chuỗi tăng trưởng.
    #
    # Tổng cổ tức 5 × 3.654 = 18.270 trên tổng lợi nhuận 20.300 = 90%.
    co = calculate_pb_roe_valuation(normalize_fundamentals(
        _raw(dividends_paid=-3_654.0, profits=PROFITS_TANG)))
    assert co.key_inputs['payout_ratio'] == pytest.approx(0.90)
    assert co.fair_value_per_share != pytest.approx(thieu.fair_value_per_share, rel=1e-6)


def test_ddm_khong_bia_co_tuc_khi_thieu_payout():
    """
    DDM định giá CHÍNH dòng cổ tức, nên mặc định 0,30 ở đó biến một con số bịa
    thành "fair value". Thiếu payout thì DDM phải tự loại mình (fv = 0).
    """
    res = calculate_ddm(normalize_fundamentals(_raw(no_cash_flow=True)))
    assert res.fair_value_per_share == 0
