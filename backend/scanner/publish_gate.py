"""
Có ghi đè tệp đầu ra hay không khi vòng lấy dữ liệu bị cắt giữa chừng.

Một quy tắc, một chỗ. `run_valuation` và `run_quality` đều hỏi hàm này; chép
sang hai nơi thì đến lúc sửa sẽ chỉ sửa một.

Quy tắc, và vì sao:

    Rổ xếp theo THANH KHOẢN GIẢM DẦN, nên dừng sớm không cắt ngẫu nhiên — nó
    cắt đúng phần đuôi. Phần còn lại thiên về mã vốn hoá lớn, và mọi con số
    tính theo NHÓM (peer median của định giá, percentile của chất lượng) đổi
    theo. Tức một tệp mỏng không phải "tệp đủ nhưng ít mã hơn": các mã còn lại
    cũng mang điểm khác với khi chạy trọn.

    Cả hai module đều dựa trên BCTC — ra theo quý. Một tệp cũ hơn một tuần gần
    như không mất gì, còn mã biến mất khỏi web thì người đọc thấy ngay. Nên khi
    chưa đủ phủ: giữ tệp lượt trước.

    Trừ khi chưa có tệp nào. Lúc đó tệp mỏng vẫn hơn không có gì.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple


def may_publish(coverage: float, min_coverage: float, existing: Path) -> Tuple[bool, str]:
    """
    (có được ghi không, câu giải thích).

    Câu giải thích rỗng khi mọi thứ bình thường — chỉ có chữ khi cần ghi log.
    """
    if coverage >= min_coverage:
        return True, ''
    if Path(existing).exists():
        return False, (f'độ phủ {coverage:.0%} < {min_coverage:.0%} — giữ nguyên '
                       f'{existing} của lượt trước, xem scanner/publish_gate.py')
    return True, (f'độ phủ {coverage:.0%} < {min_coverage:.0%} nhưng chưa có '
                  f'{Path(existing).name} — vẫn ghi để web có dữ liệu đầu tiên')
