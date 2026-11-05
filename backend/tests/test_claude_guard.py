"""
Cổng chặn cho Claude Code (`scripts/claude_guard.py`).

Hai nhóm luật, cả hai đều rút từ sự cố có thật:

  1. Pipeline ghi đè `web/data/` production. Ngày 05/10/2026 việc này xảy ra
     HAI LẦN trong một phiên — lần đầu đè tệp định giá 81 mã, lần sau đè 13
     tệp, cả hai phải khôi phục bằng `git checkout`.
  2. Hai luật git đứng của chủ kho: không `git pull --rebase`, không push/merge
     vào `main` khi chưa được duyệt.

MỘT CỔNG CHẶN SAI CÒN TỆ HƠN KHÔNG CÓ. Chặn oan thì người ta tắt nó đi, và khi
đó nó không chặn được gì nữa. Nên phân nửa số phép kiểm dưới đây là "PHẢI CHO
QUA", không phải "phải chặn".
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
GUARD = ROOT / 'scripts' / 'claude_guard.py'

sys.path.insert(0, str(GUARD.parent))
import claude_guard as G  # noqa: E402


def quyet_dinh(cmd: str, cwd=None):
    """
    Chạy cổng chặn ĐÚNG như Claude Code chạy nó: JSON vào stdin, JSON ra.

    `cwd` là tham số BẮT BUỘC PHẢI NGHĨ TỚI với mọi luật đọc trạng thái git:
    cổng chặn chạy `git rev-parse` trong thư mục làm việc của nó, nên cùng một
    lệnh ra quyết định khác nhau ở checkout chính và ở worktree phụ. Bỏ trống
    thì nó thừa hưởng thư mục của bộ test — tiện cho các luật thuần cú pháp,
    nhưng với luật phụ thuộc git thì phải truyền tường minh.
    """
    r = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps({'tool_name': 'Bash',
                                         'tool_input': {'command': cmd}}),
                       capture_output=True, text=True, encoding='utf-8',
                       cwd=None if cwd is None else str(cwd))
    assert r.returncode == 0, f'cổng chặn phải luôn thoát 0, stderr: {r.stderr[:200]}'
    out = json.loads(r.stdout or '{}')
    return (out.get('hookSpecificOutput') or {}).get('permissionDecision')


# ── Pipeline ghi đè production ──────────────────────────────────────────────

@pytest.mark.parametrize('cmd', [
    'python backend/run_daily.py --limit 60',
    'PYTHONIOENCODING=utf-8 python backend/run_valuation.py --limit 6',
    'python backend/run_quality.py --limit 200',
    'python backend/run_daily.py --web-data-dir web/data',      # vẫn trong kho
    'python backend/run_daily.py --web-data-dir ./web/data2',   # vẫn trong kho
])
def test_chan_luot_chay_ghi_de_production(cmd):
    assert quyet_dinh(cmd) == 'deny', cmd


@pytest.mark.parametrize('cmd', [
    'python backend/run_daily.py --limit 60 --web-data-dir /tmp/wd',
    'python backend/run_daily.py --web-data-dir C:/Users/x/scratch/wd',
    'python backend/run_daily.py --web-data-dir ../ngoai-kho/wd',
    'python backend/run_daily.py --web-data-dir ~/scratch/wd',
])
def test_cho_qua_khi_tro_ra_ngoai_kho(cmd):
    assert quyet_dinh(cmd) != 'deny', cmd


# ── Luật git ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('cmd', ['git pull --rebase', 'git pull --rebase origin main'])
def test_chan_pull_rebase(cmd):
    assert quyet_dinh(cmd) == 'deny', cmd


@pytest.mark.parametrize('cmd', [
    'git push origin main',
    'git push origin HEAD:main',
])
def test_chan_push_len_main(cmd):
    assert quyet_dinh(cmd) == 'deny', cmd


def test_chan_push_tran_khi_dang_dung_tren_main(monkeypatch):
    """
    `git push` trần không nói đích — phải tra nhánh hiện tại mới biết.
    Đây là chỗ dễ lọt nhất và cũng là chỗ bảo vệ `main`.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem('git push') is not None
    assert G.kiem('git push origin') is not None


def test_cho_qua_push_tran_khi_dang_o_nhanh_khac(monkeypatch):
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'feat/abc')
    assert G.kiem('git push') is None
    assert G.kiem('git push -u origin feat/abc') is None


def test_chan_merge_khi_dang_dung_tren_main(monkeypatch):
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem('git merge feat/abc') is not None


def test_cho_qua_merge_main_vao_nhanh_lam_viec(monkeypatch):
    """
    Đưa `main` VÀO nhánh làm việc là việc hằng ngày và được phép — luật chỉ cấm
    chiều ngược lại. Chặn nhầm chiều này thì cổng chặn thành vật cản.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'feat/abc')
    assert G.kiem('git merge main') is None


@pytest.mark.parametrize('cmd', [
    'git pull --ff-only', 'git status', 'git log --oneline -5',
    'pytest backend -q', 'ls web/data',
    # `gh pr merge` KHONG nam o day nua: quyet dinh cua no phu thuoc NOI CHAY,
    # xem test_merge_PR_cho_qua_o_chinh_va_chan_o_worktree_phu ngay duoi.
])
def test_cho_qua_lenh_binh_thuong(cmd):
    assert quyet_dinh(cmd) != 'deny', cmd


# ── Cổng chặn không được tự làm hỏng việc ───────────────────────────────────

def test_hong_thi_cho_qua_chu_khong_chan_oan():
    """
    Fail-open là CÓ CHỦ Ý. Một cổng chặn hay hỏng sẽ bị tắt đi, và khi đó nó
    không chặn được gì nữa. Thà lọt một lệnh còn hơn mất cả cổng.
    """
    r = subprocess.run([sys.executable, str(GUARD)], input='khong-phai-json',
                       capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0
    assert (json.loads(r.stdout or '{}').get('hookSpecificOutput') or {}) == {}


def test_loi_bat_ngo_trong_kiem_van_cho_qua(monkeypatch, capsys):
    """
    Chạy TRONG TIẾN TRÌNH, không qua subprocess: bản vá `monkeypatch` chỉ có
    tác dụng ở tiến trình này. Bản đầu của phép kiểm này gọi qua subprocess —
    nó xanh, nhưng xanh RỖNG: nó chỉ chứng minh `git status` không bị chặn,
    điều đã có phép kiểm khác lo.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai',
                        lambda: (_ for _ in ()).throw(RuntimeError('vo')))
    # Chốt chặn: `kiem` PHẢI ném thật, nếu không phép kiểm dưới vô nghĩa.
    with pytest.raises(RuntimeError):
        G.kiem('git push')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(
        {'tool_name': 'Bash', 'tool_input': {'command': 'git push'}})))
    assert G.main() == 0
    ra = json.loads(capsys.readouterr().out)
    assert (ra.get('hookSpecificOutput') or {}) == {}, 'lỗi bất ngờ phải CHO QUA'
    assert 'claude_guard lỗi' in ra.get('systemMessage', ''), 'và phải nói ra'


@pytest.mark.parametrize('cmd', [
    'git diff backend/run_daily.py',
    'grep -n WEB_OUTPUTS backend/run_daily.py',
    'cat backend/run_valuation.py',
    'git log --oneline -- backend/run_quality.py',
    'wc -l backend/run_daily.py',
])
def test_cho_qua_lenh_chi_NHAC_TEN_script(cmd):
    """
    Đọc tệp không phải chạy tệp. Bản đầu của cổng chặn khớp chuỗi con nên chặn
    oan cả `git diff backend/run_daily.py` — và một cổng chặn hay chặn oan sẽ
    bị tắt đi, lúc đó nó không chặn được gì nữa.
    """
    assert quyet_dinh(cmd) != 'deny', cmd


# ── Thân heredoc là DỮ LIỆU, không phải lệnh ────────────────────────────────

def test_cho_qua_khi_lenh_cam_chi_nam_trong_than_heredoc():
    """
    Lời nhắn commit GIẢI THÍCH một luật thường phải nhắc tên lệnh bị cấm. Chặn
    nó là chặn oan — và chuyện này đã xảy ra thật, đúng ở commit giới thiệu
    cổng chặn này: nó chặn chính lời nhắn mô tả nó.
    """
    cmd = ("git commit -q -F - <<'EOF'\n"
           "docs: ghi lai luat git\n"
           "\n"
           "Khong dung `git pull --rebase`. Dung `git pull --ff-only`.\n"
           "Khong `git push origin main` khi chua duoc duyet.\n"
           "EOF")
    assert quyet_dinh(cmd) != 'deny'


def test_van_chan_khi_lenh_cam_nam_NGOAI_heredoc():
    """
    Chốt chặn cho phép kiểm trên: nếu `bo_heredoc` nuốt luôn phần ngoài thì
    phép kiểm kia xanh một cách rỗng.
    """
    cmd = ("git commit -F - <<'EOF'\n"
           "mot loi nhan binh thuong\n"
           "EOF\n"
           "git push origin main")
    assert quyet_dinh(cmd) == 'deny'


def test_than_heredoc_khong_dau_nhay_cung_duoc_go():
    cmd = ("cat <<EOF > /tmp/x\n"
           "python backend/run_daily.py\n"
           "EOF")
    assert quyet_dinh(cmd) != 'deny'


@pytest.mark.parametrize('cmd', [
    'python backend/run_daily.py --web-data-dir "$SP/wd"',
    'python backend/run_valuation.py --web-data-dir ${TMPDIR}/wd',
    'python backend/run_quality.py --web-data-dir "$(mktemp -d)"',
])
def test_cho_qua_khi_duong_dan_la_bien_shell(cmd):
    """
    Biến shell không đoán được tĩnh. Chặn nó là chặn oan — và đã chặn oan thật:
    `--web-data-dir "$SP/wdbeta"` trỏ ra thư mục scratch ngoài kho.

    Fail-open, cùng lý lẽ với phần còn lại: lỗi thật cần chặn là QUÊN HẲN tham
    số, và `test_chan_luot_chay_ghi_de_production` vẫn canh chuyện đó.
    """
    assert quyet_dinh(cmd) != 'deny', cmd


# ── Hai cho CHAN OAN da xay ra that (13/10/2026) ────────────────────────────

@pytest.mark.parametrize('cmd', [
    'git merge-base main origin/diag/vci-latency',
    'git merge-tree main feat/abc',
    'GOC=$(git merge-base main origin/x) && git diff --stat $GOC origin/x',
])
def test_cho_qua_merge_base_va_merge_tree(monkeypatch, cmd):
    """
    `git merge-base` va `git merge-tree` la lenh CHI DOC — khong merge gi.

    Ban dau dung `\bgit\s+merge\b`, ma `\b` khop ca dau gach noi, nen
    `git merge-base` bi chan nhu the dang merge vao main. Chan oan that khi
    toi tra noi dung nhanh truoc khi xoa no.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem(cmd) is None, cmd


def test_van_chan_git_merge_that_khi_dung_tren_main(monkeypatch):
    """Chot chan cho phep kiem tren: dung ra thi `\bgit merge\b` phai con chan."""
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem('git merge feat/abc') is not None
    assert G.kiem('git merge --no-ff feat/abc') is not None


@pytest.mark.parametrize('cmd', ['git merge --abort', 'git merge --quit'])
def test_cho_qua_merge_abort(monkeypatch, cmd):
    """
    `--abort` la lenh de HUY mot lan merge dang do. Chan no la giam nguoi ta
    trong trang thai merge do — con te hon chinh viec no dinh ngan.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem(cmd) is None, cmd


def test_cho_qua_chuyen_nhanh_roi_merge_main_trong_cung_mot_lenh(monkeypatch):
    """
    `git checkout X && git merge main` — dua main VAO nhanh lam viec, viec hang
    ngay va duoc phep. Nhung hook doc nhanh hien tai TRUOC khi lenh chay, nen
    no thay 'main' va tuong la chieu nguoc lai. Da chan oan that.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem('git checkout feat/abc && git merge main') is None
    assert G.kiem('git switch feat/abc && git merge main') is None
    assert G.kiem('git checkout -b moi/abc && git merge main') is None


def test_van_chan_khi_chuyen_VE_main_roi_merge(monkeypatch):
    """
    Chot chan: `git checkout main && git merge feat/abc` la DUNG cai bi cam.
    Neu phan doc nhanh dich lam hong chieu nay thi luat mat tac dung.
    """
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'feat/abc')
    assert G.kiem('git checkout main && git merge feat/abc') is not None
    monkeypatch.setattr(G, '_nhanh_hien_tai', lambda: 'main')
    assert G.kiem('git checkout main && git merge feat/abc') is not None


# ── Chỉ checkout chính được merge PR ───────────────────────────────────────
#
# Ngày 16/10/2026 đo được NĂM phiên làm việc song song trên kho này, mỗi phiên
# một worktree, và chúng tự sinh ra nhau. `main` nhảy 5 lần trong một buổi.
# Worktree cô lập tệp nên không xung đột nội dung — cái đụng nhau là `main`:
# CI xanh trên `main` CŨ không nói gì về `main` MỚI.

@pytest.mark.parametrize('cmd', [
    'gh pr merge 96 --squash',
    'gh pr merge --squash --delete-branch=false 101',
    'cd backend && gh pr merge 99 --merge',
])
def test_chan_merge_PR_tu_worktree_phu(monkeypatch, cmd):
    monkeypatch.setattr(G, '_trong_worktree_phu', lambda: True)
    monkeypatch.setattr(G, '_cong_dang_bi_giu', lambda c: False)
    assert G.kiem(cmd) is not None


def test_cho_qua_merge_PR_o_checkout_chinh(monkeypatch):
    monkeypatch.setattr(G, '_trong_worktree_phu', lambda: False)
    monkeypatch.setattr(G, '_cong_dang_bi_giu', lambda c: False)
    assert G.kiem('gh pr merge 96 --squash') is None


@pytest.mark.parametrize('cmd', [
    'gh pr create --fill',
    'gh pr view 96 --json state',
    'gh pr checks 96 --watch',
    'gh pr list --state open',
    'gh pr comment 96 --body "xong"',
])
def test_worktree_phu_van_mo_va_doc_PR_binh_thuong(monkeypatch, cmd):
    """
    Luật là "chỉ chặn MERGE", không phải "chặn gh". Phiên phụ vẫn phải mở được
    PR và đọc được cổng, nếu không thì cách làm việc nhiều phiên đứng hẳn — và
    một cổng chặn làm người ta không làm được việc sẽ bị tắt đi.
    """
    monkeypatch.setattr(G, '_trong_worktree_phu', lambda: True)
    monkeypatch.setattr(G, '_cong_dang_bi_giu', lambda c: False)
    assert G.kiem(cmd) is None


def test_khong_doc_duoc_git_thi_cho_qua(monkeypatch):
    """Fail-open: `git rev-parse` hỏng thì không được chặn oan."""
    def hong(*a, **k):
        raise OSError('git không có ở đây')
    monkeypatch.setattr(G.subprocess, 'run', hong)
    assert G._trong_worktree_phu() is False


# ── Hai máy chủ cùng một cổng ──────────────────────────────────────────────
#
# CLAUDE.md mục 7: hai `python -m http.server` cùng cổng trên Windows chia yêu
# cầu BẤT ĐỊNH và làm treo bộ đo bố cục.

@pytest.mark.parametrize('cmd,mong_doi', [
    ('python -m http.server 8801', 8801),
    ('python -m http.server 8801 --bind 127.0.0.1', 8801),
    ('python -m http.server --bind 127.0.0.1 8801', 8801),
    ('python -m http.server --directory web 8801', 8801),
    # Ca DUY NHAT lam phan bo qua gia tri tham so co tac dung: gia tri cua
    # tham so la toan CHU SO. Khong co ca nay thi doan do la ma chet — pha no
    # di ma moi phep kiem van xanh, da do 16/10/2026.
    ('python -m http.server --directory 2026 8801', 8801),
    ('python -m http.server --bind 127.0.0.1 --directory 2026 8801', 8801),
    ('python3 -m http.server', 8000),
    ('python -m http.server --bind 127.0.0.1', 8000),
    ('cd web && python -m http.server 9000 & sleep 1', 9000),
    ('ls -la', None),
    ('grep -n "http.server" docs/*.md', None),
])
def test_doc_dung_cong_trong_lenh(cmd, mong_doi):
    """
    Cổng đứng TRƯỚC hay SAU tham số đều hợp lệ, và không có số thì
    `http.server` dùng 8000 — đúng cái cổng hay đụng nhau nhất.
    """
    assert G._cong_trong_lenh(cmd) == mong_doi


def test_chan_khi_cong_da_co_nguoi_giu_do_THAT(monkeypatch):
    """
    Buộc một cổng thật rồi hỏi cổng chặn, không giả lập: `_cong_dang_bi_giu`
    dựa vào hành vi của socket, mà hành vi đó khác nhau giữa Windows và ubuntu
    (`SO_REUSEADDR`, buộc theo giao diện). Giả lập thì không đo được chỗ đó.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen(1)
    cong = s.getsockname()[1]
    try:
        assert G._cong_dang_bi_giu(cong) is True
        monkeypatch.setattr(G, '_trong_worktree_phu', lambda: False)
        ly_do = G.kiem(f'python -m http.server {cong}')
        assert ly_do is not None and str(cong) in ly_do
    finally:
        s.close()
    # Nhả ra thì phải cho qua ngay — nếu không, cổng chặn sẽ chặn vĩnh viễn.
    assert G._cong_dang_bi_giu(cong) is False


def test_cho_qua_khi_cong_con_trong(monkeypatch):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    cong = s.getsockname()[1]
    s.close()
    monkeypatch.setattr(G, '_trong_worktree_phu', lambda: False)
    assert G.kiem(f'python -m http.server {cong}') is None


def test_nhan_biet_worktree_tren_kho_THAT(tmp_path, monkeypatch):
    """
    Dựng kho git thật + worktree thật, không giả lập `_trong_worktree_phu`.

    Mọi phép kiểm ở trên đều monkeypatch chính hàm này, nên chúng KHÔNG thấy
    được bản đầu của nó hỏng: nó cặp `--absolute-git-dir` (đường tuyệt đối) với
    `--git-common-dir` (đường TƯƠNG ĐỐI), hai chuỗi không bao giờ bằng nhau,
    nên checkout chính cũng bị coi là worktree phụ — tức luật chặn đúng cái
    phiên được phép merge. Đây là phép kiểm duy nhất ở đây bắt được chuyện đó.
    """
    kho = tmp_path / 'kho'
    kho.mkdir()
    def g(*a, cwd=kho):
        subprocess.run(['git', *a], cwd=cwd, check=True,
                       capture_output=True, text=True)
    g('init', '-q')
    g('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q',
      '--allow-empty', '-m', 'dau')

    monkeypatch.chdir(kho)
    assert G._trong_worktree_phu() is False, (
        'checkout chính bị coi là worktree phụ — luật sẽ chặn đúng phiên được '
        'phép merge')

    phu = tmp_path / 'phu'
    g('worktree', 'add', '-q', '-b', 'nhanh/phu', str(phu))
    monkeypatch.chdir(phu)
    assert G._trong_worktree_phu() is True, (
        'worktree phụ không được nhận ra — luật mất tác dụng hoàn toàn')


def test_merge_PR_cho_qua_o_chinh_va_chan_o_worktree_phu(tmp_path):
    """
    Quyết định cho `gh pr merge` phụ thuộc NƠI CHẠY, nên phép kiểm phải nói rõ
    nơi chạy.

    Ca `gh pr merge 42 --squash` từng nằm trong danh sách "phải cho qua" ở trên
    mà không truyền `cwd`, nên nó thừa hưởng thư mục của bộ test: **xanh ở
    checkout chính, ĐỎ trong mọi worktree phụ** — bộ test đỏ tuỳ nơi chạy, trên
    mã nguồn hoàn toàn sạch. Mọi phiên làm việc trong worktree đều gặp, và đúng
    lớp lỗi với `peer_multiples.json` ở CLAUDE.md mục 6. Do PR #103 gây ra; đo
    được ngày 16/10/2026 khi chạy bộ test trong một worktree tạm.

    Hai nửa dưới đây đi qua subprocess thật, trên kho git thật, và **tất định**
    ở bất cứ đâu bộ test chạy.
    """
    kho = tmp_path / 'kho'
    kho.mkdir()

    def g(*a, cwd=kho):
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                       cwd=cwd, check=True, capture_output=True, text=True)

    g('init', '-q')
    g('commit', '-q', '--allow-empty', '-m', 'dau')

    assert quyet_dinh('gh pr merge 42 --squash', cwd=kho) != 'deny', (
        'checkout CHÍNH phải merge được — chặn ở đây là chặn đúng phiên được '
        'phép merge')

    phu = tmp_path / 'phu'
    g('worktree', 'add', '-q', '-b', 'nhanh/phu', str(phu))
    assert quyet_dinh('gh pr merge 42 --squash', cwd=phu) == 'deny', (
        'worktree PHỤ phải bị chặn — nếu không thì luật mục 13 mất tác dụng')


@pytest.mark.parametrize('cmd', [
    'gh pr create --fill', 'gh pr view 42', 'gh pr checks 42 --watch',
])
def test_worktree_phu_van_mo_duoc_PR_do_tren_kho_THAT(tmp_path, cmd):
    """
    Mặt còn lại: chặn MERGE chứ không chặn `gh`. Đo trên worktree thật, không
    giả lập hàm nhận biết — các phép kiểm giả lập ở trên không thấy được một
    luật quá rộng chạy trong môi trường thật.
    """
    kho = tmp_path / 'kho'
    kho.mkdir()

    def g(*a, cwd=kho):
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                       cwd=cwd, check=True, capture_output=True, text=True)

    g('init', '-q')
    g('commit', '-q', '--allow-empty', '-m', 'dau')
    phu = tmp_path / 'phu'
    g('worktree', 'add', '-q', '-b', 'nhanh/phu', str(phu))

    assert quyet_dinh(cmd, cwd=phu) != 'deny', cmd

# ── Cổng chặn phải đọc git ở NƠI LỆNH SẼ CHẠY, không phải nơi hook chạy ────
#
# Hook khai trong `.claude/settings.json` chạy bằng
# `python "$CLAUDE_PROJECT_DIR/scripts/claude_guard.py"`, và `$CLAUDE_PROJECT_DIR`
# ĐỨNG YÊN ở gốc dự án — tức CHECKOUT CHÍNH — trong khi `cwd` của payload đi
# theo Claude (vào worktree, hay sau `cd`). Nên trong mọi worktree phụ, cổng
# chặn hỏi git ở checkout chính và nhận về nhánh của NGƯỜI KHÁC.
#
# Đo được 16/10/2026 ở PR #102: checkout chính đứng ở `main`, phiên làm việc ở
# worktree trên `claude/focused-yalow-414838`, và `git merge origin/main` —
# ĐÚNG việc CLAUDE.md mục 1 dặn phải làm — bị chặn hai lần liên tiếp với lý do
# "KHÔNG merge vào `main`".
#
# Mọi phép kiểm ở trên KHÔNG thấy được chuyện này: chúng hoặc giả lập
# `_nhanh_hien_tai`, hoặc cho tiến trình cổng chặn đứng đúng chỗ cần đọc — tức
# đã giả định sẵn cái đang hỏng. Phải tách HAI thư mục ra mới đo được.


def quyet_dinh_nhu_hook(cmd: str, *, noi_hook, noi_lenh):
    """
    Chạy cổng chặn ĐÚNG như Claude Code chạy nó trong một worktree: tiến trình
    đứng ở `noi_hook` (checkout chính, nơi `$CLAUDE_PROJECT_DIR` trỏ tới), còn
    payload mang `cwd` = `noi_lenh` (worktree mà lệnh sẽ thật sự chạy).

    `noi_lenh=None` nghĩa là payload KHÔNG có khoá `cwd` — dạng cũ, dùng để
    canh phần dự phòng.
    """
    payload = {'tool_name': 'Bash', 'tool_input': {'command': cmd}}
    if noi_lenh is not None:
        payload['cwd'] = str(noi_lenh)
    r = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps(payload),
                       capture_output=True, text=True, encoding='utf-8',
                       cwd=str(noi_hook))
    assert r.returncode == 0, f'cổng chặn phải luôn thoát 0, stderr: {r.stderr[:300]}'
    return (json.loads(r.stdout or '{}').get('hookSpecificOutput')
            or {}).get('permissionDecision')


@pytest.fixture
def kho_va_phu(tmp_path):
    """Checkout chính đứng ở `main`, cạnh nó một worktree phụ ở nhánh khác."""
    kho = tmp_path / 'kho'
    kho.mkdir()

    def g(*a, cwd=kho):
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                       cwd=cwd, check=True, capture_output=True, text=True)

    g('init', '-q', '-b', 'main')
    g('commit', '-q', '--allow-empty', '-m', 'dau')
    phu = tmp_path / 'phu'
    g('worktree', 'add', '-q', '-b', 'nhanh/phu', str(phu))

    # Chốt chặn cho chính đồ dựng: nếu hai thư mục không đứng ở hai nhánh khác
    # nhau thì mọi phép kiểm dưới đây xanh rỗng.
    def nhanh(d):
        return subprocess.run(['git', 'branch', '--show-current'], cwd=d,
                              capture_output=True, text=True).stdout.strip()
    assert nhanh(kho) == 'main' and nhanh(phu) == 'nhanh/phu', (
        f'đồ dựng hỏng: {nhanh(kho)!r} / {nhanh(phu)!r}')
    return kho, phu


@pytest.mark.parametrize('cmd', [
    'git merge main',
    'git merge origin/main',
    'git merge --no-ff main',
])
def test_merge_main_vao_nhanh_lam_viec_trong_worktree_KHONG_bi_chan(kho_va_phu, cmd):
    """
    Chính cái lỗi: lệnh chạy ở worktree (nhánh `nhanh/phu`), hook đứng ở
    checkout chính (nhánh `main`). Đưa `main` VÀO nhánh làm việc là việc
    CLAUDE.md mục 1 dặn phải làm — chặn nó là chặn đúng việc được phép.
    """
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook(cmd, noi_hook=kho, noi_lenh=phu) != 'deny', cmd


@pytest.mark.parametrize('cmd', [
    'git merge nhanh/phu',
    'git merge --no-ff nhanh/phu',
])
def test_VAN_chan_merge_vao_main_khi_lenh_chay_o_checkout_chinh(kho_va_phu, cmd):
    """
    Chốt chặn cho phép kiểm trên, và nó phải ĐỔI CHIỀU được: lần này hook đứng
    ở worktree còn lệnh chạy ở checkout chính (`main`). Nếu bản sửa chỉ "thôi
    đọc nhánh" hay luôn cho qua trong worktree thì luật mất tác dụng mà phép
    kiểm kia vẫn xanh.
    """
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook(cmd, noi_hook=phu, noi_lenh=kho) == 'deny', cmd


def test_push_tran_doc_nhanh_o_noi_lenh_chay(kho_va_phu):
    """`git push` trần không nói đích — phải tra nhánh ở ĐÚNG thư mục lệnh chạy."""
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook('git push', noi_hook=kho, noi_lenh=phu) != 'deny', (
        'đứng ở nhánh làm việc mà bị chặn push — chặn oan')
    assert quyet_dinh_nhu_hook('git push', noi_hook=phu, noi_lenh=kho) == 'deny', (
        'đứng ở `main` mà push lọt — mất chốt bảo vệ `main`')


def test_quyen_merge_PR_cung_doc_o_noi_lenh_chay(kho_va_phu):
    """
    Cùng một gốc lỗi, luật mục 13 hỏng theo chiều NGƯỢC lại: hỏi checkout chính
    thì `_trong_worktree_phu()` trả False, nên `gh pr merge` trong worktree phụ
    KHÔNG bị chặn gì cả — luật mất tác dụng ở đúng nơi nó cần có.
    """
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook('gh pr merge 42 --squash',
                               noi_hook=kho, noi_lenh=phu) == 'deny', (
        'worktree phụ merge được PR — luật mục 13 mất tác dụng')
    assert quyet_dinh_nhu_hook('gh pr merge 42 --squash',
                               noi_hook=phu, noi_lenh=kho) != 'deny', (
        'checkout chính bị chặn — chặn đúng phiên được phép merge')


@pytest.mark.parametrize('cmd', [
    'git merge-base main origin/x',
    'git merge-tree main nhanh/phu',
    'git merge --abort',
    'git merge --continue',
])
def test_cac_chot_chan_cu_van_dung_khi_lenh_chay_tren_main(kho_va_phu, cmd):
    """
    Hai chỗ đã chặn oan thật (13/10/2026) phải vẫn lọt, kể cả khi nhánh đọc
    được là `main`. Đo lại ở đây vì bản sửa động vào đúng đường đi đó.
    """
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook(cmd, noi_hook=phu, noi_lenh=kho) != 'deny', cmd


def test_khong_co_khoa_cwd_thi_quay_ve_thu_muc_tien_trinh(kho_va_phu):
    """
    Phần dự phòng. Payload không có `cwd` (phiên bản Claude Code cũ, hay phép
    kiểm gọi thẳng) thì phải giữ nguyên hành vi cũ: đọc ở thư mục tiến trình.
    Thiếu chốt này thì một bản sửa "chỉ đọc payload" sẽ âm thầm thôi đọc git.
    """
    kho, phu = kho_va_phu
    assert quyet_dinh_nhu_hook('git merge nhanh/phu',
                               noi_hook=kho, noi_lenh=None) == 'deny'
    assert quyet_dinh_nhu_hook('git merge main',
                               noi_hook=phu, noi_lenh=None) != 'deny'


def test_cwd_tro_vao_thu_muc_khong_ton_tai_thi_cho_qua(kho_va_phu, tmp_path):
    """
    Fail-open, cùng lý lẽ với phần còn lại của cổng chặn: `cwd` hỏng thì hook
    không được chết, cũng không được chặn oan.
    """
    kho, _ = kho_va_phu
    mat = tmp_path / 'khong-ton-tai'
    assert quyet_dinh_nhu_hook('git status', noi_hook=kho, noi_lenh=mat) != 'deny'
