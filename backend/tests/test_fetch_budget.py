"""
Test ngân sách thời gian và cầu dao của vòng fetch.

Ghim lại sự cố 17-20/08/2026: cả 8 ca daily-scan chết vì
`The action 'Run daily scan' has timed out after 60 minutes` — không traceback,
chỉ là hết giờ. vnstock VCI trả lỗi lai rai nên mỗi mã ngốn ~26s (3 lần thử +
sleep 2/4/6s); 500 mã thì 60 phút chỉ tới mã thứ ~140 rồi runner chặt ngang,
và vì bị chặt TRƯỚC bước ghi file nên 140 mã đó cũng mất trắng.

Hai van chặn hai thứ khác nhau, nên test cũng tách đôi:

  - time_budget_s          — trần cứng, chặn cả khi upstream chỉ CHẬM chứ không lỗi
  - max_consecutive_failures — cầu dao, chặn khi upstream SẬP hẳn

Và cả hai đều phải trả về phần đã lấy được kèm lý do dừng, chứ không được ném
exception: dừng sớm là quyết định, không phải tai nạn.

Về tính tất định: hai van được kiểm ở hai chỗ khác nhau.
  - Trần thời gian kiểm NGAY TRONG worker (`now() >= deadline`), nên số lần fetch
    thật chỉ phụ thuộc đồng hồ giả — tất định tuyệt đối, không phụ thuộc lịch
    biểu luồng.
  - Cầu dao đếm ở vòng lặp chính (nó cần biết mã hỏng hay không, mà worker không
    phân loại). Nên test cầu dao dùng `delay` thật vài mili giây để vòng lặp
    chính chắc chắn theo kịp worker, và chỉ khẳng định các chặn rộng rãi.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner import data_fetcher
from scanner.data_fetcher import fetch_universe
from run_daily import archive_decision, build_metadata


# ── Đồ giả ───────────────────────────────────────────────────────────────
class FakeClock:
    """Đồng hồ đơn điệu tăng, chỉ nhích khi có ai đó gọi fetch."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _good_frame(ticker: str) -> pd.DataFrame:
    """DataFrame vượt ngưỡng `len(df) > 60` mà fetch_universe dùng để chấm đạt."""
    return pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=70, freq='D'),
        'Close': range(70),
        'Volume': range(70),
        'Ticker': ticker,
        'Exchange': 'HOSE',
        'StaleCache': False,
    })


def universe(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        'ticker': [f'T{i:03d}' for i in range(n)],
        'exchange': ['HOSE'] * n,
    })


class Fetcher:
    """
    Thay chỗ `fetch_with_cache`. Ghi lại mã nào THỰC SỰ được gọi — đây là con số
    quan trọng nhất: mã bị bỏ qua vì van đã đóng thì không được chạm vào mạng.
    """

    def __init__(self, clock=None, cost_s=0.0, fail_set=None, fail_all=False):
        self.clock = clock
        self.cost_s = cost_s
        self.fail_set = set(fail_set or ())
        self.fail_all = fail_all
        self.calls: list[str] = []
        self.last_sessions: list = []

    def __call__(self, ticker, exchange, lookback_days, last_session=None):
        self.calls.append(ticker)
        self.last_sessions.append(last_session)
        if self.clock is not None:
            self.clock.advance(self.cost_s)
        if self.fail_all or ticker in self.fail_set:
            return None                      # vnstock trả rỗng = hỏng
        return _good_frame(ticker)


@pytest.fixture
def patched(monkeypatch):
    def install(fetcher):
        monkeypatch.setattr(data_fetcher, 'fetch_with_cache', fetcher)
        return fetcher
    return install


# ── Đường bình thường: không van nào được nhả ────────────────────────────
def test_full_run_reports_no_stop(patched):
    patched(Fetcher())
    out = fetch_universe(universe(10), delay=0)
    s = out.attrs['fetch_summary']
    assert s['stop_reason'] is None
    assert s['truncated'] is False
    assert s['ok'] == 10 and s['skipped'] == 0
    assert s['coverage'] == 1.0
    assert out['Ticker'].nunique() == 10


def test_scattered_failures_do_not_trip_breaker(patched):
    """
    Rổ 500 mã lúc nào cũng có dăm mã chết (huỷ niêm yết, mã mới chưa đủ nến).
    Đếm TỔNG số hỏng sẽ nhả cầu dao oan; phải đếm LIÊN TIẾP.
    """
    f = patched(Fetcher(fail_set={f'T{i:03d}' for i in range(0, 100, 3)}))
    out = fetch_universe(universe(100), delay=0, max_consecutive_failures=20)
    s = out.attrs['fetch_summary']
    assert s['stop_reason'] is None
    assert s['failed'] == 34                 # hỏng nhiều, nhưng không mã nào liền nhau
    assert len(f.calls) == 100               # đã thử hết


# ── Van 1: ngân sách thời gian ───────────────────────────────────────────
def test_time_budget_stops_the_loop(patched):
    """
    Trần 100s, mỗi mã tốn 30s → chỉ 4 mã kịp fetch (0, 30, 60, 90 đều < 100;
    mã thứ 5 thấy đồng hồ ở 120 nên bị bỏ). Không phụ thuộc lịch biểu luồng vì
    chính worker là chỗ kiểm hạn.
    """
    clock = FakeClock()
    f = patched(Fetcher(clock=clock, cost_s=30.0))
    out = fetch_universe(universe(50), delay=0, time_budget_s=100, clock=clock)

    s = out.attrs['fetch_summary']
    assert s['stop_reason'] == 'time_budget'
    assert s['truncated'] is True
    assert len(f.calls) == 4                 # đúng 4 lần chạm mạng
    assert s['ok'] == 4
    assert s['skipped'] == 46
    assert s['coverage'] == pytest.approx(0.08)


def test_time_budget_keeps_what_it_fetched(patched):
    """Điểm mấu chốt: 'thay vì mất trắng'. Phần đã lấy được phải nằm trong kết quả."""
    clock = FakeClock()
    patched(Fetcher(clock=clock, cost_s=30.0))
    out = fetch_universe(universe(50), delay=0, time_budget_s=100, clock=clock)

    assert not out.empty
    assert sorted(out['Ticker'].unique()) == ['T000', 'T001', 'T002', 'T003']
    assert len(out) == 4 * 70                # dữ liệu thật, không phải khung rỗng


def test_time_budget_none_means_no_cap(patched):
    clock = FakeClock()
    f = patched(Fetcher(clock=clock, cost_s=3600.0))     # mỗi mã một giờ
    out = fetch_universe(universe(20), delay=0, time_budget_s=None, clock=clock)
    assert out.attrs['fetch_summary']['stop_reason'] is None
    assert len(f.calls) == 20


def test_budget_zero_is_treated_as_no_cap(patched):
    """`--fetch-budget 0` là cách tắt trần; 0 không được hiểu thành 'hết ngay'."""
    clock = FakeClock()
    f = patched(Fetcher(clock=clock, cost_s=99.0))
    out = fetch_universe(universe(15), delay=0, time_budget_s=0, clock=clock)
    assert out.attrs['fetch_summary']['stop_reason'] is None
    assert len(f.calls) == 15


def test_budget_exhausted_before_first_ticker(patched):
    """Trần 0.5s, mã đầu tốn 30s: mã 1 vẫn được thử (lúc đó đồng hồ còn ở 0)."""
    clock = FakeClock()
    f = patched(Fetcher(clock=clock, cost_s=30.0))
    out = fetch_universe(universe(10), delay=0, time_budget_s=0.5, clock=clock)
    s = out.attrs['fetch_summary']
    assert len(f.calls) == 1
    assert s['stop_reason'] == 'time_budget'
    assert s['skipped'] == 9


# ── Van 2: cầu dao ───────────────────────────────────────────────────────
def test_circuit_breaker_trips_on_consecutive_failures(patched):
    """
    Upstream sập hẳn — mã nào cũng hỏng. Ngồi hết 45 phút để xác nhận điều đã rõ
    sau 20 mã là phí thời gian của cả job.

    `delay` thật vài mili giây để vòng lặp chính (chỗ đếm) chắc chắn theo kịp
    worker; các chặn dưới đây rộng rãi nên không phụ thuộc lịch biểu chính xác.
    """
    f = patched(Fetcher(fail_all=True))
    out = fetch_universe(universe(200), delay=0.005, max_consecutive_failures=20)

    s = out.attrs['fetch_summary']
    assert s['stop_reason'] == 'circuit_breaker'
    assert s['truncated'] is True
    assert s['ok'] == 0
    assert s['failed'] >= 20
    assert len(f.calls) < 200                # đã dừng sớm, không thử hết 200
    assert len(f.calls) <= 60                # chặn rộng cho lịch biểu luồng
    assert out.empty


def test_success_resets_the_consecutive_counter(patched):
    """
    19 hỏng → 1 đạt → 19 hỏng, ngưỡng 20: KHÔNG được nhả. Nếu đếm tổng thì 38 > 20
    và cầu dao nhả oan, giết một vòng fetch đang chạy được.
    """
    fails = {f'T{i:03d}' for i in list(range(0, 19)) + list(range(20, 39))}
    f = patched(Fetcher(fail_set=fails))
    out = fetch_universe(universe(60), delay=0.002, max_consecutive_failures=20)

    s = out.attrs['fetch_summary']
    assert s['stop_reason'] is None
    assert s['failed'] == 38
    assert len(f.calls) == 60


def test_breaker_disabled_with_zero(patched):
    f = patched(Fetcher(fail_all=True))
    out = fetch_universe(universe(40), delay=0, max_consecutive_failures=0)
    assert out.attrs['fetch_summary']['stop_reason'] is None
    assert len(f.calls) == 40


def test_breaker_threshold_is_respected(patched):
    """Ngưỡng thấp thì nhả sớm hơn — cùng một upstream sập."""
    f = patched(Fetcher(fail_all=True))
    out = fetch_universe(universe(200), delay=0.005, max_consecutive_failures=5)
    assert out.attrs['fetch_summary']['stop_reason'] == 'circuit_breaker'
    assert len(f.calls) <= 40


# ── Checkpoint ───────────────────────────────────────────────────────────
def test_checkpoint_records_what_was_fetched(patched, tmp_path):
    clock = FakeClock()
    patched(Fetcher(clock=clock, cost_s=30.0))
    cp = tmp_path / 'sub' / 'fetch_checkpoint.json'

    fetch_universe(universe(50), delay=0, time_budget_s=100,
                   checkpoint_path=cp, clock=clock)

    assert cp.exists()                       # tự tạo cả thư mục cha
    data = json.loads(cp.read_text(encoding='utf-8'))
    assert data['stop_reason'] == 'time_budget'
    assert data['truncated'] is True
    assert data['ok_tickers'] == ['T000', 'T001', 'T002', 'T003']
    assert len(data['skipped_tickers']) == 46
    assert data['total'] == 50
    assert data['time_budget_s'] == 100


def test_checkpoint_written_on_clean_run_too(patched, tmp_path):
    """Chạy trọn cũng ghi — để biết lần trước đã xong hẳn chứ không phải chưa chạy."""
    patched(Fetcher())
    cp = tmp_path / 'fetch_checkpoint.json'
    fetch_universe(universe(5), delay=0, checkpoint_path=cp)
    data = json.loads(cp.read_text(encoding='utf-8'))
    assert data['stop_reason'] is None
    assert data['ok'] == 5


def test_checkpoint_failure_does_not_kill_the_run(patched, tmp_path):
    """Checkpoint hỏng không được phép giết một vòng fetch đang chạy tốt."""
    patched(Fetcher())
    blocked = tmp_path / 'a_file'
    blocked.write_text('x', encoding='utf-8')
    out = fetch_universe(universe(5), delay=0,
                         checkpoint_path=blocked / 'nested' / 'cp.json')
    assert out.attrs['fetch_summary']['ok'] == 5


def test_checkpoint_none_is_allowed(patched):
    patched(Fetcher())
    out = fetch_universe(universe(3), delay=0, checkpoint_path=None)
    assert out.attrs['fetch_summary']['ok'] == 3


# ── Kết quả rỗng vẫn phải mang lý do ─────────────────────────────────────
def test_empty_result_still_carries_the_reason(patched):
    """
    run_daily gọi sys.exit(1) khi df rỗng. Không có `fetch_summary` đi kèm thì
    log chỉ nói 'No data fetched' — đúng cái kiểu im lặng đang phải sửa.
    """
    patched(Fetcher(fail_all=True))
    out = fetch_universe(universe(30), delay=0.002, max_consecutive_failures=5)
    assert out.empty
    assert out.attrs['fetch_summary']['stop_reason'] == 'circuit_breaker'


def test_empty_universe(patched):
    patched(Fetcher())
    out = fetch_universe(universe(0), delay=0)
    s = out.attrs['fetch_summary']
    assert s['total'] == 0 and s['coverage'] == 0.0
    assert s['stop_reason'] is None


# ── Cổng archive: lát cắt không được ghi thành bản ghi vĩnh viễn ─────────
def _summary(coverage, stop_reason=None):
    return {'coverage': coverage, 'truncated': stop_reason is not None,
            'stop_reason': stop_reason, 'ok': int(coverage * 500), 'total': 500}


def test_archive_blocked_when_fetch_truncated(monkeypatch):
    """
    File archive là VĨNH VIỄN — không ca nào chạy lại phiên cũ để sửa, và backtest
    sau này đọc nó như dữ liệu thật. Bản quét 140/500 mã không phải phiên đó.
    """
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)

    d = archive_decision(now=at_2330, fetch_summary=_summary(0.28, 'time_budget'))
    assert d['write'] is False
    assert 'time_budget' in d['reason'] and '28' in d['reason']


def test_archive_blocked_on_thin_coverage_even_without_stop(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)

    assert archive_decision(now=at_2330,
                            fetch_summary=_summary(0.5))['write'] is False


def test_archive_allowed_on_full_coverage(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)

    d = archive_decision(now=at_2330, fetch_summary=_summary(1.0))
    assert d['write'] is True


def test_force_archive_still_overrides_coverage_gate(monkeypatch):
    """`--force-archive` là để người biết rõ mình làm gì ép ghi; vẫn bị đánh dấu."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)

    d = archive_decision(force=True, now=at_2330,
                         fetch_summary=_summary(0.28, 'circuit_breaker'))
    assert d['write'] is True
    assert d['forced'] is True


def test_archive_gate_unchanged_without_fetch_summary(monkeypatch):
    """Không truyền fetch_summary thì hành vi y hệt trước — cổng đồng hồ giữ nguyên."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    assert archive_decision(now=datetime(2026, 8, 26, 23, 30, tzinfo=ICT))['write'] is True
    assert archive_decision(now=datetime(2026, 8, 26, 13, 0, tzinfo=ICT))['write'] is False


# ── Metadata: lát cắt phải tự khai báo ───────────────────────────────────
def test_metadata_stamps_truncation(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)
    summary = _summary(0.28, 'time_budget')
    summary['elapsed_s'] = 2701.4

    meta = build_metadata(5, ('HOSE',), 140, {}, '2026-08-26',
                          archive_decision(now=at_2330, fetch_summary=summary),
                          0.31, summary)
    assert meta['fetch_truncated'] is True
    assert meta['fetch_stop_reason'] == 'time_budget'
    assert meta['fetch_coverage'] == 0.28
    assert meta['fetch_elapsed_s'] == 2701.4
    assert meta['archive_written'] is False


def test_metadata_clean_run_has_no_stop_reason(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)
    summary = _summary(1.0)

    meta = build_metadata(5, ('HOSE',), 500, {}, '2026-08-26',
                          archive_decision(now=at_2330, fetch_summary=summary),
                          0.98, summary)
    assert meta['fetch_truncated'] is False
    assert meta['fetch_stop_reason'] is None
    assert meta['archive_written'] is True


def test_force_over_coverage_gate_is_recorded_in_metadata(monkeypatch):
    """
    Ép ghi qua cổng độ phủ phải để lại dấu vết. Không có `archive_forced=true`
    thì file archive dựng từ 140/500 mã trông y hệt file dựng từ 500/500 — và ba
    tháng sau không ai suy ngược được.
    """
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)
    summary = _summary(0.28, 'time_budget')

    d = archive_decision(force=True, now=at_2330, fetch_summary=summary)
    meta = build_metadata(5, ('HOSE',), 140, {}, '2026-08-26', d, 0.31, summary)
    assert meta['archive_written'] is True
    assert meta['archive_forced'] is True
    assert 'ÉP GHI' in meta['archive_gate']


def test_normal_full_run_is_not_marked_forced(monkeypatch):
    """Chiều ngược lại: chạy trọn thì tuyệt đối không được dán nhãn ép ghi."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    from datetime import datetime
    from run_daily import ICT
    at_2330 = datetime(2026, 8, 26, 23, 30, tzinfo=ICT)

    d = archive_decision(force=True, now=at_2330, fetch_summary=_summary(1.0))
    assert d['write'] is True and d['forced'] is False
    assert 'ÉP GHI' not in d['reason']
