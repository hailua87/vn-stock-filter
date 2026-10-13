"""
Luật 5 màu trạng thái giá — canh bằng máy, không bằng lời dặn (13/10/2026).

Luật ghi ở đầu `web/tokens.css` và `CLAUDE.md` mục 9: **5 màu trạng thái giá
chỉ dùng cho giá và biến động giá.** Không dùng cho badge, tab, chấm, icon,
trang trí. Phi-giá thì dùng `--system`, `--focus`, `--cat-*`, `--danger`, hoặc
thang độ sáng.

PR #76 và #78 sửa khoảng 40 chỗ **bằng tay**. Không có gì chặn chỗ thứ 41 — và
đúng như vậy: ngày 13/10 còn tìm thấy `.rec-position-pct` ("VỊ THẾ ĐỀ XUẤT",
cỡ vị thế tính theo %NAV) dùng xanh tăng giá `var(--up)` vô điều kiện. Đó không
phải giá, cũng không phải biến động giá. Nó sống sót vì luật chỉ tồn tại dưới
dạng chú thích.

## Vì sao kiểm trên TÊN TOKEN, không phải trên giá trị màu

`--danger: #ef5350` **trùng giá trị** với `--down: #ef5350`. Đó là cố ý, và
styles.css ghi rõ lý do: lỗi không phải một trạng thái giá, dùng chung token
nghĩa là đổi màu giảm giá sẽ âm thầm đổi cả màu lỗi. Một phép kiểm so theo giá
trị màu sẽ báo `--danger` là vi phạm — sai, và sai kiểu khiến người ta tắt phép
kiểm đi.

## Vì sao là sổ đăng ký, không phải danh sách mẫu

Không có cách máy móc nào biết `.rec-position-pct` là phi-giá mà
`.cd-body.up` là giá — tên lớp không nói ra điều đó. Nên mỗi chỗ dùng phải
được **ghi vào sổ kèm lý do**. Thêm chỗ mới thì test đỏ cho tới khi có người
viết ra lý do. Cùng triết lý với `tools/viewport-check/accepted.json`: bắt
người ta quyết định có ý thức, chứ không chặn cứng.

Sổ cũng bị canh ngược: mục trỏ tới selector không còn tồn tại thì cũng đỏ —
nếu không sổ sẽ mục rữa dần thành con dấu cao su.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KHO = Path(__file__).resolve().parent.parent.parent
CSS = KHO / 'web' / 'styles.css'
TOKENS = KHO / 'web' / 'tokens.css'

# 5 màu trạng thái giá của bản tối, cộng hai biến mềm chưa dùng.
TOKEN_GIA = (
    '--up', '--down', '--up-soft', '--down-soft',
    '--limit-up', '--limit-down', '--limit-ref',
)

# Sổ đăng ký: selector → vì sao chỗ này ĐÚNG là giá hoặc biến động giá.
SO_DANG_KY = {
    '.signal-table tbody td.up': 'ô ±1D/±5D trong bảng giá',
    '.signal-table tbody td.down': 'ô ±1D/±5D trong bảng giá',
    '.today-table td.up': 'ô biến động giá ở tab Hôm nay',
    '.today-table td.down': 'ô biến động giá ở tab Hôm nay',

    '.limit-up': 'giá trần — tím, một trong 5 trạng thái giá',
    '.limit-down': 'giá sàn — xanh lơ',
    '.limit-ref': 'giá tham chiếu — vàng',

    '.fib-support .fib-price': 'mức GIÁ hỗ trợ Fibo',
    '.fib-resistance .fib-price': 'mức GIÁ kháng cự Fibo',
    '.fibo-support .fibo-price': 'mức GIÁ hỗ trợ Fibo (màn phân tích)',
    '.fibo-resistance .fibo-price': 'mức GIÁ kháng cự Fibo (màn phân tích)',
    # Đảo màu CÓ CHỦ Ý: khoảng cách tới kháng cự ở trên là bất lợi.
    '.analyzer-fibo .fibo-dist.up': 'khoảng cách tới kháng cự — đảo màu có chủ ý',
    '.analyzer-fibo .fibo-dist.down': 'khoảng cách tới hỗ trợ — đảo màu có chủ ý',

    '.entry-level-buy': 'viền trái đánh dấu mức GIÁ vào',
    '.entry-level-buy .entry-level-price': 'mức GIÁ vào',
    '.entry-level-stop': 'viền trái đánh dấu mức GIÁ cắt lỗ',
    '.entry-level-stop .entry-level-price': 'mức GIÁ cắt lỗ',
    '.rec-level-entry': 'viền trái đánh dấu mức GIÁ vào (khối khuyến nghị)',
    '.rec-level-stop': 'viền trái đánh dấu mức GIÁ cắt lỗ (khối khuyến nghị)',

    '.metric-val.up': 'trị số biến động giá',
    '.metric-val.down': 'trị số biến động giá',
    '.ich-val.up': 'giá so với mây Ichimoku',
    '.ich-val.down': 'giá so với mây Ichimoku',

    '.cd-body.up': 'thân nến — giá',
    '.cd-body.down': 'thân nến — giá',
    '.cd-wick.up': 'bóng nến — giá',
    '.cd-wick.down': 'bóng nến — giá',
}


def _bo_chu_thich(s: str) -> str:
    """Xoá /* */ nhưng GIỮ số dòng, để thông báo lỗi còn trỏ đúng chỗ."""
    return re.sub(r'/\*.*?\*/',
                  lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)


def _tach_khoi(text: str):
    """
    Tách CSS thành các khối (selector, thân, số dòng).

    Đếm ngoặc thật chứ không `split('}')`: `@media { .a { } }` mà split thì
    selector của `.a` dính luôn chuỗi `@media`, và mọi phép khớp sau đó lệch.
    `@media`/`@supports` thì đệ quy vào trong — luật màu áp cho cả khối đáp ứng.
    """
    ra = []
    i, n = 0, len(text)
    while i < n:
        j = text.find('{', i)
        if j < 0:
            break
        sel = ' '.join(text[i:j].split())
        sau, bac = j + 1, 1
        while sau < n and bac:
            if text[sau] == '{':
                bac += 1
            elif text[sau] == '}':
                bac -= 1
            sau += 1
        than = text[j + 1:sau - 1]
        dong = text.count('\n', 0, j) + 1
        if sel.startswith('@'):
            ra.extend(_tach_khoi(than))
        else:
            ra.append((sel, than, dong))
        i = sau
    return ra


def _cho_dung_token_gia():
    """[(selector, dòng, [token])] cho mọi khối dùng token màu giá."""
    s = _bo_chu_thich(CSS.read_text(encoding='utf-8'))
    ra = []
    for sel, than, dong in _tach_khoi(s):
        if sel.startswith(':root'):
            continue                    # nơi ĐỊNH NGHĨA token, không phải nơi dùng
        dung = [t for t in TOKEN_GIA
                if re.search(rf'var\(\s*{re.escape(t)}\s*[,)]', than)]
        if dung:
            ra.append((sel, dong, dung))
    return ra


# ── Chốt chặn cho chính bộ đo ──────────────────────────────────────────────

def test_bo_do_thuc_su_tim_thay_cho_dung():
    """
    Nếu trình tách khối hỏng thì nó trả danh sách rỗng và MỌI phép kiểm dưới
    đây xanh một cách rỗng. Chốt số lượng tối thiểu.
    """
    cho = _cho_dung_token_gia()
    assert len(cho) >= 25, (
        f'chỉ tìm thấy {len(cho)} chỗ dùng token màu giá — trình tách khối CSS '
        f'có thể đã hỏng; đo 13/10/2026 là 28')


def test_tach_khoi_khong_dinh_at_media():
    """Chốt chặn cho `_tach_khoi`: selector trong @media không được dính @media."""
    khoi = _tach_khoi('@media (max-width: 9px) { .a { color: red } } .b { top: 0 }')
    assert [k[0] for k in khoi] == ['.a', '.b']


# ── Luật chính ──────────────────────────────────────────────────────────────

def test_moi_cho_dung_mau_gia_phai_co_trong_so_dang_ky():
    """
    Luật: 5 màu trạng thái giá CHỈ cho giá và biến động giá.

    Chỗ mới chưa ghi sổ thì đỏ. Không phải để cấm — để bắt người thêm nó phải
    viết ra vì sao đó là giá. `.rec-position-pct` ("VỊ THẾ ĐỀ XUẤT", %NAV) là
    ví dụ thật đã lọt qua lượt quét ~40 chỗ của #78 vì không có bước này.
    """
    la = [(sel, dong, tk) for sel, dong, tk in _cho_dung_token_gia()
          if sel not in SO_DANG_KY]
    assert not la, (
        'Chỗ dùng màu trạng thái giá KHÔNG có trong sổ đăng ký:\n' +
        '\n'.join(f'  styles.css:{d}  {s}  → {",".join(t)}' for s, d, t in la) +
        '\n\nNếu đây THẬT là giá/biến động giá: thêm vào SO_DANG_KY kèm lý do.'
        '\nNếu không: dùng --system, --focus, --cat-*, --danger, hoặc thang '
        '--text → --text-dim → --text-mute.')


def test_so_dang_ky_khong_co_muc_chet():
    """
    Mục trỏ tới selector không còn tồn tại thì sổ mục rữa dần thành con dấu
    cao su — và lần sau không ai tin nó nữa.
    """
    con = {sel for sel, _, _ in _cho_dung_token_gia()}
    chet = sorted(set(SO_DANG_KY) - con)
    assert not chet, (
        'Mục trong sổ không còn chỗ dùng tương ứng trong styles.css '
        f'(đã xoá hoặc đổi selector?): {chet}')


def test_khong_ghi_thang_ma_mau_gia_de_lach_token():
    """
    Lách bằng cách ghi thẳng `#26a69a` thì sổ đăng ký vô dụng. Mã màu của 5
    trạng thái giá chỉ được xuất hiện ở nơi ĐỊNH NGHĨA token.
    """
    import collections
    s = _bo_chu_thich(CSS.read_text(encoding='utf-8'))
    dinh_nghia = dict(re.findall(r'(--(?:up|down|limit-up|limit-down|limit-ref))'
                                 r':\s*(#[0-9a-fA-F]{3,8})', s))
    assert len(dinh_nghia) == 5, f'không tìm đủ 5 định nghĩa: {dinh_nghia}'

    vi_pham = collections.defaultdict(list)
    for sel, than, dong in _tach_khoi(s):
        if sel.startswith(':root'):
            continue
        for ten, ma in dinh_nghia.items():
            if re.search(re.escape(ma), than, re.I):
                vi_pham[ten].append(f'styles.css:{dong} {sel}')
    assert not vi_pham, (
        'Ghi thẳng mã màu giá thay vì dùng token:\n' +
        '\n'.join(f'  {ma} ({ten}): {", ".join(v)}'
                  for ten, v in vi_pham.items()
                  for ma in [dinh_nghia[ten]]))


def test_danger_la_token_rieng_du_trung_gia_tri_voi_down():
    """
    `--danger` trùng giá trị `--down` là CỐ Ý (lỗi hiện ở panel riêng, không
    lẫn với chiều giảm trong bảng giá). Gộp hai token lại thì đổi màu giảm giá
    sẽ âm thầm đổi cả màu lỗi. Phép kiểm này chốt rằng chúng vẫn là HAI token —
    và nhân đó giải thích vì sao các phép kiểm trên làm trên tên, không trên giá trị.
    """
    s = CSS.read_text(encoding='utf-8')
    assert re.search(r'--danger:\s*#', s), '--danger phải được định nghĩa riêng'
    assert re.search(r'--down:\s*#', s), '--down phải được định nghĩa riêng'


def test_tokens_css_khong_dat_selector_nao_ngoai_root():
    """
    `web/tokens.css` tự ghi ở đầu tệp: "Không đặt selector nào ngoài :root".
    Nó nạp TRƯỚC styles.css nên mọi selector ở đây đều bị ghi đè âm thầm —
    thêm vào là tự tạo mã chết trông như đang có tác dụng.
    """
    s = _bo_chu_thich(TOKENS.read_text(encoding='utf-8'))
    la = [sel for sel, _, _ in _tach_khoi(s) if not sel.startswith(':root')]
    assert not la, f'selector ngoài :root trong tokens.css: {la}'
