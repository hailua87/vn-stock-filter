"""
Cảnh báo khi nguồn dở chứng (28/09/2026).

Vì sao đếm tỷ lệ TREO chứ không đo thời gian chạy — ba phép đo cùng 200 mã,
cùng bước chấm chất lượng, trong hai ngày:

    cache ấm,  nguồn sạch :     37 giây
    cache lạnh, nguồn sạch :     27 phút
    cache ấm,  nguồn dở   :     70 phút (chạm trần, chỉ xong 165/200)

Thời gian chạy chênh nhau 114 lần chỉ vì cache, nên một ngưỡng theo thời gian
sẽ báo động nhầm mỗi lượt cache lạnh. Tỷ lệ treo thì không đổi theo cache:
cùng ba lượt đó đo được 0,00 / 0,00 / ~0,56.

Đây cũng là chỗ sửa một điều tôi từng chốt nhầm vào chú thích code: nguồn
KHÔNG treo "~1,7 lần mỗi mã" như một đặc tính cố định — có lượt sạch tuyệt đối.
Nó thất thường, nên phải đo từng lượt.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import health as H
from scanner.sources import http as HTTP


# ─── 1. Bộ đếm ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_counters():
    HTTP.reset_stats()
    yield
    HTTP.reset_stats()


def _call(monkeypatch, exc=None):
    class _Sess:
        def request(self, *a, **k):
            if exc:
                raise exc
            class R:
                status_code = 200
                def json(self): return {}
            return R()
    monkeypatch.setattr(HTTP, '_session', lambda: _Sess())
    monkeypatch.setattr(HTTP, 'MIN_INTERVAL', 0)
    try:
        HTTP.request_json('GET', 'https://x.test/api/y')
    except HTTP.SourceError:
        pass


def test_a_healthy_call_counts_but_does_not_flag(monkeypatch):
    _call(monkeypatch)
    s = HTTP.stats()
    assert s == {'calls': 1, 'timeouts': 0, 'timeout_ratio': 0.0}


def test_a_timeout_is_counted(monkeypatch):
    _call(monkeypatch, requests.ReadTimeout('treo'))
    s = HTTP.stats()
    assert s['calls'] == 1 and s['timeouts'] == 1 and s['timeout_ratio'] == 1.0


def test_other_network_errors_are_not_counted_as_timeouts(monkeypatch):
    """
    Một 404 hay DNS hỏng nói điều KHÁC HẲN về nguồn so với việc nó nhận request
    rồi im lặng. Gộp chung thì cảnh báo mất nghĩa.
    """
    _call(monkeypatch, requests.ConnectionError('DNS'))
    s = HTTP.stats()
    assert s['calls'] == 1 and s['timeouts'] == 0


def test_reset_clears_between_runs(monkeypatch):
    _call(monkeypatch, requests.ReadTimeout('treo'))
    HTTP.reset_stats()
    assert HTTP.stats()['calls'] == 0


# ─── 2. Cảnh báo tới người đọc ───────────────────────────────────────────────

def _health_with(tmp_path, source_stats: dict) -> dict:
    (tmp_path / 'valuation').mkdir(parents=True)
    (tmp_path / 'valuation' / 'latest.json').write_text(json.dumps({
        'generated_at': '2026-09-28T08:00:00',
        'metadata': {'fetch_coverage': 1.0, 'fetch_stop_reason': None,
                     'source_stats': source_stats},
        'signals': [{'ticker': 'A'}],
    }), encoding='utf-8')
    (tmp_path / 'health.json').write_text(json.dumps({
        'sources': {'daily_scan': {'label': 'Scan hằng ngày', 'fetch': {},
                                   'archive_written': True, 'universe': 490}},
    }), encoding='utf-8')
    return H.refresh_weekly(tmp_path / 'health.json', tmp_path,
                            now=datetime(2026, 9, 28, 9, 0))


def test_a_flaky_run_is_announced(tmp_path):
    out = _health_with(tmp_path, {'calls': 495, 'timeouts': 275, 'timeout_ratio': 0.556})
    msg = next((i['message'] for i in out['issues']
                if i['code'] == 'valuation_source_flaky'), None)
    assert msg, [i['code'] for i in out['issues']]
    assert '56%' in msg and '275/495' in msg
    assert 'vẫn đúng' in msg, 'phải nói rõ dữ liệu lấy được KHÔNG sai, tránh hiểu nhầm'


def test_a_clean_run_says_nothing(tmp_path):
    """Lượt cache lạnh 27 phút đo được 0 treo trên ~1.600 lượt gọi — không kêu."""
    out = _health_with(tmp_path, {'calls': 1600, 'timeouts': 0, 'timeout_ratio': 0.0})
    assert 'valuation_source_flaky' not in {i['code'] for i in out['issues']}


def test_missing_stats_does_not_crash_or_warn(tmp_path):
    """Tệp cũ sinh trước thay đổi này không có khoá đó — không được nổ."""
    out = _health_with(tmp_path, {})
    assert 'valuation_source_flaky' not in {i['code'] for i in out['issues']}


def test_the_threshold_sits_between_the_two_measured_runs():
    """
    Chốt chính phép chọn ngưỡng. 0,10 nằm giữa hai đầu ĐÃ ĐO (0,00 và ~0,56),
    lệch hẳn về phía sạch để kêu sớm. Chưa đo được lượt "hơi dở", nên nếu sau
    này hiệu chỉnh lại thì phải sửa cả chú thích, không lặng lẽ đổi số.
    """
    assert 0.0 < H.SOURCE_TIMEOUT_NOTICE < 0.5


# ─── 3. Hai script phải THẬT SỰ ghi con số đó ra ─────────────────────────────
#
# Thiếu phần này thì mọi thứ trên chỉ là cơ chế không ai bật: thử gỡ hẳn dòng
# ghi `source_stats` khỏi run_quality, toàn bộ 693 test vẫn xanh.

def test_run_quality_writes_source_stats(monkeypatch, tmp_path):
    import pandas as pd
    import run_quality

    monkeypatch.setattr('scanner.financial_fetcher.fetch_fundamentals',
                        lambda t, **k: None)
    monkeypatch.setattr('scanner.financial_fetcher.fetch_quarterly_statements',
                        lambda t, **k: None)
    monkeypatch.setattr('scanner.financial_fetcher.fetch_bank_ratios', lambda t: None)
    monkeypatch.setattr('scanner.data_fetcher.setup_api_key', lambda *a, **k: None)
    monkeypatch.setattr('scanner.data_fetcher.get_ticker_universe',
                        lambda ex, limit=None: pd.DataFrame({'ticker': ['AAA']}))

    run_quality.main(['--web-data-dir', str(tmp_path), '--snapshot-registry', ''])
    out = json.loads((tmp_path / 'quality' / 'latest.json').read_text(encoding='utf-8'))
    ss = out['metadata'].get('source_stats')
    assert ss is not None and 'timeout_ratio' in ss, (
        'run_quality phải ghi source_stats vào metadata — không có thì health.py '
        'không bao giờ cảnh báo được')


def test_run_valuation_writes_source_stats(monkeypatch, tmp_path):
    import run_valuation as RV
    from scanner import market_metrics, peer_database
    from scanner.strategies.valuation import normalizer

    monkeypatch.setattr(RV, 'setup_api_key', lambda *a, **k: None)
    monkeypatch.setattr(RV, 'fetch_fundamentals', lambda t, **k: {'ticker': t})
    monkeypatch.setattr(market_metrics, 'enrich_with_market_metrics', lambda t, raw: raw)
    monkeypatch.setattr(normalizer, 'normalize_fundamentals',
                        lambda raw: {'overview': {}, 'ticker': raw['ticker']})
    monkeypatch.setattr(peer_database, 'extract_peer_input', lambda d: None)
    monkeypatch.setattr(peer_database, 'save_peer_database', lambda db: None)
    monkeypatch.setattr(RV, 'value_ticker', lambda t, **k: None)

    RV.main(['--tickers', 'AAA', '--snapshot-registry', '',
             '--web-data-dir', str(tmp_path)], clock=lambda: 0)
    out = json.loads((tmp_path / 'valuation' / 'latest.json').read_text(encoding='utf-8'))
    ss = out['metadata'].get('source_stats')
    assert ss is not None and 'timeout_ratio' in ss
