"""
Cấu hình chung cho mọi lượt chạy test của backend.

Vì sao tệp này tồn tại: `vnai` (phụ thuộc của `vnstock`) tải một prompt từ
vnstocks.com và GHI ĐÈ vào tệp cấu hình của các trợ lý AI — `AGENTS.md` của thư
mục đang chạy, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`
— mỗi lần `import vnstock` (đo thật 23/09/2026; CHANGELOG 4.0.9 của vnstock
xác nhận các bản trước 4.0.9 làm vậy). PyPI cách ly vnstock + vnai 24–25/09.

Từ 26/09/2026 dự án KHÔNG còn import vnstock (xem `scanner/sources/`), nên
đường ghi đó không còn chạy từ repo này. Hook dưới đây giữ lại như lớp phòng
thủ cuối: máy cá nhân đã cài vnstock từ trước vẫn có thể bị ghi khi có thứ
khác import nó. `/AGENTS.md` trong .gitignore vẫn là thứ chặn chính — tệp có
bị ghi cũng không lọt vào commit.
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
