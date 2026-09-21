# Phase 0 — Audit đối chiếu blueprint v2 với repo

Ngày: 2026-09-21 | Commit gốc: `93a1ef2` (main) | Phương pháp: chỉ đọc mã nguồn và dữ liệu đã commit, không chạy vnstock (môi trường audit không truy cập được nguồn dữ liệu).

## Tóm tắt

Bốn phát hiện chặn Module B, phải xử lý trước khi viết entrypoint `run_quality.py`:

1. **F1** Dữ liệu định giá trên production là dữ liệu demo.
2. **F2** `financial_fetcher` chỉ giữ 5 kỳ, không đủ tính CAGR 5 năm.
3. **F3** Không có snapshot BCTC theo ngày, nên chưa có point-in-time.
4. **F9** Footgun `merge=ours` sẽ áp lên cả dữ liệu quality mới.

Phần lõi chấm điểm (thuần logic, không phụ thuộc vnstock) đã viết xong trên nhánh `feat/quality-core`, xem mục "Đã xây".

## Phát hiện

### F1 — `web/data/valuation/latest.json` là dữ liệu demo

- **Bằng chứng:** `metadata.demo = true`, chỉ 6 mã (VHM, VIB, FPT, PAN, HPG, DBC). File chỉ có đúng một commit `70fe042 evaluation`; không có commit nào từ workflow `weekly-valuation.yml`.
- **Suy luận:** bước "Verify valuation output" của workflow gọi `sys.exit` khi thấy cờ demo, nên hoặc job chưa từng chạy thành công, hoặc chạy lỗi trước bước commit. Chưa kiểm được lịch sử Actions (GitHub API bị giới hạn tần suất từ môi trường audit).
- **Ảnh hưởng:** Module B phụ thuộc định giá; hiện mọi mã sẽ ở mức "Chưa có". Dashboard valuation hiện tại cũng đang hiển thị số demo.
- **Việc cần làm:** `gh run list --workflow weekly-valuation.yml --limit 10`, đọc log lần chạy gần nhất, sửa nguyên nhân, chạy `workflow_dispatch` một lần.

### F2 — `financial_fetcher.py` cắt còn 5 kỳ gần nhất

- **Bằng chứng:** `fetch_fundamentals()` có `df_limited = df.head(5)`.
- **Ảnh hưởng:** CAGR 5 năm cần 6 điểm. Với 5 điểm, 3 chỉ tiêu CAGR + "số năm doanh thu tăng" (75% trọng số chiều Tăng trưởng của `NON_FINANCIAL`) luôn thiếu, nên Tăng trưởng rỗng cho toàn universe và mọi mã rơi vào "Thiếu dữ liệu". Test `test_non_financial_5_nam_thi_growth_thieu` ghi lại đúng hành vi này.
- **Chưa xác thực:** `head()` giả định vnstock trả kỳ mới nhất trước. Nếu thứ tự ngược, cache đang giữ 5 kỳ CŨ nhất.
- **Việc cần làm:** giữ tối thiểu 8 kỳ năm; lấy thêm kỳ quý (cần 4–5 quý cho cờ lệch dòng tiền và phát hiện công bố chậm); kiểm tra thứ tự bằng cột kỳ báo cáo, không dựa vào vị trí dòng.

### F3 — Chưa có snapshot BCTC

- **Bằng chứng:** cache `backend/data/fundamentals_cache/<ticker>_<period>.json` TTL 7 ngày, ghi đè mỗi lần làm mới, chỉ tồn tại trong Actions cache (không nằm trong git). Trường `fetched_at` có nhưng bị ghi đè.
- **Ảnh hưởng:** không đáp ứng blueprint §5.2 mục 3–4; cờ "công bố chậm" và veto "thiếu hai quý" không biết được kỳ mới nhất xuất hiện từ khi nào; backtest về sau không tái lập được.
- **Cần chốt:** lưu snapshot ở đâu. Đề xuất: lưu bản **đã chuẩn hóa** (schema trong `scanner/quality/metrics.py`, vài KB/mã) vào `web/data/quality/archive/<date>.json`; không commit dữ liệu thô vnstock vào git.

### F4 — Không có nguồn trạng thái cảnh báo / kiểm soát / ý kiến kiểm toán

- **Bằng chứng:** `m_tradable_warning` trong output scanner đến từ `price_limits.py` và chỉ phản ánh giá trần/sàn, không phải trạng thái pháp lý. Danh sách hủy niêm yết là file tĩnh nhập tay `backend/data/delisted_tickers.txt`. Không có chỗ nào đọc ý kiến kiểm toán.
- **Đã xử lý trong code:** các cờ và veto tương ứng để `enabled=False` trong `scanner/quality/config.py` và **loại khỏi mẫu số độ phủ**. Nếu để bật mà không có nguồn, độ phủ Quản trị của mọi mã chỉ còn 60%, dưới ngưỡng 70%, nên chiều Quản trị rỗng cho toàn universe.

### F5 — Scanner chưa sinh vùng vào / cắt lỗ / R:R

- **Bằng chứng:** các file `web/data/*/latest.json` có `m_supports`, `m_resistances` (Fibonacci), `m_fibo_swing`, `m_limit_status`, nhưng không có trường vùng vào, cắt lỗ hay mục tiêu.
- **Cần chốt:** đề xuất tối giản dùng dữ liệu đã có — cắt lỗ = hỗ trợ gần nhất dưới giá đóng cửa, mục tiêu = kháng cự gần nhất trên giá, R:R = (mục tiêu − giá) / (giá − cắt lỗ); bỏ cột "vùng vào", hiển thị giá đóng cửa làm mốc. Không hiển thị R:R khi thiếu một trong hai mức.

### F6 — Phân ngành

`industry_classifier.py` có 19 nhóm `ValuationIndustry`, trong đó Banking, Securities, Insurance, Real_Estate tách riêng. Ánh xạ 19 → 5 mô hình đã đặt trong `scanner/quality/config.py`. `Diversified_Holding` tạm xếp `NON_FINANCIAL`, cần xem lại từng mã.

### F7 — Lịch chạy thực tế (sửa blueprint §12)

| Job | Lịch trong repo |
|---|---|
| daily-scan | 12:05 ICT (intraday) và 23:05 ICT (EOD), thứ Hai–thứ Sáu |
| weekly-valuation | Chủ nhật 07:09 ICT, `--limit` mặc định **100**, `--period year` |

Blueprint v2 ghi valuation chạy thứ Hai và universe mặc định 200. Universe Module B phải bằng `--limit` của valuation; đề xuất giữ 100 cho tới khi F1 xong, sau đó mới nâng.

### F8 — Giao diện

`web/tokens.css` đã có trên `main` nhưng **chưa được nạp** ở đâu. Mockup đã duyệt là `design/mau-huong-2.html`. Nhánh `fix/mobile-layout` và `redesign-tokens` còn mở. Canvas "Bố cục 2 module v2" chỉ quy định **cấu trúc thông tin**; phần nhìn phải dùng `tokens.css` (hướng "Sổ tay phân tích", phi sắc, 5 màu giá chỉ cho giá). Hai bên nhất quán về nguyên tắc; Phase 2 nên làm sau bước dọn component để không sửa CSS hai lần.

### F9 — `merge=ours` trên `web/data/**`

Vấn đề đã biết: khi `git pull --rebase`, "ours" là upstream, nên commit dữ liệu cục bộ bị bỏ âm thầm. Job quality mới ghi vào `web/data/quality/`, tức là rơi đúng vào vùng này. Phải sửa trước khi thêm job ghi dữ liệu thứ ba.

### F10 — Không kiểm được trong audit này

- Tên cột thật của `Finance.balance_sheet / income_statement / cash_flow / ratio` (vnstock 4.0.7, `lang='en'`, nguồn VCI) — cần in ra từ cache trên máy có mạng.
- Bảng `ratio` có trả NIM, tỷ lệ nợ xấu, bao phủ nợ xấu cho ngân hàng hay không.
- Đơn vị tiền trong BCTC (đồng hay tỷ đồng).

## Điều chỉnh cần đưa vào blueprint (v3)

1. §6 cấu hình Module B dùng `backend/scanner/quality/config.py`, không dùng YAML (tránh thêm phụ thuộc PyYAML).
2. §8.1 universe mặc định = `--limit` của weekly valuation (hiện 100).
3. §8.5 phân biệt cờ **tắt vì chưa có nguồn** (loại khỏi mẫu số) và cờ **thiếu dữ liệu ở một mã** (giảm độ phủ); gộp "pha loãng mạnh/vừa" thành một cờ hai mức.
4. §9 thêm quy tắc: `methods_conflict = true` → "Chưa có"; giới hạn độ tin cậy áp khi phương pháp **có trọng số lớn nhất** là RNAV hoặc SOTP.
5. §12 sửa lịch theo F7.
6. §15 chèn Phase 0.5 (F1, F2, F3, F9) trước Phase 1.

## Đã xây — nhánh `feat/quality-core`

| File | Nội dung |
|---|---|
| `backend/scanner/quality/config.py` | Ngưỡng, trọng số, ánh xạ ngành, cờ và veto bật/tắt |
| `backend/scanner/quality/metrics.py` | Schema chuẩn + tính chỉ tiêu 3 mô hình |
| `backend/scanner/quality/scoring.py` | Percentile trong nhóm (min 8, winsorize khi ≥ 20, hạng trung bình khi bằng nhau), điểm chiều theo độ phủ trọng số |
| `backend/scanner/quality/governance.py` | Cờ quản trị, đếm quý thiếu, veto |
| `backend/scanner/quality/status.py` | Quy đổi định giá 4 mức, phân loại trạng thái kèm lý do, cờ "Giảm mạnh" |
| `backend/tests/test_quality.py` | 29 test |

### Guard report

| Kiểm | Kết quả | Ghi chú |
|---|---|---|
| G1 Phép kiểm có thể đỏ | PASS | 10 đột biến (ngưỡng nhóm, hạng bằng nhau, mẫu số cờ, thứ tự phân loại, "Chưa có" lọt Đủ chuẩn, giới hạn RNAV, số điểm CAGR, đỉnh bằng 0, quý đến hạn, mâu thuẫn phương pháp) đều làm test đỏ. Hai test ban đầu không đỏ được đã viết lại. |
| G2 Đi qua entrypoint | FAIL (có chủ đích) | Chưa có `run_quality.py` vì adapter vnstock phụ thuộc F2, F3, F10. Test xa nhất là `test_score_group_end_to_end_mot_mo_hinh` (metrics → scoring). |
| G3 Đẳng thức cấu trúc | N/A | |
| G4 Số từ payload | N/A | Chưa sinh báo cáo số |
| G5 Grain sau biến đổi | N/A | Chưa có join |

Toàn bộ test backend: 329 passed (300 cũ + 29 mới).
