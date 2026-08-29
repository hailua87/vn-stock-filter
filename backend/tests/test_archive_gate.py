"""
Test cổng ghi archive — bảo vệ khỏi hai lỗi ngược chiều nhau.

Bản guard cũ hỏi `os.environ['SCAN_RUN_TYPE'] == 'intraday'`. Nhãn đó do workflow
dán bằng giờ UTC lúc job KHỞI ĐỘNG rồi đóng băng, còn bước ghi file diễn ra sau
đó 30-60 phút. Hệ quả là nó sai cả hai chiều, và mỗi test dưới đây ghim một chiều:

  - CHẶN NHẦM: bản khởi động 12:00 ICT nhưng ghi lúc 15:40 vẫn mang nhãn
    'intraday' nên bị bỏ archive, dù khối lượng đã chốt từ ~15:08. Ba phiên thật
    20/07, 29/07, 31/07 rơi đúng vào đây.
    → test_intraday_label_but_written_after_cutoff_is_archived

  - LỌT: thiếu biến môi trường thì `'' != 'intraday'` trả False, tức coi như EOD
    và ghi archive vô điều kiện. Hỏng theo hướng MỞ.
    → test_missing_env_is_blocked

Cả hai test này ĐỎ nếu revert về bản cũ: hoặc vì `archive_decision` không tồn tại
(AttributeError), hoặc vì hành vi ngược lại đúng như mô tả trên.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

import pandas as pd
import pytest

from run_daily import (
    ICT,
    ARCHIVE_CUTOFF_ICT,
    archive_decision,
    build_metadata,
    session_completeness,
    session_date_from_data,
    write_strategy_outputs,
)


def at(hh, mm):
    """Một thời điểm ICT trong phiên 26/08/2026 (thứ Tư)."""
    return datetime(2026, 8, 26, hh, mm, tzinfo=ICT)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Mỗi test tự quyết định nhãn; không để rò rỉ từ môi trường thật."""
    monkeypatch.delenv('SCAN_RUN_TYPE', raising=False)


# ── Ba trường hợp bắt buộc ───────────────────────────────────────────────

def test_intraday_label_but_written_after_cutoff_is_archived(monkeypatch):
    """Khởi động 12:00 ICT (nhãn intraday) nhưng ghi lúc 15:40 → PHẢI ghi.

    Bản cũ chặn ở đây và vứt oan dữ liệu đã đủ.
    """
    monkeypatch.setenv('SCAN_RUN_TYPE', 'intraday')
    d = archive_decision(now=at(15, 40), session_date='2026-08-26')
    assert d['write'] is True
    assert d['forced'] is False
    assert d['run_type'] == 'intraday'      # nhãn vẫn được ghi lại, chỉ là không cầm quyền


def test_written_mid_session_is_blocked(monkeypatch):
    """Ghi lúc 13:00 ICT (phiên chiều chưa đóng) → PHẢI chặn."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'intraday')
    assert archive_decision(now=at(13, 0), session_date='2026-08-26')['write'] is False


def test_missing_env_is_blocked():
    """Thiếu SCAN_RUN_TYPE → PHẢI chặn (fail-closed).

    Bản cũ GHI trong trường hợp này, nên mọi caller ngoài workflow — chạy tay,
    rebuild_web_data.py, workflow khác — đều archive được vô điều kiện.
    """
    d = archive_decision(now=at(13, 0), session_date='2026-08-26')
    assert d['write'] is False
    assert d['run_type'] == 'unknown'


# ── Nhãn không còn cầm quyền theo cả hai chiều ───────────────────────────

def test_manual_eod_override_cannot_open_gate(monkeypatch):
    """workflow_dispatch chọn tay 'eod' lúc 12:00 KHÔNG được mở cổng."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    assert archive_decision(now=at(12, 0), session_date='2026-08-26')['write'] is False


def test_missing_env_after_cutoff_is_archived():
    """Thiếu nhãn nhưng đồng hồ đã qua mốc → vẫn ghi. Cổng là đồng hồ, không phải nhãn."""
    d = archive_decision(now=at(15, 40), session_date='2026-08-26')
    assert d['write'] is True
    assert d['run_type'] == 'unknown'


# ── Cửa ép ghi ───────────────────────────────────────────────────────────

def test_force_opens_gate_and_is_recorded(monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    d = archive_decision(force=True, now=at(13, 0), session_date='2026-08-26')
    assert d['write'] is True
    assert d['forced'] is True       # phải để lại dấu vết trong metadata


def test_force_is_not_marked_when_clock_already_allows():
    """Qua mốc rồi thì --force-archive không có tác dụng gì, và không bị đánh dấu."""
    d = archive_decision(force=True, now=at(15, 40), session_date='2026-08-26')
    assert d['write'] is True
    assert d['forced'] is False


# ── Biên ngưỡng ──────────────────────────────────────────────────────────

def test_cutoff_boundary_is_inclusive():
    assert ARCHIVE_CUTOFF_ICT.strftime('%H:%M') == '15:15'
    assert archive_decision(now=at(15, 15), session_date='2026-08-26')['write'] is True
    assert archive_decision(now=at(15, 14), session_date='2026-08-26')['write'] is False


def test_gate_ignores_runner_utc_clock(monkeypatch):
    """13:00 ICT = 06:00 UTC. Nếu ai đó lỡ so bằng giờ UTC thì test này đỏ."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    assert archive_decision(now=at(13, 0), session_date='2026-08-26')['write'] is False
    assert archive_decision(now=at(23, 30), session_date='2026-08-26')['write'] is True


# ── Ngày phiên lấy từ dữ liệu ────────────────────────────────────────────

def test_session_date_comes_from_data_not_clock():
    df = pd.DataFrame({'Date': pd.to_datetime(
        ['2026-08-10', '2026-08-12', '2026-08-11'])})     # cố tình không sắp xếp
    assert session_date_from_data(df) == '2026-08-12'


def test_session_date_none_when_no_data():
    assert session_date_from_data(pd.DataFrame()) is None
    assert session_date_from_data(None) is None


# ── Cờ độ trọn vẹn: đo được, nhưng KHÔNG chặn ────────────────────────────

def test_completeness_detects_half_session():
    by_ticker = {'X': pd.DataFrame({'Volume': [100] * 20 + [64]})}
    assert session_completeness(by_ticker) == pytest.approx(0.64)


def test_completeness_none_when_history_too_short():
    assert session_completeness({'X': pd.DataFrame({'Volume': [100] * 5})}) is None
    assert session_completeness({}) is None


def test_low_completeness_does_not_block(monkeypatch):
    """Cờ là cờ. Phiên trầm lắng cũng cho ratio thấp nên nó không được cầm quyền."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    assert archive_decision(now=at(23, 30), session_date='2026-08-26')['write'] is True     # không nhận completeness
    meta = build_metadata(5, ('HOSE',), 10, {}, '2026-08-26',
                          archive_decision(now=at(23, 30), session_date='2026-08-26'), 0.31)
    assert meta['session_complete'] == 0.31
    assert meta['archive_written'] is True


# ── Metadata phải nằm trong CHÍNH file archive ───────────────────────────

class _FakeResult:
    def __init__(self, ticker, score):
        self.ticker, self.total_score = ticker, score

    def to_dict(self):
        return {'ticker': self.ticker, 'total_score': self.total_score}


def _write(tmp_path, decision, session_date='2026-08-26', completeness=0.98):
    write_strategy_outputs(
        [_FakeResult('AAA', 7)], tmp_path / 'ichimoku', session_date,
        min_score=3, exchanges=('HOSE',), total_scanned=1,
        strategy_label='ichimoku', market_context={},
        decision=decision, completeness=completeness,
    )
    return tmp_path / 'ichimoku'


def test_archive_file_carries_the_three_evidence_fields(tmp_path, monkeypatch):
    """
    Bước jq của workflow chỉ vá run_type vào latest.json, không vá bản archive —
    nên nhìn một file archive không biết nó là bản nào. Ba trường này phải nằm
    trong chính file archive.
    """
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    out = _write(tmp_path, archive_decision(now=at(23, 30), session_date='2026-08-26'))

    archived = out / 'archive' / '2026-08-26.json'
    assert archived.exists()
    meta = json.loads(archived.read_text(encoding='utf-8'))['metadata']
    assert meta['run_type'] == 'eod'
    assert meta['session_complete'] == 0.98
    assert meta['written_at_ict'].startswith('2026-08-26 23:30')
    assert meta['session_date'] == '2026-08-26'
    assert meta['archive_forced'] is False


def test_archive_filename_uses_session_date_not_write_date(tmp_path, monkeypatch):
    """Bản EOD chạy 00:07 ICT ngày 22 vẫn phải ghi vào tên file của phiên 21."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    written_at = datetime(2026, 8, 22, 0, 7, tzinfo=ICT)
    # Phiên 21 đã đóng từ hôm trước → cổng thời gian PASS, không cần ép.
    # Bản cũ chặn ở đây ("00:07 < 15:15") và đó chính là lỗi đang sửa.
    assert archive_decision(now=written_at, session_date='2026-08-21')['write'] is True
    out = _write(tmp_path, archive_decision(now=written_at, session_date='2026-08-21'),
                 session_date='2026-08-21')
    assert (out / 'archive' / '2026-08-21.json').exists()
    assert not (out / 'archive' / '2026-08-22.json').exists()


def test_blocked_run_writes_latest_but_no_archive(tmp_path, monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'intraday')
    out = _write(tmp_path, archive_decision(now=at(13, 0), session_date='2026-08-26'))
    assert (out / 'latest.json').exists()             # theo dõi trong ngày vẫn cần
    assert not (out / 'archive' / '2026-08-26.json').exists()
    assert not (out / 'archive' / 'index.json').exists()


def test_forced_archive_is_flagged_in_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv('SCAN_RUN_TYPE', 'intraday')
    out = _write(tmp_path, archive_decision(force=True, now=at(13, 0), session_date='2026-08-26'))
    archived = out / 'archive' / '2026-08-26.json'
    meta = __import__('json').loads(archived.read_text(encoding='utf-8'))['metadata']
    assert meta['archive_forced'] is True
    assert meta['run_type'] == 'intraday'


def test_missing_session_date_blocks_archive(tmp_path, monkeypatch):
    """Không suy được ngày phiên thì không được đoán bằng đồng hồ."""
    monkeypatch.setenv('SCAN_RUN_TYPE', 'eod')
    out = _write(tmp_path, archive_decision(now=at(23, 30), session_date='2026-08-26'), session_date=None)
    assert (out / 'latest.json').exists()
    assert list((out / 'archive').glob('*.json')) == []


def test_legacy_intraday_key_kept_for_frontend():
    """web/app.js:373 vẫn đọc metadata.intraday làm nguồn dự phòng."""
    meta = build_metadata(5, ('HOSE',), 1, {}, '2026-08-26',
                          {'write': False, 'forced': False, 'run_type': 'intraday',
                           'written_at_ict': 'x', 'reason': 'y'}, None)
    assert meta['intraday'] is True


# ── gate_time xét PHIÊN ĐÃ CHỐT, không chỉ xét giờ ───────────────────────
#
# Ghim sự cố 28-29/08/2026: ca EOD chạy 23:42 ICT, quét 35 phút, ghi lúc 00:07
# ICT hôm sau. Phiên 28/08 đã đóng từ 9 tiếng trước — khối lượng không thể còn
# chạy vào — vậy mà cổng cũ đọc "00:07 < 15:15" rồi chặn, và archive/2026-08-28
# không bao giờ được ghi. Ca EOD theo lịch (23:05 ICT) chỉ cần quét quá 55 phút
# là dính.

def ict(y, mo, d, hh, mm):
    return datetime(y, mo, d, hh, mm, tzinfo=ICT)


def test_qua_nua_dem_phien_hom_truoc_thi_pass():
    """00:17 ICT 29/08, phiên 28/08 → PASS. Đây là ca chạy tay đã bị chặn oan."""
    d = archive_decision(now=ict(2026, 8, 29, 0, 17), session_date='2026-08-28')
    assert d['write'] is True
    assert d['forced'] is False


def test_truoc_gio_mo_cua_phien_hom_truoc_van_pass():
    """
    07:50 ICT 29/08, phiên 28/08 → PASS.

    Trước giờ mở cửa nhưng phiên đang ghi là phiên HÔM QUA, đã chốt hẳn. Cổng
    thời gian không có lý do gì chặn; thứ chặn ca này (nếu cần) là gate_coverage
    hoặc cổng stale, không phải cổng giờ.
    """
    d = archive_decision(now=ict(2026, 8, 29, 7, 50), session_date='2026-08-28')
    assert d['write'] is True


def test_giua_phien_hom_nay_van_bi_chan():
    """12:05 ICT 28/08, phiên 28/08 → FAIL. Luật cũ giữ nguyên cho phiên hôm nay."""
    d = archive_decision(now=ict(2026, 8, 28, 12, 5), session_date='2026-08-28')
    assert d['write'] is False
    assert d['gates_failed'] == ['gate_time']


def test_sau_moc_chot_trong_ngay_thi_pass():
    """23:05 ICT 28/08, phiên 28/08 → PASS. Ca EOD bình thường, không đổi."""
    d = archive_decision(now=ict(2026, 8, 28, 23, 5), session_date='2026-08-28')
    assert d['write'] is True


def test_thieu_ngay_phien_thi_dong():
    """session_date None → FAIL. Thiếu thông tin thì đóng, không đoán."""
    d = archive_decision(now=ict(2026, 8, 28, 23, 5), session_date=None)
    assert d['write'] is False
    assert d['gates_failed'] == ['gate_time']


def test_ngay_phien_tuong_lai_thi_dong():
    """
    session_date > hôm nay → FAIL.

    Không có cách đọc lành nào: hoặc dữ liệu hỏng, hoặc đồng hồ sai. Nếu nhánh
    này mở thì một `session_date` rác sẽ ghi đè file archive của một ngày chưa
    tồn tại.
    """
    d = archive_decision(now=ict(2026, 8, 28, 23, 5), session_date='2026-09-15')
    assert d['write'] is False
    assert d['gates_failed'] == ['gate_time']
