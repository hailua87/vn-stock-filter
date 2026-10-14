---
name: do-bo-cuc
description: Đo bố cục web của kho này cho đúng — chạy tools/viewport-check, chốt mốc chuẩn, và tránh sáu bẫy đã làm kết luận sai. Dùng khi sửa web/ (CSS, HTML, app.js), khi bộ đo báo đỏ, khi cần chốt lại baseline, khi đo chiều cao/bề rộng phần tử, hoặc khi người dùng nói "đo lại", "kiểm bố cục", "sao nó đỏ", "chốt mốc chuẩn".
---

# Đo bố cục — quy trình và sáu bẫy

Bộ đo ở `tools/viewport-check/`. **README của nó là nguồn chân lý** cho cách
chạy và cách chốt mốc chuẩn — đọc `tools/viewport-check/README.md` trước khi
làm gì. Tệp này không chép lại README; nó ghi **thứ tự việc** và **những bẫy đã
làm kết luận sai thật**, kèm cách kiểm chứng rẻ nhất cho từng bẫy.

Mọi con số dưới đây là **đo thật**, không phải phỏng đoán.

## Thứ tự việc

1. **Đo TRƯỚC khi sửa.** Không có số trước thì không chứng minh được gì sau.
2. Sửa.
3. **Đo lại trên cổng MỚI** (xem bẫy 1).
4. Chạy bộ đo đầy đủ, so với mốc chuẩn: `MOI PHAT SINH` phải **rỗng**.
5. **Chỉ khi bước 4 sạch** mới chốt lại mốc chuẩn (xem bẫy 4).
6. Chạy lượt thứ hai so với mốc vừa chốt — phải **0/0/0**. Không phải thì bộ đo
   bất định, sửa bộ đo trước, đừng chốt.
7. `baseline-ci.json` **phải sinh trong CI** (`workflow_dispatch`), không đoán
   được từ `baseline.json`.

## Bẫy 1 — nạp lại trang KHÔNG lấy mã mới

`index.html?v=123` vô dụng: thẻ `<script src="app.js">` giữ nguyên URL nên
trình duyệt dùng bản trong cache.

Ngày 13/10/2026 bẫy này làm kết luận sai **hai lần liên tiếp trên cùng một bản
sửa**: lần đầu "bản sửa không có tác dụng" (trang chạy mã cũ), lần sau "trang
vẫn chạy bình thường" (trong khi `app.js` đã lỗi cú pháp và cả trang chết).

**Cách làm:** khởi động máy chủ ở **cổng khác** — đổi cổng là đổi origin, tức
đổi cache.

**Kiểm chứng rẻ nhất:**
```js
const t = await (await fetch('/app.js?x=' + Date.now())).text();
t.includes('<chuỗi vừa sửa>') === renderRow.toString().includes('<chuỗi vừa sửa>')
```
Lệch nhau nghĩa là đang đo bản cũ.

## Bẫy 2 — ghim chữ động mà quên gỡ `setInterval`

Nhãn topbar đổi theo giờ. Ghim chúng vào **trường hợp rộng nhất** trước khi đo,
nhưng nếu không gỡ bộ đếm thì ứng dụng **ghi đè lại chuỗi ngắn** ngay sau đó.

Đo sai vì bẫy này: "topbar chỉ cần 1433px, không nhãn nào vỡ" — thật ra 1469px
(chuột) / 1487px (cảm ứng).

```js
const cao = setInterval(() => {}, 99999);
for (let i = 1; i <= cao; i++) clearInterval(i);   // gỡ TRƯỚC khi ghim
```

## Bẫy 3 — font chưa áp mà vẫn đo

Phông dự phòng rộng hơn Inter **~10%**, nên mọi số đo đều lệch. Và **hai cách
kiểm font đầu tiên đều xanh rỗng**:

| cách | vì sao qua được |
|---|---|
| `fonts.ready` / `fonts.status` | Không có `@font-face` nào thì không có gì đang chờ → `ready` giải quyết ngay |
| `document.fonts.check('12px Inter')` | Hỏi "render được không", không hỏi "font này có đang dùng không" |

**Cách đúng:**
```js
[...document.fonts].some(f => /Inter/i.test(f.family) && f.status === 'loaded')
```

`check.mjs` đã canh việc này (ghi `thieuFont`), và `diff.mjs` **từ chối so
sánh** khi gặp — thoát mã **2**, khác mã 1 của "trang có lỗi".

Lỗi này xảy ra **theo từng khung**, không theo cả lượt: mỗi khung mở trang mới
nên lần tải font có thể hỏng riêng. Hai khung trong `baseline-ci.json` từng
được chốt bằng phông dự phòng mà không ai biết.

## Bẫy 4 — chốt mốc chuẩn khi còn đỏ

Chốt trước là **đóng dấu chấp nhận luôn cái đang hỏng**. Đã lỡ một lần:
`cp` kết quả thành `baseline.json` trong khi khung `m-375x667` vẫn báo topbar
135px. Phải `git checkout` mốc chuẩn, sửa, rồi mới chốt lại.

## Bẫy 5 — ngưỡng đo trên Windows không đúng trên Linux

Hai mốc chuẩn tồn tại **đúng vì** bề rộng chữ khác nhau. Một ngưỡng `@media`
rút từ số đo Windows thì lệch vài px trên Linux.

Đo cảm ứng và chuột **riêng**: `@media (pointer: coarse)` đặt `min-width: 44px`
cho `.icon-btn`/`.strat-tab`, làm topbar-right nở 252 → 270. Lấy số **tốn
hơn** (cảm ứng), không phải số chuột.

Không có Docker/WSL tại máy thì đo Linux bằng một lượt `workflow_dispatch` với
mấy khung thử quanh vùng nghi vấn, rồi đọc artifact.

## Bẫy 6 — thước đo quá thô để tách hai trạng thái

Ngưỡng "chiều cao ≤ 60px" **không tách được** một dòng (45px) với hai dòng
(~52px) — biên để chịu khác biệt font đã nuốt mất chênh lệch cần đo.

Tính chất cần canh thường là **cấu trúc**, không phải px: "nhãn ở một dòng" đo
được bằng cách so chiều cao nhãn với `line-height` của **chính nó** — không phụ
thuộc font.

## Khi bộ đo báo đỏ bất thường

**Chạy lại hai lượt và so hai lượt VỚI NHAU** trước khi đổ cho thay đổi của
mình. Năm nguồn bất định đã gỡ được tìm ra đúng theo cách này; nguồn thứ năm
(bẫy 3) lộ ra khi so artifact của hai lần thử trên **cùng** mã nguồn:

```
đỏ  : tabsScrollWidth 934   tabWidths [112,124,107,121,95,90,113,143]
xanh: tabsScrollWidth 848   tabWidths [103,113,96,109,86,82,103,127]
```

Rộng hơn 10% **đều ở mọi tab** → phông dự phòng. Nếu khác nhau **không đều**
thì tìm chỗ khác.

## Vặt nhưng hay mất thời gian

- **Một máy chủ mỗi cổng.** Hai tiến trình cùng cổng trên Windows chia yêu cầu
  bất định và làm treo bộ đo.
- **`deviceScaleFactor: 3`** cho khung mobile. Quên nó thì kết luận sai về chính
  bộ đo (đã xảy ra).
- **Bản dò tạm nằm NGOÀI kho và xoá sau khi dùng** (`CLAUDE.md` mục 1). Riêng
  khung dò thì phải commit mới chạy được trong CI — dùng nhánh dùng-một-lần và
  xoá cả nhánh.
- Phép kiểm hành vi đặt trong `functional.mjs`, chỉ chạy ở khung cần: cổng gác
  theo bề rộng (`vpw <= 768`), không theo cờ `isMobile` của context.
- Bộ đo **đã** bỏ qua `text-overflow: ellipsis` cố ý và chữ ẩn-nhưng-đọc-được
  (hộp 1×1px). Dùng hai kỹ thuật đó không tạo mục mới.
