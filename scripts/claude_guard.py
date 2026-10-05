#!/usr/bin/env python3
"""
Cổng chặn cho Claude Code — chạy như PreToolUse hook trên công cụ Bash.

Đọc JSON của lần gọi công cụ từ stdin, in ra JSON quyết định. Chặn hai nhóm
lệnh, cả hai đều rút từ sự cố có thật:

  1. Chạy pipeline mà ghi đè `web/data/` production.
     `run_daily.py`, `run_valuation.py`, `run_quality.py` đều có tham số
     `--web-data-dir` mặc định là `web/data` — tức thư mục đang phục vụ người
     đọc. Ngày 05/10/2026 việc này xảy ra HAI LẦN trong một phiên: lần đầu đè
     tệp định giá 81 mã, lần sau đè 13 tệp. Cả hai lần đều phải khôi phục bằng
     `git checkout`.

  2. Hai luật git đứng của chủ kho: không `git pull --rebase`, và không
     push/merge vào `main` khi chưa được duyệt.

KHÔNG dùng jq: Git Bash trên Windows không có sẵn. Python thì chắc chắn có —
cả dự án viết bằng Python.

Thoát 0 kèm JSON quyết định. Hook không bao giờ làm hỏng lệnh vì lý do kỹ
thuật: mọi lỗi bất ngờ đều cho qua (fail-open). Một cổng chặn hay hỏng sẽ bị
người ta tắt đi, và khi đó nó không chặn được gì nữa.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

PIPELINE = ('run_daily.py', 'run_valuation.py', 'run_quality.py')


def _nhanh_hien_tai() -> str:
    try:
        r = subprocess.run(['git', 'branch', '--show-current'],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ''


def _trong_kho(duong_dan: str) -> bool:
    """Thư mục này có nằm trong kho không? Chỉ cần bắt các dạng hay gõ nhầm."""
    d = duong_dan.strip().strip('"\'').replace('\\', '/').rstrip('/')
    if not d:
        return True
    # Tương đối mà không bắt đầu bằng .. -> nằm trong kho
    if not re.match(r'^([A-Za-z]:|/|~)', d):
        return not d.startswith('..')
    return False


def bo_heredoc(cmd: str) -> str:
    """
    Gỡ phần THÂN của mọi heredoc. Thân heredoc là DỮ LIỆU, không phải lệnh.

    Không có bước này thì một lời nhắn commit nhắc tới `git pull --rebase` để
    GIẢI THÍCH luật sẽ bị chặn như thể đang chạy lệnh đó. Đã xảy ra thật ngay
    ở commit giới thiệu cổng chặn này.
    """
    dong = cmd.split('\n')
    ra, i = [], 0
    while i < len(dong):
        ra.append(dong[i])
        m = re.search(r'<<-?\s*[\'"]?([A-Za-z_][A-Za-z0-9_]*)[\'"]?', dong[i])
        if m:
            ket = m.group(1)
            i += 1
            while i < len(dong) and dong[i].strip() != ket:
                i += 1                   # bỏ thân
            if i < len(dong):
                ra.append(dong[i])       # giữ lại dấu kết thúc
        i += 1
    return '\n'.join(ra)


def kiem(cmd: str) -> str | None:
    """Trả lý do chặn, hoặc None nếu cho qua."""
    c = ' '.join(bo_heredoc(cmd).split())   # gộp khoảng trắng cho dễ khớp

    # --- 1. Pipeline ghi đè web/data production ---------------------------
    #
    # Phải khớp "ĐANG CHẠY script", không phải "có nhắc tên script". Bản đầu
    # khớp chuỗi con nên chặn oan cả `git diff backend/run_daily.py`,
    # `grep ... run_daily.py`, `cat backend/run_daily.py` — những lệnh đọc,
    # hoàn toàn vô hại. Một cổng chặn hay chặn oan sẽ bị tắt đi.
    for script in PIPELINE:
        chay = re.search(rf'\bpython[0-9.]*\s+(?:-\S+\s+)*\S*{re.escape(script)}\b', c)
        if not chay:
            continue
        m = re.search(r'--web-data-dir[= ]\s*([^\s;&|]+)', c)
        if not m:
            return (f'`{script}` mặc định ghi vào `web/data/` — tức ĐÈ LÊN DỮ '
                    f'LIỆU PRODUCTION đang phục vụ. Thêm `--web-data-dir <thư '
                    f'mục ngoài kho>` khi chạy thử. (Đã lỡ hai lần ngày '
                    f'05/10/2026; xem CLAUDE.md mục 7.)')
        if _trong_kho(m.group(1)):
            return (f'`--web-data-dir {m.group(1)}` vẫn nằm TRONG kho. Trỏ ra '
                    f'thư mục ngoài kho, nếu không lượt chạy vẫn đè dữ liệu đã '
                    f'commit. (CLAUDE.md mục 7.)')
        break

    # --- 2. Luật git đứng --------------------------------------------------
    if re.search(r'\bgit\s+pull\b.*--rebase\b', c):
        return ('Luật đứng của kho: KHÔNG dùng `git pull --rebase`. Dùng '
                '`git pull --ff-only`. (CLAUDE.md mục 1.)')

    nhanh = _nhanh_hien_tai()

    m = re.search(r'\bgit\s+push\b([^;&|]*)', c)
    if m:
        duoi = m.group(1)
        len_main = bool(re.search(r'(^|\s)(origin\s+)?(main|HEAD:main|[^\s:]+:main)(\s|$)', duoi))
        khong_neu_dich = not re.search(r'\s\S+\s+\S', duoi.strip() + ' x') and not duoi.strip()
        if len_main or (nhanh == 'main' and not re.search(r'\s\S+\s+\S+', duoi)):
            return (f'Luật đứng của kho: KHÔNG push `main` khi chưa được chủ '
                    f'kho duyệt. (Nhánh hiện tại: `{nhanh or "?"}`. '
                    f'CLAUDE.md mục 1.)')

    if nhanh == 'main' and re.search(r'\bgit\s+merge\b', c):
        return ('Luật đứng của kho: KHÔNG merge vào `main` khi chưa được chủ '
                'kho duyệt. Dùng `gh pr merge` sau khi được duyệt. '
                '(CLAUDE.md mục 1.)')

    return None


def main() -> int:
    # Windows mặc định cp1252 cho stdout, và mọi lý do chặn ở đây đều tiếng
    # Việt -> `print` ném UnicodeEncodeError và hook THOÁT KHÁC 0. Claude Code
    # không đặt PYTHONIOENCODING, nên phải tự ép ở đây.
    #
    # Phép kiểm đầu tiên của tôi KHÔNG bắt được lỗi này: tôi chạy pytest với
    # PYTHONIOENCODING=utf-8 trong shell, và biến đó rò vào tiến trình con.
    # Nay có `test_chay_duoc_khi_khong_co_PYTHONIOENCODING` chạy với môi trường
    # đã gỡ biến đó.
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding='utf-8')
        except Exception:
            pass

    try:
        data = json.load(sys.stdin)
        cmd = (data.get('tool_input') or {}).get('command') or ''
    except Exception:
        # Fail-open: hook hỏng thì cho lệnh chạy, đừng chặn oan.
        print(json.dumps({}))
        return 0

    ly_do = None
    try:
        ly_do = kiem(cmd)
    except Exception as e:
        print(json.dumps({'systemMessage': f'claude_guard lỗi, cho qua: {e}'}))
        return 0

    if ly_do:
        print(json.dumps({
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': ly_do,
            }
        }, ensure_ascii=False))
    else:
        print(json.dumps({}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
