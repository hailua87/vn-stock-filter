"""
Cập nhật phần hằng tuần của `web/data/health.json`.

Vì sao là một script RIÊNG chứ không nằm trong `run_quality`:

Ngày 23/09/2026 tôi đặt lời gọi `health.refresh_weekly()` ở cuối `run_quality`,
với lý do "một người ghi duy nhất cho mỗi phần". Lý do đó đúng, nhưng chỗ đặt
thì sai — và nó lộ ra ngày 27/09:

  Run valuation        68 phút  → xong, valuation/latest.json đã ghi
  Run quality scoring  45 phút  → CHẠM TRẦN, bị chặt giữa chừng
  → health.json không được cập nhật, nên màn Hôm nay báo định giá là
    "24/09, 61 mã" trong khi tệp thật đã là "27/09, 67 mã".

Định giá và chấm chất lượng là HAI BƯỚC RIÊNG. Bước sau chết không có nghĩa
bước trước không chạy — mà khi đó phần của bước trước lại không có ai cập nhật.

Nay script này chạy thành một bước riêng với `if: always()`, sau cả hai. Nó chỉ
ĐỌC những tệp đã thật sự được ghi, nên kết quả phản ánh đúng thứ đang có, bất kể
bước nào chết.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import health as HEALTH

log = logging.getLogger('refresh_health')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Cập nhật phần hằng tuần của health.json')
    ap.add_argument('--web-data-dir', default='web/data')
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S')

    web = Path(args.web_data_dir)
    out = HEALTH.refresh_weekly(web / 'health.json', web)
    if out is None:
        # Chưa có tệp thì KHÔNG tạo mới: một health.json thiếu hẳn phần lượt quét
        # còn khó đọc hơn là không có. Lượt quét hằng ngày sẽ tạo nó.
        log.info('Chưa có health.json — bỏ qua (lượt quét hằng ngày sẽ tạo)')
        return 0
    for key in ('valuation', 'quality'):
        s = out['sources'].get(key) or {}
        log.info(f"  {s.get('label', key)}: {s.get('as_of')} | {s.get('count')} mã")
    return 0


if __name__ == '__main__':
    sys.exit(main())
