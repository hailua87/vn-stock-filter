# VN Stock Filter — Hồ sơ tổng hợp dự án (v3)

> **Vai trò tài liệu:** nguồn tham chiếu thống nhất cho phạm vi, dữ liệu, logic sàng lọc/chấm điểm, kiến trúc, giao diện và lộ trình.
>
> **Phiên bản:** v3, cập nhật 2026-09-22. Thay v2 (2026-09-21): đưa vào 6 điều chỉnh của `docs/PHASE0_AUDIT_v1.md` và kết quả Phase 0 / 0.5 đã xác thực trên dữ liệu thật. v2 thay thế hoàn toàn v1 (hướng "chỉ dùng công bố chính thức + rebuild").  
> **Repository:** `hailua87/vn-stock-filter` (nhánh `main`)  
> **Production:** <https://vn-stock-filter.vercel.app>  
> **Mockup giao diện:** canvas "VN Stock Filter — Bố cục 2 module v2" (4 màn hình, số liệu minh họa)

---

## 1. Tóm tắt điều hành

VN Stock Filter là công cụ cá nhân, không thương mại hóa, gồm hai module dùng chung một nền dữ liệu vnstock:

| | **Module A — Scan hằng ngày** | **Module B — Watchlist dài hạn** |
|---|---|---|
| Câu hỏi trả lời | Hôm nay mã nào đáng cân nhắc vào lệnh? | Công ty nào đáng cân nhắc nắm giữ nhiều năm để tích lũy tài sản? |
| Dữ liệu chính | Giá, khối lượng ngày (đã điều chỉnh) | BCTC quý/năm, chỉ số tài chính, giá cho định giá |
| Logic lõi | Các chiến lược scanner **đã có** trong app | 4 chiều chất lượng + veto + định giá từ Valuation Engine **đã có** |
| Nhịp cập nhật | Mỗi phiên | Điểm chất lượng hằng tuần (BCTC đổi theo quý); định giá hằng tuần |
| Đầu ra | Danh sách mã khớp chiến lược kèm vùng vào, cắt lỗ | Trạng thái watchlist kèm lý do |

Nguyên tắc (giữ từ v2):

1. **Giữ backend hiện tại** (scanner kỹ thuật + Valuation Engine, chạy bằng GitHub Actions, web trên Vercel). Chỉ bổ sung phần chấm điểm chất lượng và làm lại giao diện theo bố cục đã chốt.
2. **Lấy dữ liệu qua vnstock**, không tự parse PDF báo cáo tài chính.
3. **Không gán điểm trung tính cho dữ liệu thiếu**; thiếu thì hiển thị là thiếu.
4. **Kết quả là thứ tự ưu tiên nghiên cứu**, không phải khuyến nghị mua bán, không đặt lệnh.

## 2. Nhãn trạng thái dùng trong tài liệu

| Nhãn | Ý nghĩa |
|---|---|
| **Đã có** | Đã tồn tại trong repo `main` (theo README hiện tại) |
| **Cần xây** | Đã thống nhất logic, chưa có mã nguồn |
| **Cần xác thực** | Phải kiểm tra trong mã nguồn hoặc dữ liệu vnstock thực tế trước khi dựa vào |
| **Cần chốt** | Còn là quyết định mở, xem §14 |

## 3. Nhật ký quyết định (v1 → v2 → v3)

| # | Chủ đề | v1 | v2 (đã chốt 21/09/2026) |
|---|---|---|---|
| D1 | Nguồn dữ liệu | Chỉ công bố chính thức (HOSE/HNX/SSC/IR), tự parse PDF | vnstock |
| D2 | Mục tiêu | Chỉ sàng lọc chất lượng dài hạn | Hai module: scan trading hằng ngày + watchlist dài hạn |
| D3 | Bộ lọc trading | Không có | Dùng các chiến lược scanner hiện có, thêm điều kiện Combined |
| D4 | Quản trị (Governance) | Chủ yếu từ đánh giá Fisher duyệt tay từng mã | Cờ tự động từ dữ liệu; ghi chú định tính chỉ là tùy chọn cho shortlist |
| D5 | Định giá | Engine mới, chưa thiết kế | Dùng lại Valuation Engine hiện có, quy đổi sang 4 mức |
| D6 | Hạ tầng | Rebuild Next.js + Supabase, thay app cũ | Giữ backend và luồng deploy hiện tại; không merge nhánh `rebuild/vercel-fisher` |
| D7 | Universe Module B | Toàn bộ HOSE/HNX/UPCoM | Top N mã thanh khoản, trùng universe của Valuation Engine |
| D8 | Giao diện | Một bảng screener | 4 màn: Hôm nay / Scan hằng ngày / Watchlist dài hạn / Chi tiết mã |

| # | Chủ đề | v2 | v3 (chốt 22/09/2026) |
|---|---|---|---|
| D9 | Cấu hình Module B | `backend/config/scoring_models.yml` | `backend/scanner/quality/config.py` — tránh thêm phụ thuộc PyYAML (audit §Điều chỉnh 1) |
| D10 | Universe Module B | Top 200 theo GTGD 60 phiên | Bằng `--limit` của weekly valuation. Tạm chốt **100** ngày 22/09, nâng lên **200** ngày 23/09 sau khi đo thật (§14.5) |
| D11 | Cờ quản trị | Pha loãng mạnh / vừa là hai cờ | Một cờ hai mức; phân biệt cờ **tắt vì chưa có nguồn** với **thiếu dữ liệu ở một mã** (audit §Điều chỉnh 3, §8.5) |
| D12 | Mức định giá | 4 mức theo upside + độ tin cậy | Thêm: mâu thuẫn phương pháp, nhóm tài chính, chỉ 1 phương pháp → "Chưa có"; giới hạn độ tin cậy xét **phương pháp trọng số lớn nhất** (§9) |
| D13 | Nhãn engine | Không hiển thị | Đã gỡ khỏi web; `verdict` chỉ còn trong JSON cho `backtest.py` (§9) |
| D14 | Lịch chạy | Valuation thứ Hai | Theo lịch thực trong repo (§12) |
| D15 | Lộ trình | Phase 0 → 1 | Chèn Phase 0.5 (F1, F2, F3, F9) — **đã xong** (§15) |
| D16 | Archive khi fetch dừng sớm | Luôn chặn | Dừng vì **hết giờ** mà độ phủ ≥ 80% thì cho ghi; dừng vì **cầu dao** vẫn chặn (§7.5) |
| D17 | Ngưỡng "Cần xem lại" | Quản trị < 60, Chất lượng < 60, Chống chịu < 50 | Quản trị < 30, Chất lượng < 30, Chống chịu < 25. Điểm 3 chiều là **percentile** nên trung vị ~50; ngưỡng cũ tự động đưa ~60% mã vào "Cần xem lại" (chạy thật 22/09: 55/100) (§10) |
| D18 | Cờ pha loãng | Số CP lưu hành tăng | Chỉ tính CP **phát hành lấy tiền**: phần CP tăng × min(1, tiền thu phát hành / phần vốn góp tăng). Cổ tức cổ phiếu, cổ phiếu thưởng không phải pha loãng (chạy thật: 58 → 19 mã bị cờ) (§8.5) |
| D19 | Nền màu giao diện | Mockup "Sổ tay phân tích" nền sáng (`tokens.css` --n-*, --px-*) | **Giữ nền tối cho cả app** (quyết định 29/08 trong `web/index.html`: chuyển sáng làm 8 biến đang đạt AA bị hỏng). Màn Phase 2 dùng bảng màu tối của `styles.css` + token phi màu của `tokens.css`; cấu trúc thông tin vẫn theo canvas/mockup (§11) |
| D20 | Nơi lưu luận điểm cá nhân | Chưa chốt (§14.1: trình duyệt hay backend nhỏ có xác thực) | **localStorage của trình duyệt** (chốt 23/09/2026). Đổi lại: chỉ có trên máy và trình duyệt đó, xóa dữ liệu site là mất — nên ô luận điểm nói rõ điều này ngay trên màn hình và có nút xuất/nhập tệp JSON để mang sang máy khác. Không thêm backend, không có gì rời khỏi máy người dùng (§11.1) |
| D21 | Ý kiến kiểm toán & trạng thái cảnh báo | Hai cờ + hai veto để `enabled: False`, chờ nguồn | **Gỡ hẳn** (chốt 23/09/2026). Để `enabled: False` vẫn là nói dối: giao diện mang nhãn của chúng, người đọc tưởng điểm Quản trị đã xét. Nay gỡ khỏi cấu hình và khai ở `GOVERNANCE_NOT_EVALUATED` để màn hình hiện dòng "Chưa xét: … — không có nguồn dữ liệu" (§8.5, §14.2) |
| D22 | Mô hình `REAL_ESTATE` | Chưa kích hoạt (Phase 4) | **Bật 23/09/2026.** Rổ 200 có 36 mã BĐS, 34 trong đó kẹt ở "Thiếu dữ liệu" chỉ vì thiếu bộ chỉ tiêu. Bộ chỉ tiêu ở §8.4; "người mua trả tiền trước" đã thử và bỏ vì xếp mã kiệt quệ lên đầu |
| D23 | Xếp hạng universe theo thanh khoản | Một thang điểm gộp: thanh khoản đo được và thứ hạng danh sách curated (`(623 − hạng) × 1e9`) | **Hai bậc tách rời** (sửa 24/09/2026). Bậc 1: mã có số đo trong 30 ngày, xếp theo GTGD; bậc 2: mã chưa có số đo, xếp theo danh sách curated. Hai đại lượng này không cùng đơn vị nên không bao giờ so sánh được — ép chung một thang khiến **mọi** mã curated đứng trên **mọi** mã đo được, và số đo thật chưa bao giờ được dùng (§7.2) |
| D24 | Chỉ tiêu ngân hàng | NIM / nợ xấu / bao phủ nợ xấu để `None`, chờ nguồn | **NIM lấy từ `vnstock` nguồn KBS; nợ xấu và bao phủ nợ xấu gỡ hẳn** (24/09/2026). Khảo sát ba nguồn: VCI dừng 2018, KBS không có trường nợ xấu nào, TCBS có nhưng là API nội bộ. Trọng số chia lại; `BANK_NOT_EVALUATED` để màn hình nói "Chưa xét" thay vì khóa 18 mã ở "Thiếu dữ liệu" không lý do (§8.4, §14.3) |
| D25 | Mô hình `INSURANCE` | Chưa kích hoạt, chưa rõ lý do | **Cố ý không bật** (chốt 25/09/2026). Rổ 200 chỉ có **2 mã** (BVH, MIG); điểm ba chiều là percentile trong nhóm, mà percentile trên 2 mã chỉ ra được 0 và 100 — không nói gì về doanh nghiệp. `INACTIVE_MODEL_REASON` đẩy lý do ra màn hình thay vì để "chưa kích hoạt" nghe như sắp làm đến nơi (§8.4) |
| D26 | Nhánh `rebuild/vercel-fisher` | Giữ, không merge (D6) | **Xóa 25/09/2026.** Quyết định và lý do đã nằm ở D6; nhánh code cũ không thêm thông tin gì mà còn làm người mới tưởng đó là hướng đang làm dở |
| D27 | Backtest chiến lược trading | Chưa chốt (§14.6) | **Đưa vào Phase 4** (chốt 25/09/2026). Archive tín hiệu theo phiên đã chạy từ 18/09 nên dữ liệu đang tích lũy sẵn; chỉ còn chờ đủ dài và viết phần đo (§15) |

## 4. Phạm vi

### 4.1 Trong phạm vi

- Scan kỹ thuật hằng ngày trên HOSE, HNX, UPCoM với bộ lọc thanh khoản.
- Chấm điểm chất lượng và phân loại watchlist cho universe Module B.
- Định giá theo ngành (engine hiện có) và hiển thị vùng định giá.
- Trang chi tiết mã gộp góc giao dịch và góc dài hạn.
- Theo dõi tình trạng dữ liệu (thiếu, cũ, lỗi nguồn).

### 4.2 Ngoài phạm vi

- Đặt lệnh, kết nối tài khoản môi giới, tín hiệu trong phiên.
- Theo dõi danh mục đang nắm giữ và lãi/lỗ (có thể xét ở giai đoạn sau, chưa thiết kế).
- Tự động gán điểm trung tính cho chỉ tiêu thiếu.
- Phân phối lại dữ liệu thô của bên thứ ba.
- Dữ liệu của doanh nghiệp nơi người dùng làm việc hoặc dữ liệu cá nhân không cần thiết.

## 5. Dữ liệu

### 5.1 Nguồn

vnstock 4.x (theo README, dùng `VNSTOCK_API_KEY`). Nguồn gốc bên dưới do thư viện chọn; đây là API không chính thức, có thể thay đổi hoặc giới hạn bất cứ lúc nào.

| Tập dữ liệu | Dùng cho | Trạng thái |
|---|---|---|
| Danh sách mã, sàn, ngành | Universe, phân loại mô hình | Đã có, **đã xác thực** — xem §5.4 |
| OHLCV ngày | Module A, beta, định giá lịch sử | Đã có (`data_fetcher.py`) |
| BCTC quý/năm | Module B, Valuation Engine | Đã có (`financial_fetcher.py`), **đã xác thực** dạng bảng và đơn vị — xem §5.4 |
| Chỉ số tài chính đặc thù ngân hàng (nợ xấu, bao phủ nợ xấu, NIM) | Mô hình `BANK` | **Đã xác thực: không dùng được** — bảng `ratio` bản cộng đồng chỉ có 2018; 3 bảng BCTC không đủ để tính (§5.4, §14.3) |
| Trạng thái cảnh báo / kiểm soát / hạn chế / đình chỉ | Veto, cờ quản trị, lọc Module A | Cần xác thực |
| Ý kiến kiểm toán | Veto, cờ quản trị | Cần xác thực; nhiều khả năng vnstock không có (xem §14) |

### 5.2 Quy tắc dữ liệu bắt buộc

1. **Giá đã điều chỉnh** cổ tức và chia tách cho mọi chỉ báo kỹ thuật và phép tính lịch sử. Giá hiển thị trên bảng là giá chưa điều chỉnh của phiên.
2. **Không ghi đè bằng dữ liệu rỗng.** Khi một lần lấy thất bại hoặc trả rỗng, giữ bản gần nhất, gắn cờ `stale` kèm ngày của bản đang dùng.
3. **Snapshot theo ngày lấy.** Mỗi lần lấy BCTC lưu kèm `fetched_at`, phiên bản vnstock và hash nội dung. Đây là cách duy nhất để sau này biết hệ thống đã thấy gì vào ngày nào, vì vnstock chỉ trả phiên bản số liệu mới nhất.
   *Đã có (Phase 0.5):* sổ `backend/data/snapshots/fundamentals_registry.json` ghi cho mỗi (mã, loại kỳ, kỳ) `first_seen`, `last_seen`, hash 3 bảng BCTC và lịch sử sửa số liệu kèm phiên bản vnstock. Sổ **chỉ chứa metadata, không chứa số liệu** (repo public, §4.2); số liệu đã chuẩn hóa sẽ lưu ở `web/data/quality/archive/` (Phase 1). Độ phân giải ngày giới hạn bởi lịch weekly và TTL cache 7 ngày: `first_seen` là "chậm nhất là ngày này".
4. **Quy tắc độ trễ công bố cho backtest.** Với dữ liệu lịch sử lấy lại từ vnstock (không có ngày công bố), coi số liệu kỳ quý chỉ khả dụng sau ngày kết thúc kỳ + 45 ngày, kỳ năm + 90 ngày. Từ ngày bắt đầu lưu snapshot, dùng `fetched_at` đầu tiên thay cho quy tắc này.
5. **Chuẩn hóa đơn vị** (đồng, triệu, tỷ) ngay khi nạp, kiểm tra theo từng trường.
6. **Survivorship:** danh sách mã từ vnstock là danh sách hiện tại. Kết quả backtest phải ghi rõ giới hạn này.
7. **Giá điều chỉnh bị tính lại hồi tố.** Khi có sự kiện quyền, vnstock điều chỉnh lại MỌI phiên trước đó của chuỗi giá adjusted (FPT: giá lưu 16/09 là 73,8, giá hiện tại của cùng phiên là 67,09, tỷ lệ đúng 1,1000 = cổ tức cổ phiếu 10%). Archive giữ giá tại thời điểm ghi nên vẫn đúng cho ngày đó, nhưng **backtest không được so trực tiếp giá archive cũ với giá hiện tại** — phải điều chỉnh lại theo các sự kiện quyền phát sinh sau.

### 5.3 Provenance tối thiểu cho mỗi số liệu dùng để chấm điểm

`ticker`, `metric`, `period`, `value`, `unit`, `source` (vnstock + nguồn con nếu biết), `fetched_at`, `snapshot_hash`, `is_stale`.

### 5.4 Đặc điểm vnstock 4.0.7 đã xác thực (Phase 0 / 0.5)

| Chủ đề | Thực tế | Hệ quả trong code |
|---|---|---|
| Module Finance | `vnstock.api.financial` (không có `vnstock.api.finance`) | Import sai từng làm weekly valuation đỏ 4 tuần (30/08–20/09) |
| Dạng bảng BCTC | **Dòng = khoản mục** (`item`, `item_en`, `item_id`), **cột = kỳ**, kỳ mới trước | `statement_to_records`: mỗi kỳ một record, khóa theo `item_id`; `item_id` trùng lấy giá trị khác rỗng đầu tiên |
| Đơn vị BCTC | **Đồng** | Chia 1e9 sang tỷ đồng khi nạp; normalizer làm việc bằng tỷ đồng |
| Số kỳ | Bản cộng đồng tối đa **8 kỳ** | Giữ cả 8 (`MAX_PERIODS = 8`), đủ 6 điểm cho CAGR 5 năm |
| Bảng `ratio` | Chỉ trả dữ liệu **2018** (16 cột cùng tên, Q1–Q4 lặp) | Bị bỏ khi cũ hơn BCTC quá 1 năm; ROE, EPS/BVPS lịch sử tính từ BCTC; NPL/NIM/CAR không có |
| Ngành (`Company.overview`) | Không có `icb_name2..4`; cột `sector` là **tên ICB cấp 2** tiếng Anh, kèm `icb_code_lv2`, `icb_code_lv4` | `industry` lấy từ `sector` khi có `icb_code_lv2`; phân loại cấp 4 theo mã số (`ICB_LV4_OVERRIDE`). 100/100 mã universe có ngành |
| Số cổ phiếu | `overview.issue_share`; dòng BCTC `common_shares` là **vốn cổ phần bằng tiền** | Dự phòng: vốn góp / mệnh giá 10.000đ (VCB khớp `overview` trong 0,01%) |
| Giá sau đóng cửa | Đo 16/09, 18/09: Close lúc ~17:00 ICT đã trùng giá chốt; chỉ Volume thiếu nhẹ (trung vị ~0,1%) | Nhận định cũ "giá tạm tới 22:00" không còn đúng với Close; giữ lịch cũ tới khi đo thêm |
| Tốc độ nguồn | Dao động mạnh: 18/09 lấy 500 mã trong 18 phút; 14, 17, 21/09 `trading.vietcap.com.vn` timeout 30 s liên tục | Ngân sách thời gian, điều tiết theo lượt gọi mạng, hạn chót cho mọi lệnh gọi sau vòng fetch (§7.5) |
| `vnai` (phụ thuộc của vnstock) | Tự ghi một prompt tải từ vnstocks.com vào `AGENTS.md` của thư mục chạy và `~/.claude`, `~/.codex`, `~/.gemini` | `VNSTOCK_DISABLE_AGENT_SETUP=1` **không chặn được** (đo 23/09/2026: `vnai/beam/agents.py` không đọc biến này). Chặn thật bằng `/AGENTS.md` trong `.gitignore` + hook dọn dẹp ở `backend/conftest.py`; ghim `vnai==2.6.0` |

## 6. Kiến trúc

### 6.1 Giữ nguyên

```mermaid
flowchart LR
    A["vnstock"] --> B["GitHub Actions: backend Python"]
    B --> C["JSON trong web/data (commit vào repo)"]
    C --> D["Web tĩnh trên Vercel"]
```

| Thành phần | Hiện trạng | Việc cần làm |
|---|---|---|
| `backend/run_daily.py` + `scanner/strategies/` | Đã có | Bổ sung điều kiện nền (§7.2), trường vùng vào/cắt lỗ nếu chưa có |
| `backend/run_valuation.py` + `strategies/valuation/` | Đã có; lớp quy đổi 4 mức **đã có** | Còn: nguồn NPL/CAR cho nhóm tài chính (§14.3) |
| `backend/backtest.py` | Đã có (cho định giá) | Dùng để hiệu chỉnh ngưỡng định giá |
| `industry_classifier.py`, `peer_database.py` | Đã có | Dùng lại để ánh xạ sang 5 mô hình chấm điểm (§8.2) |
| Quality scoring | **Đã có** (Phase 1): lõi `backend/scanner/quality/`, adapter BCTC → schema chỉ tiêu (`adapter.py`), `backend/run_quality.py`, `web/data/quality/latest.json` + `archive/` | Còn: nguồn NPL/NIM cho `BANK`, kích hoạt `INSURANCE`, `REAL_ESTATE` |
| Status engine (veto + phân loại watchlist) | Logic **đã có** (`scanner/quality/status.py`) | Nối vào `run_quality.py` |
| Push dữ liệu của bot | `scripts/commit-bot-data.sh` | Không rebase, không merge driver, không force-push (audit F9) |
| Cảnh báo CI | `scripts/ci-alert.sh` + `data-freshness-alert.yml` | Issue nhãn `workflow-failure` mở khi daily-scan/weekly-valuation hỏng, tự đóng khi hồi phục; chuông độ tươi bắt trường hợp không có run |
| Sổ snapshot BCTC | `backend/data/snapshots/fundamentals_registry.json` | Bot weekly-valuation commit; chỉ metadata (§5.2.3) |
| `web/` | Đã có (scanner + valuation dashboard) | Làm lại theo 4 màn hình (§11) |
| `.github/workflows/daily-scan.yml` | Đã có | Thêm job quality, xem §10 |

### 6.2 Không làm

- Không merge nhánh `rebuild/vercel-fisher`. Giữ lại để tham chiếu (schema, ý tưởng RLS) hoặc đóng PR nếu đã mở.
- Không đưa Supabase vào cho đến khi quyết định mục §14.1 cần đến nó.

### 6.3 Lưu ý bảo mật

Repo đang ở chế độ public và dữ liệu đầu ra được commit vào `web/data`. Kết quả scan và điểm số công khai là chấp nhận được. **Ghi chú luận điểm cá nhân và danh sách nắm giữ tuyệt đối không được commit vào repo** (xem §14.1). `VNSTOCK_API_KEY` chỉ nằm trong GitHub Secret.

## 7. Module A — Scan hằng ngày

### 7.1 Chiến lược (đã có trong scanner)

| Chiến lược | Định nghĩa theo README | Ghi chú |
|---|---|---|
| Pre-Breakout | Tín hiệu nén giá sắp break | Cần xác thực tham số trong `criteria.py` và ghi vào tài liệu |
| Golden Cross dài hạn | MA50 cắt lên MA200 | |
| Golden Cross ngắn hạn | MA10 cắt lên MA20 | |
| Ichimoku | TK cross, tín hiệu mây | Cần xác thực điều kiện mây đang dùng |
| Combined | Mã thỏa nhiều chiến lược | Giao diện cho chọn khớp tối thiểu 1, 2 hoặc 3 chiến lược |

Định nghĩa hiển thị trên giao diện phải lấy từ cùng tham số mà mã nguồn dùng, không viết tay riêng.

### 7.2 Điều kiện nền (áp dụng trước chiến lược)

| Điều kiện | Mặc định | Lý do |
|---|---|---|
| GTGD trung bình 20 phiên | ≥ 10 tỷ đồng | Tín hiệu trên mã thanh khoản thấp không dùng được |
| Sàn | HOSE, HNX, UPCoM | Người dùng bật/tắt |
| Loại mã cảnh báo, kiểm soát, hạn chế, đình chỉ | Bật | Phụ thuộc nguồn trạng thái (§5.1) |
| Chỉ mã có Chất lượng ≥ 60 | Tắt | Liên kết Module B; khi bật, mã chưa được chấm bị loại |

### 7.3 Trường đầu ra mỗi mã

Mã, sàn, giá và % thay đổi (màu theo quy ước bảng điện, §11.3), sparkline 20 phiên, KL/TB20, GTGD TB20, chiến lược khớp (liệt kê tất cả), vùng vào, cắt lỗ, tỷ lệ lời : lỗ, điểm Chất lượng (nếu có), cờ.

Cần xác thực scanner hiện có đã sinh vùng vào, cắt lỗ, mục tiêu hay chưa. Nếu chưa, quy tắc mặc định đề xuất cho từng chiến lược phải được viết vào tài liệu trước khi hiển thị, và luôn kèm dòng "mức gợi ý theo chiến lược, không phải lệnh".

Mã kịch trần không hiển thị vùng vào (không khả thi mua), mã kịch sàn không hiển thị tín hiệu.

### 7.4 Ràng buộc thị trường Việt Nam

- Biên độ: HOSE ±7%, HNX ±10%, UPCoM ±15% (tham số hóa, không hard-code trong logic).
- Chu kỳ thanh toán: hàng về chiều T+2; hiển thị trên trang chi tiết mã.
- Thứ tự sắp xếp mặc định: số chiến lược khớp giảm dần, sau đó KL/TB20 giảm dần.

### 7.5 Vận hành daily-scan (đã có)

| Cơ chế | Quy tắc |
|---|---|
| Ngân sách vòng fetch | 45 phút (`FETCH_BUDGET_S`); cầu dao khi 20 mã hỏng liên tiếp |
| Điều tiết | `delay` là khoảng cách tối thiểu giữa hai lượt **gọi mạng thật**; mã lấy từ cache không chờ |
| Hạn chót sau fetch | 55 phút tính từ lúc bắt đầu (`RUN_BUDGET_S`) cho mọi lệnh gọi API còn lại (sự kiện quyền); quá hạn chỉ dùng cache |
| Sự kiện quyền | Chỉ kiểm cho mã đạt ngưỡng công bố của từng chiến lược (`min_score`) |
| Cổng archive: thời gian | Phiên hôm nay phải qua 15:15 ICT; phiên đã qua luôn pass |
| Cổng archive: độ phủ | ≥ 80% và vòng fetch chạy trọn; hoặc dừng vì **hết giờ** mà vẫn ≥ 80%. Dừng vì **cầu dao** luôn chặn. Metadata ghi `fetch_coverage`, `fetch_truncated` |
| Ghi archive | Archive là **vĩnh viễn**; hiện chưa có cách quét lại một phiên đã qua (14/09, 21/09 không có archive) |

GitHub xếp hàng cron trễ: ca 12:05 ICT thực tế chạy ~16:30–17:30, ca 23:05 ICT hay chạy sau nửa đêm (§12).

## 8. Module B — Watchlist dài hạn

### 8.1 Universe

Top N mã theo thanh khoản, **N = `--limit` của weekly valuation (hiện 100)**, cấu hình được, và **dùng chung với Valuation Engine** (v3, D10: nâng N sau khi weekly valuation chạy ổn định; 100 mã hiện mất 20–70 phút tùy tốc độ nguồn). Lý do: engine cần peer database đủ lớn, và nếu chấm chất lượng rộng hơn phạm vi định giá thì phần lớn mã sẽ kẹt ở trạng thái định giá "Chưa có".

Hệ quả cần ghi nhớ: percentile chất lượng là thứ hạng **trong universe này**, không phải toàn thị trường.

### 8.2 Năm mô hình chấm điểm

Ánh xạ từ `industry_classifier.py` (19 nhóm ngành của engine) sang 5 mô hình:

| Mô hình | Gồm | Trạng thái |
|---|---|---|
| `NON_FINANCIAL` | Mọi nhóm phi tài chính (trừ bất động sản) | Kích hoạt |
| `BANK` | Banking | Kích hoạt (phụ thuộc xác thực trường ở §5.1) |
| `SECURITIES` | Chứng khoán | Kích hoạt |
| `INSURANCE` | Bảo hiểm | Chưa kích hoạt: số mã ít, mẫu BCTC riêng |
| `REAL_ESTATE` | Real_Estate | Chưa kích hoạt: chỉ tiêu cốt lõi (presales, quỹ đất pháp lý) không có trong BCTC chuẩn |

Mã thuộc mô hình chưa kích hoạt hiển thị trạng thái "Thiếu dữ liệu" với lý do "Mô hình ngành chưa kích hoạt".

Bảng ánh xạ 19 → 5 nằm trong `backend/scanner/quality/config.py` (v3, D9). `Diversified_Holding` tạm xếp `NON_FINANCIAL`, cần xem lại từng mã.

### 8.3 Bốn chiều điểm

| Chiều | Thang | Cách tính |
|---|---|---|
| Chất lượng | 0–100 | Bình quân trọng số percentile các chỉ tiêu (§8.4) |
| Tăng trưởng | 0–100 | Như trên |
| Quản trị | 0–100 | 100 trừ tổng điểm phạt từ cờ tự động (§8.5) |
| Chống chịu | 0–100 | Bình quân trọng số percentile các chỉ tiêu |

### 8.4 Chỉ tiêu theo mô hình

Chỉ giữ chỉ tiêu tính được từ BCTC/chỉ số mà vnstock trả về. Chiều "cao hơn tốt hơn" hay "thấp hơn tốt hơn" khai báo trong cấu hình.

**`NON_FINANCIAL`**

| Chiều | Chỉ tiêu | Công thức / nguồn | Trọng số |
|---|---|---|---:|
| Chất lượng | ROIC trung bình 5 năm | NOPAT / (VCSH + nợ vay − tiền) | 25% |
| Chất lượng | Ổn định biên gộp | Độ lệch chuẩn biên gộp 5 năm (thấp tốt) | 20% |
| Chất lượng | Ổn định biên hoạt động | Độ lệch chuẩn biên EBIT 5 năm (thấp tốt) | 20% |
| Chất lượng | Chuyển đổi lợi nhuận thành tiền | Tổng CFO / tổng LN ròng 3 năm | 20% |
| Chất lượng | Vòng quay tổng tài sản | Doanh thu / tổng tài sản bình quân | 15% |
| Tăng trưởng | CAGR doanh thu 5 năm | | 30% |
| Tăng trưởng | CAGR lợi nhuận hoạt động 5 năm | | 25% |
| Tăng trưởng | CAGR CFO 5 năm | | 20% |
| Tăng trưởng | Số năm doanh thu tăng / 5 | | 15% |
| Tăng trưởng | Tỷ lệ tái đầu tư | (Capex − khấu hao + Δ vốn lưu động) / NOPAT | 10% |
| Chống chịu | Nợ ròng / EBITDA | Thấp tốt; tiền ròng dương xếp tốt nhất | 35% |
| Chống chịu | Khả năng trả lãi | EBIT / chi phí lãi vay | 30% |
| Chống chịu | Thanh khoản hiện hành | TS ngắn hạn / nợ ngắn hạn | 15% |
| Chống chịu | Sụt giảm lợi nhuận lớn nhất 5 năm | Thấp tốt | 20% |

**`BANK`** (cập nhật 24/09/2026 — xem D24)

| Chiều | Chỉ tiêu | Trọng số |
|---|---|---:|
| Chất lượng | ROA trung bình 3 năm | 30% |
| Chất lượng | ROE trung bình 3 năm | 20% |
| Chất lượng | Ổn định NIM (nguồn **KBS**) | 25% |
| Chất lượng | Chi phí / thu nhập hoạt động (thấp tốt) | 25% |
| Tăng trưởng | CAGR thu nhập hoạt động 5 năm | 30% |
| Tăng trưởng | CAGR lợi nhuận trước thuế 5 năm | 30% |
| Tăng trưởng | CAGR cho vay khách hàng 5 năm | 20% |
| Tăng trưởng | Tăng trưởng thu nhập ngoài lãi 3 năm | 20% |
| Chống chịu | VCSH / tổng tài sản | 45% |
| Chống chịu | Ổn định chi phí tín dụng (độ lệch chuẩn chi phí dự phòng / dư nợ) | 30% |
| Chống chịu | Cho vay / tiền gửi khách hàng (thấp tốt) | 25% |

**NIM lấy từ nguồn `KBS` của chính `vnstock`** — không phải API bên ngoài. Bảng `ratio` của nguồn mặc định `VCI` dừng ở 2018 (§5.4); `Finance(source='KBS')` có 2022–2025 và phủ **18/18** ngân hàng trong rổ. KBS trả phần trăm, `adapter.attach_bank_ratios` đổi sang tỷ lệ — chỗ đổi đơn vị duy nhất.

**Đã gỡ: tỷ lệ nợ xấu và bao phủ nợ xấu.** Khảo sát 24/09/2026 ba nguồn:

| Nguồn | Nợ xấu |
|---|---|
| vnstock / VCI | bảng `ratio` dừng ở 2018 |
| vnstock / KBS | 32 chỉ tiêu, **không cái nào** về nợ xấu |
| TCBS | có `nonPerformingLoans`, `provisionOnNonPerformingLoans` — nhưng là **API nội bộ của công ty chứng khoán**, không tài liệu, GitHub Actions không gọi được qua MCP |

Để hai chỉ tiêu lại với giá trị `None` vĩnh viễn nghĩa là độ phủ Chất lượng 0,60 và Chống chịu 0,65 — dưới ngưỡng 0,70 — nên **cả 18 ngân hàng bị khóa ở "Thiếu dữ liệu" mà màn hình không nói vì sao**. Trọng số của chúng chia lại cho các chỉ tiêu còn lại, giữ nguyên thứ tự ưu tiên.

**Hệ quả phải nói ra:** chiều Chống chịu của ngân hàng ở đây đo bằng **vốn và thanh khoản**, không đo chất lượng tài sản. `BANK_NOT_EVALUATED` đẩy điều này ra metadata, và màn Watchlist / Chi tiết mã hiện dòng "Chưa xét" cho riêng mã ngân hàng.

**Kiểm định (12 mã có cache, 24/09/2026):** độ phủ **100% cả ba chiều**. HDB 83/87/69 cao nhất; EIB 16/4/80 — vốn dày nhưng sinh lời kém; STB 36/26/31 thấp đều, đúng với ngân hàng còn nợ tồn đọng.

**`SECURITIES`**

| Chiều | Chỉ tiêu | Trọng số |
|---|---|---:|
| Chất lượng | ROE trung bình 3 năm | 30% |
| Chất lượng | Tỷ trọng doanh thu lặp lại (môi giới + lãi cho vay ký quỹ) / doanh thu hoạt động | 35% |
| Chất lượng | Rủi ro tự doanh: tài sản FVTPL / VCSH (thấp tốt) | 35% |
| Tăng trưởng | CAGR doanh thu hoạt động 5 năm | 40% |
| Tăng trưởng | CAGR LN sau thuế 5 năm | 40% |
| Tăng trưởng | Tăng trưởng dư nợ cho vay ký quỹ 3 năm | 20% |
| Chống chịu | Dư nợ ký quỹ / VCSH (thấp tốt) | 35% |
| Chống chịu | Tổng nợ / VCSH (thấp tốt) | 35% |
| Chống chịu | Sụt giảm lợi nhuận lớn nhất 5 năm (thấp tốt) | 30% |

**`REAL_ESTATE`** (chủ đầu tư bất động sản — thiết kế 23/09/2026)

| Chiều | Chỉ tiêu | Trọng số |
|---|---|---:|
| Chất lượng | ROE trung bình 5 năm | 25% |
| Chất lượng | Biên gộp trung bình 5 năm | 25% |
| Chất lượng | CFO / LN ròng 5 năm | 25% |
| Chất lượng | Vòng quay hàng tồn kho (doanh thu / tồn kho bình quân) | 25% |
| Tăng trưởng | CAGR doanh thu 5 năm | 35% |
| Tăng trưởng | CAGR LN sau thuế 5 năm | 35% |
| Tăng trưởng | Số năm doanh thu tăng / 5 | 30% |
| Chống chịu | Tổng nợ vay / VCSH (thấp tốt) | 35% |
| Chống chịu | Khả năng trả lãi | 25% |
| Chống chịu | Thanh khoản hiện hành | 15% |
| Chống chịu | Sụt giảm lợi nhuận lớn nhất 5 năm (thấp tốt) | 25% |

Ba khác biệt so với `NON_FINANCIAL`, mỗi cái dẫn tới một lựa chọn cụ thể:

1. **Lợi nhuận lồi lõm theo chu kỳ bàn giao** → mọi trung bình lấy **5 năm**, không phải 3. Ba năm rơi trọn vào giữa một chu kỳ xây dựng là chuyện bình thường; khi đó số 3 năm nói về giai đoạn chứ không nói về doanh nghiệp.
2. **EBITDA nhảy theo năm bàn giao** → không dùng `net_debt_ebitda` (năm không bàn giao thì mẫu số gần 0, tỷ số vô nghĩa). Thay bằng `debt_equity` — mẫu số là vốn chủ, ổn định qua chu kỳ.
3. **Hàng tồn kho là quỹ đất**, không phải hàng ế. Nhưng quỹ đất nằm im vẫn là vốn chết, nên vòng quay tồn kho là chỉ báo chất lượng. Đây là chỉ tiêu bắt đúng NVL (0,05 so với VHM 1,65).

**Đã thử và BỎ — "người mua trả tiền trước".** Đây là chỉ báo dẫn dắt doanh thu, nên ban đầu đưa vào chiều Tăng trưởng. Đo thật trên 11 mã có đủ dữ liệu, ứng trước / doanh thu:

| | NVL | VHM |
|---|---:|---:|
| Ứng trước / doanh thu | **2,92** | 0,61 |

NVL — mã kiệt quệ nhất rổ — đứng **đầu**, chỉ vì doanh thu sụp từ ~15.000 xuống 6.966 tỷ nên mẫu số co lại. Đã thử ba mẫu số khác (tồn kho, tổng tài sản, vốn chủ): không cái nào tách được "hợp đồng sắp bàn giao" khỏi "tiền đã thu của dự án đắp chiếu", vì tiền thật sự nằm đó ở cả hai trường hợp. Lý do sâu hơn: **ứng trước là một khoản NỢ**, và với chủ đầu tư kiệt quệ đó là nghĩa vụ không trả được. Ba chỉ tiêu đúng hơn bốn chỉ tiêu có một cái lật ngược.

**Giới hạn đã biết.** Nhóm `REAL_ESTATE` gộp cả chủ đầu tư nhà ở, khu công nghiệp (IDC, BCM) và vận hành cho thuê (VRE). Vòng quay tồn kho của VRE là 33,28 so với NVL 0,05 — ba bậc độ lớn, do mô hình kinh doanh chứ không do chất lượng. Winsorize p5/p95 (áp dụng khi nhóm ≥ 20 mã; rổ 200 có 36 mã BĐS) kéo phần cực trị về, nhưng chưa xử lý gốc. Tách mô hình con cho KCN / cho thuê là việc của Phase 4.

**Kiểm định trên dữ liệu thật (11 mã có cache, 23/09/2026).** Xếp hạng theo tổng 3 chiều: IDC 199, VHM 196, VRE 191, … PDR 89, **NVL 59**. Hai mã cuối bảng đúng là hai chủ đầu tư kiệt quệ nhất thị trường — mô hình tự tìm ra, không được mách.

### 8.5 Cờ quản trị tự động

Điểm Quản trị = max(0, 100 − tổng điểm phạt). Mức phạt là mặc định cấu hình.

| Cờ | Điều kiện | Phạt | Nguồn |
|---|---|---:|---|
| Pha loãng | Số CP **phát hành lấy tiền** tăng bình quân 3 năm: > 10%/năm phạt 20; 5–10%/năm phạt 8 (một cờ hai mức, v3 D11, D18) | 20 / 8 | BCTC (vốn góp, tiền thu phát hành) |
| Lợi nhuận lệch dòng tiền | LN ròng dương nhưng CFO âm ở ≥ 3 trong 4 quý gần nhất, hoặc CFO/LN ròng 3 năm < 0,5 | 25 | BCTC |
| Công bố chậm | Chưa có số kỳ quý sau kết thúc kỳ + 45 ngày (dựa vào snapshot) | 10 | Snapshot |
| Đang bị cảnh báo | Trạng thái cảnh báo | 25 | Cần xác thực |
| Ý kiến kiểm toán ngoại trừ | BCTC năm hoặc bán niên gần nhất | 30 | Cần xác thực |

Phân biệt hai trường hợp (v3, D11):

- **Cờ tắt vì chưa có nguồn** ("Đang bị cảnh báo", "Ý kiến kiểm toán ngoại trừ" khi §14.2 chưa chốt): `enabled=False` trong config và **loại khỏi mẫu số** độ phủ. Nếu để trong mẫu số, độ phủ Quản trị của mọi mã chỉ còn 60% < ngưỡng 70% và chiều này rỗng cho cả universe.
- **Cờ bật nhưng thiếu dữ liệu ở một mã**: không tính là "không có cờ"; độ phủ chiều Quản trị của mã đó giảm tương ứng.

Trọng số độ phủ mỗi cờ bật bằng nhau.

Ghi chú định tính kiểu Fisher không tham gia điểm; chỉ là ô ghi chú trên trang chi tiết mã.

### 8.6 Chuẩn hóa và độ phủ

1. **Percentile** trong cùng mô hình, trong universe, tại cùng ngày chấm.
2. **Nhóm so sánh tối thiểu 8 mã.** Nhóm nhỏ hơn: không công bố percentile, chiều đó để trống (sẽ xét ngưỡng tuyệt đối ở giai đoạn sau).
3. **Winsorize p5/p95** chỉ khi nhóm có từ 20 mã; giá trị gốc vẫn lưu.
4. **CAGR** chỉ tính khi hai đầu kỳ đều dương; ngược lại là thiếu, không thay bằng số khác.
5. **Độ phủ** mỗi chiều = tổng trọng số chỉ tiêu có dữ liệu / tổng trọng số. Ngưỡng công bố 70%; dưới ngưỡng thì chiều đó để trống.
6. Khi độ phủ đạt ngưỡng, điểm tính lại trên phần trọng số có dữ liệu; danh sách chỉ tiêu thiếu được lưu và hiển thị.
7. **Dữ liệu cũ:** chỉ tiêu từ kỳ đã quá hai kỳ so với kỳ mới nhất của thị trường tính là thiếu.

### 8.7 Veto

Veto thắng mọi điểm số. Mỗi lần chạy tự đánh giá lại; veto tự hết khi điều kiện không còn đúng trên dữ liệu mới nhất.

| Veto | Nguồn |
|---|---|
| Hủy niêm yết, đình chỉ giao dịch | Danh sách mã / trạng thái (cần xác thực) |
| Bị kiểm soát hoặc hạn chế giao dịch | Cần xác thực |
| Ý kiến kiểm toán trái ngược hoặc từ chối | Cần xác thực |
| Không có BCTC hai kỳ quý liên tiếp | Snapshot |

Lỗi dữ liệu nghiêm trọng (phương trình kế toán lệch > 1%, số của cùng một kỳ thay đổi > 20% giữa hai snapshot mà không có giải thích) **không phải veto**: chiều liên quan bị để trống và tạo issue dữ liệu.

## 9. Định giá (dùng lại Valuation Engine)

Engine hiện có gồm 8 phương pháp, trọng số theo ngành, trả về upside và độ tin cậy. Blueprint chỉ thêm lớp quy đổi (đã có từ v3):

| Mức | Điều kiện |
|---|---|
| Hấp dẫn | Upside ≥ +20% và độ tin cậy ≥ 50% |
| Hợp lý | −10% ≤ upside < +20% và độ tin cậy ≥ 50% |
| Đắt | Upside < −10% và độ tin cậy ≥ 50% |
| Chưa có | Độ tin cậy < 50%, hoặc engine không chạy được |

Quy tắc:

- Không hiển thị nhãn STRONG BUY / BUY / HOLD / SELL của engine trên giao diện. Hiển thị mức, upside, độ tin cậy và phương pháp chính.
- Phương pháp đang ở dạng giản lược (RNAV với hệ số vùng mặc định, SOTP chỉ dùng số tổng hợp) nên bị giới hạn độ tin cậy tối đa dưới ngưỡng 50% cho đến khi hoàn thiện, để không tạo ra mức "Hấp dẫn" từ upside cực lớn nhưng thiếu cơ sở. Giới hạn áp khi phương pháp đó có **trọng số lớn nhất**; tên phải khớp tên engine trả về (`RNAV`, `SOTP Simplified`).
- Các trường hợp sau luôn là **"Chưa có"**, kèm lý do, kể cả khi mô hình đã tự ra HOLD (v3, D12):
  - Các phương pháp mâu thuẫn (độ phân tán > 40% quanh trung vị).
  - Nhóm tài chính (ngân hàng, chứng khoán, bảo hiểm) cho tới khi có nguồn NPL, bao phủ nợ xấu, CAR (§14.3). Engine vẫn tính fair value và upside để hiển thị.
  - Chỉ có 1 phương pháp khả dụng (không kiểm chéo được).
- Mã có upside ngoài [−80%, +200%] không được công bố; ghi vào `metadata.excluded_outliers` kèm lý do (vd. BAF: EBITDA năm đáy nhỏ hơn nợ ròng).
- Đầu ra: mỗi mã có `valuation_band` (mức, nhãn, lý do) và `guard_reason`; `metadata.band_counts` đếm theo mức. Web `/valuation` chỉ hiển thị mức, kèm dòng "không phải khuyến nghị mua bán".
- Trên trang chi tiết mã, hiển thị thêm P/E, P/B hiện tại so với dải 5 năm (từ historical multiples đã có) để đối chiếu trực quan.
- Ngưỡng 20% / −10% / 50% là mặc định, được hiệu chỉnh bằng `backtest.py` khi đã có ít nhất 3 tháng snapshot.

## 10. Trạng thái watchlist

Thứ tự đánh giá:

1. Có veto → **Loại**.
2. Thiếu bất kỳ chiều nào trong 4 chiều → **Thiếu dữ liệu**.
3. Quản trị < 30, hoặc Chất lượng < 30, hoặc Chống chịu < 25 → **Cần xem lại** (v3 D17: nhóm dưới cùng theo percentile).
4. Chất lượng ≥ 75, Tăng trưởng ≥ 70, Quản trị ≥ 70, Chống chịu ≥ 65:
   - Định giá Hấp dẫn hoặc Hợp lý → **Đủ chuẩn**.
   - Định giá Đắt hoặc Chưa có → **Theo dõi**.
5. Còn lại → **Theo dõi**.

Mỗi mã luôn kèm **lý do trạng thái** sinh tự động từ bước đã quyết định (ví dụ "Tăng trưởng 66, dưới ngưỡng 70", "Đạt 4 ngưỡng nhưng định giá Đắt").

Cờ phụ "Giảm mạnh": bất kỳ chiều nào giảm ≥ 15 điểm so với lần chấm trước. Cờ này chỉ hiển thị, không đổi trạng thái.

Các ngưỡng là mặc định cấu hình, không phải bằng chứng về khả năng dự báo.

## 11. Giao diện

### 11.1 Bốn màn hình (theo canvas v2)

| Màn | Nội dung chính |
|---|---|
| Hôm nay | Chỉ số và độ rộng thị trường; top mã scan (ưu tiên khớp nhiều chiến lược); mã watchlist đổi trạng thái hoặc định giá; tình trạng dữ liệu |
| Scan hằng ngày | Cột trái: chiến lược, Combined, điều kiện nền, liên kết Chất lượng. Bảng kết quả theo §7.3 |
| Watchlist dài hạn — **đã có** (`web/watchlist/`) | Tab trạng thái có số đếm; bảng 4 chiều dạng thanh ngắn có vạch ngưỡng; độ phủ; định giá; trạng thái; kỳ BCTC; lý do. Chưa có: P/E so với 5 năm |
| Chi tiết mã | Góc giao dịch: biểu đồ nến + MA, mức vùng vào/cắt lỗ, kế hoạch lệnh, tín hiệu đã kích hoạt, lưu ý T+2. Góc dài hạn: 4 chiều với từng chỉ tiêu, percentile, chỉ tiêu thiếu; định giá; ô luận điểm và điều kiện bán |

### 11.2 Dữ liệu cho web

| File | Nội dung | Tần suất |
|---|---|---|
| `web/data/<strategy>/latest.json` | Kết quả scan (đã có) | Mỗi phiên |
| `web/data/valuation/latest.json` | Định giá, có `valuation_band` (đã có) | Hằng tuần |
| `web/data/quality/latest.json` | Điểm 4 chiều, chỉ tiêu, độ phủ, cờ, veto, trạng thái, lý do | Hằng tuần |
| `web/data/quality/archive/<date>.json` | Snapshot cho so sánh và backtest | Hằng tuần |
| `web/data/health.json` | Tình trạng dữ liệu, issue mở | Mỗi lần chạy |

### 11.3 Quy ước hiển thị

- Màu giá theo bảng điện Việt Nam (tím trần, xanh lam sàn, xanh lá tăng, đỏ giảm, vàng tham chiếu), **chỉ dùng cho giá**.
- Trạng thái watchlist mã hóa bằng kiểu viền/tô: Đủ chuẩn (đặc), Theo dõi (viền liền), Cần xem lại (viền đứt), Thiếu dữ liệu (viền chấm, nền xám), Loại (gạch ngang).
- Dữ liệu thiếu hiển thị "—" hoặc "Thiếu dữ liệu", không hiển thị số giả.
- Font Be Vietnam Pro, số dạng bảng.

## 12. Lịch chạy

| Job | Nội dung | Lịch đề xuất |
|---|---|---|
| Daily scan (đã có) | OHLCV, chiến lược, archive; cần thêm điều kiện nền, `health.json` | Cron 12:05 và 23:05 ICT, thứ Hai–thứ Sáu. Thực tế GitHub xếp hàng trễ: ca 12:05 chạy ~16:30–17:30, ca 23:05 hay chạy sau nửa đêm |
| Weekly valuation (đã có) | Định giá universe (`--limit 100 --period year`), ghi sổ snapshot BCTC | Chủ nhật 07:09 ICT (00:09 UTC) |
| Data freshness alert (đã có) | Kiểm độ tươi `web/data/latest.json` theo lịch giao dịch | 08:07 ICT hằng ngày |
| Weekly quality (đã có) | `run_quality.py` trong workflow weekly-valuation: chấm 4 chiều, veto, trạng thái; lấy thêm BCTC quý (~3 lượt/mã) | Ngay sau bước định giá, cùng job và universe; hỏng thì định giá vẫn công bố, job đỏ để mở issue |

Không chạy hai workflow có gọi vnstock cùng lúc: chung một `VNSTOCK_API_KEY` (bản cộng đồng 60 request/phút) thì cả hai cùng chậm.

## 13. Kiểm soát chất lượng dữ liệu

| Kiểm tra | Hành động khi lỗi |
|---|---|
| Lần lấy trả rỗng hoặc lỗi | Giữ bản cũ, gắn `stale`, tạo issue |
| Cache thanh khoản cũ hơn 30 ngày | Coi như **không có số đo**, mã rơi xuống bậc 2 khi xếp universe (D23) |
| Số mã trong danh sách giảm > 5% so với lần trước | Dừng ghi đè, tạo issue |
| OHLC sai logic (high < low, giá ≤ 0) | Loại phiên đó, tạo issue |
| Giá nhảy > biên độ sàn mà không có sự kiện điều chỉnh | Tạo issue, không phát tín hiệu cho mã đó |
| Phương trình kế toán lệch > 1% | Để trống chiều liên quan, tạo issue |
| Số của cùng kỳ đổi > 20% giữa hai snapshot | Tạo issue, dùng bản mới nhưng gắn cờ |
| Đơn vị không nhất quán | Chặn nạp, tạo issue |

Mọi issue hiển thị trong khối "Tình trạng dữ liệu" của màn Hôm nay.

**Đã có (v3):** cổng độ phủ và cổng thời gian của archive (§7.5); cổng stale (tỷ lệ mã StaleCache); cổng đơn vị giá và upside ±300% ở bước Verify của weekly valuation; issue `workflow-failure` khi workflow hỏng; chuông độ tươi `data-freshness`. **Chưa có:** các kiểm tra còn lại trong bảng trên và `health.json`.

## 14. Các mục cần chốt

1. ~~**Lưu luận điểm cá nhân.**~~ **Đã chốt 23/09/2026 (D20): lưu trong trình duyệt.** Ô luận điểm và điều kiện bán nằm ở cuối màn Chi tiết mã, lưu vào `localStorage` theo từng mã. Hệ quả được nói thẳng trên màn hình chứ không giấu: chỉ có trên máy và trình duyệt đó. Có nút xuất/nhập tệp JSON để mang sang máy khác. Ghi hỏng (trình duyệt chặn lưu trữ) thì **báo ra màn hình** — khác với các lựa chọn giao diện khác vốn im lặng bỏ qua, vì ở đây là chữ người dùng vừa gõ.
2. ~~**Nguồn ý kiến kiểm toán và trạng thái cảnh báo/kiểm soát.**~~ **Đã chốt 23/09/2026 (D21): bỏ hai cờ và hai veto.** Khảo sát cùng ngày: vnstock không có; TCBS có `getListAuditFirm` nhưng chỉ cho **tên** công ty kiểm toán và năm, không có ý kiến kiểm toán; `getTickerOverview` không có trường cảnh báo/kiểm soát. Trạng thái cảnh báo được công bố dạng tin/sự kiện chứ không phải trường có cấu trúc. Hai cờ `warning_status`/`qualified_opinion` và hai veto `suspended_or_controlled`/`adverse_opinion` đã gỡ hẳn khỏi cấu hình, và ghi vào `GOVERNANCE_NOT_EVALUATED`/`VETO_NOT_EVALUATED` để giao diện nói rõ "Chưa xét" thay vì im lặng (§8.5).
3. ~~**Trường ngân hàng**~~ **Đã chốt 24/09/2026 (D24).** NIM lấy được từ `vnstock` nguồn **KBS** (2022–2025, phủ 18/18 mã) — không cần API bên ngoài. Nợ xấu và bao phủ nợ xấu **không nguồn nào có**, đã gỡ khỏi mô hình và ghi vào `BANK_NOT_EVALUATED` để màn hình nói "Chưa xét". Chi tiết ở §8.4. Định giá nhóm tài chính vẫn "Chưa có" (§9) — đó là lớp chặn riêng, không liên quan.
4. ~~**Vùng vào / cắt lỗ / mục tiêu**~~ **Đã chốt và đã làm 22–23/09/2026.** Cắt lỗ = hỗ trợ gần nhất dưới giá đóng cửa, mục tiêu = kháng cự gần nhất trên giá, R:R = (mục tiêu − giá) / (giá − cắt lỗ); bỏ cột "vùng vào"; không hiển thị R:R khi thiếu một trong hai mức (`backend/scanner/trade_levels.py`, cột trên màn Scan).
5. ~~**N của universe Module B**~~ **Đã chốt 23/09/2026: 200.** Đo thật (run 35874233924, `limit=200`): định giá **20 phút**, chấm chất lượng **19 phút** — tổng ~40 phút trên trần 90+45.

   | | 100 mã (22/09) | 200 mã (23/09) |
   |---|---:|---:|
   | "Thiếu dữ liệu" | 43% | **35%** |
   | Có mức định giá dùng được | 5 | **18** |
   | Đổi trạng thái do đổi rổ | — | **0/100 mã chung** |

   Lo ngại ban đầu — percentile tính trong nội bộ universe nên đổi rổ sẽ làm hàng loạt mã đổi trạng thái — **đã được bác bỏ bằng số liệu**: 0/100 mã chung đổi trạng thái. Điểm có dịch (Chất lượng lệch TB 1,9 điểm, Tăng trưởng 3,0, Chống chịu 1,0) nhưng không đủ vượt ngưỡng nào; Quản trị lệch 0,0 vì nó là 100 trừ mức phạt chứ không phải percentile.

   Tách được phần tăng: **+1 mã do khác ngày, +12 mã do thêm 100 mã mới**. Rổ 100 mã mới có tỷ lệ ra định giá 12%, cao hơn 6% của rổ cũ.

   **Rủi ro còn lại:** lượt đo có cache ấm cho ~một nửa số mã; lượt đầu với cache lạnh sẽ lâu hơn, và hôm nguồn chậm như 21/09 có thể chạm trần 90 phút. Hỏng theo hướng an toàn — quá giờ thì không đẩy gì lên.

   **Hệ quả:** rổ 200 có 36 mã bất động sản, 34 trong đó "Thiếu dữ liệu" vì mô hình `REAL_ESTATE` chưa bật — việc bật mô hình đó nay đáng giá hơn hẳn (15 → 36 mã).
6. ~~**Backtest chiến lược trading**~~ **Đã chốt 25/09/2026 (D27): có, đưa vào Phase 4.** Archive tín hiệu theo phiên đã chạy từ 18/09 (`web/data/*/archive/<ngày>.json`), nên dữ liệu đầu vào đang tích lũy sẵn — không cần thêm gì để bắt đầu thu thập. Còn thiếu: phần đo (giá sau N phiên so với tín hiệu) và quy ước tính. Xem §16 về survivorship và look-ahead trước khi công bố bất kỳ con số nào.

## 15. Lộ trình

| Phase | Nội dung | Điều kiện xong |
|---|---|---|
| 0. Dọn dẹp — **đã xong phần chính** | Không merge `rebuild/vercel-fisher`; lưu tài liệu vào `docs/`; xác thực các mục "Cần xác thực" ở §5.1, §7.1 | Có kết quả xác thực cho từng mục. Còn: trạng thái cảnh báo/kiểm soát, ý kiến kiểm toán (§14.2), tham số chiến lược §7.1 |
| 0.5. Nền dữ liệu — **đã xong 22/09** | F1 dữ liệu định giá thật; F2 giữ 8 kỳ BCTC; F3 sổ snapshot point-in-time; F9 bot push không rebase | Đã xác nhận trên runner thật |
| 1. Quality scoring — **đã chạy được 22/09** | Cấu hình, snapshot BCTC, chỉ tiêu 3 mô hình, cờ quản trị, độ phủ, veto, status engine, `quality/latest.json` | Chạy thật 100/100 mã, mỗi trạng thái có lý do: 52 Theo dõi, 16 Cần xem lại, 32 Thiếu dữ liệu (ngân hàng thiếu NPL/NIM, BĐS/bảo hiểm chưa kích hoạt) |
| 2. Giao diện — **còn màn Hôm nay** | 4 màn hình theo canvas v2 trên `web/` hiện có. Đã xong: Scan (§7.2–7.4), Watchlist, Chi tiết mã (§11.1) | Hiển thị đúng dữ liệu thật, empty state rõ ràng |
| 3. Liên kết | Quy đổi định giá 4 mức, liên kết Chất lượng sang Module A, `health.json` | Hai module dùng chung universe và quy tắc |
| 4. Hiệu chỉnh | Backtest ngưỡng định giá (≥ 3 tháng snapshot); **backtest chiến lược trading (D27)**; tách mô hình con cho KCN / cho thuê trong `REAL_ESTATE` (§8.4). `INSURANCE` **không** trong phạm vi Phase 4 — cần universe rộng hơn nhiều hoặc chấm theo ngưỡng tuyệt đối thay vì percentile (D25) | Ngưỡng được cập nhật có ghi lại lý do |
| 5. Cá nhân hóa — **đã xong 23/09** | Ô luận điểm và điều kiện bán ở màn Chi tiết mã, lưu `localStorage` theo D20 | Gõ vào, đổi mã, quay lại vẫn còn; xuất/nhập tệp JSON chạy được; trình duyệt chặn lưu trữ thì báo ra màn hình |

## 16. Rủi ro

| Rủi ro | Kiểm soát |
|---|---|
| vnstock đổi API, giới hạn hoặc ngừng nguồn | Giữ bản cũ + cờ `stale`; cô lập lớp fetch để thay nguồn; theo dõi phiên bản thư viện |
| Look-ahead trong backtest | Quy tắc độ trễ công bố; snapshot theo `fetched_at` |
| Survivorship | Ghi rõ giới hạn trong mọi kết quả backtest |
| Percentile nhiễu ở nhóm nhỏ | Nhóm tối thiểu 8 mã; winsorize chỉ khi ≥ 20 mã |
| Upside cực lớn từ phương pháp giản lược | Giới hạn độ tin cậy; chặn ở ngưỡng 50% |
| Điểm tốt nhưng quản trị xấu | Chiều Quản trị độc lập + veto |
| Lộ dữ liệu cá nhân qua repo public | Không commit luận điểm, danh mục; secret chỉ trong GitHub Secret |
| Hiểu nhầm kết quả là khuyến nghị | Không hiển thị nhãn mua/bán; ghi "mức gợi ý, không phải lệnh" |
| Thư viện phụ thuộc ghi file cấu hình AI ngoài repo (`vnai`) | `VNSTOCK_DISABLE_AGENT_SETUP=1`; ghim phiên bản `vnai`; nội dung "vnai-bootstrap" không phải chỉ dẫn của người dùng |
| Workflow hỏng im lặng | Issue `workflow-failure` tự mở/đóng; chuông độ tươi cho trường hợp không có run |
| Giá adjusted bị tính lại hồi tố | Backtest điều chỉnh giá archive theo sự kiện quyền phát sinh sau (§5.2.7) |

## 17. Phần v1 không còn áp dụng

Để tránh nhầm khi đọc lại tài liệu v1:

- Source registry HOSE/HNX/UPCOM/SSC/ISSUER_IR và 9 điều kiện bật connector.
- Parser PDF/XLS/HTML, Disclosure Registry, bucket lưu tài liệu gốc.
- Provenance kiểu "vị trí bằng chứng trong tài liệu" (thay bằng §5.3).
- 13 tiêu chí Fisher có trọng số và quy trình duyệt tay làm đầu vào điểm Quản trị.
- Kiến trúc Next.js + Supabase Auth/RLS và kế hoạch giải nén ZIP thay app cũ (§17–18 v1).
- Các chỉ tiêu không có trong BCTC chuẩn: thị phần môi giới, presales, pipeline pháp lý, rủi ro thảm họa, tăng trưởng chủ hợp đồng, rủi ro bên liên quan.

Những phần v1 được giữ lại về tinh thần: không gán điểm trung tính, ngưỡng độ phủ 70%, so sánh trong cùng mô hình ngành, tách định giá khỏi chất lượng, veto thắng điểm số, ngưỡng là cấu hình cần backtest.

---

### Quy ước cập nhật tài liệu

Khi logic thay đổi, cập nhật cùng lúc: tài liệu này (tăng số phiên bản trong tên file), file cấu hình tương ứng (`backend/scanner/quality/config.py`, ngưỡng định giá, ngưỡng trạng thái), test, và nhật ký quyết định ở §3. Không đổi ngưỡng, trọng số hoặc veto chỉ trên giao diện.
