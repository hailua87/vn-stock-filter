"""
Bảng tín hiệu: 18 cột, và mỗi `<td>` mang ĐÚNG lớp `prio-*` của `<th>` tương
ứng (13/10/2026).

`CLAUDE.md` mục 9 ghi luật này, và `app.js:1413` có chú thích nhắc lại nó. Cả
hai đều là **lời dặn** — không có gì chặn người sửa một mẫu hàng mà quên mẫu
còn lại.

Vì sao luật này quan trọng mà lại dễ vỡ âm thầm: cột được ẩn theo bề rộng bằng
`.signal-table .prio-N { display: none }` — `prio-4` ẩn ở ≤1100px, `prio-3` ở
≤860px, `prio-2` ở ≤600px. Quy tắc đó áp cho **cả `<th>` lẫn `<td>`**. Nếu hai
bên lệch lớp thì ở đúng dải đó header còn cột mà thân bảng mất ô (hoặc ngược
lại) — **lệch cột**. Ở màn rộng thì không thấy gì cả, nên lỗi sống rất lâu.

Phép kiểm này tìm thấy một lỗi thật ngay lần chạy đầu: mẫu hàng MA7×25 cho ô
TUỔI lớp `prio-3`, còn `<th>` của nó (`th-rating`, được đổi chữ thành "TUỔI"
lúc chạy) **không có** `prio-*`. Ở ≤860px ô biến mất, cột tiêu đề vẫn còn.

## Ba mẫu hàng

| mẫu | số `<td>` | cột cuối |
|---|---|---|
| Tổng hợp (`combined`) | 18 | PASS / HẠNG, ô TIÊU CHÍ ẩn bằng inline style |
| MA7×25 (`signalBased`) | 17 | TÍN HIỆU / TUỔI, **bỏ hẳn** ô TIÊU CHÍ |
| Mặc định (chấm điểm) | 18 | ĐIỂM / HẠNG |

MA7×25 bỏ hẳn ô thứ 16 nên `<td>` 16-17 của nó ứng với `<th>` 17-18.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KHO = Path(__file__).resolve().parent.parent.parent
HTML = (KHO / 'web' / 'index.html').read_text(encoding='utf-8')
JS = (KHO / 'web' / 'app.js').read_text(encoding='utf-8')

SO_COT = 18


def _prio(attrs: str):
    m = re.search(r'\bprio-([1-4])\b', attrs)
    return f'prio-{m.group(1)}' if m else None


def _thead():
    """[(prio, nhãn)] theo đúng thứ tự cột của bảng tín hiệu."""
    m = re.search(r'<table[^>]*class="[^"]*signal-table[^"]*"[^>]*>.*?<thead>(.*?)</thead>',
                  HTML, re.S)
    assert m, 'không tìm thấy <thead> của .signal-table'
    ra = []
    for tag, than in re.findall(r'<th\b([^>]*)>(.*?)</th>', m.group(1), re.S):
        nhan = re.sub(r'<[^>]+>', '', than)
        ra.append((_prio(tag), ' '.join(nhan.split())))
    return ra


def _than_ham(ten_ham: str) -> str:
    """
    Thân của một hàm trong app.js, cắt bằng ĐẾM NGOẶC.

    Phải khoanh đúng hàm: `renderTodayTop` cũng có mẫu `<tr data-ticker=`
    nhưng đó là bảng KHÁC (`.today-table`, lớp `td-num`, không dùng `prio-*`).
    Lần chạy đầu của phép kiểm này bắt được 4 mẫu thay vì 3 đúng vì lý do đó.
    """
    i = JS.index(f'function {ten_ham}(')
    j = JS.index('{', i)
    bac, k = 1, j + 1
    while k < len(JS) and bac:
        if JS[k] == '{':
            bac += 1
        elif JS[k] == '}':
            bac -= 1
        k += 1
    return JS[j + 1:k - 1]


def _mau_hang():
    """{tên: [prio,...]} cho ba mẫu hàng của BẢNG TÍN HIỆU, theo thứ tự."""
    than = _than_ham('renderRow')
    mau = re.findall(r'return `(<tr data-ticker=.*?</tr>)`', than, re.S)
    assert len(mau) == 3, (
        f'tìm thấy {len(mau)} mẫu hàng trong renderRow, chờ 3. Thêm mẫu mới '
        f'thì phải thêm cả phép kiểm cho nó — đó là lý do con số này bị chốt.')
    ten = ['combined', 'ma7_25', 'mac_dinh']
    return {t: _dem_td(m) for t, m in zip(ten, mau)}


def _dem_td(mau: str):
    """
    [prio,...] cho từng `<td>` của một mẫu hàng.

    PHẢI bỏ chú thích `<!-- -->` trước khi đếm. Một chú thích GIẢI THÍCH luật
    này thường phải viết ra chữ `<td>` — và lúc đó nó bị đếm như một ô thật.
    Đã xảy ra ngay ở bản sửa giới thiệu phép kiểm này: chú thích ghi "6 <td>
    hien" làm mẫu MA7×25 đếm ra 18 ô thay vì 17. Cùng loại bẫy với
    `bo_heredoc()` trong `scripts/claude_guard.py`: phần diễn giải không phải
    phần nội dung.
    """
    sach = re.sub(r'<!--.*?-->', '', mau, flags=re.S)
    return [_prio(a) for a in re.findall(r'<td\b([^>]*)>', sach)]


# ── Chốt chặn cho chính bộ đo ──────────────────────────────────────────────

def test_chu_thich_html_khong_bi_dem_la_o():
    """
    Chốt chặn cho `_dem_td`. Thiếu bước bỏ chú thích thì một chú thích nhắc
    chữ `<td>` sẽ bị đếm thành ô thật — và phép kiểm số cột báo lỗi oan. Đã
    xảy ra thật ở bản sửa giới thiệu phép kiểm này.
    """
    assert _dem_td('<td class="prio-2">a</td>') == ['prio-2']
    assert _dem_td('<td>a</td><!-- xem <td class="prio-3"> o tren -->') == [None]
    assert _dem_td('<!--\n  nhieu dong <td class="prio-1">\n--><td class="num">x</td>') == [None]


def test_khoanh_dung_ham_khong_keo_bang_khac_vao():
    """
    Chốt chặn cho `_than_ham`: `renderTodayTop` phải KHÔNG nằm trong thân
    `renderRow`. Nếu phép đếm ngoặc hỏng, nó sẽ kéo cả tệp vào và `_mau_hang`
    thấy 4 mẫu — tức phép kiểm nổ, chứ không xanh rỗng. Nhưng chốt rõ ở đây để
    thông báo lỗi nói đúng nguyên nhân.
    """
    than = _than_ham('renderRow')
    assert 'renderTodayTop' not in than
    assert 'td-num' not in than, 'lớp của .today-table không được lọt vào'


def test_bo_do_doc_duoc_ca_hai_phia():
    """
    Trình tách hỏng thì trả danh sách rỗng và mọi phép so dưới đây xanh rỗng.
    """
    th = _thead()
    assert len(th) == SO_COT, f'đọc được {len(th)} <th>'
    assert [t[1] for t in th[:4]] == ['#', 'MÃ', 'SÀN', 'GIÁ nghìn đ'], \
        f'nhãn cột đầu không như mong đợi: {[t[1] for t in th[:4]]}'
    mau = _mau_hang()
    assert sorted(len(v) for v in mau.values()) == [17, 18, 18], \
        {k: len(v) for k, v in mau.items()}


# ── Luật chính ──────────────────────────────────────────────────────────────

def test_bang_tin_hieu_co_dung_18_cot():
    assert len(_thead()) == SO_COT


@pytest.mark.parametrize('ten', ['combined', 'mac_dinh'])
def test_mau_cham_diem_co_18_o_va_khop_prio_theo_vi_tri(ten):
    th = [p for p, _ in _thead()]
    td = _mau_hang()[ten]
    assert len(td) == SO_COT, f'mẫu {ten} có {len(td)} ô, chờ {SO_COT}'
    lech = [(i + 1, th[i], td[i]) for i in range(SO_COT) if th[i] != td[i]]
    assert not lech, (
        f'mẫu hàng {ten} lệch lớp prio-* so với <th>:\n' +
        '\n'.join(f'  cột {i}: th={a or "—"}  td={b or "—"}' for i, a, b in lech) +
        '\n\nỞ dải bề rộng ẩn lớp đó, header và thân bảng sẽ LỆCH CỘT.')


def test_mau_ma7_25_bo_o_tieu_chi_va_khop_prio_voi_th_tuong_ung():
    """
    MA7×25 bỏ hẳn ô TIÊU CHÍ (cột 16) nên `<td>` 16-17 ứng với `<th>` 17-18.
    `<th>` 17 và 18 được đổi CHỮ lúc chạy ("TÍN HIỆU", "TUỔI") nhưng **không**
    đổi lớp — nên `<td>` phải khớp lớp của chúng như trong index.html.
    """
    th = [p for p, _ in _thead()]
    td = _mau_hang()['ma7_25']
    assert len(td) == SO_COT - 1, f'mẫu MA7×25 có {len(td)} ô, chờ {SO_COT - 1}'

    # 15 cột đầu khớp thẳng; hai cột cuối ứng với <th> 17 và 18.
    anh_xa = list(range(15)) + [16, 17]
    lech = [(i + 1, th[j], td[i]) for i, j in enumerate(anh_xa) if th[j] != td[i]]
    assert not lech, (
        'mẫu hàng MA7×25 lệch lớp prio-* so với <th> tương ứng:\n' +
        '\n'.join(f'  td {i} ↔ th: th={a or "—"}  td={b or "—"}' for i, a, b in lech) +
        '\n\n`prio-3` bị ẩn ở ≤860px. Nếu <td> có mà <th> không thì ở dải đó '
        'cột tiêu đề còn mà ô biến mất — LỆCH CỘT.')


def test_15_cot_dau_giong_nhau_o_ca_ba_mau():
    """
    Mười lăm cột đầu là phần dùng chung. Lệch giữa hai mẫu nghĩa là sửa một mẫu
    mà quên mẫu kia — đúng kiểu lỗi mà chú thích ở `app.js:1413` dặn tránh.
    """
    mau = _mau_hang()
    goc = mau['mac_dinh'][:15]
    for ten, td in mau.items():
        assert td[:15] == goc, (
            f'mẫu {ten} lệch ở 15 cột đầu:\n'
            f'  mac_dinh: {goc}\n  {ten:9s}: {td[:15]}')


def test_colspan_cua_hang_dang_tai_khop_so_cot():
    """
    `<td colspan>` của hàng "Đang tải..." phải phủ hết bảng. Thiếu thì hàng đó
    không trải hết và bảng nhảy bề rộng lúc nạp xong.
    """
    m = re.search(r'<tbody id="signal-rows">\s*<tr><td colspan="(\d+)"', HTML)
    assert m, 'không tìm thấy hàng "Đang tải..." của #signal-rows'
    assert int(m.group(1)) == SO_COT, (
        f'colspan={m.group(1)} nhưng bảng có {SO_COT} cột')
