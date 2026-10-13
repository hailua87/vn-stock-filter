"""
Cú pháp JS của `web/*.js` — không có gì canh, và tôi đã tự chứng minh (13/10/2026).

Khi sửa lớp `prio-*` của ô TUỔI, tôi thêm một chú thích giải thích vào **trong**
template literal của mẫu hàng. Chú thích có dấu backtick (`` `th-rating` ``) —
và backtick trong template literal thì **kết thúc chuỗi**. `web/app.js` thành
lỗi cú pháp, toàn bộ trang chết: bảng đứng ở "Đang tải..." mãi.

**Tôi không thấy, vì trình duyệt đang chạy `app.js` CŨ trong cache.** Mở lại,
bấm tab, đo lại — tất cả đều trên bản cũ. Phải đổi sang một cổng khác (tức
origin khác, cache khác) mới lộ ra. Đến lúc đó `read_console_messages` nói ngay:
`Uncaught SyntaxError: Unexpected identifier 'th'`.

Hai lỗ hổng, cùng một gốc là **không có thước đo**:

1. Không có gì kiểm cú pháp JS. 1312 phép kiểm Python xanh hết trong khi trang
   web chết hoàn toàn. `backend/tests/test_web_cot_bang.py` cũng xanh — nó khớp
   chuỗi, không phân tích JS.
2. Cache trình duyệt làm phép đo thủ công nói dối. Đây là biến thể của bẫy ghi
   ở `CLAUDE.md` mục 6: *kiểm chính thước đo trước khi tin kết luận*.

`node --check` là thước đo đúng cho (1) và nó mất 0,1 giây.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

KHO = Path(__file__).resolve().parent.parent.parent
WEB = KHO / 'web'
JS = sorted(WEB.glob('*.js'))


def test_co_tep_js_de_kiem():
    """Chốt chặn: glob rỗng thì mọi phép kiểm dưới xanh rỗng."""
    assert len(JS) >= 1, f'không tìm thấy web/*.js trong {WEB}'
    assert (WEB / 'app.js') in JS


@pytest.mark.parametrize('tep', JS, ids=lambda p: p.name)
def test_js_dung_cu_phap(tep: Path):
    """
    `node --check` — phân tích thật, không khớp chuỗi.

    KHÔNG `pytest.skip` khi thiếu node: test bị skip là test xanh rỗng
    (CLAUDE.md mục 6), và chỗ này là chỗ vừa để lọt một lỗi làm chết cả trang.
    CI đã ghim `actions/setup-node@v4`.
    """
    node = shutil.which('node')
    assert node, ('không tìm thấy `node` — phép kiểm này CỐ Ý đỏ thay vì bỏ '
                  'qua. Cài Node, hoặc sửa .github/workflows/ci.yml nếu CI '
                  'mất bước setup-node.')
    r = subprocess.run([node, '--check', str(tep)],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    assert r.returncode == 0, f'{tep.name} lỗi cú pháp:\n{r.stderr or r.stdout}'


def _than_renderRow() -> str:
    """
    Thân hàm `renderRow`, cắt bằng đếm ngoặc.

    Phải khoanh đúng hàm. `renderTodayTop` cũng dựng `<tr data-ticker=` nhưng
    nó dùng **template lồng** trong `${...}` — ví dụ
    `${v == null ? '—' : `${v.toFixed(2)}×`}` — và backtick ở đó hoàn toàn
    HỢP LỆ. Bản đầu của phép kiểm dưới đây quét cả tệp nên báo lỗi oan đúng
    chỗ đó. Ba mẫu trong `renderRow` không có nội suy lồng, nên ở đó backtick
    luôn là lỗi.
    """
    js = (WEB / 'app.js').read_text(encoding='utf-8')
    i = js.index('function renderRow(')
    j = js.index('{', i)
    bac, k = 1, j + 1
    while k < len(js) and bac:
        if js[k] == '{':
            bac += 1
        elif js[k] == '}':
            bac -= 1
        k += 1
    return js[j + 1:k - 1]


def _mau_renderRow():
    mau = re.findall(r'return `(<tr data-ticker=.*?</tr>)`', _than_renderRow(), re.S)
    assert len(mau) == 3, f'tim thay {len(mau)} mau hang trong renderRow, cho 3'
    return mau


def test_khoanh_dung_renderRow():
    """Chốt chặn: `renderTodayTop` không được lọt vào."""
    than = _than_renderRow()
    assert 'renderTodayTop' not in than
    assert 'td-num' not in than, 'lớp của .today-table không được lọt vào'


def test_mau_hang_khong_chua_backtick():
    """
    Chặn đúng cái bẫy đã sập, bằng thước đo KHÔNG cần node.

    Ba mẫu hàng của bảng tín hiệu không dùng nội suy lồng, nên mọi backtick
    trong đó đều ĐÓNG template literal và làm app.js lỗi cú pháp. Phép kiểm
    này hẹp và chắc, không cần phân tích JS. Nó bổ sung cho `node --check` chứ
    không thay — `node --check` bắt mọi lỗi cú pháp, còn phép kiểm này nói
    ĐÚNG nguyên nhân khi gặp lại đúng bẫy này.
    """
    for i, m in enumerate(_mau_renderRow(), 1):
        assert '`' not in m, (
            f'mẫu hàng #{i} của renderRow chứa dấu backtick — nó KẾT THÚC '
            f'template literal và làm app.js lỗi cú pháp. Chú thích giải thích '
            f'thì đặt NGOÀI template, dưới dạng `//`.')


def test_mau_hang_khong_chua_chu_thich_html():
    """
    Chú thích HTML trong mẫu hàng vừa đi ra DOM thật, vừa làm hỏng phép đếm ô
    của `test_web_cot_bang.py` nếu nó nhắc chữ `<td>`. Đặt chú thích ra ngoài.
    """
    for i, m in enumerate(_mau_renderRow(), 1):
        assert '<!--' not in m, f'mẫu hàng #{i} có chú thích HTML — đặt ra ngoài'
