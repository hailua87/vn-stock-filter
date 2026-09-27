"""
Hạn chót cho bộ lọc sự kiện quyền trong daily-scan.

21-22/09/2026: nguồn chậm ~10 s/lần gọi; sau vòng fetch (có ngân sách 45 phút)
bộ lọc sự kiện quyền gọi API cho ~250 mã KHÔNG giới hạn, job bị chặt ở phút 60
và mất toàn bộ kết quả đã tính. Nay quá hạn chót thì chỉ dùng cache.
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner import corporate_actions as ca


class FakeClock:
    """time.monotonic giả: mỗi lần gọi API thật tốn `cost` giây."""
    def __init__(self, cost):
        self.now, self.cost = 0.0, cost

    def monotonic(self):
        return self.now


@pytest.fixture
def env(monkeypatch, tmp_path):
    clock = FakeClock(cost=10.0)
    calls = []

    def fake_fetch(tk, lookback_days=365, lookahead_days=30):
        calls.append(tk)
        clock.now += clock.cost
        return []

    monkeypatch.setattr(ca, 'EVENTS_CACHE', tmp_path)
    monkeypatch.setattr(ca, 'fetch_events', fake_fetch)
    monkeypatch.setattr(time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    return clock, calls, tmp_path


def test_stops_calling_api_after_deadline(env):
    clock, calls, _ = env
    tickers = [f'T{i:02d}' for i in range(10)]
    out = ca.fetch_events_batch(tickers, deadline=25.0)  # đủ cho 3 lần gọi (0, 10, 20)
    assert calls == ['T00', 'T01', 'T02']
    assert out[ca.SKIPPED_KEY] == tickers[3:]


def test_cached_tickers_still_served_after_deadline(env):
    clock, calls, cache_dir = env
    ca._save_cache(cache_dir / 'T09.json', [])  # T09 có cache
    out = ca.fetch_events_batch([f'T{i:02d}' for i in range(10)], deadline=0.0)
    assert calls == []
    assert out['T09'] == [] and 'T09' not in out[ca.SKIPPED_KEY]
    assert len(out[ca.SKIPPED_KEY]) == 9


def test_no_deadline_keeps_old_behaviour(env):
    _, calls, _ = env
    ca.fetch_events_batch([f'T{i}' for i in range(5)])
    assert len(calls) == 5


def test_filter_keeps_results_it_could_not_check(env):
    """Mã không kiểm được sự kiện thì giữ nguyên (như khi API sự kiện lỗi)."""
    results = [SimpleNamespace(ticker=f'T{i}', metrics={}) for i in range(6)]
    kept = ca.apply_event_filter(results, deadline=0.0)
    assert [r.ticker for r in kept] == [r.ticker for r in results]


def test_scanner_passes_deadline_to_event_filter(monkeypatch):
    from scanner import scanner as sc
    seen = {}

    def spy(results, lookback_days, lookahead_days, deadline=None, min_score=None):
        seen['deadline'] = deadline
        seen['min_score'] = min_score
        return results
    monkeypatch.setattr(sc, 'apply_event_filter', spy)
    monkeypatch.setattr(sc, 'evaluate', lambda df, tk, cfg: SimpleNamespace(ticker=tk))
    monkeypatch.setattr(sc.BreakoutScanner, 'to_dataframe', lambda self: self.results)

    import pandas as pd
    df = pd.DataFrame({'Ticker': ['AAA', 'BBB'], 'Date': ['2026-09-22'] * 2})
    sc.BreakoutScanner(events_deadline=123.0, events_min_score=5).scan_from_dataframe(df)
    assert seen['deadline'] == 123.0
    assert seen['min_score'] == 5


def _daily_scan_budgets() -> dict:
    """Đọc ba mốc thời gian THẬT trong .github/workflows/daily-scan.yml."""
    import re
    wf = (Path(__file__).resolve().parent.parent.parent
          / '.github' / 'workflows' / 'daily-scan.yml').read_text(encoding='utf-8')
    got = {}
    for key, pat in (('fetch', r"FETCH_BUDGET_S:\s*'?(\d+)"),
                     ('run', r"RUN_BUDGET_S:\s*'?(\d+)"),
                     ('timeout', r'timeout-minutes:\s*(\d+)')):
        m = re.search(pat, wf)
        assert m, f'khong tim thay {key} trong daily-scan.yml'
        got[key] = int(m.group(1))
    got['timeout'] *= 60
    return got


def test_budgets_keep_their_order_in_code_and_workflow():
    """
    Ba mốc phải giữ thứ tự: fetch < run < timeout.

    Vì sao chốt bằng test: 17-20/08/2026 cả 8 ca bị runner giết GIỮA LÚC ĐANG
    FETCH nên mọi thứ đã lấy về mất sạch. Khoảng chênh giữa ba mốc chính là thứ
    ngăn điều đó. Nâng một mốc mà quên hai mốc kia là tái lập đúng sự cố ấy.

    Đọc THẲNG workflow chứ không chép số vào đây: bản cũ chốt cứng `60 * 60`,
    nên khi timeout đổi thành 90 phút thì test vẫn xanh trong khi nó đang canh
    một con số không còn tồn tại.
    """
    import run_daily
    wf = _daily_scan_budgets()
    assert run_daily.FETCH_BUDGET_S < run_daily.RUN_BUDGET_S
    assert wf['fetch'] < wf['run'] < wf['timeout']


def test_workflow_values_match_the_code_defaults():
    """Hai nơi cùng khai một con số thì chúng phải bằng nhau — nếu không, chạy
    tay ở máy và chạy trên runner sẽ dừng ở hai thời điểm khác nhau."""
    import run_daily
    wf = _daily_scan_budgets()
    assert wf['fetch'] == run_daily.FETCH_BUDGET_S
    assert wf['run'] == run_daily.RUN_BUDGET_S


def test_fetch_budget_fits_the_measured_rate():
    """
    Đo 26/09/2026 trên runner: nguồn Vietcap/KBS mất ~6,2s mỗi mã (442 mã /
    2732s). Rổ 500 mã cần ~3100s. Trần fetch phải chứa nổi con số đó, nếu không
    thì MỌI lượt đều dừng sớm kể cả khi cache đã ấm — đúng chuyện đã xảy ra với
    trần 2700s cũ.
    """
    import run_daily
    assert run_daily.FETCH_BUDGET_S >= 3100


# --- Chỉ kiểm sự kiện quyền cho mã đạt ngưỡng công bố ------------------------

def test_only_candidates_above_min_score_hit_the_api(env):
    """Pre-Breakout 22/09: ~250 mã được chấm, chỉ vài chục mã đạt min_score."""
    _, calls, _ = env
    results = [SimpleNamespace(ticker=f'T{i}', total_score=i, metrics={}) for i in range(10)]
    kept = ca.apply_event_filter(results, min_score=7)
    assert sorted(calls) == ['T7', 'T8', 'T9']
    # Mã dưới ngưỡng vẫn giữ nguyên, đúng thứ tự
    assert [r.ticker for r in kept] == [r.ticker for r in results]


def test_below_threshold_results_not_dropped_even_with_dilutive_event(env, monkeypatch):
    """Mã dưới ngưỡng không được kiểm nên cũng không bị loại (không vào latest.json)."""
    _, calls, _ = env
    monkeypatch.setattr(ca, 'has_recent_event', lambda events, days: True)
    monkeypatch.setattr(ca, 'fetch_events', lambda tk, *a, **k: ['event'])
    results = [SimpleNamespace(ticker='LOW', total_score=1, metrics={}),
               SimpleNamespace(ticker='HIGH', total_score=9, metrics={})]
    kept = ca.apply_event_filter(results, min_score=5)
    assert [r.ticker for r in kept] == ['LOW']        # HIGH bị loại vì sự kiện pha loãng


def test_no_candidates_means_no_api_calls(env):
    _, calls, _ = env
    results = [SimpleNamespace(ticker=f'T{i}', total_score=1, metrics={}) for i in range(5)]
    assert ca.apply_event_filter(results, min_score=5) == results
    assert calls == []
