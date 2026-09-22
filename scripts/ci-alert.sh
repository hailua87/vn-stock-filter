#!/usr/bin/env bash
# Cảnh báo khi workflow thất bại, tự đóng khi chạy lại thành công.
#
#   ci-alert.sh fail "<tên workflow>" ["<chi tiết>"]   # step: if: failure() || cancelled()
#   ci-alert.sh ok   "<tên workflow>"                  # step: if: success()
#
# Mỗi workflow có tối đa MỘT issue mở (nhãn `workflow-failure`, tiêu đề cố định
# "[ci] <tên> thất bại"): hỏng liên tiếp thì comment vào issue đó, không mở mới.
#
# Vì sao cần, bên cạnh data-freshness-alert: chuông độ tươi chỉ canh
# web/data/latest.json và cho phép trễ 1 phiên. weekly-valuation đỏ 4 tuần liền
# (30/08–20/09) và daily-scan đỏ 3 run (21–22/09) mà không có issue nào.
#
# Script KHÔNG BAO GIỜ làm hỏng workflow: lỗi gọi `gh` chỉ in ::warning::, vì
# một run thành công không được đỏ chỉ vì không đóng được issue.
set -uo pipefail

MODE="${1:-}"
NAME="${2:-}"
DETAIL="${3:-}"
LABEL="workflow-failure"
TITLE="[ci] ${NAME} thất bại"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
NOW_ICT="$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M ICT')"

if [ -z "$NAME" ] || { [ "$MODE" != fail ] && [ "$MODE" != ok ]; }; then
  echo "Dùng: ci-alert.sh fail|ok \"<tên workflow>\" [\"<chi tiết>\"]" >&2
  exit 2
fi

warn() { echo "::warning::ci-alert: $*"; }

# Issue đang mở của đúng workflow này (so khớp tiêu đề chính xác)
OPEN="$(gh issue list --label "$LABEL" --state open --limit 50 \
          --json number,title --jq ".[] | select(.title == \"$TITLE\") | .number" \
        2>/dev/null | head -n1)" || OPEN=""

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

if [ "$MODE" = fail ]; then
  {
    echo "**${NAME}** thất bại hoặc bị hủy lúc ${NOW_ICT}."
    echo ""
    echo "- Run: ${RUN_URL}"
    echo "- Sự kiện: \`${GITHUB_EVENT_NAME:-?}\` · commit \`${GITHUB_SHA:0:7}\`"
    [ -n "$DETAIL" ] && echo "- Chi tiết: ${DETAIL}"
    echo ""
    echo "Issue này tự đóng khi ${NAME} chạy lại thành công."
  } > "$BODY"

  if [ -n "$OPEN" ]; then
    gh issue comment "$OPEN" --body-file "$BODY" >/dev/null \
      && echo "::error::${NAME} thất bại — đã comment vào issue #${OPEN}" \
      || warn "không comment được vào issue #${OPEN}"
  else
    gh label create "$LABEL" --color D93F0B \
      --description "Workflow CI thất bại, tự đóng khi chạy lại thành công" >/dev/null 2>&1 || true
    gh issue create --title "$TITLE" --label "$LABEL" --body-file "$BODY" >/dev/null \
      && echo "::error::${NAME} thất bại — đã mở issue mới" \
      || warn "không mở được issue"
  fi
  exit 0
fi

# MODE = ok
if [ -z "$OPEN" ]; then
  echo "ci-alert: không có issue mở cho ${NAME}"
  exit 0
fi
{
  echo "✅ **${NAME}** đã chạy lại thành công lúc ${NOW_ICT}."
  echo ""
  echo "- Run: ${RUN_URL}"
} > "$BODY"
gh issue comment "$OPEN" --body-file "$BODY" >/dev/null || warn "không comment được vào issue #${OPEN}"
gh issue close "$OPEN" --reason completed >/dev/null \
  && echo "ci-alert: đã đóng issue #${OPEN}" \
  || warn "không đóng được issue #${OPEN}"
exit 0
