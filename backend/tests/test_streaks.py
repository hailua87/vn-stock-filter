"""
Nhật ký tín hiệu (28/09/2026).

Vì sao có: mỗi lượt quét sinh danh sách MỚI và không nhớ phiên trước, nên bảng
tín hiệu hiển thị "mã vừa xuất hiện hôm nay" y hệt "mã giữ tín hiệu tám phiên
liền" — hai thứ khác hẳn nhau về ý nghĩa.

Điều dễ làm sai nhất và được chốt kỹ ở đây: phiên KHÔNG có bản lưu (lượt quét
hỏng) không được coi là "không mã nào có tín hiệu" — coi vậy sẽ cắt nhầm mọi
chuỗi đang chạy.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import streaks as S

NOW = datetime(2026, 9, 28, 9, 0)


def _write(d: Path, day: str, tickers) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{day}.json').write_text(json.dumps(
        {'signals': [{'ticker': t, 'close': 10.0} for t in tickers]}), encoding='utf-8')


@pytest.fixture
def web(tmp_path):
    """Năm phiên, một chiến lược. AAA giữ liên tục, BBB đứt quãng, CCC đã mất."""
    d = tmp_path / 'archive'
    _write(d, '2026-09-21', ['AAA', 'CCC'])
    _write(d, '2026-09-22', ['AAA', 'BBB', 'CCC'])
    _write(d, '2026-09-23', ['AAA'])               # BBB đứt, CCC mất hẳn
    _write(d, '2026-09-24', ['AAA', 'BBB'])
    _write(d, '2026-09-25', ['AAA', 'BBB'])
    (d / 'index.json').write_text('{"dates":[]}', encoding='utf-8')   # phải bị bỏ qua
    return tmp_path


def _rows(web, **kw):
    p = S.build(web, now=NOW, strategies={'x': 'archive'}, **kw)
    return p['strategies']['x'], p


def test_an_unbroken_streak_is_counted_to_the_latest_session(web):
    rows, _ = _rows(web)
    assert rows['AAA'] == {'streak': 5, 'appearances': 5,
                           'first': '2026-09-21', 'last': '2026-09-25', 'active': True}


def test_a_broken_streak_counts_only_the_current_run(web):
    """
    BBB có mặt 3/5 phiên nhưng đứt ở 23/09, nên chuỗi HIỆN TẠI là 2 — không
    phải 3. Đây là điểm khác nhau giữa "đang giữ" và "hay xuất hiện".
    """
    rows, _ = _rows(web)
    assert rows['BBB']['streak'] == 2
    assert rows['BBB']['appearances'] == 3
    assert rows['BBB']['active'] is True


def test_a_lost_signal_has_streak_zero_but_is_still_listed(web):
    """
    CCC mất tín hiệu từ 23/09. Vẫn phải nằm trong nhật ký — biết một mã VỪA
    RỚT KHỎI danh sách cũng là thông tin, và đó là cả lý do có tệp này.
    """
    rows, _ = _rows(web)
    assert rows['CCC']['streak'] == 0 and rows['CCC']['active'] is False
    assert rows['CCC']['last'] == '2026-09-22'


def test_index_json_is_not_mistaken_for_a_session(web):
    _, payload = _rows(web)
    assert 'index' not in payload['sessions']['x']
    assert payload['sessions']['x'] == ['2026-09-21', '2026-09-22', '2026-09-23',
                                        '2026-09-24', '2026-09-25']


def test_a_corrupt_archive_is_skipped_not_read_as_empty(web):
    """
    Điểm dễ sai nhất. Bản lưu hỏng mà coi là "phiên không có mã nào" thì mọi
    chuỗi đang chạy bị cắt — AAA đang giữ 5 phiên sẽ tụt về 1, và người đọc
    thấy một tín hiệu bền bỗng thành tín hiệu mới.
    """
    (web / 'archive' / '2026-09-24.json').write_text('{ hong', encoding='utf-8')
    rows, payload = _rows(web)
    assert '2026-09-24' not in payload['sessions']['x']
    assert rows['AAA']['streak'] == 4, 'bốn phiên đọc được, không phải bị cắt về 1'
    assert rows['AAA']['active'] is True


def test_the_window_limits_how_far_back_it_looks(web):
    rows, payload = _rows(web, window=2)
    assert payload['sessions']['x'] == ['2026-09-24', '2026-09-25']
    assert rows['AAA']['appearances'] == 2
    assert 'CCC' not in rows, 'ngoài cửa sổ thì không liệt kê'


def test_rows_are_sorted_for_the_reader(web):
    """Chuỗi dài nhất lên đầu — giao diện không phải sắp lại."""
    rows, _ = _rows(web)
    assert list(rows) == ['AAA', 'BBB', 'CCC']


def test_a_missing_strategy_dir_is_empty_not_an_error(tmp_path):
    p = S.build(tmp_path, now=NOW, strategies={'x': 'khong-ton-tai'})
    assert p['strategies']['x'] == {} and p['sessions']['x'] == []


def test_output_is_rebuildable_and_stable(web):
    """Dựng lại từ đầu phải ra cùng kết quả — nhật ký không được trôi."""
    a, _ = _rows(web)
    b, _ = _rows(web)
    assert a == b


def test_it_covers_all_four_strategies_by_default():
    """Bốn chiến lược đều phải có nhật ký, không chỉ Pre-Breakout."""
    assert set(S.STRATEGY_DIRS) == {'pre_breakout', 'golden_cross_long',
                                    'golden_cross_short', 'ichimoku'}
    assert S.STRATEGY_DIRS['pre_breakout'] == 'archive', (
        'Pre-Breakout cất bản lưu thẳng trong web/data/archive, khác ba cái kia')


# ─── run_daily phải THẬT SỰ gọi ──────────────────────────────────────────────

def test_run_daily_actually_writes_the_journal():
    """
    Thiếu phần này thì module chỉ là code không ai gọi: thử gỡ hẳn lệnh ghi
    khỏi run_daily, toàn bộ 706 test vẫn xanh.

    Đọc bằng AST chứ không tìm chuỗi trong mã nguồn. Một test trước đó của tôi
    tìm chuỗi và XANH GIẢ vì khớp đúng dòng chú thích tôi viết ngay phía trên.
    AST chỉ thấy lệnh thật, không thấy chú thích.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent / 'run_daily.py').read_text(encoding='utf-8')
    calls = {
        f'{n.func.value.id}.{n.func.attr}'
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
    }
    assert 'STREAKS.build' in calls, 'run_daily không dựng nhật ký tín hiệu'
    assert 'STREAKS.write' in calls, 'run_daily dựng nhật ký nhưng không ghi ra'


def test_the_journal_path_is_in_the_published_outputs():
    """
    Ghi ra mà không nằm trong WEB_OUTPUTS thì `commit-bot-data.sh` vứt lặng lẽ
    — chạy vẫn xanh, log vẫn báo "đã ghi", và không ai biết cho tới khi mở web
    thấy 404. Đã mắc đúng lỗi này với health.json và ohlc/ ngày 23/09/2026.
    """
    import run_daily
    assert 'streaks/' in run_daily.WEB_OUTPUTS
