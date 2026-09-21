"""
Push dữ liệu của bot khi remote vừa đổi (audit F9) — chạy git thật.

Tình huống: bot sinh dữ liệu mới; trong lúc đó remote nhận một commit code
và một commit dữ liệu khác (lần chạy trước, hoặc người sửa tay).
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / 'scripts' / 'commit-bot-data.sh').as_posix()
BASH = shutil.which('bash')
pytestmark = pytest.mark.skipif(BASH is None, reason='cần bash')

ENV = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
       'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t', 'BRANCH': 'main'}


def git(cwd, *args, check=True):
    return subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=cwd, env=ENV,
                          check=check, capture_output=True, text=True, encoding='utf-8')


def write(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def read_remote(remote, rel):
    return git(remote, 'show', f'main:{rel}').stdout


@pytest.fixture
def repos(tmp_path):
    """remote (bare), `other` = người/lần chạy khác, `bot` = workflow đang chạy."""
    remote, other, bot = tmp_path / 'remote.git', tmp_path / 'other', tmp_path / 'bot'
    git(tmp_path, 'init', '-q', '--bare', '-b', 'main', str(remote))
    git(tmp_path, 'clone', '-q', str(remote), str(other))
    write(other, '.gitattributes', 'web/data/** merge=ours\n')
    write(other, 'web/data/latest.json', '{"run": "cu"}\n')
    write(other, 'app.py', 'v = 1\n')
    git(other, 'add', '-A'); git(other, 'commit', '-qm', 'init'); git(other, 'push', '-q', 'origin', 'main')
    git(tmp_path, 'clone', '-q', str(remote), str(bot))

    # Bot sinh dữ liệu mới (chưa commit)
    write(bot, 'web/data/latest.json', '{"run": "bot-moi"}\n')
    # Trong lúc đó remote nhận commit code + commit dữ liệu khác
    write(other, 'app.py', 'v = 2  # code moi\n')
    write(other, 'web/data/latest.json', '{"run": "khac"}\n')
    write(other, 'web/data/archive/2026-09-20.json', '{}\n')
    git(other, 'add', '-A'); git(other, 'commit', '-qm', 'code + data'); git(other, 'push', '-q', 'origin', 'main')
    return remote, other, bot


def run_script(bot, *paths, msg='chore(data): test'):
    return subprocess.run([BASH, SCRIPT, msg, *paths], cwd=bot, env=ENV,
                          capture_output=True, text=True, encoding='utf-8')


def test_old_rebase_with_merge_ours_drops_fresh_data(repos):
    """Tái hiện F9: cách cũ push thành công nhưng dữ liệu của bot biến mất."""
    remote, _, bot = repos
    git(bot, 'config', 'merge.ours.driver', 'true')
    git(bot, 'add', 'web/data'); git(bot, 'commit', '-qm', 'bot data')
    git(bot, 'pull', '-q', '--rebase', 'origin', 'main')
    git(bot, 'push', '-q', 'origin', 'HEAD:main')
    assert read_remote(remote, 'web/data/latest.json') == '{"run": "khac"}\n'  # bot-moi mất


def test_script_keeps_remote_code_and_publishes_fresh_data(repos):
    remote, _, bot = repos
    r = run_script(bot, 'web/data/')
    assert r.returncode == 0, r.stdout + r.stderr
    assert read_remote(remote, 'web/data/latest.json') == '{"run": "bot-moi"}\n'
    assert read_remote(remote, 'app.py') == 'v = 2  # code moi\n'
    # file dữ liệu remote có thêm vẫn được giữ
    assert read_remote(remote, 'web/data/archive/2026-09-20.json') == '{}\n'
    log = git(remote, 'log', '--format=%s', 'main').stdout.splitlines()
    assert log[0] == 'chore(data): test' and 'code + data' in log


def test_script_never_commits_outside_declared_paths(repos):
    remote, _, bot = repos
    write(bot, 'app.py', 'v = 999  # bot lo sua code\n')
    r = run_script(bot, 'web/data/')
    assert r.returncode == 0, r.stdout + r.stderr
    assert read_remote(remote, 'app.py') == 'v = 2  # code moi\n'


def test_script_no_change_makes_no_commit(repos):
    remote, other, bot = repos
    write(bot, 'web/data/latest.json', '{"run": "khac"}\n')  # trùng remote
    before = git(remote, 'rev-parse', 'main').stdout
    r = run_script(bot, 'web/data/')
    assert r.returncode == 0 and 'Không có thay đổi' in r.stdout
    assert git(remote, 'rev-parse', 'main').stdout == before


def test_script_handles_multiple_paths_including_missing(repos):
    remote, _, bot = repos
    write(bot, 'backend/data/snapshots/fundamentals_registry.json', '{"schema": 1}\n')
    r = run_script(bot, 'web/data/', 'backend/data/snapshots/', 'web/data/khong-ton-tai/')
    assert r.returncode == 0, r.stdout + r.stderr
    assert read_remote(remote, 'backend/data/snapshots/fundamentals_registry.json') == '{"schema": 1}\n'
