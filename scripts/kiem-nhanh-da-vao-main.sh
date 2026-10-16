#!/usr/bin/env bash
#
# Nhánh này đã vào `main` chưa? Trả lời bằng NỘI DUNG, không bằng lịch sử.
#
# Vì sao cần: dự án dùng squash merge, nên `git branch --merged` không nhận ra
# nhánh đã merge (CLAUDE.md mục 1). Câu dặn "kiểm bằng nội dung, diff với main
# rỗng" đúng, nhưng `git diff main <nhánh>` LẪN HAI CHIỀU: nhánh nào đi sau
# `main` cũng hiện ra "dòng thêm". Ngày 16/10/2026 tôi đọc đúng cái nhiễu đó và
# tưởng bốn nhánh còn nội dung chưa merge; thực ra cả bốn đã sạch, chỉ là `main`
# đã đi trước chúng.
#
# Thước đúng là hợp cây thử: hợp nhánh vào `main` mà cây kết quả KHÔNG đổi thì
# nhánh không mang thêm gì.
#
#   dùng:  scripts/kiem-nhanh-da-vao-main.sh <nhánh> [gốc]
#   gốc mặc định `origin/main` (và sẽ `git fetch` trước — `main` cục bộ hay bị
#   lùi vài commit, hôm 16/10 nó lùi hai lần trong mười phút).
#
#   thoát 0 = sạch, xoá được
#   thoát 1 = còn nội dung `main` chưa có
#   thoát 2 = xung đột hoặc không so được, phải xem bằng mắt
set -u

nhanh="${1:-}"
goc="${2:-origin/main}"
if [ -z "$nhanh" ]; then
  echo "dùng: $0 <nhánh> [gốc, mặc định origin/main]" >&2
  exit 2
fi

# Chỉ fetch khi gốc là ref của remote. Nhờ vậy phép kiểm chạy được trên kho tạm
# không có remote nào.
case "$goc" in
  origin/*) git fetch -q origin || echo "  (fetch lỗi, đang dùng ref cục bộ)" >&2 ;;
esac

for r in "$nhanh" "$goc"; do
  if ! git rev-parse --verify -q "$r" >/dev/null; then
    echo "không có ref: $r" >&2
    exit 2
  fi
done

cay_goc="$(git rev-parse "$goc^{tree}")"
ra="$(git merge-tree --write-tree "$goc" "$nhanh" 2>&1)"
ma=$?
cay_hop="$(printf '%s\n' "$ra" | head -1)"

if [ "$ma" -gt 1 ]; then
  echo "KHÔNG SO ĐƯỢC  $nhanh"
  printf '%s\n' "$ra" | sed 's/^/    /'
  exit 2
fi

if [ "$ma" -eq 1 ]; then
  echo "XUNG ĐỘT  $nhanh  — hợp vào $goc không tự động được."
  echo "    Xem bằng mắt. Xung đột KHÔNG có nghĩa là mất việc: thường là nhánh"
  echo "    giữ bản cũ của cùng một đoạn mà \`$goc\` đã viết lại."
  git diff "$cay_goc" "$cay_hop" --stat 2>/dev/null | sed 's/^/    /'
  exit 2
fi

if [ "$cay_hop" = "$cay_goc" ]; then
  echo "SẠCH  $nhanh  — hợp vào $goc không đổi gì. Xoá được."
  exit 0
fi

echo "CÒN NỘI DUNG  $nhanh  — $goc chưa có những thứ này:"
git diff "$cay_goc" "$cay_hop" --stat | sed 's/^/    /'
exit 1
