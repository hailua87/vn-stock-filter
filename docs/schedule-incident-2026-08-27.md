# Sự cố lịch chạy — 27/08/2026

Ghi lại để lần sau không phải dựng lại từ đầu. **Chưa kết luận.**

## Hiện tượng

Ba khung `schedule` liên tiếp không chạy, tính từ run `schedule` cuối cùng
lúc `2026-08-26T05:33Z`:

| khung (UTC) | workflow | |
| --- | --- | --- |
| 26/08 16:00 | Daily Scan — EOD | không có run |
| 27/08 01:07 | Data Freshness Alert | không có run |
| 27/08 05:05 | Daily Scan — intraday | không có run |

## Những gì vẫn bình thường

- `push` và `workflow_dispatch` chạy tốt — 6 run CI xanh, 3 run dispatch (26/08 tối)
- `actions/permissions` → `enabled: true`
- Cả 4 workflow đều `state: active`
- Repo public → không dính giới hạn phút
- GitHub Status: Actions **operational**, không có sự cố nào về scheduler
- `default_branch` = `main`; cả 4 file workflow có mặt tại `origin/main`,
  cú pháp `on:` hợp lệ, cron đúng như đã commit

Tức không phải: file ngoài default branch, cron sai cú pháp, Actions bị tắt.

## Cập nhật 27/08 13:23Z — một khung đã chạy, RẤT MUỘN

Run `33066152315` — Data Freshness Alert, `event=schedule`, `success`,
chạy lúc **11:09:40Z**. Cron của nó là `7 1 * * *` = 01:07Z.

**Trễ 10 giờ 02 phút.** Không phải bị bỏ — bị hoãn.

Điều này mở cách đọc thứ ba, và hiện nó là cách đọc khớp nhất:

> **(c) Scheduler tồn đọng nghiêm trọng.** Tick không mất, chỉ đến rất muộn.
> Tick đến quá muộn thì có thể bị bỏ hẳn. Giải thích được cả ba khung mà
> không cần giả thiết nào về đăng ký lại hay hỏng hệ thống.

Hai cách đọc ban đầu, ghi lại nguyên trạng:

- **(a) Trễ đăng ký, lành tính.** Alert là workflow mới hoàn toàn, khung đầu
  tiên của một scheduled workflow thường bị bỏ. Daily Scan vừa đổi cron
  khoảng 11 tiếng trước khung 05:05Z.
- **(b) Hỏng có hệ thống ở sự kiện `schedule` cho riêng repo này.**

Bằng chứng 11:09Z **làm yếu cả (a) lẫn (b)**: (b) sai vì `schedule` vẫn hoạt
động; (a) không giải thích được vì sao tick vẫn tới sau 10 tiếng thay vì mất
hẳn.

## Phép thử phân biệt

| khung (UTC) | ý nghĩa |
| --- | --- |
| 27/08 16:05 | Daily Scan EOD. Cron này đã đăng ký từ 26/08 18:02Z, tức hơn 22 tiếng — dư cho mọi độ trễ đăng ký hợp lý. |
| 28/08 01:07 | Data Freshness Alert, chu kỳ kế tiếp. |

Đọc kết quả:

- chạy **đúng giờ** → (a), đã qua
- chạy **muộn nhiều giờ** → (c)
- **không chạy** → (b)

Khi đọc, so `createdAt` với giờ cron chứ đừng chỉ nhìn có/không — đúng cái
bẫy đã suýt làm bỏ sót run 11:09Z.

## Kết quả phép thử 27/08 16:05Z

| | |
| --- | --- |
| run | `33092622907` |
| `createdAt` | `2026-08-27T16:19:27Z` |
| trễ so với cron 16:05Z | **14 phút** |
| kết quả | `completed/success` |

**Kết luận: (a) — scheduler trở lại hành vi thường ngày.**

Ngưỡng 15 phút trong phép thử ban đầu là **tuỳ tiện**, tôi bịa ra chứ không
dựa vào gì. Mốc đúng để so là **dải trễ thực tế của chính repo này**. Các ca
EOD trước đó với cron `0 16`:

```
16:12   16:16   16:18   16:20   16:21     →  dải 12–21 phút
```

14 phút nằm giữa dải đó. Nên đọc chính xác là "quay lại hành vi bình thường",
không phải "đúng giờ tuyệt đối" — GitHub chưa bao giờ giao tick đúng phút cho
repo này. Lần sau đo trễ thì so với dải này, đừng so với một con số tròn.

### Nhưng chưa đóng hồ sơ

Ba khung đã trượt **vẫn không có lời giải**:

```
26/08 16:00Z   Daily Scan EOD
27/08 01:07Z   Data Freshness Alert
27/08 05:05Z   Daily Scan intraday
```

Việc khung 16:05Z chạy bình thường chứng minh `schedule` **hiện đang** hoạt
động — nó không nói gì về việc ba khung kia đã đi đâu.

Và run alert `33066152315` trễ **10 giờ 02 phút** vẫn chỉ có **(c)** giải
thích được. (a) không giải thích nổi một tick tới muộn 10 tiếng thay vì mất
hẳn. Nên (c) chưa bị loại, nó chỉ không áp dụng cho khung 16:05Z.

## Chẩn đoán cũ đã bị bác

Ngày 27/08 tôi kết luận khung 26/08 16:00Z là **"GitHub bỏ tick"** — chuyện
thường của scheduler best-effort. Kết luận đó **không còn đứng vững**: ba
khung liên tiếp trên hai workflow khác nhau không giải thích được bằng nghẽn
lịch, và bằng chứng 11:09Z cho thấy cơ chế là hoãn chứ không phải bỏ.

Commit **`f15fd55`** (dời cron daily-scan sang phút 05) dựa một phần trên
tiền đề đó. Việc dời cron không sai, nhưng **nó không phải cách sửa**, và
tiền đề của nó đã hỏng.

**Khung 26/08 16:00Z xảy ra TRƯỚC `f15fd55`** (commit lúc 26/08 18:02Z, và
lúc đó `.github/workflows/` chưa bị chạm gì trong ngày). Nên ít nhất một
khung hỏng **không** do thay đổi cron gây ra.

## Lỗ dữ liệu

**Giá đóng cửa phiên 26/08 chưa từng được lấy.** Ca EOD 26/08 không chạy, nên
dữ liệu duy nhất của phiên đó là ảnh chụp intraday lúc 12:33 ICT.

`web/data/archive/2026-08-26.json` do bản code cũ ghi (trước khi cổng archive
và `session_date` lên `main`). **File TRUY ĐƯỢC** — nó tự khai đầy đủ:

```
"data_quality": "partial_session"
"session_complete": null
"data_quality_note": "Ghi luc 13:00 ICT — giua phien chieu (13:00-14:45),
   truoc moc chot khoi luong ~15:08. CAN CU DANH DAU LA GIO GHI, khong phai
   phep do. session_complete = null vi parquet cache dung o 2026-08-12 nen
   khong co dong nao cua phien nay de so [...] Khong dung cho backtest."
```

Lỗ thật **chỉ là thiếu bốn khoá**: `session_date`, `run_type`,
`written_at_ict`, `archive_written` — do code cũ ghi, trước khi cổng archive
lên `main`. Thiếu bốn khoá đó không có nghĩa là không truy được nguồn gốc file.

Xác nhận bằng **ba nguồn độc lập**, cùng chỉ một kết luận:

| nguồn | nội dung |
| --- | --- |
| `gh run list` ngày 26/08 | đúng **một** run: `32934495261`, `05:33Z`, `schedule`, success |
| commit dữ liệu duy nhất | `0e5d3b2` — nhãn `[intraday 13:00]` |
| chính `data_quality_note` | `partial_session`, ghi lúc 13:00 ICT |

**Phiên 26/08 không có bản chốt và sẽ không bao giờ có**, vì không ca nào
chạy lại phiên cũ.

> **Bài học.** Lượt trước tôi kết luận metadata rỗng nghĩa sau khi chỉ `get()`
> bốn khoá mình mong đợi, thấy `None` cả bốn, rồi dừng — không in toàn bộ khối
> ra xem. Kiểm sự **vắng mặt** của khoá mình mong đợi không thay được việc đọc
> cái đang **có**. Nhận định sai đó đã kịp vào doc này và nằm trên `main` một
> ngày.

Hệ quả cho chuông báo: sáng 27/08 `latest.json` mang phiên 26/08, đúng bằng
phiên kỳ vọng → trễ 0 phiên → chuông im, hợp lệ. Nhưng nó im về một phiên chỉ
có dữ liệu nửa vời. Chuông đo **ngày phiên**, không đo **chất lượng phiên**.

## Việc còn treo

- [x] Khung 27/08 16:05Z — đã đọc, kết quả (a). Xem mục trên.
- [ ] Khung 28/08 01:07Z — nửa còn lại của phép thử, chưa tới
- [x] **Phiên 26/08 KHÔNG lấy lại được.** `daily-scan` luôn quét phiên HIỆN
      TẠI: `session_date` lấy từ `df_all['Date'].max()`, và `run_daily.py`
      không có tham số nào chọn phiên cũ (12 tham số CLI, không cái nào là
      ngày). Chạy tay bây giờ chỉ ghi đè bằng dữ liệu phiên mới nhất.

      Giá đóng cửa 26/08 nằm trong cache OHLCV của runner — nến ngày 26/08 đã
      chốt hẳn khi ca EOD 27/08 fetch trọn 500/500 mã. (Chưa xác minh trực
      tiếp: `gh cache list` chỉ trả siêu dữ liệu, muốn đọc nội dung phải chạy
      một job.) Nhưng **file archive của phiên đó vĩnh viễn là bản 13:00 ICT.**

      `backend/rebuild_web_data.py` KHÔNG phải lối thoát, dù nghe có vẻ đúng
      việc: nó sinh lại dashboard offline từ cache, nhưng giới hạn ghi ngay
      trong docstring là "ngày dữ liệu là phiên cuối trong cache" — tức nó
      cũng bám phiên mới nhất, không nhắm được vào một phiên chọn trước. Output
      của nó còn bị đánh dấu `metadata.offline_rebuild = true`.
- [x] **`f15fd55` — GIỮ.** Ca EOD 27/08 chạy sạch với cron mới: `16:19:27Z`,
      trễ 14 phút (trong dải 12–21 phút bình thường của repo), fetch trọn
      **500/500 mã** trong 1524.8s, cả hai cổng archive PASS, archive ghi
      thành công. Không có lý do revert. Lưu ý: giữ commit này **không** có
      nghĩa là tiền đề của nó đúng — tiền đề "GitHub bỏ tick" đã bị bác ở mục
      trên; nó được giữ vì vô hại và vẫn giảm rủi ro nghẽn, không vì nó đã sửa
      được gì.
- [x] **Chuông đã có trục 2** (PR #4, merge `ac1c4d1`): kêu khi
      `archive_written == False`, tức bắt được "phiên chưa chốt" mà trục ngày
      phiên không thấy. **NHƯNG KHÔNG HỒI TỐ.** Chạy chính bản vá đó trên
      `latest.json` thật của 26/08 (`git show 0e5d3b2a:web/data/latest.json`):
      cả hai trục đều im — trục 1 vì ngày phiên đúng, trục 2 vì file thiếu
      `archive_written` nên tự tắt. Chỉ hiệu lực **từ 27/08 trở đi**, khi mọi
      `latest.json` đều mang khoá đó. Sự cố 26/08 vẫn sẽ lọt nếu tái hiện y
      nguyên trên dữ liệu cũ.
- [ ] Chuông báo độ tươi phụ thuộc cùng một scheduler với thứ nó đang canh.
      Nó độc lập với *code* và *dữ liệu* của daily-scan, nhưng **không** độc
      lập với `schedule`. Cả hai cùng câm vì cùng một nguyên nhân.

## Đã vá — 28/08/2026

Sự cố lịch chạy ở trên chưa đóng, nhưng nó đã lôi ra một lỗi khác, nặng hơn và
đã vá xong. Ghi lại đây vì hai chuyện dính vào nhau: nếu tick không tới muộn thì
lỗi này còn nằm im không biết đến bao giờ.

### Nguyên nhân gốc

`last_trading_session` (`scanner/trading_calendar.py`) chỉ nhận `date`, **không
xét giờ trong ngày**, nên nó luôn khai phiên T là "phiên gần nhất" miễn hôm nay
là ngày giao dịch. Tick intraday 27/08 tới muộn 19h45, chạy lúc **08:17 ICT ngày
28/08** — trước giờ mở cửa. HOSE khớp ATO trong khung 09:00-09:15; trước đó
phiên T chưa có cây nến nào, không nguồn dữ liệu nào trả về được.

Dây chuyền:

```
last_session = 2026-08-28  (phiên chưa mở)
    → df.last (27/08) < last_session  → StaleCache = True cho 500/500 mã
    → criteria.py:176, golden_cross.py:139, ichimoku.py:143 reject sạch
    → cả 4 bộ quét trả 0
    → 3 file web/data/*/latest.json bị ghi đè bằng kết quả rỗng
```

404 trong 500 mã đó có dữ liệu **hoàn toàn tươi** cho phiên đã chốt. Mức stale
thật chỉ là 96/500 ≈ 0,19.

### Ba khiếm khuyết độc lập

Khiếm khuyết 1 gây ra sự cố; 2 và 3 quyết định nó phá được tới đâu.

| # | khiếm khuyết | commit vá |
| --- | --- | --- |
| 1 | `last_trading_session` không xét giờ | `93695ba` (hàm `last_expected_session` + mốc 09:15), `cf106ff` (data_fetcher dùng nó, kèm sửa `datetime.now()` trần → giờ ICT) |
| 2 | `write_strategy_outputs` ghi `latest.json` **trước** cổng archive (`run_daily.py`) | `f450b9f` — cổng `check_stale_universe` chặn trước MỌI lệnh ghi |
| 3 | Lá chắn bất đối xứng: pre-breakout thoát nhờ `if not df_pb.empty:`, ba strategy kia không có gì | `f450b9f` |

Kèm theo: `91b969a` (run_strategy không nuốt exception nữa — "0 candidates" giờ
luôn có một dòng đứng cạnh nói vì sao), `026768a` (cổng đọc `last_session` từ
`fetch_summary` thay vì tự tính lại, xoá bản sao phép tính).

### Bẫy đã gặp: `if:` ngầm AND `success()`

GitHub tự AND `success()` vào **mọi** biểu thức `if:` không chứa hàm kiểm trạng
thái. Nên `daily-scan.yml:259` (`if: steps.runtype.outputs.run_type == 'eod'`)
thực chất là `success() && ...`.

Quan trọng hơn: bước **Commit latest.json + archive** (`daily-scan.yml:266`)
**không có dòng `if:` nào**, và nó bị skip khi job đỏ **nhờ đúng mặc định đó** —
không nhờ điều gì được viết ra trong file. Cổng `sys.exit(1)` có hiệu lực là vì
vậy.

> **Thêm `if: always()` vào bước commit đó sẽ THÁO cổng stale.** Job đỏ mà vẫn
> commit thì file rỗng vẫn lên `main`. Nếu có ngày cần commit khi hỏng, phải
> dựng cổng khác thay chỗ, đừng chỉ thêm `always()`.

Bước duy nhất mang `always()` hiện nay là *Report fetch checkpoint* (dòng 145) —
nó chỉ đọc và in, không ghi gì.

### Flake có sẵn, không do các commit này

`backend/tests/test_fetch_budget.py::test_checkpoint_records_what_was_fetched`
đỏ ngẫu nhiên khoảng 1/10 lượt, tại:

```python
assert data['ok_tickers'] == ['T000', 'T001', 'T002', 'T003']
```

Checkpoint được ghi từ vòng lặp chính trong lúc worker vẫn đang chạy, nên số mã
đã `ok` tại đúng thời điểm ghi là một cuộc đua.

Đã xác minh trên **bản gốc**: `git stash` toàn bộ thay đổi rồi chạy 11 lượt
(282 test) — lượt 5 đỏ, cùng test đó. Có sẵn từ trước.

### Ngoài phạm vi, còn nợ

- **`_last_trading_session` (`data_fetcher.py:397`) giờ chết trong code chạy
  thật** — chỉ còn `test_trading_calendar.py:91` gọi. Docstring của nó vẫn hứa
  *"Caller vẫn có trách nhiệm hiểu phiên T có thể CHƯA đóng cửa (intraday)"*,
  trong khi caller duy nhất từng nhận trách nhiệm đó vừa phải sửa vì đã không
  nhận. Xoá hẳn hoặc gắn cảnh báo, ở một lượt riêng.

- **`actions/cache@v4` khai `post-if: success()`** (chưa xác minh). Nếu đúng,
  run bị cổng stale chặn sẽ **không lưu cache OHLCV** — mất luôn checkpoint của
  vòng fetch, tức ~26 phút fetch bị vứt. Không ảnh hưởng tính đúng đắn của cổng,
  nhưng là cái giá cần biết. Muốn xác nhận phải có một run đỏ thật.
