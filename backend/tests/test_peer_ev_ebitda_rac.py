#!/usr/bin/env python3
"""
Canh hai tầng bảo vệ cho bội số MỤC TIÊU EV/EBITDA.

Lỗi thật đã xảy ra (lượt 200 mã 13/10/2026): ngành Technology có đúng 4 mã —
FPT 8,0x · CMG 9,2x · VTC 46,8x · UNI 2.723,9x (UNI: EV 351 tỷ / EBITDA
0,13 tỷ). Trung vị rổ = 28,0x, CAO HƠN bội số của cả hai mã lành. FPT nhận
bội số mục tiêu 28,0x với độ tin cậy 0,75 (cao nhất trong ba phương pháp),
fair value 226.134đ trên giá 58.000đ (+290%), và fair value tổng hợp +170%
đi thẳng vào latest.json (dưới trần công bố +200%).

Không phải lỗi đơn vị: EV và EBITDA đều tỷ đồng, đã soát riêng. Mẫu số thật
sự gần 0 (doanh thu UNI 4,5 tỷ trên vốn góp 426 tỷ).

Hai tầng, mỗi tầng tự đủ sức chặn lỗi này, và mỗi tầng có phép kiểm riêng:
  1. peer_database.loc_quan_sat_co_nghia — rác không được ĐẾM vào rổ
  2. methods_ev_ebitda.MAX_PEER_SPREAD   — rổ phân tán không được làm MỤC TIÊU
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanner.peer_database import build_peer_database
from scanner.strategies.valuation import methods_ev_ebitda as M


# Rổ Technology THẬT của lượt 13/10/2026, số đo lại từ cache ngày 16/10.
RO_TECHNOLOGY_THAT = [
    {'ticker': 'FPT', 'industry': 'Technology', 'pe': 11.66, 'pb': 1.9,
     'ev_ebitda': 8.02, 'roe': 0.26},
    {'ticker': 'CMG', 'industry': 'Technology', 'pe': 11.34, 'pb': 1.5,
     'ev_ebitda': 9.23, 'roe': 0.12},
    {'ticker': 'VTC', 'industry': 'Technology', 'pe': 12.34, 'pb': 1.1,
     'ev_ebitda': 46.83, 'roe': 0.07},
    # EBITDA 0,13 tỷ trên EV 351 tỷ — tỷ lệ nói về mẫu số, không về giá.
    {'ticker': 'UNI', 'industry': 'Technology', 'pe': None, 'pb': 0.9,
     'ev_ebitda': 2723.91, 'roe': 0.001},
]

# Dải peer THẬT đã nằm trong backend/data/peer_multiples.json ngày 13/10/2026.
DAI_PEER_VO = {'median': 28.0, 'p25': 8.89, 'p75': 749.09, 'mean': 729.99, 'n': 4}

# Dải peer lành: ngành Steel_Metals của cùng lượt chạy đó.
DAI_PEER_LANH = {'median': 8.63, 'p25': 6.33, 'p75': 9.28, 'mean': 9.51, 'n': 7}


# ─────────────────────────────────────────────────────────────────────────────
# TẦNG 1 — rác không được đếm vào rổ (đi qua entrypoint build_peer_database)
# ─────────────────────────────────────────────────────────────────────────────

def test_quan_sat_rac_khong_duoc_dem_vao_ro_peer():
    """UNI 2.723,9x phải bị loại TRƯỚC khi đếm, không chỉ bị cắt đuôi."""
    db = build_peer_database(RO_TECHNOLOGY_THAT)
    stats = db['industries']['Technology']['ev_ebitda']

    # Sau khi loại UNI chỉ còn 3 quan sát <= 60x; trung vị phải là 9,23 (CMG),
    # KHÔNG phải 28,0 — con số không mã nào trong rổ ở gần.
    assert stats is not None, "Rổ 3 mã lành vẫn phải cho peer stats"
    assert stats['n'] == 3, f"Phải còn đúng 3 quan sát, đang có {stats['n']}"
    assert stats['median'] == pytest.approx(9.23, abs=0.01), (
        f"Trung vị {stats['median']} — rác 2.723,9x vẫn đang đẩy thứ hạng")
    # p75 và mean cũng phải sạch: 749 và 730 là dấu vết của rác.
    assert stats['p75'] < 60, f"p75 = {stats['p75']} vẫn mang dấu vết rác"
    assert stats['mean'] < 60, f"mean = {stats['mean']} vẫn mang dấu vết rác"


def test_boi_so_cao_nhung_co_nghia_khong_bi_loai_oan():
    """Trần 60x không được cắt vào dải liên tục dưới 53x của rổ thật."""
    ro = [{'ticker': f'T{i}', 'industry': 'Healthcare', 'ev_ebitda': v}
          for i, v in enumerate([5.4, 6.5, 10.3, 44.5, 49.5])]
    stats = build_peer_database(ro)['industries']['Healthcare']['ev_ebitda']
    assert stats is not None
    # 44,5 và 49,5 là bội số cao nhưng EBITDA/EV > 2% — vẫn là quan sát thật.
    assert stats['n'] >= 3


def test_tran_chi_ap_cho_ev_ebitda():
    """pb/roe không có mẫu số tiến về 0 — đừng áp trần 60x lên chúng."""
    ro = [{'ticker': f'B{i}', 'industry': 'Banking', 'pe': 9.0 + i,
           'pb': 1.5, 'roe': 0.18} for i in range(4)]
    banking = build_peer_database(ro)['industries']['Banking']
    assert banking['pb'] is not None and banking['pb']['n'] == 4
    assert banking['roe'] is not None and banking['roe']['n'] == 4


# ─────────────────────────────────────────────────────────────────────────────
# TẦNG 2 — rổ phân tán không được làm bội số MỤC TIÊU
# ─────────────────────────────────────────────────────────────────────────────

def _mau_fpt():
    """Số thật của FPT, đủ cho calculate_ev_ebitda_valuation (tỷ đồng)."""
    return {
        'ticker': 'FPT',
        '_industry': 'Technology',
        'market': {'current_price': 58_000.0, 'shares_outstanding': 1_885_727_648},
        'balance_sheet': {'short_term_debt': 19_169.70, 'long_term_debt': 1_903.79,
                          'cash_and_equivalents': 10_522.11,
                          'minority_interest': 7_265.10},
        'ratios': {'ev_ebitda': 8.02},
        'cash_flow': {'ebitda_ttm': 15_865.85, 'ebitda_5y_avg': 9_583.30},
        'income': {'revenue': 62_000.0},
    }


def test_ro_peer_phan_tan_khong_duoc_lam_boi_so_muc_tieu(monkeypatch):
    """Dải peer VỠ thật (n=4, p75/p25 = 84) không được thành mục tiêu 28,0x."""
    monkeypatch.setattr('scanner.peer_database.get_peer_band',
                        lambda ind, metric='pe', peer_db=None: DAI_PEER_VO)

    kq = M.calculate_ev_ebitda_valuation(_mau_fpt(), is_cyclical=False)
    muc_tieu = kq.key_outputs['target_multiple']

    assert muc_tieu != pytest.approx(28.0), (
        "Bội số mục tiêu vẫn là trung vị của rổ vỡ")
    assert muc_tieu == pytest.approx(
        M.INDUSTRY_DEFAULT_EV_EBITDA['Technology']), (
        f"Phải rơi về mặc định ngành, đang là {muc_tieu}")

    # Và fair value phải về mức hợp lý, không còn +290%.
    assert kq.upside_pct < 1.0, (
        f"upside {kq.upside_pct:+.1%} — rác vẫn đang đi vào fair value")
    assert any('phân tán' in w for w in kq.warnings), (
        "Phải nói rõ vì sao không dùng peer median")


def test_ro_peer_hoi_tu_van_duoc_dung(monkeypatch):
    """Cổng phân tán không được chặn rổ lành (Steel_Metals thật, p75/p25=1,47)."""
    monkeypatch.setattr('scanner.peer_database.get_peer_band',
                        lambda ind, metric='pe', peer_db=None: DAI_PEER_LANH)

    kq = M.calculate_ev_ebitda_valuation(_mau_fpt(), is_cyclical=False)
    assert kq.key_outputs['target_multiple'] == pytest.approx(8.63), (
        "Rổ hội tụ n=7 phải được dùng làm mục tiêu")
    assert kq.confidence >= 0.75, "Rổ peer thật phải giữ độ tin cậy cao"


def test_khong_do_duoc_phan_tan_thi_khong_dung_peer(monkeypatch):
    """Thiếu p25/p75 = không biết rổ có hội tụ không ⇒ mặc định BI QUAN.

    Mặc định ngược lại nghĩa là một nguồn peer mới quên ghi p25/p75 sẽ lặng lẽ
    đi qua cổng này — cùng loại bẫy với khoá `weak` của beta_coverage.
    """
    monkeypatch.setattr('scanner.peer_database.get_peer_band',
                        lambda ind, metric='pe', peer_db=None:
                        {'median': 28.0, 'n': 4})

    kq = M.calculate_ev_ebitda_valuation(_mau_fpt(), is_cyclical=False)
    assert kq.key_outputs['target_multiple'] == pytest.approx(
        M.INDUSTRY_DEFAULT_EV_EBITDA['Technology'])


def test_do_phan_tan_tu_choi_do_khi_thieu_khoa():
    assert M.do_phan_tan_ro_peer(DAI_PEER_LANH) == pytest.approx(9.28 / 6.33)
    assert M.do_phan_tan_ro_peer({'median': 9.0, 'n': 5}) is None
    assert M.do_phan_tan_ro_peer({'p25': 0, 'p75': 9.0}) is None
    assert M.do_phan_tan_ro_peer(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# Hai tầng cùng chạy trên rổ thật: đi từ peer_inputs tới bội số mục tiêu
# ─────────────────────────────────────────────────────────────────────────────

def test_tu_ro_that_den_boi_so_muc_tieu(monkeypatch):
    """Đường đi đầy đủ: build_peer_database → get_peer_band → bội số mục tiêu."""
    db = build_peer_database(RO_TECHNOLOGY_THAT)
    monkeypatch.setattr('scanner.peer_database.get_peer_band',
                        lambda ind, metric='pe', peer_db=None:
                        db['industries'].get(ind, {}).get(metric))

    kq = M.calculate_ev_ebitda_valuation(_mau_fpt(), is_cyclical=False)
    muc_tieu = kq.key_outputs['target_multiple']
    assert muc_tieu < 15.0, (
        f"Bội số mục tiêu {muc_tieu}x cho FPT — rổ 4 mã có rác vẫn đang lọt")
    # FPT tự giao dịch ở 8,0x; mục tiêu phải nằm trong tầm đó, không phải 28x.
    assert kq.upside_pct < 1.0, f"upside {kq.upside_pct:+.1%} vẫn phi lý"
