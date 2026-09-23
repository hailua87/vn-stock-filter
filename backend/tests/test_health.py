"""
health.json — tình trạng dữ liệu cho màn Hôm nay (blueprint v3 §11.2, §13).

Hai thứ dễ sai nhất: (1) coi ca intraday không ghi archive là LỖI, trong khi
đó là đúng thiết kế; (2) không giữ lại số mã của lần chạy trước, nên kiểm tra
"rổ co lại > 5%" của §13 không bao giờ chạy được.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner import health as H


NOW = datetime(2026, 9, 23, 18, 0, 0)


def args(**over):
    base = dict(
        session_date='2026-09-22',
        run_meta={'run_type': 'eod', 'run_date_ict': '2026-09-23', 'run_time_ict': '02:46'},
        fetch_summary={'coverage': 1.0, 'ok': 480, 'skipped': 0, 'failed': 0, 'stop_reason': None},
        completeness=0.92,
        decision={'write': True, 'reason': 'phiên đã đóng dứt khoát'},
        stale_ratio=0.05,
        universe=480,
        base_conditions={'universe_after': 340, 'dropped_low_liquidity': 140},
    )
    base.update(over)
    return base


def codes(payload):
    return {i['code'] for i in payload['issues']}


def write_weekly(web, sub, generated_at, n=3, as_of='2026-09-22'):
    d = web / sub
    d.mkdir(parents=True, exist_ok=True)
    key = 'items' if sub == 'quality' else 'signals'
    (d / 'latest.json').write_text(json.dumps({
        'as_of': as_of, 'generated_at': generated_at, key: [{}] * n,
    }), encoding='utf-8')


def test_clean_run_has_no_issues(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    p = H.build(web_dir=tmp_path, now=NOW, **args())
    assert p['issues'] == []
    assert p['sources']['daily_scan']['universe'] == 480
    assert p['sources']['quality']['count'] == 3
    # Khoa fetch_summary that la 'ok'/'skipped' (data_fetcher._summary), khong
    # phai 'succeeded' — doc nham thi con so hien ra man hinh la null.
    assert p['sources']['daily_scan']['fetch']['succeeded'] == 480


def test_intraday_archive_skip_is_info_not_error(tmp_path):
    """Ca intraday KHÔNG ghi archive theo đúng thiết kế — gắn nhãn 'error' sẽ
    làm khối tình trạng dữ liệu đỏ mỗi trưa mà không có gì hỏng."""
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    p = H.build(web_dir=tmp_path, now=NOW,
                **args(decision={'write': False, 'reason': 'phiên chưa đóng'}))
    issue = next(i for i in p['issues'] if i['code'] == 'archive_skipped')
    assert issue['severity'] == 'info'
    assert 'phiên chưa đóng' in issue['message']


def test_universe_shrink_uses_previous_file(tmp_path):
    """§13: so với lần chạy TRƯỚC, nên phải đọc health.json cũ trước khi ghi đè."""
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    H.write(tmp_path / 'health.json', H.build(web_dir=tmp_path, now=NOW, **args(universe=500)))

    p = H.build(web_dir=tmp_path, now=NOW, **args(universe=400))     # −20%
    assert 'universe_shrank' in codes(p)
    assert next(i for i in p['issues'] if i['code'] == 'universe_shrank')['severity'] == 'error'


def test_small_universe_change_is_not_an_issue(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    H.write(tmp_path / 'health.json', H.build(web_dir=tmp_path, now=NOW, **args(universe=500)))
    p = H.build(web_dir=tmp_path, now=NOW, **args(universe=485))     # −3%
    assert 'universe_shrank' not in codes(p)


def test_no_previous_file_means_no_shrink_claim(tmp_path):
    """Lần chạy đầu không có gì để so — không được bịa ra một kết luận."""
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    assert 'universe_shrank' not in codes(H.build(web_dir=tmp_path, now=NOW, **args()))


def test_weekly_sources_flagged_when_old_or_missing(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-01T07:00:00')        # 22 ngày
    p = H.build(web_dir=tmp_path, now=NOW, **args())
    assert 'valuation_stale' in codes(p)
    assert 'quality_missing' in codes(p)
    assert p['sources']['quality']['available'] is False


def test_fetch_problems_surface(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    p = H.build(web_dir=tmp_path, now=NOW, **args(
        fetch_summary={'coverage': 0.62, 'ok': 300, 'skipped': 0, 'failed': 12,
                       'stop_reason': 'hết ngân sách thời gian'}))
    assert {'fetch_stopped', 'fetch_failed'} <= codes(p)


@pytest.mark.parametrize('ratio,flagged', [(0.05, False), (0.19, False), (0.20, True), (0.43, True)])
def test_stale_notice_threshold(tmp_path, ratio, flagged):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    p = H.build(web_dir=tmp_path, now=NOW, **args(stale_ratio=ratio))
    assert ('stale_high' in codes(p)) is flagged


def test_unreadable_previous_file_does_not_crash(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    (tmp_path / 'health.json').write_text('{ hong', encoding='utf-8')
    assert H.build(web_dir=tmp_path, now=NOW, **args())['issues'] == []


def test_age_days_reads_both_stamp_shapes():
    assert H._age_days('2026-09-20T07:00:00', NOW) == 3
    assert H._age_days('2026-09-20', NOW) == 3
    assert H._age_days('2026-09-20T07:00:00Z', NOW) == 3
    assert H._age_days('khong phai ngay', NOW) is None
    assert H._age_days(None, NOW) is None


def test_write_is_readable(tmp_path):
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    p = H.write(tmp_path / 'health.json', H.build(web_dir=tmp_path, now=NOW, **args()))
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['schema'] == H.SCHEMA and d['sources']['daily_scan']['session_date'] == '2026-09-22'


# ─── refresh_weekly: hai lượt chạy theo hai lịch, mỗi lượt sở hữu phần của nó ──

def test_refresh_weekly_updates_only_its_own_part(tmp_path):
    """
    `run_daily` ghi tệp, `run_quality` chạy SAU theo lịch khác. Nếu lượt sau
    dựng lại cả tệp thì mọi số của lượt quét (độ phủ fetch, tỷ lệ stale, cổng
    archive) biến mất — run_quality không biết chúng.
    """
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00', as_of='2026-09-20')
    H.write(tmp_path / 'health.json', H.build(web_dir=tmp_path, now=NOW, **args()))

    # Lượt chấm chất lượng mới hơn
    write_weekly(tmp_path, 'quality', '2026-09-23T14:00:00', n=200, as_of='2026-09-23')
    out = H.refresh_weekly(tmp_path / 'health.json', tmp_path, now=NOW)

    assert out['sources']['quality']['as_of'] == '2026-09-23'
    assert out['sources']['quality']['count'] == 200
    # Phần của lượt quét còn NGUYÊN
    d = out['sources']['daily_scan']
    assert d['universe'] == 480 and d['stale_ratio'] == 0.05
    assert d['fetch']['coverage'] == 1.0 and d['archive_written'] is True


def test_refresh_weekly_does_not_create_a_half_file(tmp_path):
    """Chưa có tệp thì KHÔNG tạo: một health.json thiếu hẳn phần lượt quét còn
    khó đọc hơn là không có tệp nào."""
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    assert H.refresh_weekly(tmp_path / 'health.json', tmp_path, now=NOW) is None
    assert not (tmp_path / 'health.json').exists()


def test_refresh_weekly_does_not_claim_universe_shrank(tmp_path):
    """Kiểm tra 'rổ co lại' là việc của lượt quét. Tính lại ở đây sẽ so tệp với
    chính nó và luôn ra 0% — vô nghĩa, nhưng tệ hơn là nó có thể ra dương nếu
    ai đó đổi thứ tự."""
    write_weekly(tmp_path, 'valuation', '2026-09-20T07:00:00')
    write_weekly(tmp_path, 'quality', '2026-09-20T07:00:00')
    H.write(tmp_path / 'health.json', H.build(web_dir=tmp_path, now=NOW, **args()))
    out = H.refresh_weekly(tmp_path / 'health.json', tmp_path, now=NOW)
    assert 'universe_shrank' not in {i['code'] for i in out['issues']}


def test_valuation_as_of_falls_back_to_generated_at(tmp_path):
    """Tệp định giá không có `as_of` lẫn `metadata.session_date`. Trước đây ô
    ngày trên màn Hôm nay hiện '—' trong khi tệp hoàn toàn biết nó sinh ngày nào."""
    d = tmp_path / 'valuation'
    d.mkdir(parents=True)
    (d / 'latest.json').write_text(json.dumps({
        'generated_at': '2026-09-23T16:30:27.904759',
        'metadata': {'period': 'year'},
        'signals': [{}] * 65,
    }), encoding='utf-8')
    write_weekly(tmp_path, 'quality', '2026-09-23T14:00:00')
    p = H.build(web_dir=tmp_path, now=NOW, **args())
    assert p['sources']['valuation']['as_of'] == '2026-09-23'
    assert p['sources']['valuation']['count'] == 65
