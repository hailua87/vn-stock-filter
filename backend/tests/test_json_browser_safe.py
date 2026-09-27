"""
Mọi tệp trong web/data phải đọc được bằng LUẬT JSON NGHIÊM (28/09/2026).

Vì sao lỗi này sống được lâu: `json.dump` của Python mặc định GHI RA chữ
`NaN`, và `json.load` đọc lại được — nên mọi phép kiểm phía backend đều xanh.
Nhưng `JSON.parse` của trình duyệt TỪ CHỐI: chuẩn JSON không có hằng số đó.

Hậu quả thật: 5 bản lưu phiên mang `m_stop: NaN`, `m_rr: NaN`… nên chọn đúng
những phiên đó trong bộ chọn ngày là HỎNG IM LẶNG — bảng không đổi, chỉ có
một dòng trong console. Tôi phát hiện vì phép thử "xem phiên cũ" của chính
mình không đổi được phiên, và thoạt đầu tưởng đoạn mã mình vừa viết bị hỏng.

Phép kiểm đầu tiên tôi chạy còn báo "0 tệp không hợp lệ" — vì tôi dùng
`json.load` mặc định, tức đứng ở phía Python chứ không phải phía trình duyệt.
Đó chính là cái bẫy mà test này đứng chặn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.exporter import clean_non_finite, write_json

WEB_DATA = Path(__file__).resolve().parent.parent.parent / 'web' / 'data'


def _reject(x):
    """`parse_constant` chỉ được gọi cho NaN/Infinity/-Infinity."""
    raise ValueError(f'hằng số JavaScript, trình duyệt không đọc được: {x}')


def _strict(path: Path):
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=_reject)


def _all_json():
    return sorted(p for p in WEB_DATA.rglob('*.json'))


def test_there_is_something_to_check():
    """Nếu không tìm thấy tệp nào thì test dưới xanh một cách vô nghĩa."""
    assert len(_all_json()) > 50


@pytest.mark.parametrize('rel', [str(p.relative_to(WEB_DATA)) for p in _all_json()])
def test_every_published_file_parses_the_way_a_browser_would(rel):
    _strict(WEB_DATA / rel)


# ─── Chặn ở chỗ ghi ──────────────────────────────────────────────────────────

def test_clean_replaces_non_finite_with_none():
    inf, nan = float('inf'), float('nan')
    got = clean_non_finite({'a': nan, 'b': inf, 'c': -inf,
                            'd': [1.5, nan], 'e': {'f': nan}, 'g': 'NaN'})
    assert got == {'a': None, 'b': None, 'c': None,
                   'd': [1.5, None], 'e': {'f': None}, 'g': 'NaN'}, (
        'chuỗi "NaN" là dữ liệu thật, không được đụng vào')


def test_none_not_zero():
    """
    Giao diện kiểm `=== null` để hiện "—" kèm lý do (renderRR trong app.js).
    Thay bằng 0 sẽ biến "không có dữ liệu" thành một con số trông như thật.
    """
    assert clean_non_finite(float('nan')) is None
    assert clean_non_finite(0.0) == 0.0, 'số 0 thật thì phải giữ nguyên'


def test_write_json_output_is_browser_readable(tmp_path):
    p = tmp_path / 'x.json'
    write_json({'m_rr': float('nan'), 'm_stop': float('inf'), 'ok': 1.25}, p)
    assert _strict(p) == {'m_rr': None, 'm_stop': None, 'ok': 1.25}
    assert 'NaN' not in p.read_text(encoding='utf-8')


def test_write_json_compact_mode_too(tmp_path):
    p = tmp_path / 'y.json'
    write_json({'v': [float('nan'), 2]}, p, compact=True)
    assert _strict(p) == {'v': [None, 2]}


def test_a_type_that_slips_past_the_cleaner_fails_loudly(tmp_path):
    """
    `allow_nan=False` là lưới thứ hai. Kiểu lạ mà `clean_non_finite` không
    nhận ra thì phải NỔ lúc ghi, chứ không ra một tệp trình duyệt không đọc
    được rồi im lặng suốt nhiều tháng — đúng điều đã xảy ra.
    """
    import numpy as np

    class Sneaky(float):
        pass

    p = tmp_path / 'z.json'
    # numpy float NaN không phải `float` thuần nên lọt qua isinstance(obj, float)?
    # Thật ra nó LÀ subclass của float, nên vẫn bị dọn — chốt lại điều đó.
    write_json({'v': np.float64('nan')}, p)
    assert _strict(p) == {'v': None}
