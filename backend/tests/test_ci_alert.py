"""
scripts/ci-alert.sh — cảnh báo khi workflow thất bại, tự đóng khi hồi phục.

Chạy script thật với một `gh` giả trên PATH: ghi lại mọi lệnh gọi, trả danh
sách issue đang mở theo biến môi trường, và có thể giả lập `gh` hỏng.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / 'scripts' / 'ci-alert.sh').as_posix()
BASH = shutil.which('bash')
pytestmark = pytest.mark.skipif(BASH is None, reason='cần bash')

FAKE_GH = r'''#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
[ -n "${FAKE_GH_FAIL:-}" ] && exit 1
if [ "$1 $2" = "issue list" ]; then printf '%s' "${FAKE_OPEN:-}"; fi
exit 0
'''


@pytest.fixture
def run(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    gh = bindir / 'gh'
    gh.write_text(FAKE_GH, encoding='utf-8', newline='\n')
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / 'gh.log'

    def _run(*args, open_issue='', gh_fail=False):
        log.write_text('', encoding='utf-8')
        env = {**os.environ,
               'PATH': f"{bindir.as_posix()}{os.pathsep}{os.environ['PATH']}",
               'GH_LOG': log.as_posix(), 'FAKE_OPEN': open_issue,
               'GITHUB_REPOSITORY': 'o/r', 'GITHUB_RUN_ID': '42',
               'GITHUB_EVENT_NAME': 'schedule', 'GITHUB_SHA': 'abcdef1234'}
        if gh_fail:
            env['FAKE_GH_FAIL'] = '1'
        # bash trên Windows cần PATH kiểu /c/... — để bash tự chèn thư mục giả lên đầu
        cmd = f'export PATH="$(cygpath -u "{bindir}" 2>/dev/null || echo "{bindir.as_posix()}"):$PATH"; ' \
              f'bash "{SCRIPT}" ' + ' '.join(f'"{a}"' for a in args)
        r = subprocess.run([BASH, '-c', cmd], env=env, capture_output=True,
                           text=True, encoding='utf-8')
        calls = [l for l in log.read_text(encoding='utf-8').splitlines() if l]
        return r, calls
    return _run


def test_first_failure_opens_issue(run):
    r, calls = run('fail', 'Daily scan', 'eod')
    assert r.returncode == 0, r.stdout + r.stderr
    create = [c for c in calls if c.startswith('issue create')]
    assert len(create) == 1
    assert '[ci] Daily scan thất bại' in create[0] and 'workflow-failure' in create[0]
    assert not any(c.startswith('issue comment') for c in calls)


def test_repeated_failure_comments_instead_of_new_issue(run):
    r, calls = run('fail', 'Daily scan', open_issue='21')
    assert r.returncode == 0
    assert any(c.startswith('issue comment 21') for c in calls)
    assert not any(c.startswith('issue create') for c in calls)


def test_success_closes_open_issue(run):
    r, calls = run('ok', 'Weekly Valuation', open_issue='22')
    assert r.returncode == 0
    assert any(c.startswith('issue comment 22') for c in calls)
    assert any(c.startswith('issue close 22') for c in calls)


def test_success_without_open_issue_does_nothing(run):
    r, calls = run('ok', 'Weekly Valuation')
    assert r.returncode == 0
    assert [c.split()[:2] for c in calls] == [['issue', 'list']]


def test_title_is_per_workflow(run):
    """Chỉ tìm issue có đúng tiêu đề của workflow này (so khớp trong --jq)."""
    _, calls = run('fail', 'Weekly Valuation')
    listing = next(c for c in calls if c.startswith('issue list'))
    assert '[ci] Weekly Valuation thất bại' in listing


def test_gh_errors_never_fail_the_workflow(run):
    for mode in ('fail', 'ok'):
        r, _ = run(mode, 'Daily scan', open_issue='5', gh_fail=True)
        assert r.returncode == 0, (mode, r.stdout, r.stderr)


def test_bad_usage_exits_nonzero(run):
    r, _ = run('boom', 'Daily scan')
    assert r.returncode == 2
