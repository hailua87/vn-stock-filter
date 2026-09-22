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

    def spy(results, lookback_days, lookahead_days, deadline=None):
        seen['deadline'] = deadline
        return results
    monkeypatch.setattr(sc, 'apply_event_filter', spy)
    monkeypatch.setattr(sc, 'evaluate', lambda df, tk, cfg: SimpleNamespace(ticker=tk))
    monkeypatch.setattr(sc.BreakoutScanner, 'to_dataframe', lambda self: self.results)

    import pandas as pd
    df = pd.DataFrame({'Ticker': ['AAA', 'BBB'], 'Date': ['2026-09-22'] * 2})
    sc.BreakoutScanner(events_deadline=123.0).scan_from_dataframe(df)
    assert seen['deadline'] == 123.0


def test_run_daily_default_budget_is_under_workflow_timeout():
    import run_daily
    assert run_daily.FETCH_BUDGET_S < run_daily.RUN_BUDGET_S < 60 * 60
