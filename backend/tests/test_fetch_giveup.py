"""
Bỏ sớm mã đã chết, và thời gian chờ cho nhóm lời gọi BCTC (27/09/2026).

Vì sao: lượt định giá 27/09 mất 41 phút — 34% ngân sách — cho bảy mã (TNH,
PVI, AST, ASM, BWE, DLG, NDN) treo toàn bộ 13 lượt gọi và trả về KHÔNG GÌ CẢ.
Gọi lại chính bảy mã đó trên runner hôm sau thì cả bảy xong trong ~2 s với dữ
liệu đủ: nguồn không chậm, nó suy giảm theo đợt.

Hai thứ sinh ra từ đó, và cả hai đều đo được:
  1. Trần chờ 30 s không bảo vệ lượt chậm — nó chỉ kéo dài lượt TREO. p90 của
     lượt thành công là 2,05 s.
  2. Mất bảng cân đối hoặc kết quả kinh doanh là mã đã chết; gọi nốt các bảng
     còn lại chỉ tốn thời gian để rồi vẫn bị loại.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import financial_fetcher as FF
from scanner.sources import http as H
from scanner.sources import vci


# ─── 1. Thời gian chờ ────────────────────────────────────────────────────────

def test_statement_timeout_is_well_above_the_measured_p90():
    """
    10 s không phải con số tròn cho đẹp: p90 của lượt gọi thành công đo trên
    runner là 2,05 s, nên trần này gấp 5 lần — cùng tỷ lệ mà OHLCV đã chọn.
    """
    assert 5 <= H.STATEMENT_TIMEOUT <= 15
    assert H.STATEMENT_TIMEOUT < H.TIMEOUT, 'phải ngắn hơn trần chung'


def test_statement_calls_actually_use_the_shorter_timeout(monkeypatch):
    """
    Hằng số đúng mà không ai truyền vào thì vô nghĩa. Test này chốt đường dây
    thật: mọi GET của vci đều tới iq.vietcap.com.vn — đúng nhóm đã đo.
    """
    seen = {}

    def fake(method, url, *, headers=None, params=None, payload=None, timeout=None):
        seen['url'], seen['timeout'] = url, timeout
        return {'data': {'ticker': 'AAA'}}

    monkeypatch.setattr(vci, 'request_json', fake)
    try:
        vci.company_overview('AAA')
    except Exception:
        pass
    assert 'iq.vietcap.com.vn' in seen['url']
    assert seen['timeout'] == H.STATEMENT_TIMEOUT


# ─── 2. Bỏ sớm ───────────────────────────────────────────────────────────────

class _Source:
    """Giả lập vci.financial_statement: bảng nào nêu tên thì treo."""

    def __init__(self, failing: set):
        self.failing = failing
        self.calls = []

    def __call__(self, ticker, name, period='year'):
        self.calls.append(name)
        if name in self.failing:
            raise ConnectionError('ReadTimeout giả lập')
        import pandas as pd
        return pd.DataFrame({'item': ['x'], '2025': [1]})


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Vòng thử lại ngủ 2 s và 4 s — test không cần chờ thật."""
    monkeypatch.setattr(FF.time, 'sleep', lambda s: None)


def _run(monkeypatch, failing: set):
    src = _Source(failing)
    monkeypatch.setattr(FF.vci, 'financial_statement', src)
    out = FF.fetch_financial_statements('TEST')
    return out, src.calls


def test_losing_the_balance_sheet_stops_everything(monkeypatch):
    """
    Đây chính là ca của sáu trong bảy mã hôm 27/09. Trước: 9 lượt gọi cho ba
    bảng rồi vẫn bị loại. Nay: 3 lượt rồi dừng.
    """
    out, calls = _run(monkeypatch, {'balance_sheet'})
    assert out is None
    assert calls == ['balance_sheet'] * 3, calls
    assert 'income' not in calls and 'cash_flow' not in calls


def test_losing_the_income_statement_also_stops(monkeypatch):
    out, calls = _run(monkeypatch, {'income'})
    assert out is None
    assert calls == ['balance_sheet'] + ['income'] * 3
    assert 'cash_flow' not in calls, 'mất kết quả kinh doanh là đã chết rồi'


def test_losing_only_the_cash_flow_does_not_stop(monkeypatch):
    """
    Lưu chuyển tiền tệ KHÔNG bắt buộc: `normalize_fundamentals` chỉ cần bảng
    cân đối và kết quả kinh doanh. Bỏ mã ở đây là vứt một mã dùng được.
    """
    out, calls = _run(monkeypatch, {'cash_flow'})
    assert out is not None
    assert set(out) == {'balance_sheet', 'income'}
    assert calls.count('cash_flow') == 3, 'vẫn thử đủ ba lần trước khi bỏ qua'


def test_a_healthy_ticker_is_untouched(monkeypatch):
    out, calls = _run(monkeypatch, set())
    assert set(out) == {'balance_sheet', 'income', 'cash_flow'}
    assert calls == ['balance_sheet', 'income', 'cash_flow'], 'mỗi bảng đúng một lượt'


def test_a_bad_argument_is_not_treated_as_a_dead_ticker(monkeypatch):
    """
    ValueError là lỗi tham số của mình, không phải nguồn hỏng. Gộp nó vào
    "mã chết" sẽ biến một lỗi lập trình thành mã biến mất khỏi web mà không ai
    hiểu vì sao.
    """
    def raiser(ticker, name, period='year'):
        if name == 'balance_sheet':
            raise ValueError('tham số sai')
        import pandas as pd
        return pd.DataFrame({'item': ['x'], '2025': [1]})

    monkeypatch.setattr(FF.vci, 'financial_statement', raiser)
    out = FF.fetch_financial_statements('TEST')
    assert out is not None and set(out) == {'income', 'cash_flow'}


# ─── 3. Không lấy giá cho mã đã chết ─────────────────────────────────────────

def test_no_price_call_for_a_ticker_with_no_statements(monkeypatch, tmp_path):
    """
    Trước 27/09 lời gọi giá nằm TRƯỚC phép kiểm `if not statements` — mỗi mã
    treo tốn thêm ba lần thử để lấy một con số bị vứt ngay dòng sau.
    """
    called = []
    monkeypatch.setattr(FF, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(FF, '_cache_path', lambda t, p: tmp_path / f'{t}_{p}.json')
    monkeypatch.setattr(FF, 'fetch_company_overview', lambda t, **k: {})
    monkeypatch.setattr(FF, 'fetch_financial_statements', lambda t, **k: None)
    monkeypatch.setattr(FF, 'fetch_current_price',
                        lambda t, **k: called.append(t) or 10.0)

    assert FF.fetch_fundamentals('TEST', use_cache=False) is None
    assert called == [], 'đã bỏ mã rồi thì không gọi thêm gì nữa'


def test_price_is_still_fetched_for_a_healthy_ticker(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(FF, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(FF, '_cache_path', lambda t, p: tmp_path / f'{t}_{p}.json')
    monkeypatch.setattr(FF, 'fetch_company_overview', lambda t, **k: {})
    monkeypatch.setattr(FF, 'fetch_financial_statements',
                        lambda t, **k: {'balance_sheet': None, 'income': None})
    monkeypatch.setattr(FF, 'fetch_current_price',
                        lambda t, **k: called.append(t) or 10.0)

    out = FF.fetch_fundamentals('TEST', use_cache=False)
    assert out is not None and called == ['TEST']
    assert out['current_price'] == 10.0


# ─── 4. Chốt lại phép tính đã dùng để quyết định ─────────────────────────────

def test_the_saving_is_what_was_claimed():
    """
    Bảy mã treo, mỗi mã: trước là 13 lượt gọi ở trần 30 s, nay là 4 lượt ở
    trần 10 s. Con số này là căn cứ của cả hai thay đổi trên — để nguyên đây
    thì lần sau đổi trần sẽ thấy ngay nó kéo theo gì.
    """
    truoc = 13 * 3 * 30          # 13 lượt gọi × 3 lần thử × 30 s
    nay = 4 * 3 * H.STATEMENT_TIMEOUT
    assert truoc / nay >= 5, 'nếu tỷ lệ tụt dưới 5 thì lập luận đã đổi'
    assert 7 * (truoc - nay) / 60 > 100, 'bảy mã phải tiết kiệm hơn 100 phút'


# ─── 5. Đường BCTC quý KHÔNG được dùng luật của đường năm ────────────────────

def test_the_quarterly_path_does_not_give_up_early(monkeypatch):
    """
    Lỗi suýt mắc khi làm việc này: áp `REQUIRED_STATEMENTS` lên cả đường quý.

    Hai đường có yêu cầu KHÁC NHAU. Định giá cần bảng cân đối và kết quả kinh
    doanh năm. Module B thì lấy kỳ quý gần nhất từ HỢP của kết quả kinh doanh
    và lưu chuyển tiền tệ (`quality/adapter.governance_inputs`), và không đụng
    tới bảng cân đối quý. Nên mất bảng cân đối quý mà bỏ luôn mã là vứt đúng
    thứ Module B cần.
    """
    src = _Source({'balance_sheet'})
    monkeypatch.setattr(FF.vci, 'financial_statement', src)
    monkeypatch.setattr(FF, '_is_cache_fresh', lambda *a, **k: False)

    out = FF.fetch_financial_statements('TEST', period='quarter',
                                        tables=FF.QUARTER_TABLES, required=())
    assert out is not None, 'mất bảng cân đối quý KHÔNG được làm mã chết'
    assert set(out) == {'income', 'cash_flow'}
    assert 'cash_flow' in src.calls, 'phải chạy tiếp tới lưu chuyển tiền tệ'


def test_the_annual_path_is_the_one_with_the_rule(monkeypatch):
    """Cùng một kiểu hỏng, hai đường xử khác nhau — chốt cả hai cạnh nhau."""
    src = _Source({'balance_sheet'})
    monkeypatch.setattr(FF.vci, 'financial_statement', src)
    assert FF.fetch_financial_statements('TEST', period='year') is None
    assert 'cash_flow' not in src.calls


def test_quarterly_caller_really_passes_the_exemption(monkeypatch, tmp_path):
    """
    Tham số đúng mà nơi gọi không truyền thì vô nghĩa — nên chốt ở NƠI GỌI.

    Bản đầu của test này đọc mã nguồn bằng `inspect.getsource` và tìm chuỗi
    `required=()`. Nó xanh cả khi tôi cố tình gỡ tham số đó ra: chuỗi ấy cũng
    nằm trong dòng chú thích ngay phía trên. Một test xanh vì chú thích thì
    không chốt được gì. Nay gọi thẳng hàm thật.
    """
    src = _Source({'balance_sheet'})
    monkeypatch.setattr(FF.vci, 'financial_statement', src)
    monkeypatch.setattr(FF, '_cache_path', lambda t, p: tmp_path / f'{t}_{p}.json')

    out = FF.fetch_quarterly_statements('TEST', use_cache=False)
    assert out is not None, (
        'fetch_quarterly_statements phải truyền required=() — nếu không nó '
        'dùng mặc định của đường năm và vứt dữ liệu Module B cần')
    assert 'cash_flow' in src.calls
