"""
Đo độ sâu cache OHLCV — chạy trước và sau backfill để biết nó làm được gì.

Vì sao là script riêng chứ không phải vài dòng trong workflow: đo cùng một thứ
bằng cùng một đoạn mã ở cả hai mốc. Viết hai đoạn inline khác nhau thì chênh
lệch có thể đến từ cách đo.

Ngưỡng 3 năm không phải số tròn cho đẹp: `calculate_historical_multiples` lấy
giá ở cuối mỗi năm trong `lookback_years = 5`, và cần ít nhất 3 mốc để trung vị
có nghĩa. Dưới 3 năm thì phương pháp Historical Multiple trả fair = 0, bị loại
khỏi blend, và độ tin cậy của P/E lẫn P/B-ROE tụt theo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.data_fetcher import CACHE_DIR, VNINDEX_CACHE

NEEDED_YEARS = 3
NEEDED_DAYS = NEEDED_YEARS * 365


def main() -> int:
    files = sorted(CACHE_DIR.glob('*_adj.parquet'))
    print(f'CACHE_DIR = {CACHE_DIR}')
    print(f'VN-Index  = {"có" if VNINDEX_CACHE.exists() else "KHÔNG CÓ"}')
    if not files:
        print('Chưa có tệp cache nào.')
        return 0

    spans = []
    for f in files:
        try:
            d = pd.to_datetime(pd.read_parquet(f, columns=['Date'])['Date'])
        except Exception:
            continue
        spans.append(((d.max() - d.min()).days, len(d), f.stem[:-4]))
    if not spans:
        print('Không đọc được tệp nào.')
        return 0

    spans.sort()
    days = [s[0] for s in spans]
    deep = sum(1 for d in days if d >= NEEDED_DAYS)
    print(f'{len(spans)} mã | bề dài (ngày): nhỏ nhất {days[0]} '
          f'trung vị {days[len(days) // 2]} lớn nhất {days[-1]}')
    print(f'ĐỦ {NEEDED_YEARS} năm cho historical multiples: {deep}/{len(spans)} '
          f'= {deep / len(spans):.0%}')
    print(f'  (cần >= {NEEDED_DAYS} ngày; dưới mức này thì Historical Multiple '
          f'trả fair = 0 và bị loại khỏi blend)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
