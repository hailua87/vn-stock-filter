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
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)


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
