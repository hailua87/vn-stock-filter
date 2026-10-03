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


# ─── Giả dược: phân xử "chiến lược kém" vs "rổ thua chỉ số vốn hoá" ─────────

def _uni_series(n=40):
    """Rổ giả: mọi mã đủ thanh khoản, giá phẳng trừ mã được chỉ định."""
    return _series([100.0] * n)


def test_placebo_draws_from_the_same_dates_not_random_dates(tmp_path):
    """
    Khớp NGÀY là điểm mấu chốt. Lấy ngày ngẫu nhiên nữa thì pha thị trường
    thành biến thứ hai và phép thử mất nghĩa.
    """
    days = _days(40)
    # days[25] va days[30]: _eligible can >=20 phien lich su de tinh GTGD TB20,
    # nen tin hieu o phien dau chuoi gia se khong co doi chung — dung thiet ke.
    #
    # Va days[27] phai la phien RONG: khong co no thi hai phien kia lien ke
    # trong dong thoi gian cua ban luu, tuc MOT lan vao chu khong phai hai.
    _archive(tmp_path, 'archive', {days[25]: ['A'], days[27]: [], days[30]: ['A']})
    uni = ['A'] + [f'T{i}' for i in range(10)]
    big = pd.DataFrame({'Date': days, 'Close': [100.0] * 40, 'Volume': [10_000_000] * 40})
    out = O.build(tmp_path, lambda t: big, None, horizons=(5,), now=NOW,
                  strategies={'x': 'archive'}, universe=uni)
    pl = out['strategies']['x']['placebo']
    assert {r['date'] for r in pl['rows']} == {days[25], days[30]}


def test_placebo_excludes_tickers_that_had_the_signal(tmp_path):
    """Đối chứng phải là mã KHÔNG có tín hiệu — đó là thứ cần so."""
    days = _days(40)
    _archive(tmp_path, 'archive', {days[25]: ['A', 'B']})
    uni = ['A', 'B'] + [f'T{i}' for i in range(10)]
    big = pd.DataFrame({'Date': days, 'Close': [100.0] * 40, 'Volume': [10_000_000] * 40})
    out = O.build(tmp_path, lambda t: big, None, horizons=(5,), now=NOW,
                  strategies={'x': 'archive'}, universe=uni)
    picked = {r['ticker'] for r in out['strategies']['x']['placebo']['rows']}
    assert not (picked & {'A', 'B'}), f'đã lấy chính mã có tín hiệu: {picked}'


def test_placebo_only_draws_liquid_enough_tickers(tmp_path):
    """
    Tín hiệu chỉ phát ra từ rổ sau điều kiện nền. Đối chứng lấy cả mã kém thanh
    khoản thì so hai thứ khác nhau — mã kém thanh khoản có hành vi giá khác hẳn.
    """
    days = _days(40)
    _archive(tmp_path, 'archive', {days[25]: ['A']})
    thin = pd.DataFrame({'Date': days, 'Close': [100.0] * 40, 'Volume': [1] * 40})
    fat = pd.DataFrame({'Date': days, 'Close': [100.0] * 40, 'Volume': [10_000_000] * 40})
    out = O.build(tmp_path, lambda t: fat if t in ('A', 'RICH') else thin, None,
                  horizons=(5,), now=NOW, strategies={'x': 'archive'},
                  universe=['A', 'RICH', 'POOR1', 'POOR2'])
    picked = {r['ticker'] for r in out['strategies']['x']['placebo']['rows']}
    assert picked == {'RICH'}, f'đã lấy mã kém thanh khoản: {picked}'


def test_placebo_is_reproducible(tmp_path):
    """Hạt giống suy từ (ngày, mã) nên dựng lại lúc nào cũng ra cùng kết quả."""
    days = _days(40)
    _archive(tmp_path, 'archive', {days[25]: ['A']})
    big = pd.DataFrame({'Date': days, 'Close': [100.0] * 40, 'Volume': [10_000_000] * 40})
    uni = ['A'] + [f'T{i}' for i in range(20)]
    f = lambda: O.build(tmp_path, lambda t: big, None, horizons=(5,), now=NOW,
                        strategies={'x': 'archive'}, universe=uni
                        )['strategies']['x']['placebo']['rows']
    assert [(r['ticker'], r['date']) for r in f()] == [(r['ticker'], r['date']) for r in f()]


def test_no_universe_means_no_placebo(tmp_path):
    days = _days(10)
    _archive(tmp_path, 'archive', {days[0]: ['A']})
    out = O.build(tmp_path, lambda t: _series([100.0] * 10), None, horizons=(5,),
                  now=NOW, strategies={'x': 'archive'})
    assert 'placebo' not in out['strategies']['x']


# ─── Khoảng tin cậy cho chênh lệch ──────────────────────────────────────────
#
# `median_gap_ci` nhận các cặp (ngày_vào, excess) chứ không phải list số trần:
# nó lấy mẫu theo KHỐI NGÀY để xử lý việc các lần vào không độc lập.


def _cap(gia_tri, moi_ngay=1, start='2026-01-01'):
    """Rải `gia_tri` ra các ngày, `moi_ngay` giá trị mỗi ngày."""
    ngay = _days(-(-len(gia_tri) // moi_ngay), start)
    return [(ngay[i // moi_ngay], v) for i, v in enumerate(gia_tri)]


def test_identical_groups_give_an_interval_containing_zero():
    """Hai nhóm y hệt nhau thì chênh lệch phải KHÔNG khác 0."""
    a = _cap([0.01 * (i % 7) - 0.03 for i in range(200)])
    ci = O.median_gap_ci(a, list(a), block=5)
    assert ci is not None and ci['includes_zero']


def test_a_clearly_better_group_gives_an_interval_above_zero():
    """
    Nếu khoảng tin cậy chứa 0 với MỌI dữ liệu thì nó vô dụng. Phải có trường
    hợp nó loại được 0.
    """
    a = _cap([0.10 + 0.001 * (i % 5) for i in range(200)])
    b = _cap([0.00 + 0.001 * (i % 5) for i in range(200)])
    ci = O.median_gap_ci(a, b, block=5)
    assert ci is not None and not ci['includes_zero'] and ci['gap_lo'] > 0


def test_a_tiny_sample_gets_no_interval_rather_than_a_fake_one():
    """Mẫu 10 quan sát thì bootstrap cũng không cứu — nói KHÔNG BIẾT."""
    assert O.median_gap_ci(_cap([0.01] * 10), _cap([0.02] * 10), block=5) is None


def test_the_level_is_95_percent():
    """
    90% là mức dễ dãi hơn quy ước, và người đọc mặc định hiểu là 95%. Một
    khoảng 90% in ra không kèm nhãn sẽ bị đọc thành kết luận mạnh hơn sự thật.
    """
    assert (O.CI_LO, O.CI_HI) == (2.5, 97.5)
    ci = O.median_gap_ci(_cap([0.01 * (i % 9) for i in range(300)]),
                         _cap([0.01 * (i % 9) for i in range(300)]), block=5)
    assert ci['level'] == 95


def test_clustered_entries_get_a_wider_interval_than_spread_out_ones():
    """
    ĐÂY LÀ LÝ DO CÓ BOOTSTRAP KHỐI.

    Cùng một tập 200 giá trị. Bản A rải ra 100 ngày; bản B dồn vào 10 ngày.
    Bản B có ÍT QUAN SÁT ĐỘC LẬP HƠN HẲN dù số dòng y hệt, nên khoảng tin cậy
    của nó phải RỘNG HƠN. Lấy mẫu từng dòng sẽ cho hai khoảng gần bằng nhau —
    tức khai khống độ chắc chắn của bản dồn cục.
    """
    val = [0.01 * (i % 20) - 0.10 for i in range(200)]   # 20 muc, moi muc 10 lan

    # Rai: 100 ngay x 2 gia tri, moi ngay mot hon hop -> trung vi it lay dong.
    rai = O.median_gap_ci(_cap(val, moi_ngay=2),
                          _cap([0.0] * 200, moi_ngay=2), block=2)
    # Don: sap xep de MOI NGAY chi mang MOT muc, lap 10 lan -> 20 ngay. Day la
    # tuong quan trong ngay that: rut mot ngay ra hay vao lam trung vi nhay han.
    don = O.median_gap_ci(_cap(sorted(val), moi_ngay=10),
                          _cap([0.0] * 200, moi_ngay=10), block=2)

    rong_rai = rai['gap_hi'] - rai['gap_lo']
    rong_don = don['gap_hi'] - don['gap_lo']
    assert rong_don > rong_rai * 1.5, (
        f'dồn cục {rong_don:.4f} phải rộng hơn hẳn rải đều {rong_rai:.4f}')


def test_too_few_dates_refuses_instead_of_guessing():
    """
    Cần ít nhất HAI khối, nếu không mọi lần lấy mẫu đều ra gần như cùng một tập
    và khoảng hẹp giả — đúng loại sai đang đi chữa. Nói không đủ, đừng đoán.
    """
    a = _cap([0.01 * (i % 7) for i in range(100)], moi_ngay=10)   # 10 ngày
    ci = O.median_gap_ci(a, list(a), block=20)                    # cần >= 40 ngày
    assert ci['includes_zero'] is None and ci['gap_lo'] is None
    assert '10 ngay' in ci['ly_do'] and '40' in ci['ly_do']


def test_the_block_length_follows_the_horizon():
    """Khối phải dài bằng kỳ quan sát: đó mới là độ dài cửa sổ chồng lấn."""
    sessions = {d: ['A'] for d in _days(60)}
    rows = [{'date': d, 'exits': {'20': {'ret': 0.0, 'excess': 0.001 * i}}}
            for i, d in enumerate(sessions)]
    ci = O.median_gap_ci([(r['date'], r['exits']['20']['excess']) for r in rows],
                         [(r['date'], 0.0) for r in rows], block=20)
    assert ci['block'] == 20


def test_the_interval_is_fed_excess_not_raw_return(tmp_path, monkeypatch):
    """
    Con số in ra là `median_excess`, nên khoảng đi kèm phải tính trên `excess`.
    Bản trước tính trên `ret` — khoảng mô tả một đại lượng KHÁC với đại lượng
    nó đứng cạnh.

    Kiểm THẲNG thứ `build` truyền vào hàm, không kiểm qua chênh lệch: chỉ số
    triệt tiêu khi trừ hai nhóm đo trên cùng ngày, nên chênh lệch gần như
    không phân biệt được hai đại lượng. Đó chính là lý do lỗi này sống lâu.
    """
    ghi = {}

    def bat(a, b, **kw):
        ghi['a'], ghi['b'], ghi['kw'] = a, b, kw
        return {'gap_lo': 0.0, 'gap_hi': 0.0, 'rounds': 1,
                'includes_zero': True, 'block': kw.get('block'), 'level': 95}

    monkeypatch.setattr(O, 'median_gap_ci', bat)

    days = _days(60)
    _archive(tmp_path, 'archive', {days[25]: ['A'], days[27]: [], days[30]: ['A']})
    uni = ['A'] + [f'T{i}' for i in range(10)]
    khung = pd.DataFrame({'Date': days, 'Close': [100.0 * (1.002 ** i) for i in range(60)],
                          'Volume': [10_000_000] * 60})
    chi_so = _series([100.0 * (1.005 ** i) for i in range(60)])
    out = O.build(tmp_path, lambda t: khung, chi_so, horizons=(5,), now=NOW,
                  strategies={'x': 'archive'}, universe=uni)

    r = out['strategies']['x']
    mong = [(x['date'], x['exits']['5']['excess']) for x in r['rows']
            if '5' in x['exits'] and x['exits']['5'].get('excess') is not None]
    assert ghi['a'] == mong, 'phai truyen (ngay, excess) cua chinh cac dong tin hieu'

    # Chot chan: neu ret va excess bang nhau thi phep kiem tren khong phan biet
    # duoc gi. Chi so tang nhanh hon gia nen hai dai luong phai tach han.
    ret = [x['exits']['5']['ret'] for x in r['rows'] if '5' in x['exits']]
    exc = [v for _, v in mong]
    assert ret and exc and ret != exc, 'fixture khong tach duoc ret voi excess'

    # Khoi phai dai bang ky quan sat.
    assert ghi['kw'].get('block') == 5
