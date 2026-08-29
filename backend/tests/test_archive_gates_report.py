"""
Test bảng cổng archive — mọi cổng phải được chấm và báo cáo, kể cả cổng đã pass.

Bản cũ đoản mạch ở cổng hỏng đầu tiên và trả về đúng một câu lý do. Hệ quả:

  - Ca intraday có vòng fetch bị cắt thì CẢ HAI cổng cùng chặn, nhưng log chỉ
    nói về một. Sửa xong cái đó, chạy lại, vẫn không ghi archive, và không hiểu
    tại sao.
  - Khi độ phủ mỏng thì không biết cổng giờ đã pass hay chưa — phải suy ngược
    từ `written_at_ict`.
  - Nhìn một file archive ba tháng sau không biết nó qua được nhờ cổng nào.

Ràng buộc quan trọng nhất của bản mới: QUYẾT ĐỊNH không được đổi. Chỉ phần
trình bày đổi. Nhóm test cuối ghim đúng điều đó.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

import pytest

from run_daily import (
    ICT,
    archive_decision,
    build_metadata,
    evaluate_archive_gates,
    format_gates,
)


@pytest.fixture(autouse=True)
def _run_type(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')


def at(h, m):
    return datetime(2026, 8, 27, h, m, tzinfo=ICT)


def summary(coverage, stop_reason=None):
    return {'coverage': coverage, 'truncated': stop_reason is not None,
            'stop_reason': stop_reason, 'ok': int(coverage * 500), 'total': 500}


def gate(gates, name):
    return next(g for g in gates if g['name'] == name)


# ── Mọi cổng đều có mặt, bất kể kết quả ──────────────────────────────────
def test_both_gates_always_reported():
    cases = [(at(23, 12), summary(0.98)),
             (at(12, 52), summary(0.62, 'time_budget')),
             (at(23, 12), None),
             (at(12, 0), summary(1.0))]
    for now, fs in cases:
        names = [g['name'] for g in evaluate_archive_gates(now, fs, session_date='2026-08-27')]
        assert names == ['gate_time', 'gate_coverage'], (now, fs)


def test_passing_gate_is_reported_not_omitted():
    """Cổng giờ pass vẫn phải xuất hiện khi cổng độ phủ hỏng."""
    gates = evaluate_archive_gates(at(23, 12), summary(0.62, 'time_budget'), session_date='2026-08-27')
    assert gate(gates, 'gate_time')['passed'] is True
    assert '23:12' in gate(gates, 'gate_time')['detail']
    assert '15:15' in gate(gates, 'gate_time')['detail']
    assert gate(gates, 'gate_coverage')['passed'] is False


def test_both_gates_can_fail_at_once():
    """
    Ca intraday + vòng fetch bị cắt. Bản cũ chỉ nói về độ phủ; người đọc sửa
    xong độ phủ rồi vẫn không ghi được archive vì cổng giờ vẫn chặn.
    """
    d = archive_decision(now=at(12, 52), fetch_summary=summary(0.62, 'time_budget'), session_date='2026-08-27')
    assert d['gates_failed'] == ['gate_time', 'gate_coverage']
    assert d['write'] is False
    assert 'gate_time: fail' in d['reason']
    assert 'gate_coverage: fail' in d['reason']


# ── Con số thật nằm trong detail ─────────────────────────────────────────
def test_detail_carries_the_numbers():
    gates = evaluate_archive_gates(at(23, 12), summary(0.62, 'time_budget'), session_date='2026-08-27')
    detail = gate(gates, 'gate_coverage')['detail']
    assert '62%' in detail and '80%' in detail
    assert 'time_budget' in detail


def test_passing_coverage_detail_says_so():
    detail = gate(evaluate_archive_gates(at(23, 12), summary(0.98), session_date='2026-08-27'),
                  'gate_coverage')['detail']
    assert '98%' in detail and '80%' in detail
    assert 'trọn' in detail


def test_unmeasured_coverage_is_not_dressed_up_as_pass():
    """
    Không có fetch_summary thì cổng không chặn được gì — nhưng detail phải nói
    rõ là KHÔNG ĐO ĐƯỢC, khác hẳn với "đã đo và đạt".
    """
    g = gate(evaluate_archive_gates(at(23, 12), None, session_date='2026-08-27'), 'gate_coverage')
    assert g['passed'] is True
    assert 'không đo được' in g['detail']
    assert '%' not in g['detail']


def test_custom_threshold_shows_in_detail():
    g = gate(evaluate_archive_gates(at(23, 12), summary(0.62), min_coverage=0.5, session_date='2026-08-27'),
             'gate_coverage')
    assert g['passed'] is True
    assert '50%' in g['detail']


def test_truncated_but_above_threshold_still_fails():
    """Dừng sớm là dừng sớm, kể cả khi độ phủ tình cờ vẫn trên ngưỡng."""
    g = gate(evaluate_archive_gates(at(23, 12), summary(0.95, 'circuit_breaker'), session_date='2026-08-27'),
             'gate_coverage')
    assert g['passed'] is False
    assert 'circuit_breaker' in g['detail']
    assert '95%' in g['detail']


# ── format_gates: một dòng cho log ───────────────────────────────────────
def test_format_matches_the_agreed_shape():
    line = format_gates(evaluate_archive_gates(at(23, 12),
                                               summary(0.62, 'time_budget'), session_date='2026-08-27'))
    assert line.startswith('gate_time: pass (')
    assert ' | gate_coverage: fail (' in line


def test_format_lists_every_gate():
    gates = evaluate_archive_gates(at(12, 0), summary(1.0), session_date='2026-08-27')
    assert format_gates(gates).count('|') == len(gates) - 1


# ── Metadata mang bản có cấu trúc ────────────────────────────────────────
def test_metadata_carries_structured_gates():
    fs = summary(0.62, 'time_budget')
    d = archive_decision(now=at(23, 12), fetch_summary=fs, session_date='2026-08-27')
    meta = build_metadata(5, ('HOSE',), 310, {}, '2026-08-27', d, 0.31, fs)

    assert [g['name'] for g in meta['archive_gates']] == ['gate_time', 'gate_coverage']
    assert meta['archive_gates'][0]['passed'] is True
    assert meta['archive_gates'][1]['passed'] is False
    assert meta['archive_gates_failed'] == ['gate_coverage']
    # Khoá chuỗi cũ vẫn còn: web/app.js và bước Verify của workflow đọc nó.
    assert 'gate_time: pass' in meta['archive_gate']


def test_metadata_gates_are_json_serialisable():
    import json
    fs = summary(0.62, 'time_budget')
    d = archive_decision(now=at(23, 12), fetch_summary=fs, session_date='2026-08-27')
    meta = build_metadata(5, ('HOSE',), 310, {}, '2026-08-27', d, 0.31, fs)
    round_tripped = json.loads(json.dumps(meta, default=str))
    assert round_tripped['archive_gates_failed'] == ['gate_coverage']
    assert round_tripped['archive_gates'][0]['name'] == 'gate_time'


def test_metadata_survives_decision_without_gates():
    """
    Bản decision dựng tay (test cũ, script khác) không có khoá `gates`.
    build_metadata phải chịu được thay vì nổ KeyError.
    """
    legacy = {'write': True, 'forced': False, 'run_type': 'eod',
              'written_at_ict': 'x', 'reason': 'y'}
    meta = build_metadata(5, ('HOSE',), 10, {}, '2026-08-27', legacy, None)
    assert meta['archive_gates'] == []
    assert meta['archive_gates_failed'] == []


# ── Ép ghi nêu đích danh cổng bị ép ──────────────────────────────────────
def test_force_names_the_gates_it_overrode():
    d = archive_decision(force=True, now=at(12, 52),
                         fetch_summary=summary(0.62, 'time_budget'), session_date='2026-08-27')
    assert d['write'] is True and d['forced'] is True
    assert 'ÉP GHI' in d['reason']
    tail = d['reason'].split('ÉP GHI')[1]
    assert 'gate_time' in tail
    assert 'gate_coverage' in tail


def test_force_on_a_clean_run_is_not_marked_forced():
    d = archive_decision(force=True, now=at(23, 12), fetch_summary=summary(1.0), session_date='2026-08-27')
    assert d['write'] is True and d['forced'] is False
    assert 'ÉP GHI' not in d['reason']


# ── QUYẾT ĐỊNH KHÔNG ĐƯỢC ĐỔI ────────────────────────────────────────────
@pytest.mark.parametrize('hour,minute,cov,stop,force,write,forced', [
    # giờ    phút  độ phủ  dừng sớm         force  ghi?   đánh dấu ép?
    (23,     12,   1.00,   None,            False, True,  False),
    (23,     12,   0.62,   'time_budget',   False, False, False),
    (23,     12,   0.62,   'time_budget',   True,  True,  True),
    (12,     52,   1.00,   None,            False, False, False),
    (12,     52,   1.00,   None,            True,  True,  True),
    (12,     52,   0.62,   'time_budget',   False, False, False),
    (12,     52,   0.62,   'time_budget',   True,  True,  True),
    (15,     15,   1.00,   None,            False, True,  False),   # đúng mốc = mở
    (15,     14,   1.00,   None,            False, False, False),   # sớm 1 phút = đóng
])
def test_decision_table_unchanged_by_the_rewrite(hour, minute, cov, stop,
                                                 force, write, forced):
    """
    Bảng này là hợp đồng. Viết lại để liệt kê mọi cổng là thay đổi TRÌNH BÀY;
    nếu một ô nào ở đây đổi thì đó là thay đổi hành vi và phải cố ý.
    """
    d = archive_decision(force=force, now=at(hour, minute),
                         fetch_summary=summary(cov, stop), session_date='2026-08-27')
    assert d['write'] is write
    assert d['forced'] is forced


def test_missing_fetch_summary_behaves_like_before():
    assert archive_decision(now=at(23, 30), session_date='2026-08-27')['write'] is True
    assert archive_decision(now=at(13, 0), session_date='2026-08-27')['write'] is False
