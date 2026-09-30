"""
Nợ xấu và CAR cho ngân hàng (30/09/2026).

Quyết định D24 (24/09) kết luận "không nguồn nào có nợ xấu" và gỡ hai chỉ tiêu
khỏi mô hình BANK. Kết luận đó SAI: khảo sát hôm ấy thử bảng `ratio` của VCI
(dừng ở 2018) và 32 chỉ tiêu KBS, nhưng KHÔNG thử section NOTE của chính
endpoint BCTC đang dùng — nơi có phân loại nợ 5 nhóm tới 2025, đủ cho 17/17
ngân hàng trong rổ.

Kiểm chéo khi tìm ra, hai nguồn độc lập trên VCB 2025:
    tổng 5 nhóm nợ (thuyết minh)         1.673.530 tỷ
    loans_and_advances (bảng cân đối)    1.673.526 tỷ
    bao phủ = 24.976 / 9.670 = 258%      (VCB công bố ~250%)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.quality import adapter
from scanner.quality import config as C
from scanner.quality import metrics
from scanner.sources import vci


# ─── Bẫy 1: ĐƠN VỊ. Lệch đúng một tỷ lần và trông như 0% ───────────────────

def test_coverage_converts_between_dong_and_ty_dong():
    """
    Thuyết minh trả số tiền theo ĐỒNG; `annual` theo TỶ ĐỒNG. Quên chia 1e9 thì
    bao phủ nợ xấu ra 0,00000026 thay vì 2,58 — và nó KHÔNG báo lỗi, chỉ làm
    mọi ngân hàng trông như không dự phòng gì.

    Số thật của VCB 2025: dự phòng 24.975,679 tỷ, nợ xấu 9.670 tỷ.
    """
    annual = {'period_end': ['2025-12-31'], 'loan_allowance': [-24975.679]}
    q = {2025: {'npl_ratio': 0.0058, 'car': 0.1156,
                'npl_amount': 9_670_000_000_000.0, 'gross_loans': 1.67e15}}
    out = adapter.attach_bank_asset_quality(annual, q)
    assert out['npl_coverage'][0] == pytest.approx(2.58, rel=0.01), (
        'bao phủ phải khoảng 258%, không phải 0,00000026 hay 2,58 tỷ')


def test_allowance_sign_is_handled():
    """Nguồn ghi dự phòng ÂM (khoản giảm trừ tài sản). Bao phủ phải DƯƠNG."""
    annual = {'period_end': ['2025-12-31'], 'loan_allowance': [-1000.0]}
    q = {2025: {'npl_ratio': 0.02, 'car': 0.12,
                'npl_amount': 500_000_000_000.0, 'gross_loans': 2.5e13}}
    out = adapter.attach_bank_asset_quality(annual, q)
    assert out['npl_coverage'][0] == pytest.approx(2.0)


def test_ratios_stay_ratios_not_percents():
    """
    Nguồn trả CAR và nợ xấu SẴN ở dạng tỷ lệ (0,1156 = 11,56%). Nhân 100 ở đây
    thì giao diện nhân tiếp và hiện 1156%. Đây đúng lỗi đã mắc với NIM của KBS.
    """
    annual = {'period_end': ['2025-12-31'], 'loan_allowance': [None]}
    out = adapter.attach_bank_asset_quality(
        annual, {2025: {'npl_ratio': 0.0058, 'car': 0.1156,
                        'npl_amount': None, 'gross_loans': None}})
    assert out['npl_ratio'][0] == 0.0058 and out['car'][0] == 0.1156


# ─── Bẫy 2: CHIỀU xếp hạng. Đảo ngược mà không có gì báo lỗi ───────────────

def test_lower_npl_is_better_and_higher_coverage_is_better():
    """
    Đảo chiều thì ngân hàng nợ xấu 6% được chấm cao hơn ngân hàng 0,6%, và
    KHÔNG có gì báo lỗi — bảng vẫn ra số, chỉ là xếp hạng ngược.
    """
    spec = {k: hb for specs in C.MODELS['BANK'].values() for k, _, hb in specs}
    assert spec['npl_ratio'] is False, 'nợ xấu THẤP hơn là tốt hơn'
    assert spec['npl_coverage'] is True, 'bao phủ CAO hơn là tốt hơn'


def test_asset_quality_carries_real_weight():
    """
    Với ngân hàng, nợ xấu quyết định nhiều hơn lợi nhuận: một ngân hàng ROE cao
    mà nợ xấu 6% không phải ngân hàng tốt. Trọng số nhỏ quá thì chỉ tiêu có mặt
    cho có.
    """
    q = {k: w for k, w, _ in C.MODELS['BANK']['quality']}
    assert q['npl_ratio'] + q['npl_coverage'] >= 30
    assert sum(w for _, w, _ in C.MODELS['BANK']['quality']) == 100


# ─── Nguồn: nợ xấu = nhóm 3+4+5, không phải nhóm 2 hay cả 5 nhóm ───────────

def test_npl_is_groups_three_four_five():
    """
    Thông tư 02/2013 và 11/2021: nợ xấu là nhóm 3 (dưới tiêu chuẩn), 4 (nghi
    ngờ), 5 (có khả năng mất vốn). Nhóm 2 "cần chú ý" KHÔNG phải nợ xấu — gộp
    vào sẽ thổi tỷ lệ lên gấp nhiều lần.
    """
    assert vci.NPL_GROUPS == ('nob42', 'nob43', 'nob44')
    assert 'nob41' not in vci.NPL_GROUPS, 'nhóm 2 không phải nợ xấu'
    assert set(vci.NPL_GROUPS) < set(vci.LOAN_GROUPS)
    assert len(vci.LOAN_GROUPS) == 5


def test_a_year_without_classification_data_is_none_not_zero():
    """
    0% nợ xấu là một khẳng định RẤT mạnh. Thiếu thuyết minh thì nói không biết.
    """
    annual = {'period_end': ['2019-12-31'], 'loan_allowance': [-100.0]}
    out = adapter.attach_bank_asset_quality(annual, {2025: {'npl_ratio': 0.01}})
    assert out['npl_ratio'][0] is None and out['npl_coverage'][0] is None


def test_metrics_read_the_attached_values():
    """Nối vào `annual` mà `metrics.bank` không đọc thì cả đường dây vô dụng."""
    annual = {'period_end': ['2024-12-31', '2025-12-31'],
              'loan_allowance': [None, -2000.0],
              'npl_ratio': [0.02, 0.015], 'npl_coverage': [None, 2.5]}
    m = metrics.bank(annual)
    assert m['npl_ratio'] == 0.015, 'phải lấy kỳ GẦN NHẤT'
    assert m['npl_coverage'] == 2.5
