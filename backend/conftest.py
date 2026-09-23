"""
Cấu hình chung cho mọi lượt chạy test của backend.

Vì sao tệp này tồn tại: `vnai` (phụ thuộc của `vnstock`) tải một prompt từ
vnstocks.com và GHI ĐÈ vào tệp cấu hình của các trợ lý AI — `AGENTS.md` của thư
mục đang chạy, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`.
Nó làm việc đó khi `import vnstock`, mà suite này có `test_financial_fetcher_
import.py` import thật để kiểm API. Kết quả: `AGENTS.md` mọc lại sau mỗi lượt
pytest, mang theo chỉ dẫn của bên thứ ba cho mọi trợ lý mở repo này.

ĐO THẬT 23/09/2026 — `VNSTOCK_DISABLE_AGENT_SETUP=1` KHÔNG chặn được:

    VNSTOCK_DISABLE_AGENT_SETUP=1      -> AGENTS.md DUOC TAO
    VNSTOCK_DISABLE_AGENT_SETUP=unset  -> AGENTS.md DUOC TAO

`vnai/beam/agents.py` (bản 2.5.6) không đọc biến nào tên như vậy; cả tệp không
có một nhánh tắt nào. Việc ghi chỉ phụ thuộc có API key hay không. Biến đó đang
được đặt trong 4 workflow và được nhắc tới trong README, BLUEPRINT_v3 và
requirements.txt — những chỗ ấy mô tả SAI tác dụng của nó.

Thứ thật sự bảo vệ repo là `/AGENTS.md` trong `.gitignore`: tệp có bị ghi cũng
không bao giờ lọt vào commit. Hook dưới đây dọn nốt phần rác trên đĩa, để lượt
pytest không để lại thứ gì.
"""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = ('AGENTS.md',)


def _is_tracked(path: Path) -> bool:
    """git có theo dõi tệp này không. Lỗi thì trả True — thà không xóa."""
    try:
        r = subprocess.run(['git', 'ls-files', '--error-unmatch', str(path)],
                           cwd=REPO_ROOT, capture_output=True)
        return r.returncode == 0
    except Exception:
        return True


def pytest_sessionfinish(session, exitstatus):
    """
    Dọn tệp cấu hình trợ lý mà `vnai` ghi ra trong lượt chạy.

    Chỉ xóa tệp git KHÔNG theo dõi: nếu có ngày nào đó dự án tự viết `AGENTS.md`
    và commit nó, hook này phải để yên. Xóa nhầm tài liệu thật của dự án còn tệ
    hơn là để lại một tệp rác đã bị gitignore.
    """
    for name in AGENT_FILES:
        p = REPO_ROOT / name
        if p.exists() and not _is_tracked(p):
            try:
                p.unlink()
            except OSError:
                pass        # Không xóa được thì thôi; .gitignore vẫn chặn commit.
