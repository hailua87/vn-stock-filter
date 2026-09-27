"""
Ngân sách thời gian nội bộ cho hai script hằng tuần (thêm 27/09/2026).

Vì sao có file này: ngày 27/09 bước chấm chất lượng chạm trần 45 phút và bị
runner giết GIỮA vòng lấy dữ liệu — tức chết trước mọi bước ghi file, nên toàn
bộ công đã chấm không thành cái gì. `run_daily` đã có `FETCH_BUDGET_S` để chặn
đúng kiểu hỏng đó từ sự cố 17-20/08/2026; hai script hằng tuần thì chưa.

Hai thứ được chốt ở đây:
  1. Vòng lấy dữ liệu DỪNG khi hết ngân sách, và phần chấm điểm + ghi file
     phía sau vẫn chạy trọn.
  2. Rổ bị cắt thì KHÔNG ghi đè tệp đủ của lượt trước (scanner/publish_gate).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_quality import build_quality
from scanner.publish_gate import may_publish

AS_OF = date(2026, 9, 27)


def _raw(ticker: str) -> dict:
    """BCTC tối thiểu — test này lo về vòng lặp và cổng ghi, không lo về điểm."""
    return {
        'ticker': ticker,
        'overview': {'industry': 'Technology'},
        'fetched_at': '2026-09-27',
    }


# ─── 1. Vòng lấy dữ liệu tự dừng ─────────────────────────────────────────────

def test_build_quality_stops_when_told_and_still_returns_a_full_payload():
    """
    Điểm mấu chốt: dừng sớm phải cho ra một payload ĐẦY ĐỦ HÌNH DẠNG, không
    phải một mẩu dở dang. Đó chính là khác biệt với bị runner giết.
    """
    tickers = [f'T{i:02d}' for i in range(20)]
    seen = []

    def fetch_year(t):
        seen.append(t)
        return _raw(t)

    payload = build_quality(
        tickers, fetch_year=fetch_year, fetch_quarter=lambda t: None,
        valuation_signals={}, as_of=AS_OF, delisted=set(), previous={},
        should_stop=lambda: len(seen) >= 5,
    )

    assert len(seen) == 5, 'phải dừng đúng chỗ, không chạy nốt cả rổ'
    m = payload['metadata']
    assert m['attempted'] == 5 and m['universe_size'] == 20
    assert m['fetch_coverage'] == 0.25
    assert '5/20' in m['fetch_stop_reason']
    # Payload vẫn ghi được ra JSON như một lượt bình thường
    assert payload['schema'] and payload['as_of'] == '2026-09-27'
    assert len(payload['items']) == 5
    assert set(payload['metadata']) >= {'status_counts', 'model_counts', 'thresholds'}


def test_should_stop_is_asked_before_fetching_not_after():
    """
    Hỏi sau khi fetch thì vẫn vượt trần: một lượt gọi nguồn có thể mất tới ~20s
    khi Vietcap/KBS timeout rồi retry ba lần.
    """
    seen = []

    def fetch_year(t):
        seen.append(t)
        return _raw(t)

    payload = build_quality(
        ['A', 'B', 'C'], fetch_year=fetch_year, fetch_quarter=lambda t: None,
        valuation_signals={}, as_of=AS_OF, delisted=set(), previous={},
        should_stop=lambda: True,
    )
    assert seen == [], 'đã hết ngân sách thì không được gọi nguồn thêm lần nào'
    assert payload['metadata']['attempted'] == 0
    assert payload['items'] == []


def test_no_budget_means_the_whole_universe():
    """Mặc định (should_stop=None) phải y hệt trước khi có ngân sách."""
    tickers = [f'T{i:02d}' for i in range(12)]
    payload = build_quality(
        tickers, fetch_year=_raw, fetch_quarter=lambda t: None,
        valuation_signals={}, as_of=AS_OF, delisted=set(), previous={},
    )
    m = payload['metadata']
    assert m['attempted'] == 12 and m['fetch_coverage'] == 1.0
    assert m['fetch_stop_reason'] is None


# ─── 2. Cổng công bố ─────────────────────────────────────────────────────────

def test_full_coverage_publishes_quietly(tmp_path):
    existing = tmp_path / 'latest.json'
    existing.write_text('{}', encoding='utf-8')
    ok, why = may_publish(1.0, 0.8, existing)
    assert ok and why == '', 'lượt bình thường không được sinh cảnh báo'


def test_thin_run_does_not_overwrite_last_weeks_file(tmp_path):
    """
    Lý do không nằm ở "ít mã hơn" mà ở CHỖ BỊ CẮT: rổ xếp theo thanh khoản giảm
    dần, nên phần còn lại thiên về mã lớn và mọi con số tính theo nhóm (peer
    median, percentile) đổi theo. Tệp tuần trước — dựa trên BCTC ra theo quý —
    gần như không mất gì khi cũ thêm một tuần.
    """
    existing = tmp_path / 'latest.json'
    existing.write_text('{"signals": ["đủ 200 mã"]}', encoding='utf-8')
    ok, why = may_publish(0.4, 0.8, existing)
    assert not ok
    assert '40%' in why and '80%' in why
    assert existing.read_text(encoding='utf-8') == '{"signals": ["đủ 200 mã"]}'


def test_thin_run_still_publishes_when_there_is_nothing_to_keep(tmp_path):
    """Chưa có tệp nào thì tệp mỏng vẫn hơn không có gì — web phải có dữ liệu."""
    ok, why = may_publish(0.4, 0.8, tmp_path / 'chua-ton-tai.json')
    assert ok
    assert 'vẫn ghi' in why, 'ghi trong trường hợp này thì phải nói ra vì sao'


def test_exactly_at_the_floor_publishes(tmp_path):
    """Ngưỡng là >=, không phải >: 80% đúng bằng ngưỡng thì công bố."""
    existing = tmp_path / 'latest.json'
    existing.write_text('{}', encoding='utf-8')
    ok, _ = may_publish(0.8, 0.8, existing)
    assert ok


# ─── 3. Vòng PASS 1 của định giá ─────────────────────────────────────────────
#
# Chốt riêng vì đây là bước đắt nhất và là bước đã chạy 68 phút ngày 27/09.
# Chốt bằng hằng số thôi thì không chứng minh được vòng lặp thật sự dừng.

def _stub_valuation(monkeypatch, fetched: list):
    """Thay mọi lời gọi mạng và mọi phép tính nặng bằng hàm rỗng."""
    import run_valuation as RV
    from scanner import peer_database, market_metrics
    from scanner.strategies.valuation import normalizer

    monkeypatch.setattr(RV, 'setup_api_key', lambda *a, **k: None)
    monkeypatch.setattr(RV, 'fetch_fundamentals',
                        lambda t, **k: fetched.append(t) or {'ticker': t})
    monkeypatch.setattr(market_metrics, 'enrich_with_market_metrics', lambda t, raw: raw)
    monkeypatch.setattr(normalizer, 'normalize_fundamentals',
                        lambda raw: {'overview': {}, 'ticker': raw['ticker']})
    monkeypatch.setattr(peer_database, 'extract_peer_input', lambda d: None)
    monkeypatch.setattr(peer_database, 'save_peer_database', lambda db: None)
    monkeypatch.setattr(RV, 'value_ticker', lambda t, **k: None)
    return RV


def test_valuation_pass1_stops_at_the_budget_and_still_reaches_the_writes(tmp_path, monkeypatch):
    """
    Đồng hồ giả nhảy vọt qua ngân sách sau 3 mã. Vòng PASS 1 phải dừng, và
    tiến trình phải ĐI TIẾP tới bước ghi file — đó là cả lý do tồn tại của
    ngân sách nội bộ.
    """
    fetched = []
    RV = _stub_valuation(monkeypatch, fetched)

    ticks = iter([0, 0, 1, 2, 9999, 9999, 9999])   # mốc bắt đầu, rồi 3 mã, rồi vọt
    rc = RV.main(['--tickers', 'A,B,C,D,E,F', '--fetch-budget', '60',
                  '--snapshot-registry', '', '--web-data-dir', str(tmp_path)],
                 clock=lambda: next(ticks))

    assert fetched == ['A', 'B', 'C'], f'phải dừng sau 3 mã, thực tế {fetched}'
    assert rc == 0
    # Bước ghi file đã chạy — chưa có tệp cũ nên lượt mỏng vẫn được công bố
    import json
    payload = json.loads((tmp_path / 'valuation' / 'latest.json').read_text(encoding='utf-8'))
    m = payload['metadata']
    assert m['universe_size'] == 6 and m['total_attempted'] == 3
    assert m['fetch_coverage'] == 0.5
    assert 'hết ngân sách PASS 1' in m['fetch_stop_reason']


def test_valuation_keeps_last_weeks_file_when_the_run_was_cut(tmp_path, monkeypatch):
    """Đã có tệp đủ của lượt trước thì lượt mỏng KHÔNG được ghi đè, và phải đỏ."""
    web = tmp_path / 'valuation'
    web.mkdir(parents=True)
    (web / 'latest.json').write_text('{"signals": ["tuần trước, đủ mã"]}', encoding='utf-8')

    fetched = []
    RV = _stub_valuation(monkeypatch, fetched)
    ticks = iter([0, 0, 9999, 9999, 9999])
    rc = RV.main(['--tickers', 'A,B,C,D', '--fetch-budget', '60',
                  '--snapshot-registry', '', '--web-data-dir', str(tmp_path)],
                 clock=lambda: next(ticks))

    assert rc == 1, 'bỏ công bố phải làm job đỏ để ci-alert mở issue'
    assert (web / 'latest.json').read_text(encoding='utf-8') == '{"signals": ["tuần trước, đủ mã"]}'
    assert not (web / 'archive').exists() or not list((web / 'archive').glob('*.json'))


def test_valuation_without_a_cut_publishes_normally(tmp_path, monkeypatch):
    """Đồng hồ đứng yên: chạy trọn rổ, công bố như thường, mã thoát 0."""
    fetched = []
    RV = _stub_valuation(monkeypatch, fetched)
    rc = RV.main(['--tickers', 'A,B,C,D', '--fetch-budget', '60',
                  '--snapshot-registry', '', '--web-data-dir', str(tmp_path)],
                 clock=lambda: 0)

    assert fetched == ['A', 'B', 'C', 'D'] and rc == 0
    import json
    m = json.loads((tmp_path / 'valuation' / 'latest.json').read_text(encoding='utf-8'))['metadata']
    assert m['fetch_coverage'] == 1.0 and m['fetch_stop_reason'] is None


# ─── 4. Người đọc phải biết lượt đó bị cắt ───────────────────────────────────

def _health_with(tmp_path, valuation_meta: dict) -> dict:
    """health.json + tệp định giá mang metadata cho trước, rồi refresh_weekly."""
    import json
    from scanner import health as H

    web = tmp_path
    (web / 'valuation').mkdir(parents=True)
    (web / 'valuation' / 'latest.json').write_text(json.dumps({
        'generated_at': '2026-09-27T08:00:00',
        'metadata': valuation_meta,
        'signals': [{'ticker': 'A'}, {'ticker': 'B'}],
    }), encoding='utf-8')
    (web / 'health.json').write_text(json.dumps({
        'sources': {'daily_scan': {'label': 'Scan hằng ngày', 'fetch': {},
                                   'archive_written': True, 'universe': 490}},
    }), encoding='utf-8')
    return H.refresh_weekly(web / 'health.json', web,
                            now=datetime(2026, 9, 27, 9, 0))


def test_a_cut_but_published_run_is_announced_to_the_reader(tmp_path):
    """
    Lượt bị cắt nhưng còn đủ phủ thì VẪN công bố — và đó mới là trường hợp nguy
    hiểm: con số trông hoàn toàn bình thường, không có gì tự lộ ra. Khối "Tình
    trạng dữ liệu" là chỗ duy nhất người đọc biết được.
    """
    out = _health_with(tmp_path, {'fetch_coverage': 0.85,
                                  'fetch_stop_reason': 'hết ngân sách PASS 1 sau 170/200 mã'})
    codes = {i['code'] for i in out['issues']}
    assert 'valuation_partial' in codes
    msg = next(i['message'] for i in out['issues'] if i['code'] == 'valuation_partial')
    assert '85%' in msg and '170/200' in msg
    assert 'không phải cả rổ' in msg, 'phải nói rõ hệ quả, không chỉ nói "dừng sớm"'


def test_a_normal_run_says_nothing_about_being_cut(tmp_path):
    out = _health_with(tmp_path, {'fetch_coverage': 1.0, 'fetch_stop_reason': None})
    assert 'valuation_partial' not in {i['code'] for i in out['issues']}


def test_being_cut_does_not_hide_the_staleness_warning(tmp_path):
    """
    Hai cảnh báo độc lập. Trước khi sửa, một `continue` còn sót của code cũ nằm
    ngay sau khối mới — nên lượt bị cắt sẽ NUỐT mất cảnh báo "dữ liệu đã cũ".
    """
    from scanner import health as H
    import json
    web = tmp_path
    (web / 'valuation').mkdir(parents=True)
    (web / 'valuation' / 'latest.json').write_text(json.dumps({
        'generated_at': '2026-08-01T08:00:00',          # rất cũ
        'metadata': {'fetch_coverage': 0.85,
                     'fetch_stop_reason': 'hết ngân sách PASS 1 sau 170/200 mã'},
        'signals': [{'ticker': 'A'}],
    }), encoding='utf-8')
    (web / 'health.json').write_text(json.dumps({
        'sources': {'daily_scan': {'label': 'Scan hằng ngày', 'fetch': {},
                                   'archive_written': True, 'universe': 490}},
    }), encoding='utf-8')
    out = H.refresh_weekly(web / 'health.json', web, now=datetime(2026, 9, 27, 9, 0))
    codes = {i['code'] for i in out['issues']}
    assert {'valuation_partial', 'valuation_stale'} <= codes, codes


# ─── 5. `--help` phải chạy được ──────────────────────────────────────────────

def test_help_does_not_crash(capsys):
    """
    Lỗi có sẵn, thấy khi thêm --fetch-budget: argparse chạy mọi chuỗi help qua
    phép định dạng `%`, nên `'upside % tối thiểu'` làm `--help` nổ ngay —
    ValueError: unsupported format character 't'. Dấu % trần phải viết `%%`.

    Chốt cho cả hai script vì chuỗi help là chỗ dễ lặp lại đúng lỗi này nhất.
    """
    import pytest
    import run_quality
    import run_valuation
    for mod in (run_valuation, run_quality):
        with pytest.raises(SystemExit) as e:
            mod.main(['--help'])
        assert e.value.code == 0
        assert '--fetch-budget' in capsys.readouterr().out
