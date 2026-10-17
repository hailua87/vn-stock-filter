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
  trước khi xoá. Dùng `scripts/kiem-nhanh-da-vao-main.sh <nhánh>`, **đừng tự
  đọc `git diff main <nhánh>`**: diff lẫn hai chiều (xem mục 13).
- **Chỉ checkout chính được `gh pr merge`.** Phiên ở worktree phụ mở PR thì
  được, merge thì không — `scripts/claude_guard.py` chặn. Lý do ở mục 13.

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

Nhịp đó tính **chung cho cả máy**, không riêng từng tiến trình: `threading.Lock`
chỉ điều tiết trong một tiến trình, nên nhiều phiên song song từng biến trần
thành 1 lượt/giây **nhân** số phiên (mục 13). Nay có thêm khoá tệp ở
`%TEMP%/vn-stock-filter-nhip.lock`. Tắt bằng `SOURCE_CROSS_PROCESS_PACE=0` — chỉ
để **đo lại hành vi cũ bằng cùng một thước**, không phải để chạy nhanh hơn.
Khoá **tệp** chứ không phải tệp PID là cố ý: hệ điều hành nhả khoá khi tiến
trình chết, nên không có khoá mồ nào treo được lượt chạy.

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
- **Test bị TREO cũng không phải test đỏ.** Phá bỏ chặn trên
  `min(..., MIN_INTERVAL)` ở nhịp gọi nguồn làm hàm ngủ 86.400 giây: phép kiểm
  không đỏ, nó đứng — và trên CI thì nó đốt trọn `timeout-minutes` rồi báo một
  lỗi không liên quan tới nguyên nhân. Phép kiểm nào có thể chờ vô hạn thì phải
  chạy trong **tiến trình con có trần thời gian**, và coi hết giờ là **đỏ**.
- **Đo khoảng cách giữa các lượt, đừng đo tổng thời gian tiến trình.** Khởi động
  Python trên Windows mất ~2 giây (phải nạp `requests`); đo nhịp 0,25 giây bằng
  tổng thời gian tiến trình thì thước gần như chỉ đo khởi động. Hai phép kiểm
  nhịp đã đỏ oan vì chuyện này.
- Trước khi kết luận, **đo trước và sau** bằng cùng một thước. Và kiểm chính
  thước đo: đã có lần thước báo ba lỗi giả `1:1` vì bỏ kênh alpha khi trộn màu
  nền, và một lần khác kết luận sai vì quên `deviceScaleFactor: 3`.
- **Đo lại trang web sau khi sửa: phải đổi CỔNG, không phải nạp lại.**
  `index.html?v=123` không giải quyết gì — thẻ `<script src="app.js">` giữ
  nguyên URL nên trình duyệt dùng lại bản trong cache. Ngày 13/10/2026 việc này
  làm tôi kết luận sai **hai lần liên tiếp** trên cùng một bản sửa: lần đầu
  "bản sửa không có tác dụng" (trang đang chạy mã cũ), lần sau "trang vẫn chạy
  bình thường" (trong khi `app.js` đã lỗi cú pháp và cả trang chết — cache che
  mất). Đổi cổng là đổi origin, tức đổi cache. Kiểm chứng rẻ nhất:
  `fetch('/app.js?x='+Date.now())` rồi so với `renderRow.toString()` của trang
  đang chạy — lệch nhau nghĩa là đang đo bản cũ.
- **Một tệp bị `.gitignore` vẫn đổi được kết luận của bộ test.** Lượt chạy
  `run_valuation.py` tại máy ghi ra `backend/data/peer_multiples.json`, và
  `methods_pe.py` với `methods_ev_ebitda.py` đọc nó **trong lúc chạy test**. CI
  không bao giờ có tệp đó, nên bộ test đỏ **chỉ ở máy người phát triển, trên mã
  nguồn hoàn toàn sạch** — người gặp phải sẽ đi tìm lỗi trong thay đổi của
  mình. Đo 16/10/2026: quét 75 nội dung peer DB, **18 nội dung** làm ba phép
  kiểm định giá đỏ. Nay fixture `autouse` `_co_lap_peer_db` ở
  `backend/conftest.py` trỏ `PEER_DB_PATH` sang `tmp_path` cho mọi phép kiểm,
  và `backend/tests/test_peer_db_co_lap.py` canh nó. Thêm đường dẫn cứng nào
  vào `backend/data/` thì hỏi ngay hai câu: **CI có tệp này không**, và **test
  có đọc nó không**. Nới ngưỡng cho tới khi xanh không gỡ được chuyện này —
  beta 2,7 chỉ hạ từ 18/75 xuống 1/75.
- **`node --check web/*.js` trước khi tin bộ test Python.** Toàn bộ 1312 phép
  kiểm từng xanh trong khi trang web chết hoàn toàn vì một dấu backtick trong
  template literal. Nay `backend/tests/test_web_cu_phap_js.py` canh, và ci.yml
  ghim `actions/setup-node@v4` để phép kiểm đó không phải bỏ qua.

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

Bộ đo từng không tất định (báo lỗi khác nhau giữa hai lượt cùng mã nguồn). **Năm**
nguồn đã gỡ: ngưỡng dải nhìn thấy quá lỏng, mẫu ổn định chỉ lấy lớp của trang
scanner, đọc `document.fonts.status` thay vì đợi `fonts.ready`, ghim chữ động
**sau** khi ổn định rồi đo ngay, và — nguồn thứ năm, 14/10/2026 — **font web
không tải được mà bộ đo vẫn đo**.

Nguồn thứ năm đáng đọc kỹ vì nó qua được cả hai cách kiểm font đầu tiên:

- `fonts.ready` và `fonts.status === 'loaded'` **vẫn thoả mãn** khi bảng kiểu
  Google Fonts không về được — không có `@font-face` nào thì không có gì đang
  chờ, nên `ready` giải quyết ngay và cả trang render bằng **phông dự phòng**.
- `document.fonts.check('12px Inter')` **cũng trả `true`**, vì nó hỏi "render
  được không" chứ không hỏi "font này có đang dùng không": danh sách font luôn
  kết thúc bằng một phông dự phòng sẵn có.

Phông dự phòng rộng hơn Inter **~10%**, nên mọi số đo bố cục đều lệch. Đo thật,
hai lượt CI trên **cùng** mã nguồn (PR #92 lần đầu và lần chạy lại):

```
đỏ  : tabsScrollWidth 934   tabWidths [112,124,107,121,95,90,113,143]
xanh: tabsScrollWidth 848   tabWidths [103,113,96,109,86,82,103,127]
```

Dải tab nở 86px, topbar tràn, bốn nhãn vỡ dòng. Cổng báo lỗi về **trang**, trong
khi lỗi ở **mạng**.

Nay `check.mjs` hỏi đúng câu — trong `FontFaceSet` có `@font-face` nào của họ
font đó **đã tải xong** không — và nếu hết 10s vẫn không có thì ghi `thieuFont`,
còn `diff.mjs` **từ chối so sánh** và thoát mã 2. Một lượt đo bằng phông dự
phòng không được phép thành "phát sinh lỗi mới", cũng không được phép thành
"sạch": nó không nói gì về trang cả.

Nếu thấy nó đỏ bất thường, chạy lại hai lượt và **so hai lượt với nhau** trước
khi đổ cho thay đổi của mình — đó chính là cách tìm ra nguồn thứ năm.

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
| Làm beta có ý nghĩa cho mã thanh khoản thấp | `docs/beta-weak-regression.md` |
| Tích hợp TradingAgents (multi-agent LLM) | `docs/tradingagents-khong-tich-hop.md` |

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

---

## 12. Đọc `beta_coverage` cho đúng — BA ô, không phải hai

`real` nghĩa là "tính được **và** khác 1,0 có ý nghĩa thống kê (khoảng 95%)",
không phải "tính được". Ô `weak` là tính được mà khoảng tin cậy chứa 1,0 — đã
rơi về 1,0, và bị trừ độ tin cậy **y như** `fallback`.

Lượt 11/10/2026 báo `real: 84, fallback: 0` và nghe như xong việc. Đo lại bằng
phép kiểm ý nghĩa: **45% rổ** không phân biệt được với 1,0. Đừng đọc `real`
tách khỏi `median_r_squared` — R² trung vị ~0,14 nói rõ hơn nhiều.

Hai bẫy khi sửa chỗ này:

- Phép kiểm chạy trên `beta_raw`, **không** trên beta đã điều chỉnh Blume.
  Blume (`0,67·raw + 0,33·1,0`) vốn đã co ước lượng về 1,0; kiểm trên giá trị
  đã co thì gần như mã nào cũng "yếu".
- `std_error` phải lưu **4 chữ số**. Ba chữ số thì chênh lệch do bậc tự do
  (`n−2` so với `n`, ~1%) bị làm tròn nuốt mất, và không ai kiểm lại được công
  thức bằng chính đầu ra nữa.

Thiếu khoá `weak` thì đếm vào ô **yếu** — mặc định bi quan ở cả ba chỗ
(`methods_pb_roe`, `_beta_info`, `_tong_hop_beta`). Mặc định ngược lại nghĩa là
một nguồn beta mới quên gắn cờ sẽ lặng lẽ làm đẹp số liệu.

Chi tiết và phần đã khảo: `docs/beta-weak-regression.md`.

---

## 13. Nhiều phiên chạy song song — chỗ đụng KHÔNG phải tệp

Ngày 16/10/2026 đo được **năm phiên** làm việc cùng lúc trên kho này, bốn còn
chạy, và chúng **tự sinh ra nhau** theo chuỗi (`#97` → `#98` + `#99` → `#100` →
…). Không ai quyết định là có năm.

Mỗi phiên nằm trong **worktree riêng**, nên những thứ tưởng sẽ đụng thì không:

| Tài nguyên | Vì sao an toàn |
|---|---|
| Cây làm việc, index, `git checkout` | worktree riêng, không chạm nhau |
| `backend/data/cache`, `peer_multiples.json` | bị `.gitignore` nên **không** được sao sang worktree mới — đo được 591 / 200 / 1 / 1 / 0 tệp, tức năm bản riêng |
| `web/data/` khi chạy thử pipeline | mỗi worktree một bản |

Cái đụng nhau thật:

1. **`main` chạy dưới chân.** Nó nhảy **5 lần** trong một buổi. `main` cục bộ
   lùi 1 commit **hai lần trong mười phút** — và một lần tôi so các nhánh với
   `main` cũ rồi rút ra bộ số vô nghĩa. Hệ quả nặng hơn: **CI xanh trên `main`
   cũ không nói gì về `main` mới.** Vì vậy chỉ checkout chính được merge, và
   phải `git fetch` trước khi kết luận bất cứ điều gì về nhánh.
2. **Nhịp gọi nguồn.** `MIN_INTERVAL` do `threading.Lock` giữ, tức **mỗi tiến
   trình một trần**. Bốn phiên là 4 lượt/giây vào Vietcap/KBS, gấp bốn mức mục 3
   cố ý chọn. Và vì cache không dùng chung, mỗi worktree tải lại từ đầu — bản
   591 tệp với bản 200 tệp là hai lần tải riêng cùng một dữ liệu. Nay có khoá
   liên tiến trình (mục 3).
3. **Cổng `http.server` là cấp máy**, không phải cấp worktree — mục 7. Cổng
   chặn nay thử buộc vào cổng trước khi cho chạy. Đừng thêm `SO_REUSEADDR` vào
   phép thử đó, và **cũng đừng tin** rằng thêm vào thì hỏng: đã đo 16/10/2026,
   cổng đang LISTEN từ chối cả hai cách (10048 và errno 13). Thứ thật sự làm mất
   khả năng phát hiện là `SO_REUSEPORT`.
4. **Hai PR đụng cùng một tệp.** `#99` tạo `test_peer_db_co_lap.py`, `#97` sửa
   chính tệp đó; `merge-tree` giữa `main` và nhánh `#99` **vẫn báo xung đột** sau
   khi cả hai đã merge. Không mất gì (bản `main` mới hơn), nhưng thứ tự merge
   ngược lại thì một bên bị ghi đè lặng lẽ.
5. **Thư mục memory dùng chung** cho mọi phiên của kho này — hai phiên ghi cùng
   một tệp thì người ghi sau thắng, không cảnh báo gì.

**`git diff main <nhánh>` là thước SAI** cho câu hỏi "nhánh đã vào `main`
chưa": nó lẫn hai chiều, nhánh đi sau `main` cũng hiện ra "dòng thêm". Dùng
`scripts/kiem-nhanh-da-vao-main.sh` — nó hợp cây thử và chỉ báo sạch khi cây
không đổi; xung đột thì **từ chối kết luận** (thoát 2) thay vì đoán, cùng kiểu
`diff.mjs` từ chối so sánh khi thiếu font (mục 8).

**CI xanh là xanh cho MỘT commit — hỏi xanh cho commit NÀO.** Luật "chỉ checkout
chính được merge" không tự lo được chuyện này. Lượt merge #103 (16/10/2026): PR
mở ra, CI xanh 4 cổng, nhưng trong lúc chờ thì `#100` vào `main`, nên nhánh lùi
1 commit và **4 cổng xanh kia là xanh trên nền chưa có `#100`**. Đưa `main` vào
nhánh rồi chạy lại: 1471 → **1479** phép kiểm. Vì vậy trước mỗi lần merge:
`git fetch`, rồi `git rev-list --count <nhánh>..origin/main` phải ra **0**;
không ra 0 thì `git merge main` và chờ CI chạy lại.

**Và đừng tin con số CI mà không hỏi nó thuộc commit nào.** Cùng lượt đó,
`mcp__ccd_pr__get_status` của ứng dụng vẫn báo `4 passing / 0 pending` **sau
khi** commit hợp nhất đã được đẩy lên — nó đọc từ bộ đệm, còn `gh pr checks`
báo đúng là `test` và `sources-live` đang chạy lại. Tin con số đệm đó là merge
một nhánh chưa ai kiểm trên nền thật. Kiểm chứng rẻ nhất, cùng tinh thần với
mẹo `fetch('/app.js?x='+Date.now())` ở mục 6:

```
gh pr view <số> --json headRefOid --jq '.headRefOid[0:7]'   # so với
git rev-parse --short HEAD
```

Lệch nhau nghĩa là đang đọc trạng thái của commit khác.

**Cổng vắng mặt chưa chắc là cổng bị bỏ.** `kiem` (`viewport-check.yml`) lọc
`paths: web/**`, nên PR không đụng `web/**` thì nó **không xuất hiện trong danh
sách checks** — khác hẳn với "đã chạy và bỏ qua". Trước khi kết luận một cổng
không chạy, đọc `paths`/`paths-ignore` của **chính** workflow đó, và đọc đúng
**sự kiện**: trong `ci.yml`, `**/*.md` chỉ bị bỏ qua ở `push`, **không** ở
`pull_request` — nên một PR chỉ sửa tài liệu vẫn chạy `test` và `sources-live`.
Tôi vừa viết ngược điều này vào đây rồi phải sửa: hai khối `paths-ignore` của
hai sự kiện **không giống nhau**, đừng đọc một khối rồi suy ra khối kia.
