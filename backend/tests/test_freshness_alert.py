"""
Test chuông báo độ tươi dữ liệu.

Cái chuông này chỉ có giá trị nếu nó im lặng đúng lúc. Một chuông kêu oan mỗi
sáng Thứ Hai sẽ bị tắt trong một tuần, và khi sự cố thật xảy ra thì không còn ai
nghe. Nên phần lớn test dưới đây ghim các trường hợp PHẢI IM:

  - sáng Thứ Hai: dữ liệu Thứ Sáu trễ 3 ngày lịch nhưng 0 phiên
  - sáng sau kỳ nghỉ Tết: trễ 9 ngày lịch nhưng 0 phiên
  - sáng T7/CN: phiên kỳ vọng vẫn là Thứ Sáu

Và các trường hợp PHẢI KÊU:

  - trễ từ 2 phiên trở lên (đúng hình dạng sự cố 17-20/08/2026)
  - file mất, JSON vỡ, thiếu session_date — fail closed
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

import pytest

from check_freshness import (
    COMPANIONS,
    PRIMARY,
    evaluate,
    expected_session,
    read_session_date,
    render_issue,
)
from scanner.trading_calendar import trading_sessions_between


# ── Dựng repo giả ────────────────────────────────────────────────────────
def _write(root: Path, rel: str, session_date, **meta):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'generated_at': '2026-08-20T23:40:00',
        'strategy': 'pre_breakout',
        'total': 7,
        'metadata': {'session_date': session_date, 'run_type': 'eod', **meta},
        'signals': [],
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return p


def make_repo(tmp_path: Path, session_date, companions=True):
    """Repo giả với latest.json (+ 3 file chiến lược) mang ngày phiên cho trước."""
    _write(tmp_path, PRIMARY, session_date)
    if companions:
        for rel in COMPANIONS:
            _write(tmp_path, rel, session_date)
    return tmp_path


# ── trading_sessions_between: đơn vị đo của toàn bộ cái chuông ───────────
def test_sessions_between_consecutive_weekdays():
    # T4 → T5 = 1 phiên
    assert trading_sessions_between(date(2026, 8, 19), date(2026, 8, 20)) == 1


def test_sessions_between_friday_to_monday_is_one_session():
    # 3 ngày lịch nhưng chỉ 1 phiên — đây là lý do không đếm bằng ngày lịch.
    assert trading_sessions_between(date(2026, 8, 21), date(2026, 8, 24)) == 1


def test_sessions_between_same_day_is_zero():
    assert trading_sessions_between(date(2026, 8, 20), date(2026, 8, 20)) == 0


def test_sessions_between_end_before_start_is_zero():
    # Dữ liệu tươi HƠN kỳ vọng (job chạy muộn, đã có phiên mới) — không phải lỗi.
    assert trading_sessions_between(date(2026, 8, 21), date(2026, 8, 19)) == 0


def test_sessions_between_skips_tet_holiday():
    # Tết Bính Ngọ 16-20/02/2026. Phiên cuối trước Tết 13/02 (T6) → 23/02 (T2)
    # là 10 ngày lịch nhưng đúng 1 phiên.
    assert trading_sessions_between(date(2026, 2, 13), date(2026, 2, 23)) == 1


def test_sessions_between_caps_runaway():
    assert trading_sessions_between(date(2020, 1, 1), date(2026, 1, 1), cap=50) == 50


# ── expected_session: mốc so sánh ────────────────────────────────────────
def test_expected_is_yesterday_on_a_trading_day():
    # Sáng T5 20/08 → phiên kỳ vọng là T4 19/08, KHÔNG phải 20/08: lúc 08:00 ICT
    # HOSE chưa mở cửa (09:00), đòi phiên hôm nay là đòi thứ chưa tồn tại.
    assert expected_session(date(2026, 8, 20)) == date(2026, 8, 19)


def test_expected_on_monday_is_friday():
    assert expected_session(date(2026, 8, 24)) == date(2026, 8, 21)


def test_expected_on_saturday_is_friday():
    assert expected_session(date(2026, 8, 22)) == date(2026, 8, 21)


def test_expected_on_sunday_is_friday():
    assert expected_session(date(2026, 8, 23)) == date(2026, 8, 21)


def test_expected_first_morning_after_tet():
    # 23/02/2026 là T2 đầu tiên sau Tết → phiên cuối trước Tết là 13/02 (T6).
    assert expected_session(date(2026, 2, 23)) == date(2026, 2, 13)


# ── PHẢI IM LẶNG ─────────────────────────────────────────────────────────
def test_fresh_data_is_quiet(tmp_path):
    root = make_repo(tmp_path, '2026-08-19')
    r = evaluate(root, date(2026, 8, 20))
    assert r['stale'] is False
    assert r['lag'] == 0


def test_monday_morning_with_friday_data_is_quiet(tmp_path):
    """Kêu oan mỗi sáng Thứ Hai là cách nhanh nhất để cái chuông bị tắt."""
    root = make_repo(tmp_path, '2026-08-21')      # T6
    r = evaluate(root, date(2026, 8, 24))         # sáng T2
    assert r['stale'] is False
    assert r['lag'] == 0


def test_morning_after_tet_with_pre_tet_data_is_quiet(tmp_path):
    root = make_repo(tmp_path, '2026-02-13')      # phiên cuối trước Tết
    r = evaluate(root, date(2026, 2, 23))         # sáng T2 đầu tiên sau Tết
    assert r['stale'] is False
    assert r['lag'] == 0


def test_one_session_late_is_tolerated(tmp_path):
    """Một ca hỏng đơn lẻ thì im — GitHub thỉnh thoảng bỏ tick, ca sau vá lại."""
    root = make_repo(tmp_path, '2026-08-18')
    r = evaluate(root, date(2026, 8, 20))         # kỳ vọng 19/08
    assert r['lag'] == 1
    assert r['stale'] is False


def test_data_newer_than_expected_is_quiet(tmp_path):
    root = make_repo(tmp_path, '2026-08-20')
    r = evaluate(root, date(2026, 8, 20))         # kỳ vọng 19/08, có sẵn 20/08
    assert r['lag'] == 0
    assert r['stale'] is False


# ── PHẢI KÊU ─────────────────────────────────────────────────────────────
def test_two_sessions_late_alerts(tmp_path):
    root = make_repo(tmp_path, '2026-08-17')
    r = evaluate(root, date(2026, 8, 20))         # kỳ vọng 19/08
    assert r['lag'] == 2
    assert r['stale'] is True


def test_the_actual_august_outage(tmp_path):
    """
    Ghim đúng sự cố thật: dữ liệu đóng băng ở 14/08, daily-scan fail cả 8 ca
    17-20/08. Bảng dưới là ngày mà cái chuông ĐÁNG LẼ đã kêu nếu nó tồn tại.
    """
    root = make_repo(tmp_path, '2026-08-14')      # T6, phiên tốt cuối cùng
    seen = {}
    for day in (17, 18, 19, 20, 21):
        seen[day] = evaluate(root, date(2026, 8, day))['stale']

    # Sáng T2 17/08: kỳ vọng vẫn là 14/08 → chưa có gì sai.
    assert seen[17] is False
    # Sáng 18/08: kỳ vọng 17/08, trễ 1 phiên → còn trong ngưỡng.
    assert seen[18] is False
    # Sáng 19/08: trễ 2 phiên → KÊU. Sớm hơn thực tế phát hiện 8 ngày.
    assert seen[19] is True
    assert seen[20] is True and seen[21] is True


def test_missing_file_alerts(tmp_path):
    """Fail closed: không có file thì không chứng minh được gì."""
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert r['lag'] is None
    assert 'không tồn tại' in r['reason']


def test_corrupt_json_alerts(tmp_path):
    p = tmp_path / PRIMARY
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"metadata": {"session_date": "2026-08-', encoding='utf-8')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert 'JSON' in r['reason']


def test_missing_session_date_alerts(tmp_path):
    _write(tmp_path, PRIMARY, None)
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert 'session_date' in r['reason']


def test_non_iso_session_date_alerts(tmp_path):
    _write(tmp_path, PRIMARY, '20/08/2026')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert 'ISO' in r['reason']


def test_json_array_instead_of_object_alerts(tmp_path):
    p = tmp_path / PRIMARY
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('[]', encoding='utf-8')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True


# ── Ngưỡng điều chỉnh được ───────────────────────────────────────────────
def test_max_lag_zero_alerts_on_single_session(tmp_path):
    root = make_repo(tmp_path, '2026-08-18')
    assert evaluate(root, date(2026, 8, 20), max_lag=0)['stale'] is True
    assert evaluate(root, date(2026, 8, 20), max_lag=1)['stale'] is False


# ── Báo cáo ──────────────────────────────────────────────────────────────
def test_issue_body_carries_the_numbers(tmp_path):
    root = make_repo(tmp_path, '2026-08-14')
    r = evaluate(root, date(2026, 8, 20))
    title, body = render_issue(r)
    assert '2026-08-14' in title and '2026-08-19' in title
    assert '2026-08-14' in body
    assert 'daily-scan.yml' in body          # có lệnh kiểm tiếp
    for rel in COMPANIONS:                   # ba file kia có mặt để đối chiếu
        assert rel in body


def test_issue_body_reports_truncated_fetch(tmp_path):
    """Khi việc 2 dừng sớm vì ngân sách, issue phải nói ra lý do đó."""
    _write(tmp_path, PRIMARY, '2026-08-14',
           fetch_stop_reason='time_budget', fetch_coverage=0.28)
    r = evaluate(tmp_path, date(2026, 8, 20))
    _, body = render_issue(r)
    assert 'time_budget' in body
    assert '0.28' in body


def test_companion_files_reported_even_when_primary_ok(tmp_path):
    root = make_repo(tmp_path, '2026-08-19', companions=False)
    r = evaluate(root, date(2026, 8, 20))
    assert r['stale'] is False               # chấm điểm chỉ dựa trên latest.json
    assert all(c['session_date'] is None for c in r['companions'])


def test_read_session_date_returns_context(tmp_path):
    p = _write(tmp_path, PRIMARY, '2026-08-19', session_complete=0.98)
    sd, ctx = read_session_date(p)
    assert sd == '2026-08-19'
    assert ctx['session_complete'] == 0.98
    assert ctx['run_type'] == 'eod'
    assert 'error' not in ctx


# ── Đường lùi khi latest.json còn ở schema cũ ────────────────────────────
def _write_archive_index(root: Path, latest):
    p = root / 'web' / 'data' / 'archive' / 'index.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'latest': latest, 'dates': [latest], 'count': 1}),
                 encoding='utf-8')


def test_falls_back_to_archive_index_when_session_date_missing(tmp_path):
    """
    Mọi file commit trước 27/08/2026 chỉ có run_type/run_date_ict, chưa có
    session_date. Không có đường lùi thì cái chuông kêu oan ngay lần chạy đầu
    vì LỆCH SCHEMA — và chuông kêu oan hôm đầu thì hôm sau không ai nghe.
    """
    _write(tmp_path, PRIMARY, None)                  # schema cũ
    _write_archive_index(tmp_path, '2026-08-19')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['session_date'] == '2026-08-19'
    assert r['stale'] is False
    assert 'dự phòng' in r['session_date_source']


def test_fallback_still_alerts_when_archive_itself_is_late(tmp_path):
    """Đường lùi là để đọc được ngày, không phải để tha thứ."""
    _write(tmp_path, PRIMARY, None)
    _write_archive_index(tmp_path, '2026-08-14')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert r['lag'] == 3          # 17, 18, 19/08 — kỳ vọng là 19/08 chứ không phải 20/08


def test_session_date_wins_over_archive_index(tmp_path):
    """Có session_date thì dùng nó, kể cả khi archive index nói khác."""
    _write(tmp_path, PRIMARY, '2026-08-19')
    _write_archive_index(tmp_path, '2026-08-14')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['session_date'] == '2026-08-19'
    assert r['session_date_source'] == 'metadata.session_date'
    assert r['stale'] is False


def test_no_fallback_when_primary_file_is_missing(tmp_path):
    """
    Dashboard đọc chính latest.json. File mất mà archive index còn tốt thì vẫn
    phải kêu — đường lùi chỉ vá lỗ hổng SCHEMA, không vá lỗ hổng FILE.
    """
    _write_archive_index(tmp_path, '2026-08-19')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert r['session_date'] is None
    assert r['session_date_source'] is None


def test_no_fallback_when_primary_is_corrupt(tmp_path):
    p = tmp_path / PRIMARY
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{oops', encoding='utf-8')
    _write_archive_index(tmp_path, '2026-08-19')
    assert evaluate(tmp_path, date(2026, 8, 20))['stale'] is True


def test_corrupt_archive_index_is_ignored(tmp_path):
    _write(tmp_path, PRIMARY, None)
    p = tmp_path / 'web' / 'data' / 'archive' / 'index.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('not json', encoding='utf-8')
    r = evaluate(tmp_path, date(2026, 8, 20))
    assert r['stale'] is True
    assert r['session_date'] is None
