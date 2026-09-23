"""
Danh sách đường dẫn bot đẩy lên phải phủ hết những gì run_daily ghi ra.

`scripts/commit-bot-data.sh` chụp các path được liệt kê, `git reset --hard`
về origin, rồi chép lại ĐÚNG những path đó. Tệp không có tên trong danh sách
bị vứt lặng lẽ: workflow vẫn xanh, log vẫn báo "đã ghi", và chỉ phát hiện ra
khi mở web thấy 404.

Đã mắc đúng lỗi này ngày 23/09/2026: `health.json` và `ohlc/latest.json` sinh
ra trên runner rồi biến mất.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import run_daily

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / '.github' / 'workflows' / 'daily-scan.yml'


def pushed_paths() -> list:
    r"""Các đối số web/data/... truyền cho commit-bot-data.sh, đã nối dòng \."""
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'commit-bot-data.sh' in text, 'workflow không còn gọi commit-bot-data.sh'
    # Nối các dòng kết thúc bằng \ để lệnh nhiều dòng thành một dòng
    joined = re.sub(r'\\s*\n\s*', ' ', text)
    # Lay dong LENH, khong phai dong chu thich — ca hai deu chua ten script.
    cmds = [l for l in joined.splitlines() if 'bash scripts/commit-bot-data.sh' in l]
    assert len(cmds) == 1, f'mong doi dung mot lenh push, thay {len(cmds)}'
    return re.findall(r'web/data/\S+', cmds[0])


def test_workflow_still_calls_the_push_script():
    assert pushed_paths(), 'không đọc được đường dẫn nào từ lệnh push'


@pytest.mark.parametrize('out', run_daily.WEB_OUTPUTS)
def test_every_output_is_pushed(out):
    """Mỗi mục trong WEB_OUTPUTS phải được một đối số phủ."""
    pushed = [p.rstrip('/') for p in pushed_paths()]
    want = f"web/data/{out}".rstrip('/')
    covered = want in pushed or any(
        want.startswith(p + '/') for p in pushed
    )
    assert covered, (
        f"run_daily ghi ra {want} nhưng daily-scan.yml không đẩy nó lên. "
        f"Đang đẩy: {pushed}"
    )


def test_pushed_paths_have_no_typos():
    """Đối số trỏ tới thứ không tồn tại trong WEB_OUTPUTS thường là gõ nhầm —
    và gõ nhầm ở đây nghĩa là một tệp thật KHÔNG được đẩy."""
    known = {f"web/data/{o}".rstrip('/') for o in run_daily.WEB_OUTPUTS}
    for p in (x.rstrip('/') for x in pushed_paths()):
        assert p in known, f"{p} không nằm trong run_daily.WEB_OUTPUTS"


def test_outputs_list_is_not_silently_empty():
    assert len(run_daily.WEB_OUTPUTS) >= 7
