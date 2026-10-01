"""
Workflow nào KHÔI PHỤC cache OHLCV thì phải LƯU lại nó.

01/10/2026: `weekly-valuation` chỉ có `actions/cache/restore`, không có `save`,
kể từ khi workflow ra đời (cd012b9, 13/08/2026). Mọi thứ lượt tuần ghi vào
`backend/data/cache` đều bị bỏ khi job kết thúc:

  - `vnindex_cache.parquet` — beta 2 năm tính từ đây. Không có nó thì beta rơi
    về giá trị dự phòng 1.0 cho MỌI mã, và beta là đầu vào của WACC trong DCF.
    Trên CI nó CHƯA BAO GIỜ được giữ lại.
  - OHLCV của rổ 200 mã — historical P/E / P-B cần >= 3 năm (xem
    test_cache_depth.py). Lượt tuần kéo về rồi vứt đi, lượt sau kéo lại từ đầu.

Quy tắc ở đây là CẶP restore-save, không phải "nhớ sửa weekly-valuation": lỗi
này sinh ra từ việc thêm một workflow mới mà quên vế thứ hai, nên cái phải canh
là mọi workflow, kể cả workflow chưa tồn tại.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
WF_DIR = ROOT / '.github' / 'workflows'
CACHE_PATH = 'backend/data/cache'
PREFIX = 'ohlcv-cache-v3-'
STEP = re.compile(r'^      - ', re.M)      # mức thụt của một bước trong cả ba workflow


class Step:
    """Một bước, đọc ở mức văn bản.

    Không dùng PyYAML: nó không có trong backend/requirements.txt, và thêm một
    phụ thuộc SẢN XUẤT chỉ để một test đọc được tệp cấu hình là cái giá sai.
    Các test workflow khác trong thư mục này cũng đọc bằng regex.
    """

    def __init__(self, text: str):
        self.text = text
        self.uses = self._field('uses') or ''
        self.path = self._field('path') or ''
        self.key = self._field('key') or ''
        self.cond = self._field('if') or ''

    def _field(self, name):
        m = re.search(rf'^\s*{name}:\s*(.+?)\s*$', self.text, re.M)
        return m.group(1) if m else None


def _cache_steps(wf: Path):
    """(restore, save) — các bước đụng tới đúng thư mục cache OHLCV."""
    text = wf.read_text(encoding='utf-8')
    blocks = STEP.split(text)[1:]
    restore, save = [], []
    for raw in blocks:
        st = Step(raw)
        if st.path != CACHE_PATH:
            continue
        if st.uses.startswith('actions/cache/restore@'):
            restore.append(st)
        elif st.uses.startswith('actions/cache/save@'):
            save.append(st)
        elif st.uses.startswith('actions/cache@'):
            # Dạng gộp: vừa khôi phục vừa lưu ở post-step.
            restore.append(st)
            save.append(st)
    return restore, save


WORKFLOWS = sorted(WF_DIR.glob('*.yml'))
RESTORERS = [wf for wf in WORKFLOWS if _cache_steps(wf)[0]]


def test_some_workflow_actually_restores_the_cache():
    """Chốt chặn cho chính bộ test: nếu không workflow nào khớp thì mọi test
    dưới đây xanh một cách rỗng."""
    assert RESTORERS, f'không workflow nào khôi phục {CACHE_PATH}'


@pytest.mark.parametrize('wf', RESTORERS, ids=lambda w: w.name)
def test_restoring_the_cache_implies_saving_it(wf):
    restore, save = _cache_steps(wf)
    assert save, (
        f'{wf.name} khôi phục {CACHE_PATH} nhưng không lưu lại — '
        'mọi thứ lượt chạy ghi vào đó sẽ bị bỏ')


@pytest.mark.parametrize('wf', RESTORERS, ids=lambda w: w.name)
def test_the_saved_key_is_reachable_by_the_other_workflows(wf):
    """Khoá lưu phải mang tiền tố chung, nếu không thì lưu xong cũng không ai
    đọc được: cả ba workflow tìm cache bằng restore-keys `ohlcv-cache-v3-`."""
    _, save = _cache_steps(wf)
    for st in save:
        assert st.key.startswith(PREFIX), (
            f'{wf.name}: khoá {st.key!r} không mang tiền tố {PREFIX!r}')


@pytest.mark.parametrize('wf', RESTORERS, ids=lambda w: w.name)
def test_the_key_is_unique_per_run(wf):
    """Khoá cố định thì GitHub bỏ qua lần lưu thứ hai trở đi (khoá đã tồn tại),
    tức là lưu một lần rồi đóng băng mãi mãi."""
    _, save = _cache_steps(wf)
    for st in save:
        assert 'github.run_id' in st.key, (
            f'{wf.name}: khoá {st.key!r} không đổi theo lượt chạy')


@pytest.mark.parametrize('wf', RESTORERS, ids=lambda w: w.name)
def test_the_save_survives_a_run_that_was_cut_short(wf):
    """Lượt chạm trần bị chặt vẫn đã kéo về được một phần. Bỏ phần đó là bắt
    lượt sau làm lại từ đầu, đúng cái đã làm hỏng lượt này."""
    _, save = _cache_steps(wf)
    for st in save:
        if st.uses.startswith('actions/cache@'):
            continue    # dạng gộp tự lo phần này
        assert 'always()' in st.cond, (
            f'{wf.name}: bước lưu cache thiếu `if: always()`')
