"""
VN-Index cache phải nằm TRONG đường dẫn mà workflow cache (27/09/2026).

Lỗi: `VNINDEX_CACHE` trỏ tới `backend/data/vnindex_cache.parquet`, trong khi
hai workflow chỉ cache `backend/data/cache`. Nên tệp không bao giờ sống sót
qua các lượt chạy. Bài đo trên runner in ra đúng một dòng:

    VN-Index cache: KHÔNG CÓ -> sẽ phải gọi mạng

Vì sao đáng sửa dù chỉ tốn một lượt gọi mỗi lượt chạy: nếu lượt gọi đó hỏng
thì `_load_vnindex` trả None, `calculate_beta` rơi về 1,0 cho CẢ RỔ, và mọi
định giá dùng sai beta mà không có gì báo. Một lượt gọi, nhưng là lượt gọi
mà cả rổ phụ thuộc vào.

Test đọc thẳng YAML chứ không chép lại đường dẫn: chép lại thì hai bên lệch
nhau đúng kiểu đã gây ra lỗi này.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.data_fetcher import CACHE_DIR, CHECKPOINT_PATH, VNINDEX_CACHE

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = ROOT / '.github' / 'workflows'


def _cached_paths(name: str) -> list:
    """Các `path:` của những bước actions/cache trong một workflow."""
    text = (WORKFLOWS / name).read_text(encoding='utf-8')
    return [m for m in re.findall(r'uses:\s*actions/cache(?:/restore)?@v\d[\s\S]{0,200}?'
                                  r'path:\s*(\S+)', text)]


@pytest.mark.parametrize('workflow', ['daily-scan.yml', 'weekly-valuation.yml'])
def test_vnindex_cache_is_inside_a_cached_path(workflow):
    paths = _cached_paths(workflow)
    assert paths, f'{workflow}: không tìm thấy bước actions/cache nào'

    rel = VNINDEX_CACHE.resolve().relative_to(ROOT.resolve()).as_posix()
    assert any(rel.startswith(p.rstrip('/') + '/') for p in paths), (
        f'{rel} nằm NGOÀI mọi đường dẫn mà {workflow} cache ({paths}) — '
        f'tệp sẽ không sống sót qua các lượt chạy và beta sẽ rơi về 1,0')


def test_it_sits_with_the_other_things_that_ride_the_ohlcv_cache():
    """Cùng lý do với CHECKPOINT_PATH, vốn đã làm đúng từ trước."""
    assert VNINDEX_CACHE.parent == CACHE_DIR
    assert CHECKPOINT_PATH.parent == CACHE_DIR


def test_every_module_uses_the_same_path():
    """
    Hằng số này từng được định nghĩa LẠI ở bốn tệp. Bốn bản giống nhau cho tới
    khi một bản đổi — và đó chính là cách lỗi này tồn tại được.

    Chạy trong TIẾN TRÌNH RIÊNG, không đọc thuộc tính của module đã nạp:
    `backend/test_market_metrics.py` gán đè `mm.VNINDEX_CACHE` ngay lúc import
    và giữ nguyên cho cả phiên, nên bản đầu của test này xanh khi chạy riêng và
    đỏ khi chạy cả bộ. Một test đổi kết quả theo thứ tự chạy thì không chốt
    được gì.
    """
    import subprocess

    code = (
        'import sys; sys.path.insert(0, %r)\n'
        'from scanner.data_fetcher import VNINDEX_CACHE as want\n'
        'import backfill_history, rebuild_web_data, run_backtest\n'
        'from scanner import market_metrics\n'
        'bad = [m.__name__ for m in (market_metrics, backfill_history,\n'
        '                            rebuild_web_data, run_backtest)\n'
        '       if m.VNINDEX_CACHE != want]\n'
        'print("|".join(bad))\n'
    ) % str(Path(__file__).resolve().parent.parent)

    r = subprocess.run([sys.executable, '-c', code], capture_output=True,
                       text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    bad = r.stdout.strip()
    assert not bad, (f'{bad} có đường dẫn riêng — phải import từ '
                     f'scanner.data_fetcher')


def test_the_new_location_is_not_committed_by_accident():
    """
    `backend/data/cache/*.parquet` đã nằm trong .gitignore, nhưng chốt lại:
    chuyển một tệp cache vào thư mục được cache mà quên bỏ qua nó thì lượt
    chạy của bot sẽ commit vài MB parquet mỗi lần.
    """
    ignored = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'backend/data/cache/*.parquet' in ignored
