"""
Số lần thử lại khi lấy giá ngày (28/09/2026).

Đo trên lượt quét theo lịch 36416599174 — lượt theo lịch đầu tiên chạy được
sau sự cố vnstock:

    90 mã có ít nhất một lần treo
    88 mã treo CẢ BA lần  → không lấy được gì
     2 mã treo rồi lấy được, và cả hai đều ở LẦN THỨ HAI

Lần thử thứ ba cứu được 0/88 mã, trong khi 88 mã vô vọng đó ngốn 53 phút —
76% ngân sách 70 phút — và lượt quét dừng ở 208/500 mã, tức chỉ phủ 42%.

Điều này xác nhận chính chú thích đã có ở sources/http.py từ 26/09: "lượt
hỏng là TREO hẳn tới hết thời gian chờ, chờ lâu hơn cũng không ra". Hôm đó
mới hạ THỜI GIAN CHỜ mà chưa xem lại SỐ LẦN THỬ.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import data_fetcher as DF

# Số đo, giữ lại để lần sau đổi còn biết nó dựa trên gì.
MEASURED_HOPELESS, MEASURED_RECOVERED_ON_2ND = 88, 2


class _Source:
    """Giả lập nguồn: treo `fail_times` lần đầu rồi mới trả dữ liệu."""

    def __init__(self, fail_times: int, never=False):
        self.fail_times, self.never, self.calls = fail_times, never, 0

    def __call__(self, ticker, start, end):
        self.calls += 1
        if self.never or self.calls <= self.fail_times:
            raise TimeoutError('treo giả lập')
        import pandas as pd
        return pd.DataFrame({'time': ['2026-09-28'], 'open': [1.0], 'high': [1.0],
                             'low': [1.0], 'close': [1.0], 'volume': [100]})


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr(DF.time, 'sleep', lambda s: None)


def _run(monkeypatch, src, **kw):
    monkeypatch.setattr(DF._vci, 'ohlcv', src)
    return DF.fetch_ohlcv('AAA', '2026-09-01', '2026-09-28', **kw)


def test_a_hopeless_ticker_costs_two_calls_not_three(monkeypatch):
    """
    Đây là 88/90 mã của lượt đo. Mỗi lượt gọi thừa tốn trọn thời gian chờ
    10 giây, nhân 88 mã là 15 phút đổi lấy không gì cả.
    """
    src = _Source(0, never=True)
    assert _run(monkeypatch, src) is None
    assert src.calls == 2, f'mong 2 lượt gọi, thực tế {src.calls}'


def test_a_ticker_that_recovers_on_the_second_try_still_works(monkeypatch):
    """
    Đây là 2/90 mã còn lại. Bỏ hẳn thử lại sẽ mất chúng — nên giữ đúng một
    lần thử lại, không nhiều hơn, không ít hơn.
    """
    src = _Source(1)
    out = _run(monkeypatch, src)
    assert out is not None and src.calls == 2


def test_a_healthy_ticker_costs_exactly_one_call(monkeypatch):
    src = _Source(0)
    assert _run(monkeypatch, src) is not None
    assert src.calls == 1


def test_the_default_matches_the_measurement():
    assert DF.OHLCV_RETRIES == 1, (
        'lần thử thứ ba cứu 0/88 mã trong phép đo 28/09 — nếu đổi số này thì '
        'sửa cả chú thích, đừng lặng lẽ đổi')


def test_callers_can_still_ask_for_more(monkeypatch):
    """
    Backfill lịch sử là lần dùng MỘT LẦN, không có ngân sách thời gian, và ở
    đó một mã thiếu dữ liệu là thiếu vĩnh viễn — nên nó được trả thêm thời
    gian để đổi lấy đầy đủ.
    """
    src = _Source(0, never=True)
    assert _run(monkeypatch, src, retries=2) is None
    assert src.calls == 3


def test_backfill_actually_asks_for_more():
    """Tham số đúng mà nơi gọi không truyền thì vô nghĩa — đọc bằng AST."""
    import ast

    src = (Path(__file__).resolve().parent.parent / 'backfill_history.py').read_text(encoding='utf-8')
    found = False
    for n in ast.walk(ast.parse(src)):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'fetch_ohlcv'):
            if any(k.arg == 'retries' for k in n.keywords):
                found = True
    assert found, 'backfill_history phải truyền retries= rõ ràng, không dựa mặc định'


def test_a_bad_argument_still_fails_fast(monkeypatch):
    """ValueError là lỗi của code gọi — thử lại cũng vậy, phải dừng ngay."""
    def raiser(ticker, start, end):
        raise ValueError('tham số sai')

    monkeypatch.setattr(DF._vci, 'ohlcv', raiser)
    assert DF.fetch_ohlcv('AAA', 'x', 'y') is None


# ─── Thời gian chờ ───────────────────────────────────────────────────────────

def test_ohlcv_timeout_stays_well_above_the_measured_p90():
    """
    Đo trên runner 26/09: lượt gọi THÀNH CÔNG có trung vị 0,33s, p90 1,8s.
    Thời gian chờ chỉ để cắt lượt TREO, không để đợi lượt chậm — nên nó phải
    rộng hơn p90 vài lần, chứ không cần rộng hơn nữa.

    Hạ 10 → 5 ngày 29/09 sau khi hai lượt quét theo lịch 28/09 đều dừng sớm:
    144 mã × 2 lần × 10s = 48 phút trong ngân sách 70 phút.
    """
    from scanner.sources import http as H
    P90 = 1.8
    assert H.OHLCV_TIMEOUT >= P90 * 2, 'quá sát p90 — sẽ cắt nhầm lượt gọi tốt'
    assert H.OHLCV_TIMEOUT <= P90 * 6, 'quá rộng — chỉ kéo dài lượt treo'


def test_ohlcv_waits_less_than_the_statement_calls():
    """
    Hai nhóm lời gọi, hai mức chờ, và thứ tự phải đúng: BCTC nặng hơn giá ngày
    (p90 2,05s so với 1,8s) nên được chờ lâu hơn. Đảo lại là sai.
    """
    from scanner.sources import http as H
    assert H.OHLCV_TIMEOUT < H.STATEMENT_TIMEOUT < H.TIMEOUT


def test_the_worst_case_per_ticker_fits_the_budget():
    """
    Chốt phép tính đã dùng để quyết. Mã treo tệ nhất = số lần thử × thời gian
    chờ. Với 500 mã, nếu MỌI mã đều treo thì vẫn phải nằm trong ngân sách —
    nếu không thì một ngày nguồn thật xấu sẽ không quét nổi mã nào.
    """
    import re
    from scanner.sources import http as H
    from scanner.data_fetcher import OHLCV_RETRIES

    wf = (Path(__file__).resolve().parent.parent.parent
          / '.github' / 'workflows' / 'daily-scan.yml').read_text(encoding='utf-8')
    budget = int(re.search(r"FETCH_BUDGET_S:\s*'(\d+)'", wf).group(1))
    worst = (OHLCV_RETRIES + 1) * H.OHLCV_TIMEOUT
    assert worst * 500 > budget, (
        'nếu 500 mã treo hết mà vẫn lọt ngân sách thì phép tính này vô nghĩa — '
        'xem lại giả định')
    assert worst <= 12, (
        f'mỗi mã treo tốn {worst}s; với vài trăm mã treo là hết sạch ngân sách')
