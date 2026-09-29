"""
Sổ theo dõi kết quả tín hiệu (29/09/2026).

Hợp đồng: docs/outcomes-contract.md. Test ở đây kiểm đúng bốn quyết định quyết
định con số có nghĩa hay không — grain, gốc giá, lịch đếm phiên, và mốc so sánh.

Đây là code phân tích: nó LUÔN ra một con số, kể cả khi sai. Nên mỗi phép kiểm
dưới đây đều đã được thử cho ĐỎ bằng cách đổi đúng một biến.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import outcomes as O

NOW = datetime(2026, 9, 29, 9, 0)


def _days(n, start='2026-09-01'):
    return [str(d.date()) for d in pd.bdate_range(start, periods=n)]


def _series(prices, start='2026-09-01'):
    d = _days(len(prices), start)
    return pd.DataFrame({'Date': d, 'Close': prices})


def _archive(tmp, rel, per_day):
    """per_day: {ngày: [mã]} → viết bản lưu."""
    d = tmp / rel
    d.mkdir(parents=True, exist_ok=True)
    for day, tks in per_day.items():
        (d / f'{day}.json').write_text(json.dumps(
            {'signals': [{'ticker': t, 'close': 999.0} for t in tks]}), encoding='utf-8')
    (d / 'index.json').write_text('{"dates":[]}', encoding='utf-8')
    return d


# ─── Grain: một lần vào, không phải mỗi phiên ────────────────────────────────

def test_a_long_streak_is_one_entry_not_many():
    """
    MCH có tín hiệu 20 phiên liền. Đếm mỗi phiên là một lần vào thì một mã
    chiếm 20 quan sát gần như trùng nhau và lấn át thống kê — đúng lỗi
    overlapping observations, và nó luôn làm kết quả trông chắc chắn hơn thực tế.
    """
    days = _days(5)
    sessions = [(d, {'MCH'}) for d in days]
    assert O.entries_from(sessions) == [('MCH', days[0])]


def test_leaving_and_coming_back_is_two_entries():
    """Hai lần tín hiệu THẬT SỰ phát ra thì là hai quan sát."""
    d = _days(5)
    sessions = [(d[0], {'A'}), (d[1], set()), (d[2], {'A'}), (d[3], {'A'}), (d[4], set())]
    assert O.entries_from(sessions) == [('A', d[0]), ('A', d[2])]


def test_entries_are_sorted_and_complete():
    d = _days(2)
    sessions = [(d[0], {'B', 'A'}), (d[1], {'C'})]
    assert O.entries_from(sessions) == [('A', d[0]), ('B', d[0]), ('C', d[1])]


# ─── Gốc giá: chuỗi điều chỉnh, KHÔNG phải close trong bản lưu ───────────────

def test_entry_price_comes_from_the_series_not_the_archive(tmp_path):
    """
    Bản lưu ghi close=999 (giá tại thời điểm đó, chưa điều chỉnh sự kiện quyền).
    Chuỗi điều chỉnh nói giá vào là 100. Lấy nhầm gốc sẽ biến một lần chia cổ
    tức thành khoản lỗ khổng lồ.
    """
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A']})
    s = _series([100.0] * 5 + [110.0] * 5)
    out = O.build(tmp_path, lambda t: s, None, horizons=(5,), now=NOW,
                  strategies={'x': 'archive'})
    row = out['strategies']['x']['rows'][0]
    assert row['entry'] == 100.0, 'phải lấy từ chuỗi giá, không phải close=999 của bản lưu'
    assert row['exits']['5']['ret'] == pytest.approx(0.10)


# ─── Lịch: đếm phiên của chính mã đó ────────────────────────────────────────

def test_horizon_counts_the_tickers_own_sessions(tmp_path):
    """
    Mã nghỉ giao dịch vài phiên: "sau 3 phiên" phải là phiên thứ 3 TRONG CHUỖI
    CỦA NÓ, không phải ngày lịch thứ 3.
    """
    _archive(tmp_path, 'archive', {'2026-09-01': ['A']})
    s = pd.DataFrame({'Date': ['2026-09-01', '2026-09-10', '2026-09-20', '2026-09-30'],
                      'Close': [100.0, 101.0, 102.0, 130.0]})
    out = O.build(tmp_path, lambda t: s, None, horizons=(3,), now=NOW,
                  strategies={'x': 'archive'})
    assert out['strategies']['x']['rows'][0]['exits']['3']['ret'] == pytest.approx(0.30)


# ─── Thiếu dữ liệu: LOẠI, không thay bằng 0 ─────────────────────────────────

def test_incomplete_horizon_is_excluded_not_zeroed(tmp_path):
    """
    Một tín hiệu chưa đủ thời gian KHÔNG phải một tín hiệu hoà vốn. Thay bằng 0
    sẽ kéo trung vị về 0 và làm mọi chiến lược trông trung tính.
    """
    days = _days(4)
    _archive(tmp_path, 'archive', {days[0]: ['A']})
    s = _series([100.0, 101.0, 102.0, 103.0])        # chỉ 4 phiên
    out = O.build(tmp_path, lambda t: s, None, horizons=(20,), now=NOW,
                  strategies={'x': 'archive'})
    h = out['strategies']['x']['by_horizon']['20']
    assert h['n'] == 0 and h['incomplete'] == 1
    assert h['median_ret'] is None, 'không có dữ liệu thì phải là None, không phải 0'


def test_a_ticker_with_no_price_is_counted_separately(tmp_path):
    _archive(tmp_path, 'archive', {'2026-09-01': ['A']})
    out = O.build(tmp_path, lambda t: None, None, now=NOW, strategies={'x': 'archive'})
    assert out['strategies']['x']['skipped']['no_price'] == 1
    assert out['strategies']['x']['entries'] == 0


# ─── Mốc so sánh: phần hơn/kém thị trường ───────────────────────────────────

def test_excess_subtracts_the_index_over_the_same_dates(tmp_path):
    """
    "Sau 5 phiên +10%" vô nghĩa nếu thị trường cùng kỳ cũng +10%. Không có mốc
    so sánh thì sổ này chỉ đo thị trường, không đo chiến lược.
    """
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A']})
    stock = _series([100.0] * 5 + [110.0] * 5)        # +10%
    index = _series([1000.0] * 5 + [1040.0] * 5)      # +4%
    out = O.build(tmp_path, lambda t: stock, index, horizons=(5,), now=NOW,
                  strategies={'x': 'archive'})
    e = out['strategies']['x']['rows'][0]['exits']['5']
    assert e['ret'] == pytest.approx(0.10)
    assert e['excess'] == pytest.approx(0.06)


def test_no_index_means_excess_is_none_not_zero(tmp_path):
    """Không có mốc so sánh thì nói KHÔNG BIẾT, đừng nói bằng 0."""
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A']})
    out = O.build(tmp_path, lambda t: _series([100.0] * 10), None, horizons=(5,),
                  now=NOW, strategies={'x': 'archive'})
    assert out['strategies']['x']['rows'][0]['exits']['5']['excess'] is None
    assert out['strategies']['x']['by_horizon']['5']['hit_rate'] is None
    assert out['benchmark'] is None


# ─── Thống kê: trung vị, không phải trung bình ──────────────────────────────

def test_one_huge_winner_does_not_move_the_median(tmp_path):
    """
    Một mã tăng 300% kéo TRUNG BÌNH lên và làm cả chiến lược trông tốt. Trung
    vị cho biết mã điển hình ra sao.
    """
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A', 'B', 'C']})
    flat = _series([100.0] * 10)
    moon = _series([100.0] * 5 + [400.0] * 5)
    out = O.build(tmp_path, lambda t: moon if t == 'C' else flat, None,
                  horizons=(5,), now=NOW, strategies={'x': 'archive'})
    h = out['strategies']['x']['by_horizon']['5']
    assert h['n'] == 3
    assert h['median_ret'] == pytest.approx(0.0), (
        'trung bình sẽ là +1.0 vì mã C tăng 300%; trung vị là 0')


# ─── G2: có test đi qua ENTRYPOINT THẬT của pipeline ────────────────────────

def test_run_daily_builds_and_writes_the_ledger():
    """
    Mọi test trên đều gọi `O.build` — chúng chứng minh hàm đúng, KHÔNG chứng
    minh pipeline gọi nó đúng cách, đúng thứ tự, với đúng tham số.

    Đọc bằng AST chứ không tìm chuỗi: một test trước đó của tôi từng xanh giả
    vì khớp với chính dòng chú thích mình viết.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent / 'run_daily.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    calls = {f'{n.func.value.id}.{n.func.attr}' for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name)}
    assert 'OUTCOMES.build' in calls and 'OUTCOMES.write' in calls

    # Và phải truyền ĐÚNG nguồn giá: `by_ticker_all` (chưa lọc điều kiện nền),
    # không phải `by_ticker`. Lấy nhầm thì sổ chỉ còn mã sống sót qua bộ lọc
    # thanh khoản, và mọi con số đẹp lên một cách giả tạo.
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'build' and isinstance(n.func.value, ast.Name)
                and n.func.value.id == 'OUTCOMES'):
            src_arg = ast.unparse(n.args[1])
            assert 'by_ticker_all' in src_arg, (
                f'nguồn giá là {src_arg} — phải là by_ticker_all, nếu không sổ '
                f'chỉ còn mã qua được điều kiện nền (survivorship)')
            break
    else:
        raise AssertionError('không tìm thấy lời gọi OUTCOMES.build')


def test_the_ledger_path_is_published():
    """Ghi ra mà không nằm trong WEB_OUTPUTS thì commit-bot-data.sh vứt lặng lẽ."""
    import run_daily
    assert 'outcomes/' in run_daily.WEB_OUTPUTS


# ─── G5: grain còn nguyên sau biến đổi ──────────────────────────────────────

def test_no_duplicate_ticker_date_rows(tmp_path):
    """
    Grain đã khai: một dòng = (chiến lược, mã, phiên vào). Trùng khóa nghĩa là
    một lần vào bị đếm hai lần, và mọi thống kê sau đó bị thổi phồng.
    """
    days = _days(8)
    _archive(tmp_path, 'archive', {days[0]: ['A', 'B'], days[1]: ['A'],
                                   days[2]: set(), days[3]: ['A', 'B']})
    out = O.build(tmp_path, lambda t: _series([100.0] * 8), None, horizons=(2,),
                  now=NOW, strategies={'x': 'archive'})
    rows = out['strategies']['x']['rows']
    keys = [(r['ticker'], r['date']) for r in rows]
    assert len(keys) == len(set(keys)), f'khóa trùng: {keys}'
    # A vào ở days[0] và days[3]; B vào ở days[0] và days[3]
    assert sorted(keys) == sorted([('A', days[0]), ('B', days[0]),
                                   ('A', days[3]), ('B', days[3])])


def test_counts_come_from_the_rows_not_from_a_stored_number(tmp_path):
    """
    G4: `n` phải là len() của dữ liệu THẬT SỰ tính được, không phải một con số
    mô tả nó. Cho payload ít dòng hẳn đi rồi xem con số có đổi theo không.
    """
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A', 'B', 'C']})
    out3 = O.build(tmp_path, lambda t: _series([100.0] * 10), None, horizons=(5,),
                   now=NOW, strategies={'x': 'archive'})
    _archive(tmp_path, 'archive2', {days[0]: ['A']})
    out1 = O.build(tmp_path, lambda t: _series([100.0] * 10), None, horizons=(5,),
                   now=NOW, strategies={'x': 'archive2'})
    assert out3['strategies']['x']['by_horizon']['5']['n'] == 3
    assert out1['strategies']['x']['by_horizon']['5']['n'] == 1
    assert out3['strategies']['x']['entries'] == 3
