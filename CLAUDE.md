# CLAUDE.md — những gì cần biết trước khi sửa kho này

Tài liệu này chỉ ghi thứ **không đọc ra được từ mã nguồn**: các bẫy đã gây lỗi
thật, các quyết định có lý do lịch sử, và kỷ luật làm việc của dự án. Kiến trúc
và chức năng xem `docs/`.

Viết bằng tiếng Việt vì toàn bộ chú thích, lời nhắn commit và giao diện đều
tiếng Việt. Giữ như vậy.

---

## 1. Luật đứng khi làm việc

- **Không merge vào `main`, không push `main` khi chưa được chủ kho duyệt.**
- **Không dùng `git pull --rebase`.** Dùng `git pull --ff-only`. Đưa `main` vào
  nhánh thì `git merge main`.
- Mỗi bước xong thì dừng, đưa `git diff --stat` và kết quả lệnh ra, chờ xác nhận.
- **Bản dò tạm phải nằm ngoài kho và phải xoá sau khi dùng.** Thư mục scratch
  của phiên, không phải `tools/` hay `backend/`.
- Nhánh đã merge thì xoá cả local lẫn origin. Vì dự án dùng **squash merge**,
  `git branch --merged` sẽ **không** nhận ra nhánh — phải kiểm bằng **nội dung**
  (diff với `main` rỗng) trước khi xoá.

---

## 2. Bẫy đơn vị — nguy hiểm nhất ở kho này

Loại lỗi này **không làm test đỏ**. Nó chỉ làm số sai.

| Nơi | Đơn vị |
|---|---|
| Cache OHLCV, `web/data/**` (pipeline kỹ thuật) | **nghìn đồng** — giống bảng điện |
| Báo cáo tài chính (balance sheet, income) | **tỷ đồng** |
| Thuyết minh BCTC (section `NOTE` của VCI) | **đồng** |
| Pipeline định giá | **đồng** — mọi giá phải qua `price_units.quote_to_vnd()` |

`backend/scanner/price_units.py` là nguồn chân lý duy nhất. Đọc docstring của nó
trước khi đụng bất kỳ phép tính nào có tiền.

**Đã gây lỗi thật:**

- `fair_value` (đồng) so với `current_price` (nghìn đồng) → upside +98.600%
- Fixture test ghi giá `30000` vào cache vốn tính bằng nghìn đồng → hai phép
  kiểm âm thầm hỏng với `observations=0` mà vẫn báo `4 passed`
- `bank_npl_coverage` phải đổi đồng → tỷ đồng ở **đúng một chỗ**

---

## 3. Nguồn dữ liệu

`vnstock` và `vnai` **đã bị rút khỏi PyPI** (24–26/09/2026). Dự án gọi thẳng API
Vietcap và KBS qua `backend/scanner/sources/`. Đừng thêm lại hai gói đó.

**`MIN_INTERVAL = 1.0` trong `sources/http.py` là nút thắt.** Hàm chặn nhịp ngủ
khi đang giữ khoá, nên **song song hoá vô ích** — đã đo hai lần (cục bộ và trên
runner), cả hai ra **0,99×**. Nới nó ra nghĩa là đập vào máy chủ của bên thứ ba
mạnh hơn mức mã này cố ý cho phép. Đừng "tối ưu" chỗ này.

Nguồn **không chậm đều** — nó chập chờn theo đợt. Một nhóm mã "chết" có thể chạy
ngon trong 2 giây ở lượt sau. Trước khi kết luận "nguồn chậm", hãy đo.

---

## 4. Ba tầng ngân sách thời gian

```
FETCH_BUDGET_S  <  script tự dừng  <  timeout-minutes của workflow
```

`backend/tests/test_events_deadline.py` đọc **chính tệp workflow** và chốt thứ
tự đó. Nâng một mốc mà quên hai mốc kia thì test đỏ. Đó là cố ý.

---

## 5. Thêm thư mục đầu ra mới? Nhớ ba chỗ

`scripts/commit-bot-data.sh` chụp **đúng các đường dẫn được liệt kê**, rồi
`git reset --hard`, rồi chép lại. **Tệp không nằm trong danh sách bị vứt lặng lẽ.**

Thêm một thư mục dưới `web/data/` thì phải thêm vào:

1. `WEB_OUTPUTS` trong `backend/run_daily.py`
2. hai danh sách verify trong `.github/workflows/daily-scan.yml`
3. danh sách đẩy (gọi `commit-bot-data.sh`) trong cùng workflow

`backend/tests/test_bot_push_paths.py` canh cả ba. Nó đã bắt được lỗi này khi
thêm `ma7_25/`.

`weekly-valuation.yml` cũng có cặp **restore + save** cho `backend/data/cache`.
Thiếu `save` thì mọi thứ lượt chạy ghi vào đó đều bị vứt —
`backend/tests/test_cache_save.py` canh cặp này trên **mọi** workflow.

---

## 6. Kỷ luật đo đạc

Đây là mã phân tích: **nó luôn ra một con số, kể cả khi sai.** Vì vậy:

- **Mỗi test mới phải được phá cho ĐỎ** rồi mới tính là có canh. Đã có nhiều lần
  phá mà không ra đỏ — mỗi lần là một lỗ hổng thật phải vá.
- **Đừng tìm chuỗi trong mã nguồn** để kiểm "hàm này có được gọi không". Dùng
  AST, hoặc viết phép kiểm hành vi. Một lần `inspect.getsource` đã khớp đúng
  chú thích của chính mình và xanh giả.
- **Lấy số từ payload, không lấy từ metadata** khi hai bên lệch nhau.
- **Test bị `skip` là test xanh rỗng** — nó không chứng minh gì.
- Trước khi kết luận, **đo trước và sau** bằng cùng một thước. Và kiểm chính
  thước đo: đã có lần thước báo ba lỗi giả `1:1` vì bỏ kênh alpha khi trộn màu
  nền, và một lần khác kết luận sai vì quên `deviceScaleFactor: 3`.

Có skill `analysis-guard` cho việc này.

---

## 7. Chạy pipeline tại máy — cẩn thận

`run_daily.py`, `run_valuation.py`, `run_quality.py` mặc định ghi thẳng vào
`web/data/` — tức **đè lên dữ liệu production đang phục vụ**.

Luôn dùng `--web-data-dir` trỏ ra thư mục ngoài kho khi chạy thử. Đã lỡ hai lần
trong một phiên.

Chỉ chạy **một** `python -m http.server` mỗi cổng. Hai tiến trình cùng cổng trên
Windows chia yêu cầu bất định và làm treo bộ đo bố cục.

---

## 8. Bộ đo bố cục (`tools/viewport-check`)

Hai mốc chuẩn, không được dùng lẫn: `baseline.json` (Chromium/Windows, đo tại
máy) và `baseline-ci.json` (ubuntu, cổng CI). Font khác thì bề rộng chữ khác.

Chốt lại mốc chuẩn **sau** khi sửa, không phải trước — chốt trước là đóng dấu
chấp nhận luôn cái đang hỏng.

`accepted.json` độc lập với mốc chuẩn: mục đã cân nhắc không sửa vẫn phải được
in ra mỗi lượt.

Bộ đo từng không tất định (báo lỗi khác nhau giữa hai lượt cùng mã nguồn). Bốn
nguồn đã gỡ: ngưỡng dải nhìn thấy quá lỏng, mẫu ổn định chỉ lấy lớp của trang
scanner, đọc `document.fonts.status` thay vì đợi `fonts.ready`, và ghim chữ động
**sau** khi ổn định rồi đo ngay. Nếu thấy nó đỏ bất thường, chạy lại hai lượt và
so hai lượt với nhau trước khi đổ cho thay đổi của mình.

---

## 9. Giao diện

- **5 màu trạng thái giá chỉ dùng cho giá và biến động giá.** Không dùng cho
  badge, tab, chấm, icon, trang trí. Phi-giá thì dùng `--system`, `--focus`,
  `--cat-*`, `--danger`, hoặc thang độ sáng (`--text` → `--text-dim` →
  `--text-mute`). Quy tắc này ghi ở đầu `web/tokens.css`.
- `web/tokens.css` nạp **trước** `styles.css` là **cố ý**: lấy token phi màu
  (`--fs-*`, `--sp-*`, `--r-*`, `--fw-*`), còn màu để `styles.css` ghi đè.
  **Đừng làm theo câu dặn cũ "nạp SAU styles.css"** — làm vậy sẽ lật toàn bộ
  ứng dụng sang nền sáng. Phần màu sáng trong tệp đó là đồ đỗ, chưa dùng được;
  chú thích đầu tệp ghi rõ 4 chỗ còn hỏng tương phản.
- Bảng tín hiệu có **18 cột**. Chiến lược không chấm điểm (MA7×25) dùng **mẫu
  hàng riêng** với số cột khác và ẩn cột tiêu chí — theo khuôn tab Tổng hợp.
- Mỗi `<td>` phải mang đúng lớp `prio-*` của cột tương ứng.

---

## 10. Những gì đã khảo và KHÔNG làm được

Đọc trước khi định làm lại:

| Việc | Tài liệu |
|---|---|
| Mở định giá cho Chứng khoán và Bảo hiểm | `docs/securities-insurance-source-survey.md` |
| Backtest ngưỡng chất lượng | `docs/threshold-backtest.md` |
| Bố cục mobile | `docs/mobile-layout-out-of-scope.md` |
| Hợp đồng sổ theo dõi kết quả | `docs/outcomes-contract.md` |

Ngày 24/09 có một kết luận **sai** là "không nguồn nào có NPL ngân hàng". Nó
sống sót vì không ai ghi lại đã hỏi ở đâu. Dữ liệu nằm ngay trong section `NOTE`
của VCI, và khi tìm đúng chỗ thì mở được 17/17 ngân hàng. **Kết quả âm phải
được ghi kèm "đã hỏi những đâu"**, nếu không nó sẽ bị khảo lại từ đầu — hoặc tệ
hơn, được tin mà không ai kiểm.

---

## 11. Đọc số của sổ theo dõi kết quả cho đúng

`web/data/outcomes/latest.json` so tín hiệu với **giả dược** (vào ngẫu nhiên
cùng rổ, cùng phiên). Luôn đọc hai con số cạnh nhau, đừng đọc riêng con số của
chiến lược.

Khoảng tin cậy là **95%**, bootstrap **khối ngày** (độ dài khối = kỳ quan sát,
lấy mẫu cặp cho cả hai nhóm). Lấy mẫu từng dòng là **sai**: hai lần vào cách
nhau 3 phiên dùng chung 17 ngày giá, và mọi lần vào cùng phiên chịu chung một cú
chuyển động thị trường.

**Khoảng chứa 0 = chưa đủ dữ liệu để nói**, không phải "chiến lược vô dụng" cũng
không phải "có tác dụng". Tính đến 03/10/2026, **không chiến lược nào** trong
bốn cái chứng minh được là khác chọn bừa.
