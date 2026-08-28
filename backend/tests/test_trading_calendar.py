"""
Test lịch giao dịch — bảo vệ khỏi lỗi "dashboard trống suốt kỳ nghỉ Tết".
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, datetime

from scanner.trading_calendar import (
    ICT,
    SESSION_BARS_AVAILABLE_FROM,
    is_trading_day,
    last_expected_session,
    last_trading_session,
    previous_trading_day,
    infer_last_session_from_dates,
    has_holiday_table,
)
from scanner.data_fetcher import _last_trading_session


# ── Cuối tuần (hành vi cũ phải được giữ nguyên) ──────────────────────────
def test_saturday_falls_back_to_friday():
    assert last_trading_session(date(2026, 8, 8)) == date(2026, 8, 7)   # T7 → T6


def test_sunday_falls_back_to_friday():
    assert last_trading_session(date(2026, 8, 9)) == date(2026, 8, 7)


def test_weekday_is_itself():
    assert last_trading_session(date(2026, 8, 12)) == date(2026, 8, 12)  # T4


# ── Nghỉ lễ (hành vi MỚI) ────────────────────────────────────────────────
def test_tet_holiday_is_not_trading_day():
    """Tết Bính Ngọ 2026: 16-20/02 nghỉ."""
    for day in range(16, 21):
        assert not is_trading_day(date(2026, 2, day)), f"2026-02-{day} phải là ngày nghỉ"


def test_last_session_during_tet_skips_back_before_holiday():
    """
    Thứ Tư 18/02/2026 nằm giữa kỳ nghỉ Tết → phiên gần nhất phải là 13/02 (T6
    trước Tết), KHÔNG phải chính ngày đó. Đây chính là lỗi làm mọi mã bị gắn
    StaleCache và dashboard trống.
    """
    assert last_trading_session(date(2026, 2, 18)) == date(2026, 2, 13)


def test_last_session_after_tet():
    """Thứ Hai 23/02/2026 là phiên giao dịch bình thường sau Tết."""
    assert last_trading_session(date(2026, 2, 23)) == date(2026, 2, 23)


def test_national_day_holiday():
    """2-3/09/2026 nghỉ Quốc khánh → phiên gần nhất là 01/09."""
    assert last_trading_session(date(2026, 9, 3)) == date(2026, 9, 1)


def test_reunification_day():
    """30/4 và 1/5/2026 nghỉ → phiên gần nhất là 29/04."""
    assert last_trading_session(date(2026, 5, 1)) == date(2026, 4, 29)


def test_previous_trading_day_excludes_today():
    assert previous_trading_day(date(2026, 8, 12)) == date(2026, 8, 11)


# ── Năm chưa có bảng: không được đoán bừa ────────────────────────────────
def test_unknown_year_degrades_to_weekend_only():
    assert not has_holiday_table(2035)
    # 2035-01-01 là Thứ Hai — không có bảng nên coi như ngày giao dịch
    assert is_trading_day(date(2035, 1, 1))


# ── Suy từ dữ liệu thật ──────────────────────────────────────────────────
def test_infer_from_index_dates():
    dates = ['2026-02-11', '2026-02-12', '2026-02-13']
    assert infer_last_session_from_dates(dates, today=date(2026, 2, 18)) == date(2026, 2, 13)


def test_infer_ignores_future_dates():
    assert infer_last_session_from_dates(['2030-01-01'], today=date(2026, 2, 18)) is None


def test_infer_empty():
    assert infer_last_session_from_dates([], today=date(2026, 2, 18)) is None


# ── data_fetcher dùng đúng lịch mới ──────────────────────────────────────
def test_data_fetcher_uses_holiday_calendar():
    assert _last_trading_session(date(2026, 2, 18)) == date(2026, 2, 13)


# ── last_expected_session: phiên T chưa có nến trước 09:15 ───────────────
#
# Sự cố 28/08/2026: tick intraday tới muộn 19h45, chạy lúc 08:17 ICT. Sàn chưa
# mở, không mã nào có nến phiên T, `last_trading_session` vẫn khai phiên T →
# 500/500 mã bị đóng dấu StaleCache → mọi strategy trả 0 → ba file latest.json
# bị ghi đè bằng rỗng.

def at_ict(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ICT)


def test_before_open_returns_previous_session():
    """07:50 thứ Sáu 28/08/2026 — sàn chưa mở, phiên có nến là 27/08."""
    assert last_expected_session(at_ict(2026, 8, 28, 7, 50)) == date(2026, 8, 27)


def test_after_ato_returns_today():
    """09:20 cùng ngày — ATO đã khớp, phiên 28/08 đã có nến."""
    assert last_expected_session(at_ict(2026, 8, 28, 9, 20)) == date(2026, 8, 28)


def test_boundary_one_minute_before_ato_close():
    """
    09:14 — biên. ATO khớp trong khung 09:00-09:15, một phút trước mốc thì vẫn
    chưa có gì. Ghim để lần sau ai đó nới mốc còn thấy nó đổi.
    """
    assert last_expected_session(at_ict(2026, 8, 28, 9, 14)) == date(2026, 8, 27)
    assert SESSION_BARS_AVAILABLE_FROM.strftime('%H:%M') == '09:15'


def test_before_open_monday_after_tet_skips_whole_holiday():
    """
    07:50 thứ Hai 23/02/2026, ngay sau kỳ nghỉ Tết Bính Ngọ (16-20/02).
    Phải lùi qua CẢ kỳ nghỉ lẫn cuối tuần về 13/02 — phiên cuối trước Tết.
    Đây là chỗ hai lỗi chồng nhau: nghỉ lễ và giờ chưa mở cửa.
    """
    assert last_expected_session(at_ict(2026, 2, 23, 7, 50)) == date(2026, 2, 13)


def test_weekend_returns_last_weekday_session():
    """Cuối tuần thì giờ trong ngày không đổi được gì — vẫn là phiên T6."""
    assert last_expected_session(at_ict(2026, 8, 29, 10, 0)) == date(2026, 8, 28)
    assert last_expected_session(at_ict(2026, 8, 30, 23, 59)) == date(2026, 8, 28)


def test_utc_clock_is_converted_not_trusted():
    """
    02:50 UTC ngày 28/08 = 09:50 ICT — đã qua ATO. Nếu hàm tin tên tham số mà
    không quy đổi, nó đọc 02:50 và trả nhầm phiên hôm trước.
    """
    from datetime import timezone as _tz
    utc_now = datetime(2026, 8, 28, 2, 50, tzinfo=_tz.utc)
    assert last_expected_session(utc_now) == date(2026, 8, 28)
