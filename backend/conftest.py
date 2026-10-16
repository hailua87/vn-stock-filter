"""
Cấu hình chung cho mọi lượt chạy test của backend.

Tệp này giữ HAI việc, cả hai đều là chuyện của *thước đo*, không phải của mã
được đo:

1. Cô lập peer database khỏi tệp cache gitignored (fixture `_co_lap_peer_db`).
2. Dọn tệp cấu hình trợ lý AI mà `vnai` có thể ghi ra (`pytest_sessionfinish`).

Phần (1) — vì sao: xem docstring của fixture.

Phần (2) — vì sao: `vnai` (phụ thuộc của `vnstock`) tải một prompt từ
vnstocks.com và GHI ĐÈ vào tệp cấu hình của các trợ lý AI — `AGENTS.md` của thư
mục đang chạy, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`
— mỗi lần `import vnstock` (đo thật 23/09/2026; CHANGELOG 4.0.9 của vnstock
xác nhận các bản trước 4.0.9 làm vậy). PyPI cách ly vnstock + vnai 24–25/09.

Từ 26/09/2026 dự án KHÔNG còn import vnstock (xem `scanner/sources/`), nên
đường ghi đó không còn chạy từ repo này. `pytest_sessionfinish` giữ lại như
lớp phòng thủ cuối: máy cá nhân đã cài vnstock từ trước vẫn có thể bị ghi khi
có thứ khác import nó. `/AGENTS.md` trong .gitignore vẫn là thứ chặn chính — tệp có
bị ghi cũng không lọt vào commit.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = ('AGENTS.md',)

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _co_lap_peer_db(monkeypatch, tmp_path):
    """
    Trỏ `peer_database.PEER_DB_PATH` sang một đường dẫn trong `tmp_path` cho
    MỌI phép kiểm của backend.

    ## Vì sao (đo ngày 16/10/2026)

    `backend/data/peer_multiples.json` bị gitignore, nên **CI không bao giờ có
    nó**. Nhưng **một lượt chạy `run_valuation.py` tại máy sẽ tạo ra nó**
    (`save_peer_database()` ghi vào đúng đường dẫn cứng này), và từ đó trở đi
    `methods_pe.py` với `methods_ev_ebitda.py` đọc được nó qua
    `get_peer_band()` — kể cả trong test.

    Hậu quả: bộ test cho kết luận KHÁC NHAU trên cùng một mã nguồn, tuỳ theo
    máy người chạy đã từng chạy pipeline hay chưa. Người gặp phải sẽ đi tìm lỗi
    trong thay đổi của mình, không phải trong một tệp cache.

    Không phải nguy cơ lý thuyết. Đo trên cây SẠCH, fixture FPT của
    `test_valuation_loai_lac.py` ở beta 2,3, tỷ lệ `DCF FCFF` so với trung vị
    các phương pháp (ngưỡng loại là 1/3 = 0,3333):

        không có tệp                      0,3327   → DCF bị loại (xanh)
        tệp thật, 200 mã, 13/10           0,2084   → DCF bị loại (xanh)
        tệp có Technology pe=5, ev=4      1,0000   → KHÔNG loại gì (ĐỎ)

    Quét 75 nội dung peer DB khác nhau (pe × roe × ev_ebitda của ngành
    Technology): **18/75 làm ba phép kiểm đỏ** ở beta 2,3, và **1/75** ở beta
    2,7. Tức beta cao hơn chỉ nới khoảng dự phòng, KHÔNG gỡ được sự phụ thuộc —
    nên bản sửa nằm ở đây, không nằm ở ngưỡng.

    ## Vì sao trỏ sang chỗ KHÔNG tồn tại

    Đây đúng là điều kiện của CI: `load_peer_database()` trả `None`, các method
    rơi về VN-Index proxy. Chốt test vào điều kiện CI nghĩa là đỏ tại máy thì
    cũng đỏ trên CI, và ngược lại.

    Phép kiểm nào CẦN peer data thì tự ghi nội dung vào
    `peer_database.PEER_DB_PATH` (giờ là tmp_path, ghi vào đó an toàn), hoặc
    truyền `peer_db=` tường minh — xem `backend/test_peer_database.py`.

    `tmp_path` riêng từng phép kiểm nên nó cũng chặn chiều ngược lại: một phép
    kiểm gọi `save_peer_database()` không tham số sẽ ghi vào tmp, không còn
    ngầm tạo tệp cache trong kho.

    Canh bởi `backend/tests/test_peer_db_co_lap.py`.
    """
    from scanner import peer_database
    monkeypatch.setattr(peer_database, 'PEER_DB_PATH',
                        tmp_path / 'peer_multiples.json')


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
