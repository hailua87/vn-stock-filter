"""
Beta phải đi ra đầu ra (04/10/2026).

Beta quyết định WACC trong DCF, và `methods_pb_roe` trừ 5% độ tin cậy khi beta
là giá trị dự phòng 1.0 — tức nó ĐỔI KẾT QUẢ. Nhưng trước ngày này nó không
được ghi ra bất kỳ đâu.

Hậu quả cụ thể: ngày 04/10 không ai — kể cả người viết — nói được từ dữ liệu
công bố rằng lượt chạy đó dùng beta thật hay 1.0. Một đầu vào làm đổi kết quả
mà không để lại dấu vết thì không kiểm chứng được, và không sửa được khi hỏng.

Phép kiểm quan trọng nhất ở đây là cái CUỐI: con số ghi ra phải là con số đã
THỰC SỰ được dùng, không phải một con số tính lại ở chỗ khác.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from run_valuation import _tong_hop_beta
from test_valuation_quality_fixes import _raw, no_dispersion  # noqa: F401 (fixture)

THAT = {'beta': 1.3, 'fallback': False, 'r_squared': 0.42,
        'method': 'weekly_log_returns_blume_adjusted'}


def _dinh_gia(beta_info=None, price=66_400.0, shares=1_000_000_000):
    # FPT: fixture phi tai chinh co san, du khoan muc de DCF chay that.
    from scanner.strategies.valuation import value_ticker
    raw = _raw('FPT', overview={'industry': 'Computer Services',
                                'outstanding_share': shares})
    raw['current_price'] = price
    if beta_info is not None:
        raw['beta_info'] = beta_info
    # enrich_market_metrics=False: mac dinh value_ticker TU TINH LAI beta tu
    # cache OHLCV va ghi de beta_info. De bat thi phep kiem nay chay khac nhau
    # giua may co cache (beta that) va CI khong cache (beta du phong) — tuc no
    # khong kiem cai no tuong la dang kiem.
    return value_ticker('FPT', raw_fundamentals=raw, enrich_market_metrics=False)


def test_the_report_records_the_beta_it_used(no_dispersion):
    d = _dinh_gia(THAT).to_dict()
    assert d['beta'] == {'value': 1.3, 'fallback': False,
                         'method': 'weekly_log_returns_blume_adjusted',
                         'r_squared': 0.42}


def test_a_fallback_beta_says_so_instead_of_looking_real(no_dispersion):
    """
    Không có regression thì beta là 1.0 — nhưng 1.0 cũng là một giá trị beta
    hợp lệ. Nếu đầu ra chỉ ghi con số, người đọc không phân biệt được "beta đo
    được đúng bằng 1.0" với "không đo được nên lấy mặc định".
    """
    d = _dinh_gia(None).to_dict()
    assert d['beta']['value'] == 1.0
    assert d['beta']['fallback'] is True
    assert d['beta']['r_squared'] is None


def test_the_rollup_separates_real_from_fallback():
    tong = _tong_hop_beta([
        {'beta': {'value': 1.2, 'fallback': False, 'r_squared': 0.4}},
        {'beta': {'value': 0.9, 'fallback': False, 'r_squared': 0.6}},
        {'beta': {'value': 1.0, 'fallback': True, 'r_squared': None}},
        {'beta': None},
    ])
    assert tong == {'n': 3, 'real': 2, 'fallback': 1, 'median_r_squared': 0.6}


def test_the_rollup_survives_a_run_with_no_beta_at_all():
    assert _tong_hop_beta([{'beta': None}, {}]) == {
        'n': 0, 'real': 0, 'fallback': 0, 'median_r_squared': None}


def test_the_exported_beta_is_the_one_that_actually_drove_the_numbers(no_dispersion):
    """
    ĐÂY LÀ PHÉP KIỂM CÓ GIÁ TRỊ NHẤT.

    Một trường `beta` ghi ra đầu ra mà không gắn với con số đã dùng thì tệ hơn
    là không ghi: nó trông như bằng chứng. Đổi beta phải làm ĐỔI CẢ HAI — con
    số ghi ra VÀ kết quả định giá. Nếu chỉ đổi con số ghi ra thì đó là trang
    trí; nếu chỉ đổi kết quả thì đầu ra đang nói dối.
    """
    thap = _dinh_gia({**THAT, 'beta': 0.6})
    cao = _dinh_gia({**THAT, 'beta': 1.9})

    assert thap.to_dict()['beta']['value'] == 0.6
    assert cao.to_dict()['beta']['value'] == 1.9

    # Beta cao -> WACC cao -> chiết khấu mạnh hơn -> fair value THẤP hơn.
    assert cao.fair_value < thap.fair_value, (
        f'beta phải đổi được kết quả: beta 1,9 ra {cao.fair_value:,.0f} '
        f'nhưng beta 0,6 ra {thap.fair_value:,.0f}')
