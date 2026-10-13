"""
Beta tính được nhưng VÔ NGHĨA THỐNG KÊ (13/10/2026).

Sau khi cache OHLCV được lưu lại (#73) và beta được ghi ra đầu ra (#80), lượt
weekly 11/10 cho thấy **84/84 mã có beta thật, 0 dự phòng**. Nghe như xong.

Nhưng R² trung vị là **0,162**, thấp nhất **0,008** — thị trường chỉ giải thích
~16% biến động của mã trung vị. Hồi quy yếu thì hệ số dốc có sai số lớn:

    SE(β) = |β| × sqrt((1 − R²) / (R² × (n − 2)))

Với DGC (số thật): β=0,83, R²=0,175, n=96 → SE=0,186, khoảng 95% [0,47 ; 1,20]
— **chứa 1,0**. Hồi quy không cho lý do nào để tin 0,83 hơn tin 1,0.
**35/84 mã (42%) rơi vào trường hợp này.**

Mã cũ trừ 5% độ tin cậy cho beta DỰ PHÒNG nhưng không trừ gì cho beta thật mà
vô nghĩa — tức **phạt sự trung thực và thưởng cho nhiễu**. 1,0 ít nhất là một
tiên nghiệm thành thật; 0,22 với R²=0,008 là một con số trông tự tin mà sai, và
nó đi thẳng vào WACC trong DCF.

Ngưỡng ở đây KHÔNG phải số áp đặt — nó là phép kiểm ý nghĩa thống kê chuẩn trên
chính dữ liệu đã có (R², n). Không có hằng số nào phải chọn.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import market_metrics as MM


def _gia(rets, start=100.0):
    gia = [start]
    for r in rets:
        gia.append(gia[-1] * math.exp(r))
    return gia


def _khung(n_tuan=120, beta=1.5, nhieu=0.0, seed=7):
    """
    Dựng giá tuần cho mã và chỉ số sao cho beta THẬT là `beta`, và `nhieu` điều
    khiển R²: nhiễu lớn -> R² thấp -> ước lượng yếu.
    """
    rnd = np.random.default_rng(seed)
    idx_ret = rnd.normal(0, 0.02, n_tuan)
    stock_ret = beta * idx_ret + rnd.normal(0, nhieu, n_tuan)
    ngay = pd.bdate_range('2024-01-05', periods=n_tuan, freq='W-FRI')
    return (pd.DataFrame({'Date': ngay, 'Close': _gia(stock_ret)[1:]}),
            pd.DataFrame({'Date': ngay, 'Close': _gia(idx_ret)[1:]}))


@pytest.fixture
def nguon(monkeypatch):
    """Thay hai hàm đọc cache bằng dữ liệu dựng sẵn."""
    def dat(beta, nhieu, n_tuan=120, seed=7):
        ma, idx = _khung(n_tuan=n_tuan, beta=beta, nhieu=nhieu, seed=seed)
        monkeypatch.setattr(MM, '_load_ohlcv_from_cache', lambda t, d=None: ma)
        monkeypatch.setattr(MM, '_load_vnindex', lambda d=None: idx)
    return dat


# ── Hồi quy mạnh: giữ nguyên ước lượng ──────────────────────────────────────

def test_hoi_quy_manh_thi_dung_uoc_luong(nguon):
    """Nhiễu ~0 -> R² gần 1 -> khoảng rất hẹp -> phải TIN ước lượng."""
    nguon(beta=1.8, nhieu=0.0005)
    b = MM.calculate_beta('X')
    assert b['fallback'] is False
    assert b['weak'] is False, f"R²={b['r_squared']} mà vẫn coi là yếu"
    assert b['r_squared'] > 0.9
    # Blume kéo về 1,0: 0,67×1,8 + 0,33 = 1,536
    assert b['beta'] == pytest.approx(0.67 * b['beta_raw'] + 0.33, abs=0.02)
    assert b['method'] == 'weekly_log_returns_blume_adjusted'


# ── Hồi quy yếu: trả về tiên nghiệm ─────────────────────────────────────────

def test_hoi_quy_yeu_thi_tra_ve_tien_nghiem_1(nguon):
    """
    Nhiễu lớn -> R² thấp -> khoảng chứa 1,0 -> KHÔNG được giả vờ biết.
    Đây là 42% số mã trong rổ thật.
    """
    nguon(beta=0.6, nhieu=0.06)
    b = MM.calculate_beta('X')
    assert b['fallback'] is False, 'vẫn tính được, không phải thiếu dữ liệu'
    assert b['weak'] is True
    assert b['beta'] == 1.0, 'phải trả về tiên nghiệm, không phải điểm ước lượng'
    assert b['method'] == 'weak_regression_prior'
    # `beta_raw` vẫn giữ để còn truy được
    assert b['beta_raw'] != 1.0


def test_weak_khac_fallback(nguon):
    """
    "Không tính được" và "tính được nhưng vô nghĩa" là HAI chuyện. Gộp chúng
    lại thì bản tổng hợp cả lượt nói sai: lượt 11/10 báo "84/84 beta thật" mà
    thực ra 35 trong số đó không phân biệt được với 1,0.
    """
    nguon(beta=0.6, nhieu=0.06)
    yeu = MM.calculate_beta('X')
    assert (yeu['fallback'], yeu['weak']) == (False, True)


def test_sai_so_chuan_duoc_ghi_ra(nguon):
    """Không ghi SE thì không ai kiểm lại được quyết định yếu/mạnh."""
    nguon(beta=0.6, nhieu=0.06)
    b = MM.calculate_beta('X')
    assert b['std_error'] is not None and b['std_error'] > 0
    du = 1.96 * b['std_error']
    assert b['beta_raw'] - du <= 1.0 <= b['beta_raw'] + du, 'SE phải khớp kết luận'


def test_cong_thuc_SE_dung_dung_bac_tu_do_n_tru_2(nguon):
    """
    Chốt chặn cho mọi phép kiểm trên: nếu SE tính sai thì chúng vẫn xanh, vì
    chúng chỉ đọc lại chính con số sai đó.

    Chọn R² trung bình (~0,25) là CÓ CHỦ Ý và phải giữ:
      • R² quá thấp (0,002): `r_squared` làm tròn 3 chữ số, mà công thức có
        1/R² nên sai số làm tròn nở ra tới 7% — phép kiểm thành vô dụng.
      • R² quá cao (0,99): SE teo về ~0,01, chênh lệch do bậc tự do rơi xuống
        dưới mức làm tròn — cũng không phân biệt được.
    Ở R²≈0,25: SE≈0,150, dùng `n` thay `n-2` lệch 0,00127 — gấp hơn hai lần
    sai số làm tròn 4 chữ số cộng sai số từ R² (≈0,00025). Chỗ này đo được.
    """
    # seed/nhiễu KHÔNG phải chọn bừa: cấu hình này cho SE=0,1292 — một giá
    # trị mà làm tròn 2 chữ số (0,13) lệch 8,9e-4, tức vượt sai số cho phép,
    # nên một lần hạ độ chính xác sẽ bị bắt. Cấu hình cũ (nhieu=0,03) cho
    # SE=0,149962, làm tròn 2 chữ số ra đúng 0,15: KHÔNG phân biệt được.
    nguon(beta=0.9, nhieu=0.025, seed=1)
    b = MM.calculate_beta('X')
    assert 0.15 < b['r_squared'] < 0.45, (
        f"R²={b['r_squared']} ra ngoài dải đo được — xem docstring, "
        f"phép kiểm này mất tác dụng ngoài dải đó")

    n = b['observations']
    def se(bac_tu_do):
        return abs(b['beta_raw']) * math.sqrt(
            (1 - b['r_squared']) / (b['r_squared'] * bac_tu_do))

    assert b['std_error'] == pytest.approx(se(n - 2), abs=5e-4)
    # Và PHẢI khác hẳn bản sai — nếu không, phép kiểm trên không phân biệt
    # được đúng/sai và chỉ là một phép làm tròn.
    assert abs(se(n - 2) - se(n)) > 1e-3, 'dải đo đã mất khả năng phân biệt'
    assert b['std_error'] != pytest.approx(se(n), abs=5e-4)
    # Và độ chính xác LƯU TRỮ phải đủ: nếu `std_error` bị làm tròn về 2 chữ
    # số thì chính phép kiểm này mất khả năng phân biệt n với n-2. Cấu hình
    # trên được chọn sao cho 2 chữ số là KHÔNG đủ.
    assert abs(round(se(n - 2), 2) - se(n - 2)) > 5e-4, (
        'cấu hình đã trôi: 2 chữ số lại vừa đủ, phép kiểm tự vô hiệu hoá')


def test_nguong_la_khoang_95pc_khong_phai_90pc(nguon):
    """
    Mọi phép kiểm khác đều ở xa biên nên không phân biệt được 1,96 với 1,64
    — đổi mức tin cậy mà cả bộ vẫn xanh. Lượt phá đã chứng minh đúng vậy.

    Cấu hình này nằm ĐÚNG GIỮA hai mức: β_raw=1,279 và SE=0,1592, nên
    z = |1,279 − 1| / 0,1592 = 1,75. Khoảng 95% (±1,96·SE) CHỨA 1,0 → yếu;
    khoảng 90% (±1,64·SE) thì KHÔNG → sẽ bị coi là mạnh.

    95% là mức dùng thống nhất cả kho — sổ theo dõi kết quả cũng 95%
    (CLAUDE.md mục 11). Hạ riêng chỗ này xuống 90% là lặng lẽ nới chuẩn.
    """
    nguon(beta=1.4, nhieu=0.03, seed=1)
    b = MM.calculate_beta('X')
    z = abs(b['beta_raw'] - 1.0) / b['std_error']
    assert 1.64 < z < 1.96, (
        f'z={z:.3f} ra ngoài khoảng giữa hai mức — cấu hình đã trôi và phép '
        f'kiểm này không còn phân biệt được 95% với 90%')
    assert b['weak'] is True, 'ở z=1,75 thì khoảng 95% vẫn chứa 1,0'
    assert b['beta'] == 1.0


# ── Cờ phải ĐI QUA được tới nơi dùng nó ─────────────────────────────────────

def _raw_co_beta(beta_info):
    """Bộ `raw` tối thiểu cho normalizer, khuôn lấy theo test_valuation_logic."""
    return {
        'ticker': 'TEST',
        'current_price': 30_000,
        'beta_info': beta_info,
        'overview': {'industry': 'Công nghệ', 'outstanding_share': 1_000_000_000},
        'balance_sheet': [{'owner_s_equity': 30_000, 'total_assets': 60_000}],
        'income': [{'net_profit_for_the_year': 5_000, 'revenue': 40_000,
                    'operating_profit': 6_000}],
        'cash_flow': [{'depreciation_and_amortisation': 1_200}],
        'ratio': [{'eps': 5_000, 'bvps': 30_000, 'roe': 17.0, 'pb': 1.0,
                   'pe': 6.0, 'dividend_yield': 5.0, 'payout_ratio': 30.0}],
    }


@pytest.mark.parametrize('beta_info,mong', [
    ({'beta': 1.0, 'weak': True, 'fallback': False, 'std_error': 0.2}, True),
    ({'beta': 1.4, 'weak': False, 'fallback': False, 'std_error': 0.05}, False),
    ({'beta': 1.0, 'weak': True, 'fallback': True, 'std_error': None}, True),
    ({}, True),          # không có beta_info -> coi như tệ nhất
])
def test_normalizer_dua_co_beta_weak_sang_market(beta_info, mong):
    """
    SEAM DỄ ĐỨT NHẤT, và lượt phá đầu tiên đã CHỨNG MINH nó đứt không ai biết:
    tôi thay `'beta_weak': beta_info.get('weak', True)` thành `False` cứng ở
    normalizer và **cả 11 phép kiểm vẫn xanh**. Hai đầu dây đều đúng, chỉ dây
    bị cắt — và trong production thì khoản trừ độ tin cậy không bao giờ nổ.
    """
    from scanner.strategies.valuation.normalizer import normalize_fundamentals
    data = normalize_fundamentals(_raw_co_beta(beta_info))
    assert data['market']['beta_weak'] is mong


def test_normalizer_dua_ca_sai_so_chuan_sang_market():
    """Không mang SE qua thì đầu ra JSON không có gì để người đọc kiểm lại."""
    from scanner.strategies.valuation.normalizer import normalize_fundamentals
    data = normalize_fundamentals(_raw_co_beta(
        {'beta': 1.0, 'weak': True, 'fallback': False, 'std_error': 0.1863}))
    assert data['market']['beta_std_error'] == pytest.approx(0.1863)


def test_engine_ghi_ca_weak_va_std_error_ra_dau_ra():
    """
    Seam thứ hai: `market` -> khối `beta` trong `latest.json`. Đứt chỗ này thì
    bản tổng hợp ba trạng thái đọc toàn `weak=False` và nói sai cả lượt.
    """
    from scanner.strategies.valuation.engine import _beta_info
    ra = _beta_info({'beta_2y': 1.0, 'beta_fallback': False, 'beta_weak': True,
                     'beta_r_squared': 0.175, 'beta_std_error': 0.18634,
                     'beta_method': 'weak_regression_prior'})
    assert ra['weak'] is True
    assert ra['std_error'] == pytest.approx(0.1863, abs=1e-9), 'phải giữ 4 chữ số'
    assert ra['method'] == 'weak_regression_prior'


def test_engine_mac_dinh_weak_khi_thieu_khoa():
    from scanner.strategies.valuation.engine import _beta_info
    assert _beta_info({'beta_2y': 1.0})['weak'] is True


# ── Ảnh hưởng tới độ tin cậy ────────────────────────────────────────────────

def _du_lieu_ngan_hang(**market_extra):
    """Bộ dữ liệu tối thiểu nhưng ĐỦ TỐT để mọi khoản trừ khác không kích hoạt.

    Mục đích: cô lập đúng một biến là cờ beta. Nếu thiếu `roe_5y` hay
    `pb_5y_median` thì độ tin cậy tụt vì lý do khác và phép so sánh dưới đây
    không nói được gì về beta.
    """
    market = {'current_price': 25_000.0, 'beta_2y': 1.0,
              'beta_fallback': False, 'beta_weak': False}
    market.update(market_extra)
    return {
        'ticker': 'TEST',
        '_industry': 'Banking',
        'market': market,
        'balance_sheet': {'car': 0.12},
        'ratios': {'roe_ttm': 0.18, 'payout_ratio': 0.30,
                   'pb_5y_median': 1.5, 'pb_5y_p25': 1.2, 'pb_5y_p75': 1.9,
                   'pb_current': 1.4},
        'growth': {'book_value_growth_3y': 0.12},
        'per_share': {'bvps': 18_000.0},
        'income': {'roe_5y': [0.17, 0.18, 0.18, 0.19, 0.18]},
    }


def _do_tin_cay(**market_extra):
    from scanner.strategies.valuation.methods_pb_roe import calculate_pb_roe_valuation
    return calculate_pb_roe_valuation(_du_lieu_ngan_hang(**market_extra)).confidence


def test_beta_tot_khong_bi_tru():
    """Mốc so sánh. Không có mốc thì ba phép kiểm dưới vô nghĩa."""
    assert _do_tin_cay() == pytest.approx(0.85, abs=1e-9)


def test_beta_du_phong_bi_tru_5pc():
    """Hành vi cũ, phải giữ."""
    assert _do_tin_cay(beta_fallback=True) == pytest.approx(0.80, abs=1e-9)


def test_beta_yeu_cung_bi_tru_5pc():
    """
    LỖI ĐƯỢC SỬA: bản cũ cho beta thật-mà-vô-nghĩa đi qua KHÔNG BỊ TRỪ, tức
    phạt sự trung thực và thưởng cho nhiễu. Một beta 1,0 vì thiếu dữ liệu bị
    trừ 5%, còn beta 0,22 với R²=0,008 thì không — và nó đi thẳng vào CoE.
    """
    assert _do_tin_cay(beta_weak=True) == pytest.approx(0.80, abs=1e-9)


def test_tru_mot_lan_khi_vua_du_phong_vua_yeu():
    """Hai cờ cùng bật là MỘT nguyên nhân, không phải hai. Trừ 10% là sai."""
    assert _do_tin_cay(beta_fallback=True, beta_weak=True) == pytest.approx(0.80, abs=1e-9)


def test_thieu_khoa_beta_thi_coi_nhu_te_nhat():
    """
    `market` không có khoá beta nào -> không được mặc định "tốt". Mặc định tốt
    nghĩa là mọi đường gọi quên truyền cờ đều lặng lẽ được thưởng.
    """
    du = _du_lieu_ngan_hang()
    del du['market']['beta_fallback']
    del du['market']['beta_weak']
    from scanner.strategies.valuation.methods_pb_roe import calculate_pb_roe_valuation
    assert calculate_pb_roe_valuation(du).confidence == pytest.approx(0.80, abs=1e-9)


# ── Bản tổng hợp cả lượt phải nói đúng ba trạng thái ────────────────────────

def test_tong_hop_tach_rieng_yeu_va_du_phong():
    """
    Lượt 11/10 báo "84/84 beta thật, 0 dự phòng" — đúng theo nghĩa hẹp mà
    GÂY NHẦM: 35 trong 84 không phân biệt được với 1,0. Bản tổng hợp phải nói
    được cả ba trạng thái, nếu không người đọc tin là đã xong.
    """
    from run_valuation import _tong_hop_beta
    signals = [
        {'beta': {'fallback': False, 'weak': False, 'r_squared': 0.42}},
        {'beta': {'fallback': False, 'weak': False, 'r_squared': 0.38}},
        {'beta': {'fallback': False, 'weak': True, 'r_squared': 0.02}},
        {'beta': {'fallback': True, 'weak': True, 'r_squared': 0.0}},
        {},                                  # mã không có beta
    ]
    t = _tong_hop_beta(signals)
    assert t['n'] == 4
    assert t['real'] == 2
    assert t['weak'] == 1
    assert t['fallback'] == 1
    assert t['real'] + t['weak'] + t['fallback'] == t['n'], 'ba trạng thái phải khít'


def test_tong_hop_thieu_khoa_weak_thi_dem_vao_o_YEU():
    """
    Chiều mặc định quan trọng: một nguồn beta mới quên gắn cờ `weak` thì phải
    rơi vào ô YẾU, không phải ô "thật". Mặc định ngược lại chính là dạng báo
    cáo sai đang được sửa ở đây — và lần sau sẽ không ai thấy nó.
    """
    from run_valuation import _tong_hop_beta
    t = _tong_hop_beta([{'beta': {'fallback': False, 'r_squared': 0.4}}])
    assert (t['real'], t['weak'], t['fallback']) == (0, 1, 0)
