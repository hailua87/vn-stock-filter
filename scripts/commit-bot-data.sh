#!/usr/bin/env bash
# Commit + push dữ liệu do bot sinh ra, KHÔNG rebase, KHÔNG merge driver,
# KHÔNG force-push.
#
#   BRANCH=main scripts/commit-bot-data.sh "<message>" <path>...
#
# Vì sao không `git pull --rebase` + `merge=ours` như trước (audit F9):
# khi rebase, "ours" là bản TRÊN REMOTE, "theirs" là commit của bot. Driver
# `merge=ours` (= `true`) giữ "ours" nên hễ có conflict trên file dữ liệu thì
# dữ liệu VỪA SINH RA bị bỏ âm thầm — ngược hẳn ý định "bản mới nhất thắng".
#
# Cách làm ở đây: chụp lại các path dữ liệu, reset về đúng origin/<branch>
# mới nhất, chép chúng đè lên, commit, push. Hệ quả:
#   - Commit code trên remote luôn được giữ (không đụng path nào khác).
#   - Dữ liệu của lần chạy này thắng trên chính các path của nó.
#   - File dữ liệu mà remote có thêm (vd. archive của lần chạy khác) được giữ,
#     vì chỉ chép đè chứ không xóa.
#   - Push hỏng 3 lần thì thất bại; lần chạy sau sinh lại dữ liệu.
set -euo pipefail

MSG="${1:?Thiếu commit message}"
shift
[ "$#" -gt 0 ] || { echo "Thiếu path dữ liệu" >&2; exit 2; }
BRANCH="${BRANCH:?Đặt BRANCH, vd. BRANCH=main}"

PATHS=()
for p in "$@"; do PATHS+=("${p%/}"); done

SNAP="$(mktemp -d)"
trap 'rm -rf "$SNAP"' EXIT
for p in "${PATHS[@]}"; do
  [ -e "$p" ] || continue
  mkdir -p "$SNAP/$(dirname "$p")"
  cp -a "$p" "$SNAP/$(dirname "$p")/"
done

for i in 1 2 3; do
  git fetch --quiet origin "$BRANCH"
  git reset --quiet --hard "origin/$BRANCH"
  cp -a "$SNAP/." .

  for p in "${PATHS[@]}"; do
    [ -e "$p" ] && git add -- "$p"
  done
  if git diff --cached --quiet; then
    echo "ℹ️  Không có thay đổi dữ liệu để commit"
    exit 0
  fi

  # Chốt chặn: chỉ được commit đúng các path đã khai báo
  while IFS= read -r f; do
    ok=0
    for p in "${PATHS[@]}"; do
      case "$f" in "$p"|"$p"/*) ok=1 ;; esac
    done
    if [ "$ok" = 0 ]; then
      echo "❌ Bot đang cố commit file ngoài path đã khai báo: $f" >&2
      exit 1
    fi
  done < <(git diff --cached --name-only)

  git commit --quiet -m "$MSG"
  if git push --quiet origin "HEAD:$BRANCH"; then
    echo "✓ Push thành công ở lần thử $i"
    exit 0
  fi
  echo "⚠️  Lần thử $i thất bại (remote vừa đổi?), thử lại"
  sleep $((i * 5))
done

echo "❌ Không push được sau 3 lần thử. KHÔNG force-push: dữ liệu sẽ được"
echo "   tạo lại ở lần chạy sau, còn commit code trên remote thì không."
exit 1
