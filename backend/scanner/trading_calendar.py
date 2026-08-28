"""
LỊCH GIAO DỊCH HOSE/HNX/UPCOM
================================================================================
Vì sao cần file này:

`_last_trading_session()` cũ chỉ trừ Thứ Bảy/Chủ Nhật. Trong kỳ nghỉ lễ dài
(Tết Nguyên đán nghỉ ~5-7 phiên, 30/4-1/5, 2/9), "phiên gần nhất" theo lịch rơi
vào một ngày thường KHÔNG có giao dịch. Hệ quả dây chuyền:

  - Dữ liệu mới nhất trong cache là phiên trước kỳ nghỉ
  - `df.last_date < last_session` ⇒ mọi mã bị gắn `StaleCache = True`
  - Golden Cross + Ichimoku reject toàn bộ ⇒ dashboard trống suốt kỳ nghỉ
  - Workflow vẫn commit file rỗng đè lên dữ liệu tốt

Cách tiếp cận: bảng nghỉ lễ tĩnh (nguồn: thông báo nghỉ lễ hàng năm của HOSE)
kết hợp cơ chế suy ra từ dữ liệu thực (`infer_last_session_from_index`) để không
phụ thuộc hoàn toàn vào việc cập nhật bảng mỗi năm.

BẢO TRÌ: bổ sung HOLIDAYS mỗi năm khi HOSE công bố (thường tháng 12).
Nếu năm hiện tại chưa có trong bảng, hàm sẽ tự động chỉ dựa vào cuối tuần và
ghi cảnh báo — an toàn hơn là đoán bừa.

RÀNG BUỘC: FILE NÀY CHỈ ĐƯỢC DÙNG THƯ VIỆN CHUẨN Ở MỨC MODULE.
`check_freshness.py:48-79` nạp lẻ chính file này bằng `importlib`, trong một
môi trường CỐ Ý không cài `requirements.txt` — chuông báo độ tươi phải chạy được
kể cả khi vòng scan hỏng. Thêm một dòng `import` ngoài thư viện chuẩn ở đây
(pandas, numpy, ...) sẽ làm gãy chuông đó, và gãy im lặng: máy phát triển nào
cũng có sẵn pandas nên test local không thấy. Đã xảy ra thật — run 32998375558
(26/08/2026) chết với `ModuleNotFoundError: No module named 'pandas'`.
`test_runs_without_pandas` ghim điều này; pandas chỉ được import MUỘN, bên trong
`infer_last_session_from_dates`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

log = logging.getLogger(__name__)


# Việt Nam ở UTC+7 và không có DST từ 1975, nên offset cố định là chính xác và
# không phụ thuộc gói tzdata của máy chạy. `datetime.now()` trần KHÔNG dùng được:
# runner của GitHub Actions chạy giờ UTC, nên nó lệch 7 tiếng.
#
# Đặt ở đây chứ không ở run_daily (nơi nó ra đời) vì data_fetcher cũng cần, mà
# `data_fetcher -> run_daily` là import vòng: run_daily nạp data_fetcher ngay ở
# thân module. File này không import ngược lên đâu cả nên ai cũng gọi được.
ICT = timezone(timedelta(hours=7), name='ICT')


def now_ict() -> datetime:
    """Giờ ICT tại THỜI ĐIỂM GỌI — không phải nhãn dán lúc job khởi động."""
    return datetime.now(timezone.utc).astimezone(ICT)


# Ngày nghỉ giao dịch (không tính T7/CN). Định dạng ISO.
# Nguồn: thông báo lịch nghỉ lễ, Tết của HOSE/HNX.
HOLIDAYS: dict[int, tuple[str, ...]] = {
    2024: (
        '2024-01-01',                                                   # Tết Dương lịch
        '2024-02-08', '2024-02-09', '2024-02-12', '2024-02-13', '2024-02-14',  # Tết Giáp Thìn
        '2024-04-18',                                                   # Giỗ Tổ
        '2024-04-29', '2024-04-30', '2024-05-01',                       # 30/4 - 1/5
        '2024-09-02', '2024-09-03',                                     # Quốc khánh
    ),
    2025: (
        '2025-01-01',
        '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31',  # Tết Ất Tỵ
        '2025-04-07',                                                   # Giỗ Tổ
        '2025-04-30', '2025-05-01', '2025-05-02',                       # 30/4 - 1/5
        '2025-09-01', '2025-09-02',                                     # Quốc khánh
    ),
    2026: (
        '2026-01-01',
        '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20',  # Tết Bính Ngọ
        '2026-04-27',                                                   # Giỗ Tổ
        '2026-04-30', '2026-05-01',                                     # 30/4 - 1/5
        '2026-09-02', '2026-09-03',                                     # Quốc khánh
    ),
}


def _holiday_set(year: int) -> set[date]:
    return {date.fromisoformat(d) for d in HOLIDAYS.get(year, ())}


def is_trading_day(d: date) -> bool:
    """True nếu `d` là ngày giao dịch (không phải T7/CN và không phải ngày nghỉ)."""
    if d.weekday() >= 5:            # 5 = T7, 6 = CN
        return False
    if d.year not in HOLIDAYS:
        # Chưa có bảng cho năm này → chỉ dựa vào cuối tuần.
        return True
    return d not in _holiday_set(d.year)


def has_holiday_table(year: int) -> bool:
    return year in HOLIDAYS


def previous_trading_day(d: date) -> date:
    """Phiên giao dịch gần nhất TRƯỚC `d` (không tính chính `d`)."""
    cur = d - timedelta(days=1)
    for _ in range(30):             # đủ cho mọi kỳ nghỉ dài nhất
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    return cur


def last_trading_session(today: date) -> date:
    """
    Phiên giao dịch gần nhất tính đến `today` (bao gồm chính `today` nếu là
    ngày giao dịch — caller tự hiểu phiên hôm nay có thể chưa đóng cửa).
    """
    cur = today
    for _ in range(30):
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    return cur


# Nến của phiên T chỉ tồn tại từ mốc này trở đi. HOSE khớp lệnh mở cửa (ATO)
# trong khung 09:00-09:15; trước khi ATO khớp xong, phiên T CHƯA có cây nến nào —
# không nguồn dữ liệu nào trả về được, kể cả một nguồn hoàn hảo.
SESSION_BARS_AVAILABLE_FROM = time(9, 15)


def last_expected_session(now_ict: datetime) -> date:
    """
    Phiên gần nhất mà dữ liệu ĐÃ PHẢI tồn tại — xét cả ngày LẪN giờ.

    Khác `last_trading_session` ở đúng một chỗ, và đó là chỗ quan trọng:
    hàm kia trả lời "theo lịch, phiên gần nhất là ngày nào"; hàm này trả lời
    "tới thời điểm này thì phiên nào đã có nến". Trước 09:15 của một ngày giao
    dịch, hai câu trả lời khác nhau — và chính khoảng chênh đó gây sự cố
    08:17 ICT ngày 28/08/2026: `last_trading_session` khai phiên T, không mã nào
    có nến phiên T, cả 500 mã bị đóng dấu StaleCache oan.

    Dùng làm mốc so `df['Date'].max()` khi đóng dấu StaleCache.
    `last_trading_session` giữ nguyên — nó chỉ nhận `date`, không có giờ để xét,
    và nhiều chỗ đang gọi nó đúng nghĩa "phiên gần nhất theo lịch".
    """
    # Nhận nhầm đồng hồ UTC vào đây là tái hiện đúng lớp lỗi đang sửa, nên quy
    # đổi thay vì tin tên tham số. Datetime naive coi như đã là ICT.
    if now_ict.tzinfo is not None:
        now_ict = now_ict.astimezone(ICT)
    d = now_ict.date()
    if is_trading_day(d) and now_ict.time() >= SESSION_BARS_AVAILABLE_FROM:
        return d
    return previous_trading_day(d)


def trading_sessions_between(start: date, end: date, cap: int = 400) -> int:
    """
    Số phiên giao dịch nằm trong khoảng (start, end] — tức KHÔNG tính `start`,
    có tính `end` nếu nó là ngày giao dịch.

    Dùng để đo độ trễ dữ liệu bằng ĐƠN VỊ PHIÊN thay vì ngày lịch. Đếm bằng ngày
    lịch sẽ báo động sai mỗi sáng Thứ Hai (dữ liệu Thứ Sáu trễ 3 ngày lịch nhưng
    0 phiên) và ngược lại im lặng suốt kỳ nghỉ Tết dài.

    `cap` chặn vòng lặp khi dữ liệu cũ tới mức vô lý (hoặc ngày hỏng); trả về
    đúng `cap` — caller chỉ cần biết "rất trễ", không cần con số chính xác.
    """
    if end <= start:
        return 0
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            count += 1
            if count >= cap:
                return cap
        cur += timedelta(days=1)
    return count


def infer_last_session_from_dates(dates, today: date | None = None) -> date | None:
    """
    Suy phiên gần nhất TỪ DỮ LIỆU THẬT (thường là chuỗi ngày của VN-Index).

    An toàn hơn bảng tĩnh: nếu HOSE nghỉ đột xuất hoặc bảng HOLIDAYS chưa được
    cập nhật cho năm mới, dữ liệu index vẫn phản ánh đúng thực tế.

    Trả về None nếu không suy được (caller fallback về `last_trading_session`).
    """
    if dates is None or len(dates) == 0:
        return None
    try:
        import pandas as pd
        latest = pd.to_datetime(max(dates)).date()
    except Exception:
        return None

    today = today or date.today()
    if latest > today:
        return None
    return latest
