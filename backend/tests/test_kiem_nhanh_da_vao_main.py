"""
`scripts/kiem-nhanh-da-vao-main.sh` — nhánh đã vào `main` chưa, theo NỘI DUNG.

Dự án dùng squash merge nên `git branch --merged` không nhận ra nhánh đã merge
(CLAUDE.md mục 1). Câu dặn "diff với main rỗng" đúng về ý nhưng
`git diff main <nhánh>` lẫn hai chiều: nhánh đi sau `main` cũng hiện ra "dòng
thêm". Ngày 16/10/2026 tôi đọc đúng cái nhiễu đó và tưởng bốn nhánh còn nội
dung chưa merge — cả bốn đã sạch.

Mỗi phép kiểm dựng kho git THẬT trong `tmp_path`: đây là mã dùng git để kết
luận "xoá được", nên phải đo trên git thật, không giả lập.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
KICH = ROOT / 'scripts' / 'kiem-nhanh-da-vao-main.sh'

bash = shutil.which('bash')
pytestmark = pytest.mark.skipif(
    bash is None,
    reason='không có bash — phép kiểm này PHẢI chạy trên CI (ubuntu có bash)')


def _g(kho: Path, *a: str) -> str:
    r = subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                       cwd=kho, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    assert r.returncode == 0, f'git {" ".join(a)}: {r.stderr[:300]}'
    return r.stdout.strip()


def _ghi(kho: Path, ten: str, noi_dung: str) -> None:
    (kho / ten).write_text(noi_dung, encoding='utf-8')
    _g(kho, 'add', ten)
    _g(kho, 'commit', '-q', '-m', f'ghi {ten}')


@pytest.fixture
def kho(tmp_path: Path) -> Path:
    k = tmp_path / 'kho'
    k.mkdir()
    _g(k, 'init', '-q', '-b', 'main')
    _ghi(k, 'a.txt', 'mot\n')
    return k


def _chay(kho: Path, nhanh: str, goc: str = 'main'):
    r = subprocess.run([bash, str(KICH), nhanh, goc],
                       cwd=kho, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout + r.stderr


# ── Ba kết luận phải đúng ──────────────────────────────────────────────────

def test_nhanh_da_squash_merge_thi_SACH(kho):
    """
    Đúng tình huống của kho này: nhánh được squash merge, nên lịch sử không
    nối, `git branch --merged` không thấy — mà nội dung thì đã nằm trong `main`.
    """
    _g(kho, 'checkout', '-q', '-b', 'viec/abc')
    _ghi(kho, 'b.txt', 'hai\n')
    _g(kho, 'checkout', '-q', 'main')
    _g(kho, 'merge', '-q', '--squash', 'viec/abc')
    _g(kho, 'commit', '-q', '-m', 'gop viec/abc')

    ma, ra = _chay(kho, 'viec/abc')
    assert ma == 0, f'phải báo SẠCH nhưng thoát {ma}:\n{ra}'
    assert 'SẠCH' in ra


def test_nhanh_di_SAU_main_van_SACH(kho):
    """
    Chỗ `git diff` đọc sai. Nhánh đã merge rồi `main` đi thêm mấy commit nữa:
    `git diff main <nhánh>` sẽ hiện "dòng thêm" (bản cũ của tệp `main` vừa
    sửa), còn thước này phải vẫn báo SẠCH.
    """
    _g(kho, 'checkout', '-q', '-b', 'viec/abc')
    _ghi(kho, 'b.txt', 'hai\n')
    _g(kho, 'checkout', '-q', 'main')
    _g(kho, 'merge', '-q', '--squash', 'viec/abc')
    _g(kho, 'commit', '-q', '-m', 'gop viec/abc')
    # `main` phải SỬA một dòng, không chỉ thêm dòng: nếu chỉ thêm thì
    # `git diff main <nhánh>` ra toàn dòng XOÁ và cái nhiễu cần tránh không
    # xuất hiện — phép tự kiểm ngay dưới đã bắt được đúng chỗ này.
    _ghi(kho, 'a.txt', 'mot DA SUA\n')
    _ghi(kho, 'c.txt', 'bon\n')

    tho = subprocess.run(['git', 'diff', 'main', 'viec/abc', '--numstat'],
                         cwd=kho, capture_output=True, text=True,
                       encoding='utf-8', errors='replace').stdout
    them = sum(int(d.split('\t')[0]) for d in tho.strip().splitlines() if d)
    assert them > 0, ('fixture không tái hiện được cái nhiễu cần tránh — '
                      '`git diff` phải thấy "dòng thêm" ở đây')

    ma, ra = _chay(kho, 'viec/abc')
    assert ma == 0, (f'`git diff` thấy {them} dòng thêm (nhiễu), thước này '
                     f'phải vẫn báo SẠCH nhưng thoát {ma}:\n{ra}')


def test_nhanh_con_viec_chua_merge_thi_bao_CON(kho):
    _g(kho, 'checkout', '-q', '-b', 'viec/abc')
    _ghi(kho, 'b.txt', 'hai\n')
    _g(kho, 'checkout', '-q', 'main')

    ma, ra = _chay(kho, 'viec/abc')
    assert ma == 1, f'phải báo CÒN NỘI DUNG nhưng thoát {ma}:\n{ra}'
    assert 'b.txt' in ra, 'phải chỉ ra tệp nào còn, không chỉ nói "còn"'


def test_xung_dot_thi_thoat_2_chu_khong_bao_SACH(kho):
    """
    Xung đột KHÔNG được báo thành SẠCH — báo sạch là xoá mất việc. Cũng không
    được báo thành CÒN, vì cây có dấu xung đột thì mọi con số đọc ra đều vô
    nghĩa; đúng kiểu `diff.mjs` từ chối so sánh khi thiếu font (CLAUDE.md mục 8).
    """
    _g(kho, 'checkout', '-q', '-b', 'viec/abc')
    _ghi(kho, 'a.txt', 'nhanh sua\n')
    _g(kho, 'checkout', '-q', 'main')
    _ghi(kho, 'a.txt', 'main sua khac\n')

    ma, ra = _chay(kho, 'viec/abc')
    assert ma == 2, f'xung đột phải thoát 2 nhưng thoát {ma}:\n{ra}'
    assert 'XUNG ĐỘT' in ra


# ── Không được kết luận khi không đo được ──────────────────────────────────

@pytest.mark.parametrize('nhanh,goc', [
    ('khong/co', 'main'),
    ('main', 'khong/co'),
])
def test_ref_khong_co_thi_thoat_2(kho, nhanh, goc):
    ma, ra = _chay(kho, nhanh, goc)
    assert ma == 2, f'ref không có phải thoát 2 nhưng thoát {ma}:\n{ra}'
    assert ma != 0, 'không bao giờ được báo SẠCH khi không so được'
    # Phải nói ref NÀO thiếu. Chỉ xét mã thoát là chưa đủ: bỏ hẳn phần kiểm ref
    # thì `merge-tree` cũng hỏng và cũng ra mã 2 — đúng số, lời báo vô dụng.
    # Đã phá thử ngày 16/10/2026 và bản phép kiểm cũ vẫn xanh.
    assert 'không có ref' in ra, f'phải nói rõ ref nào không có:\n{ra}'


def test_thieu_doi_so_thi_thoat_2(kho):
    r = subprocess.run([bash, str(KICH)], cwd=kho,
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    assert r.returncode == 2
    # Cùng lý lẽ: phải in CÁCH DÙNG, không chỉ thoát 2 rồi im.
    assert 'dùng:' in (r.stdout + r.stderr)
