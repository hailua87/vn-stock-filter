"""
Phễu ngưỡng (30/09/2026).

Câu hỏi ban đầu là "backtest ngưỡng". Backtest KHÔNG làm được — 4 bản lưu trong
8 ngày, chân trời ~6 phiên, và bốn bản lưu ấy còn không độc lập (bốn ngày liên
tiếp của cùng một kỳ BCTC). Lý do đầy đủ ở docs/threshold-backtest.md.

Cái LÀM được ngay: ngưỡng có đạt tới được không, và nút thắt ở đâu.

Đo thật 27/09: 200 mã → 184 chấm đủ → 3 vượt cả 4 ngưỡng → 0 đạt chuẩn. Cả ba
rớt ở bước cuối vì thiếu định giá. Tức ngưỡng không sai; nút thắt là độ phủ
định giá.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.quality import config as C
from scanner.quality import diagnostics as D

TH = {'quality': 75, 'growth': 70, 'governance': 70, 'resilience': 65}


def _item(ticker, q=None, g=None, gov=None, r=None, band='NOT_AVAILABLE',
          status='MON', model='NON_FINANCIAL'):
    def dim(v):
        return None if v is None else {'score': v}
    return {'ticker': ticker, 'model': model, 'status': status,
            'valuation': {'band': band},
            'dims': {'quality': dim(q), 'growth': dim(g),
                     'governance': dim(gov), 'resilience': dim(r)}}


def test_the_funnel_counts_each_step_separately():
    items = [
        _item('A', 90, 90, 90, 90, band='FAIR', status='QUAL'),   # đạt chuẩn
        _item('B', 90, 90, 90, 90),                               # vượt ngưỡng, kẹt định giá
        _item('C', 50, 90, 90, 90),                               # rớt quality
        _item('D', None, 90, 90, 90),                             # thiếu điểm
    ]
    f = D.funnel(items, TH)
    assert f['universe'] == 4
    assert f['scored_all_dims'] == 3, 'mã thiếu điểm không được tính là đã chấm'
    assert f['passed_all_thresholds'] == 2
    assert f['qualified'] == 1
    assert f['blocked_by_valuation'] == 1


def test_it_names_which_tickers_are_blocked_and_why():
    """
    Đây là phần đáng đọc nhất: danh sách dài mà số đạt chuẩn vẫn 0 nghĩa là
    vấn đề KHÔNG nằm ở ngưỡng.
    """
    items = [_item('HDB', 86, 88, 100, 66, model='BANK'),
             _item('CTR', 92, 78, 100, 66, band='EXPENSIVE')]
    f = D.funnel(items, TH)
    assert f['blocked_by_valuation'] == 2
    by = {m['ticker']: m for m in f['near_miss']}
    assert by['HDB']['band'] == 'NOT_AVAILABLE' and by['HDB']['model'] == 'BANK'
    assert by['CTR']['band'] == 'EXPENSIVE'
    assert by['HDB']['scores']['quality'] == 86


def test_a_qualified_ticker_is_not_listed_as_blocked():
    items = [_item('X', 90, 90, 90, 90, band='ATTRACTIVE', status='QUAL')]
    f = D.funnel(items, TH)
    assert f['qualified'] == 1 and f['blocked_by_valuation'] == 0
    assert f['near_miss'] == []


def test_the_binding_dimension_is_the_one_that_rejects_most():
    """
    Nút thắt phải là chiều làm rớt NHIỀU NHẤT. Chỉ ra nhầm chiều sẽ dẫn người
    sửa đi chỉnh đúng cái ngưỡng không phải vấn đề.
    """
    items = [_item(f'T{i}', 50, 90, 90, 90) for i in range(5)]      # rớt quality
    items += [_item(f'U{i}', 90, 50, 90, 90) for i in range(2)]     # rớt growth
    f = D.funnel(items, TH)
    assert f['binding_dim'] == 'quality'
    assert f['fail_by_dim']['quality'] == 5 and f['fail_by_dim']['growth'] == 2


def test_a_ticker_failing_two_dims_counts_in_both():
    """Đếm theo chiều, không theo mã: một mã rớt hai chiều là hai lần rớt."""
    f = D.funnel([_item('A', 50, 50, 90, 90)], TH)
    assert f['fail_by_dim']['quality'] == 1 and f['fail_by_dim']['growth'] == 1
    assert f['passed_all_thresholds'] == 0


def test_an_empty_universe_says_it_does_not_know():
    """Rổ rỗng thì không có nút thắt nào — nói None, đừng chọn bừa một chiều."""
    f = D.funnel([], TH)
    assert f['scored_all_dims'] == 0 and f['binding_dim'] is None


def test_it_uses_the_real_thresholds_by_default():
    """
    Mặc định phải là ngưỡng THẬT trong config. Truyền ngưỡng riêng chỉ để test;
    phễu chạy thật mà dùng ngưỡng khác thì nó mô tả một hệ không tồn tại.
    """
    items = [_item('A', 76, 71, 71, 66)]
    assert D.funnel(items)['passed_all_thresholds'] == 1
    assert set(C.QUALIFY) == set(TH), 'ngưỡng trong config đã đổi — xem lại test'


def test_qualifying_bands_match_what_classify_actually_requires():
    """
    `classify` cho ĐẠT CHUẨN khi định giá thuộc ATTRACTIVE/FAIR. Lệch danh sách
    này thì phễu báo "kẹt định giá" cho mã thật ra đã qua, hoặc ngược lại.
    """
    import inspect

    from scanner.quality import status
    src = inspect.getsource(status.classify)
    for band in D.QUALIFYING_BANDS:
        assert f"'{band}'" in src, f'{band} không có trong classify'
