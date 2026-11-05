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
import os
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
    # Có biến shell hoặc thay thế lệnh -> KHÔNG đoán được tĩnh. Cho qua.
    #
    # Fail-open, cùng lý lẽ với phần còn lại của tệp này: lỗi thật cần chặn là
    # QUÊN HẲN tham số, và trường hợp đó vẫn bị bắt. Người đã gõ
    # `--web-data-dir "$SP/wd"` là người đã nghĩ tới chuyện này rồi. Chặn họ chỉ
    # khiến cổng chặn bị tắt đi.
    if '$' in d or '`' in d:
        return False
    # Tương đối mà không bắt đầu bằng .. -> nằm trong kho
    if not re.match(r'^([A-Za-z]:|/|~)', d):
        return not d.startswith('..')
    return False


def _trong_worktree_phu() -> bool:
    """
    Đang ở worktree phụ, hay ở checkout chính?

    Không dò theo đường dẫn `.claude/worktrees/` — đó là quy ước của ứng dụng,
    đổi lúc nào không biết. Dò bằng chính git: trong worktree phụ thì `--git-dir`
    trỏ vào `.git/worktrees/<tên>` còn `--git-common-dir` trỏ về `.git` gốc;
    ở checkout chính hai cái TRÙNG nhau.

    `--path-format=absolute` là BẮT BUỘC, không phải cho đẹp. Bản đầu dùng
    `--absolute-git-dir` cặp với `--git-common-dir`, mà cái thứ hai trả đường
    TƯƠNG ĐỐI (`.git`) — hai chuỗi không bao giờ bằng nhau, nên checkout chính
    cũng bị coi là worktree phụ và luật chặn đúng cái phiên được phép merge.
    Phép kiểm cũ `test_cho_qua_lenh_binh_thuong[gh pr merge 42 --squash]` bắt
    được; phép kiểm mới KHÔNG, vì nó giả lập chính hàm này.
    """
    try:
        r = subprocess.run(['git', 'rev-parse', '--path-format=absolute',
                            '--git-dir', '--git-common-dir'],
                           capture_output=True, text=True, timeout=5)
        dong = [d.strip() for d in r.stdout.splitlines() if d.strip()]
        if len(dong) != 2:
            return False          # không đọc được -> fail-open
        rieng, chung = (d.replace('\\', '/').rstrip('/') for d in dong)
        return rieng != chung
    except Exception:
        return False


def _cong_trong_lenh(c: str) -> int | None:
    """
    Cổng mà `python -m http.server` trong lệnh này sẽ chiếm, hoặc None.

    Cổng có thể đứng trước hoặc sau các tham số (`http.server 8801 --bind ...`
    và `http.server --bind 127.0.0.1 8801` đều hợp lệ), nên phải quét token chứ
    không khớp một khuôn cố định. Không có số nào thì `http.server` dùng 8000 —
    và đó chính là cổng hay đụng nhau nhất.
    """
    m = re.search(r'\bpython[0-9.]*\s+-m\s+http\.server\b', c)
    if not m:
        return None
    duoi = re.split(r'[;&|]', c[m.end():])[0].split()
    i = 0
    while i < len(duoi):
        t = duoi[i]
        if t.startswith('-'):
            # `--bind X` / `-b X` / `-d X` ăn thêm một token; `--foo=X` thì không.
            if '=' not in t and i + 1 < len(duoi) and not duoi[i + 1].startswith('-'):
                i += 1
        elif t.isdigit():
            return int(t)
        i += 1
    return 8000


def _cong_dang_bi_giu(cong: int) -> bool:
    """
    Có tiến trình nào đang giữ cổng này chưa?

    Thử BUỘC vào cổng, không đọc `netstat`: netstat phải phân tích chuỗi, khác
    nhau giữa Windows và ubuntu, và từng là nguồn kết luận sai ở kho này. Buộc
    được thì cổng trống.

    Không đặt `SO_REUSEADDR`, nhưng ĐỪNG tin rằng đặt vào thì hỏng — tôi từng
    viết thế vào đây mà chưa đo. Đo ngày 16/10/2026 trên Windows, cổng đang
    LISTEN: không đặt thì bị từ chối (WSAEADDRINUSE 10048), đặt vào cũng bị từ
    chối (errno 13). `SO_REUSEADDR` chỉ cho dùng lại cổng ở TIME_WAIT, không
    cho chen vào cổng đang nghe — trên ubuntu cũng vậy. Thứ thật sự làm mất khả
    năng phát hiện là `SO_REUSEPORT` (chỉ có trên Linux), nên đừng thêm nó.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', cong))
        return False
    except OSError:
        return True
    except Exception:
        return False              # fail-open
    finally:
        s.close()


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

    # `git checkout X && git merge main` trong MỘT lệnh: hook đọc nhánh hiện
    # tại TRƯỚC khi lệnh chạy, nên thấy nhanh='main' và tưởng là đang merge
    # vào main. Đã chặn oan thật ngày 13/10/2026. Nếu lệnh tự chuyển sang
    # nhánh khác thì lúc `git merge` chạy, nhánh không còn là main — nên đọc
    # nhánh đích từ chính lệnh. Chỉ nhận dạng `checkout <tên>` / `switch
    # <tên>` đơn giản; dạng nào không đọc ra được thì GIỮ phán đoán cũ (chặn).
    m_ck = re.search(r'\bgit\s+(?:checkout|switch)\s+(?:-b\s+)?([^\s;&|-][^\s;&|]*)', c)
    if m_ck:
        # Lay nhanh SAU khi chuyen, ca HAI chieu. Ban dau toi chi xu ly
        # chieu main -> nhanh khac (de thoi chan oan), va `git checkout main
        # && git merge feat/abc` — DUNG cai bi cam — lot qua. Chinh phep
        # kiem chot chan bat duoc.
        nhanh = m_ck.group(1)

    m = re.search(r'\bgit\s+push\b([^;&|]*)', c)
    if m:
        duoi = m.group(1)
        len_main = bool(re.search(r'(^|\s)(origin\s+)?(main|HEAD:main|[^\s:]+:main)(\s|$)', duoi))
        khong_neu_dich = not re.search(r'\s\S+\s+\S', duoi.strip() + ' x') and not duoi.strip()
        if len_main or (nhanh == 'main' and not re.search(r'\s\S+\s+\S+', duoi)):
            return (f'Luật đứng của kho: KHÔNG push `main` khi chưa được chủ '
                    f'kho duyệt. (Nhánh hiện tại: `{nhanh or "?"}`. '
                    f'CLAUDE.md mục 1.)')

    # `(?![-\\w])` chứ không phải `\\b`: `\\b` khớp cả `git merge-base` và
    # `git merge-tree` — hai lệnh CHỈ ĐỌC, không merge gì. Ngày 13/10/2026 nó
    # chặn oan `git merge-base main origin/diag/vci-latency`, một lệnh tra cứu.
    #
    # Cũng loại trừ `--abort` / `--continue` / `--quit`: đó là thao tác trên
    # một lần merge ĐANG dở, và `--abort` chính là lệnh để HUỶ nó — chặn nó là
    # giam người ta trong trạng thái merge dở.
    co_merge = re.search(r'\bgit\s+merge(?![-\w])([^;&|]*)', c)
    if nhanh == 'main' and co_merge:
        if not re.search(r'--(abort|continue|quit)\b', co_merge.group(1)):
            return ('Luật đứng của kho: KHÔNG merge vào `main` khi chưa được '
                    'chủ kho duyệt. Dùng `gh pr merge` sau khi được duyệt. '
                    '(CLAUDE.md mục 1.)')

    # --- 3. Chỉ checkout chính được merge PR -------------------------------
    #
    # Ngày 16/10/2026 có NĂM phiên chạy song song trên kho này, mỗi phiên một
    # worktree, và chúng tự sinh ra nhau. `main` nhảy 5 lần trong một buổi
    # (#96 → #97 → #98 → commit dữ liệu → #100). Hệ quả không phải xung đột
    # tệp — worktree cô lập chuyện đó — mà là: CI xanh trên `main` CŨ không nói
    # gì về `main` MỚI, và chính tôi đã so các nhánh với `main` cục bộ đã lùi
    # 1 commit rồi rút ra bộ số vô nghĩa.
    #
    # Dồn quyền merge về một chỗ thì `main` chỉ nhảy ở nơi biết nó đang nhảy.
    # Chặn `gh pr merge`, KHÔNG chặn `gh pr create/view/checks` — các phiên phụ
    # vẫn mở PR và đọc cổng bình thường.
    if re.search(r'\bgh\s+pr\s+merge\b', c) and _trong_worktree_phu():
        return ('Chỉ checkout CHÍNH được merge PR — đây là worktree phụ. Mở PR '
                'ở đây thì được, còn merge thì để phiên ở checkout chính làm, '
                'sau khi `git fetch` và kiểm nhánh có đứng trên `origin/main` '
                'hiện tại. (CLAUDE.md mục 1.)')

    # --- 4. Hai máy chủ cùng một cổng --------------------------------------
    #
    # CLAUDE.md mục 7: hai `python -m http.server` cùng cổng trên Windows chia
    # yêu cầu BẤT ĐỊNH và làm treo bộ đo bố cục. Với nhiều phiên song song thì
    # mặc định 8000 gần như chắc chắn đụng.
    cong = _cong_trong_lenh(c)
    if cong is not None and _cong_dang_bi_giu(cong):
        return (f'Cổng {cong} đã có tiến trình khác giữ. Hai `http.server` cùng '
                f'cổng chia yêu cầu bất định và làm TREO bộ đo bố cục — chọn '
                f'cổng khác, hoặc dừng tiến trình đang giữ. (CLAUDE.md mục 7.)')

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

    # Dời tiến trình về ĐÚNG THƯ MỤC LỆNH SẼ CHẠY trước khi hỏi git.
    #
    # `_nhanh_hien_tai()` và `_trong_worktree_phu()` chạy `git` trong thư mục
    # làm việc của tiến trình này. Hook khai trong `.claude/settings.json` là
    # `python "$CLAUDE_PROJECT_DIR/scripts/claude_guard.py"`, và
    # `$CLAUDE_PROJECT_DIR` ĐỨNG YÊN ở gốc dự án — tức CHECKOUT CHÍNH — còn
    # `cwd` của payload đi theo Claude (vào worktree, hay sau `cd`). Nên trong
    # mọi worktree phụ, cổng chặn đọc trạng thái git của NGƯỜI KHÁC.
    #
    # Hỏng cả hai chiều, và đo được cả hai ngày 16/10/2026:
    #
    #   - Chặn oan. Checkout chính đứng ở `main`, phiên làm việc ở worktree
    #     trên `claude/focused-yalow-414838` (PR #102): `git merge origin/main`
    #     — ĐÚNG việc CLAUDE.md mục 1 dặn phải làm — bị chặn hai lần liên tiếp
    #     với lý do "KHÔNG merge vào `main`". Lách được bằng `git checkout
    #     <nhánh> && git merge <ref>`, nhưng đó là lách, không phải sửa.
    #   - Để lọt. `_trong_worktree_phu()` hỏi checkout chính, thấy "không phải
    #     worktree phụ", nên `gh pr merge` trong worktree phụ KHÔNG bị chặn gì
    #     cả — luật mục 13 mất tác dụng ở đúng nơi nó cần có.
    #
    # Dời cả tiến trình thay vì truyền tham số xuống từng hàm: hook sống vài
    # chục mili giây, và cách này không bỏ sót chỗ đọc git nào — kể cả chỗ
    # thêm vào sau này. Không có khoá `cwd` thì giữ nguyên hành vi cũ.
    noi_chay = data.get('cwd')
    if noi_chay:
        try:
            os.chdir(noi_chay)
        except Exception:
            pass          # fail-open: không dời được thì đo bằng thước cũ

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
