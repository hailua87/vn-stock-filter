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


def quyet_dinh(cmd: str):
    """Chạy cổng chặn ĐÚNG như Claude Code chạy nó: JSON vào stdin, JSON ra."""
    r = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps({'tool_name': 'Bash',
                                         'tool_input': {'command': cmd}}),
                       capture_output=True, text=True, encoding='utf-8')
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
    'pytest backend -q', 'ls web/data', 'gh pr merge 42 --squash',
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
