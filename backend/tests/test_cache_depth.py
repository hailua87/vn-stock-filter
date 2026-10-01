"""
Ngưỡng độ sâu cache OHLCV (01/10/2026).

Vì sao con số 3 năm quan trọng: 21/69 mã định giá bị báo "các phương pháp mâu
thuẫn" và không có mức định giá. Cả 21 mã đều thiếu historical multiples, và độ
tin cậy của chúng là trung vị 32% — dưới ngưỡng 50%. Nhóm 48 mã còn lại có trung
vị 57%, và 44/48 đạt ngưỡng.

`calculate_historical_multiples` lấy giá ở cuối mỗi năm và cần >= 3 mốc. Dưới 3
năm thì nó trả fair = 0, bị loại khỏi blend, và độ tin cậy của P/E lẫn P/B-ROE
tụt theo.

Cache trên CI có trung vị 548 ngày = 1,5 năm, vì `fetch_with_cache` lần đầu chỉ
lấy `--lookback 400` ngày rồi CHỈ nới về phía trước.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import measure_cache_depth as M

ROOT = Path(__file__).resolve().parent.parent.parent
WF = ROOT / '.github' / 'workflows' / 'backfill-ohlcv.yml'


def test_the_threshold_matches_what_the_method_needs():
    """
    3 năm không phải số tròn cho đẹp — đó là số mốc cuối năm tối thiểu để trung
    vị historical multiple có nghĩa.
    """
    assert M.NEEDED_YEARS == 3
    assert M.NEEDED_DAYS == 3 * 365


def test_the_backfill_asks_for_more_than_the_threshold():
    """
    Backfill đúng 3 năm thì vừa đủ hôm nay và thiếu ngay tháng sau, vì mốc cuối
    năm cũ trượt ra khỏi cửa sổ. Phải xin dư.
    """
    years = int(re.search(r"years:\s*\n\s*description:[^\n]*\n\s*required:[^\n]*\n\s*default:\s*'(\d+)'",
                          WF.read_text(encoding='utf-8')).group(1))
    assert years >= M.NEEDED_YEARS + 1, f'backfill {years} năm, cần dư trên {M.NEEDED_YEARS}'


def test_the_backfill_covers_the_valuation_universe():
    """Rổ định giá là 200 mã; backfill ít hơn thì vẫn còn mã thiếu lịch sử."""
    limit = int(re.search(r"limit:\s*\n\s*description:[^\n]*\n\s*required:[^\n]*\n\s*default:\s*'(\d+)'",
                          WF.read_text(encoding='utf-8')).group(1))
    assert limit >= 200


def test_the_workflow_saves_the_cache_where_the_others_read_it():
    """
    Backfill mà không lưu, hoặc lưu sai tiền tố, thì cache sâu biến mất khi job
    kết thúc và cả lượt chạy thành vô ích.

    `daily-scan` và `weekly-valuation` khôi phục bằng `restore-keys:
    ohlcv-cache-v3-`, nên khoá lưu phải mang đúng tiền tố đó.
    """
    text = WF.read_text(encoding='utf-8')
    assert 'actions/cache/save' in text, 'workflow không lưu cache'
    keys = re.findall(r'key:\s*(\S+)', text)
    save_keys = [k for k in keys if 'backfill' in k]
    assert save_keys, 'không tìm thấy khoá lưu'
    for k in save_keys:
        assert k.startswith('ohlcv-cache-v3-'), (
            f'{k} sai tiền tố — daily-scan sẽ không nhận được cache này')


def test_it_runs_only_by_hand():
    """
    ~1.000 lượt gọi nguồn trong một lượt chạy. Đặt lịch cho việc này là gọi dồn
    dập vào máy chủ của người khác mỗi tuần để lấy dữ liệu không đổi.
    """
    text = WF.read_text(encoding='utf-8')
    assert 'workflow_dispatch' in text
    assert not re.search(r'^\s*schedule:', text, re.M), 'không được đặt lịch'


def test_it_measures_before_and_after():
    """
    Đo một đầu thì không biết backfill làm được gì. Và phải đo bằng CÙNG một
    đoạn mã ở cả hai mốc — hai đoạn inline khác nhau thì chênh lệch có thể đến
    từ cách đo.
    """
    text = WF.read_text(encoding='utf-8')
    assert text.count('measure_cache_depth.py') == 2
