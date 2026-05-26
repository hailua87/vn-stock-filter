# CHANGELOG — 2026-05-26

---

## Vấn đề mới nhất (2026-05-26 evening) — ACB partial data

User phát hiện sau khi đã apply tất cả fix v3 + valuation module: ACB hiển
thị giá 24.30 / KL 22M trên VN-SCANNER, trong khi SSI iBoard báo 24.80 /
58.82M cùng phiên 26/05/2026.

**Diagnosis:** vnstock VCI trả về data PARTIAL (có data lịch sử nhưng thiếu
phiên 26/05). Code v3 chỉ check `df is None or df.empty` → data partial vượt
qua check, được ghi vào cache, return df bình thường (StaleCache=False) →
strategy `evaluate()` không reject → output sai data dưới ngày đúng.

**Fix v4 (data_fetcher.py):**

Refactor toàn bộ `fetch_with_cache` để có **STRICT SESSION VALIDATION** ở
cuối function. Bất kể df đến từ đâu (cache fresh / merged / fresh fetch),
luôn check `df['Date'].max().date() >= last_session`. Nếu KHÔNG → flag
`StaleCache=True` → strategy reject.

Thêm guard: chỉ ghi cache mới khi refetch trả data tới phiên gần nhất —
tránh "infinite partial cache" (cache cũ partial → refetch partial → ghi
đè cache vẫn partial → lần sau vẫn miss).

3 smoke tests reproduce chính xác bug ACB và verify fix:
1. vnstock trả partial → StaleCache=True ✓
2. vnstock trả full → StaleCache=False ✓
3. Cache cũ partial + refetch partial → StaleCache=True (defense in depth) ✓

**Trade-off:** Mã nào vnstock không có data phiên gần nhất sẽ KHÔNG xuất
hiện trong kết quả scan. Đây là behavior đúng — thà thiếu mã còn hơn hiển
thị sai data. Mã đó sẽ tự xuất hiện lại khi vnstock catch up.

---

## Module Valuation (định giá cổ phiếu) — bundle riêng từ chat khác

Module valuation đã được phát triển trong session khác, gồm:

- `backend/scanner/strategies/valuation/` — 9 files:
  - `engine.py` — orchestrator chính
  - `industry_classifier.py` — phân loại ngành (banking, real estate, tech, etc.)
  - `methods_pb_roe.py` — P/B-ROE justified (cho banking)
  - `methods_pe.py` — P/E multiple
  - `methods_ev_ebitda.py` — EV/EBITDA (cho cyclical)
  - `methods_dcf_ddm.py` — DCF FCFF + DDM (với safeguards)
  - `methods_rnav_sotp.py` — RNAV/SOTP (cho real estate/holding)
  - `normalizer.py` — normalize fundamentals
- `backend/scanner/financial_fetcher.py` — fetch BCTC từ vnstock
- `backend/scanner/market_metrics.py` — beta, market parameters
- `backend/scanner/peer_database.py` — peer benchmark database
- `backend/run_valuation.py` — entry point pipeline valuation
- `backend/backtest.py` — backtest framework (90 ngày forward)
- `web/valuation/` — dashboard riêng:
  - `index.html`, `valuation.css`, `valuation.js`
- 4 test suites: `test_valuation_integration.py`, `test_market_metrics.py`,
  `test_peer_database.py`, `test_backtest.py`

Methods, weights, confidence theo industry và safeguards xem chi tiết trong
`ROADMAP_FINAL.md` và `VALUATION_INTEGRATION.md`.

---

# CHANGELOG — 2026-05-26

Bản update này fix một loạt bug phát hiện trong session 25-26/05/2026 khi user
nhận thấy giá VND trên VN-SCANNER (17.90) không khớp với CafeF (17.60).

Quá trình điều tra phát hiện ra **nhiều bug chồng chéo**, chứ không phải chỉ 1
bug duy nhất như `PUSH_GUIDE.md` cũ giả định. Document này thay thế cho
`PUSH_GUIDE.md` cũ (đã xóa vì giả thuyết sai).

---

## Vấn đề ban đầu

User báo cáo giá VND trên VN-SCANNER ngày 25/05/2026 không khớp với CafeF:
- CafeF: 17.60 (+0.86%), KL 19.43M
- VN-SCANNER: 17.90 (+7.51%), KL 2.99M

Khối lượng chênh **6.5 lần** là dấu hiệu loại trừ ngay giả thuyết "adjustment cổ tức"
của `PUSH_GUIDE.md` cũ — cổ tức không ảnh hưởng KL.

---

## Các bug đã phát hiện và fix

### Bug 1 — vnstock 4.x bỏ source `TCBS` (MOST CRITICAL)

**Triệu chứng:** Mọi request fetch fail với:
```
ValueError: Lớp Quote chỉ nhận giá trị tham số source là kbs, vci, msn, dnse, binance, fmp, fmarket.
```

**Root cause:** `PUSH_GUIDE.md` cũ đặt `source='TCBS'` trong `fetch_ohlcv`, nhưng
vnstock 4.x đã bỏ TCBS. Mọi fetch raise ValueError → fallback xuống cache cũ →
data sai phiên hiển thị trên web.

**Fix (`backend/scanner/data_fetcher.py`):**
- Đổi default `source='TCBS'` → `source='vci'` (lowercase, hợp lệ)
- Đổi `adjusted=False` → `adjusted=True` (VCI luôn trả adjusted price)
- Xóa fallback `if source == 'TCBS' ... try VCI` (vô nghĩa)
- Thêm **fast-fail RuntimeError** khi gặp ValueError "Lớp Quote chỉ nhận" —
  tránh retry 3 lần × 500 mã × 2-4s = ~1h CI vô ích trước khi fail

**Trade-off:** VCI trả adjusted price (đã trừ cổ tức quá khứ). Giá sẽ KHÁC
CafeF/SSI cho mã có cổ tức gần đây. Ví dụ VND có cổ tức 500đ chia 15/07/2025
→ giá VCI thấp hơn CafeF 0.50. Đây là **trade-off có chủ ý**: adjusted price
chính xác hơn cho phân tích kỹ thuật (RSI/Ichimoku/Fibonacci không bị gap giả).

### Bug 2 — Code duplicate trong `data_fetcher.py`

**Triệu chứng:** File có **2 bản** của 5 hàm (`fetch_ohlcv`, `fetch_with_cache`,
`fetch_universe`, `_load_fallback_universe`, `fetch_vnindex`) — lines 257-455
và lines 503-692.

**Root cause:** Code rot. Python override với bản SAU. Bản 2 thiếu rate-limit
retry và VCI fallback so với bản 1.

**Fix:** Xóa duplicate. File từ 692 dòng còn 538 dòng. Một định nghĩa duy nhất
mỗi function.

### Bug 3 — Logic stale-cache phantom session

**Triệu chứng:** Header web báo "Thứ Hai 25/05" nhưng data hiển thị là của
Thứ Sáu 22/05 (KL 22/05, giá 22/05).

**Root cause:** Trong `fetch_with_cache`:
```python
if last_date >= end - timedelta(days=1):
    df = cached[...]  # dùng cache cũ
```
Logic này coi cache là "tươi" nếu chỉ cũ 1 ngày, BẤT KỂ phiên đó có phải phiên
giao dịch hợp lệ hay không. Khi refetch fail (Bug 1 ở trên), code rơi vào
nhánh `else: df = cached` → dùng dữ liệu Thứ Sáu mà vẫn báo cáo dưới ngày
Thứ Hai (header lấy từ `datetime.now()`).

**Fix:**
- Thêm hàm `_last_trading_session(today)` trả về phiên giao dịch gần nhất theo
  lịch (lùi qua Thứ Bảy/Chủ Nhật).
- Đổi check `last_date >= last_session` thay vì `last_date >= end - 1 day`.
- Khi refetch fail và phải dùng cache cũ, đánh dấu cột `df['StaleCache'] = True`.

### Bug 4 — Sanity check chiến lược không reject stale data

**Fix (`ichimoku.py`, `golden_cross.py`):**
- Thêm check ở đầu `evaluate()`: nếu `df['StaleCache']` là `True` → return None,
  mã không lọt vào kết quả scan.

### Bug 5 — `_sort_by_liquidity` glob sai pattern

**Triệu chứng:** Liquidity ranking không hoạt động → fallback hoàn toàn vào
curated list cứng.

**Root cause:** Default suffix là `_raw.parquet` (sau khi PUSH_GUIDE cũ đổi sang
TCBS), nhưng `_sort_by_liquidity` chỉ glob `*_adj.parquet` → liquidity dict
luôn rỗng.

**Fix:** Glob cả 2 pattern (`*_adj.parquet` và `*_raw.parquet`) với dedupe.
Sau khi fix Bug 1, default lại là `_adj.parquet` → đảo thứ tự ưu tiên.

### Bug 6 — `df.attrs` mất qua `pd.concat`/slice

**Root cause:** Ý định ban đầu của tôi là dùng `df.attrs['stale_cache']`, nhưng
`run_daily.py` gọi `pd.concat()` rồi `df[df['Ticker']==t]` để slice → attrs
bị mất hết.

**Fix:** Chuyển từ `df.attrs` sang cột `df['StaleCache']` (bảo toàn qua mọi
phép biến đổi pandas).

---

## Cải tiến (không phải fix bug)

### Cải tiến 1 — Workflow chạy 2 lần/ngày (intraday + EOD)

**File `.github/workflows/daily-scan.yml`:**

Trước đây: 1 cron 16:00 ICT (`0 9 * * 1-5`).

Sau:
- `0 5 * * 1-5` = **12:00 ICT** (INTRADAY, sau phiên sáng đóng cửa 30 phút)
- `0 10 * * 1-5` = **17:00 ICT** (EOD, sau phiên chiều đóng cửa 2 tiếng)

Đẩy EOD từ 16:00 → 17:00 vì đôi khi vnstock chưa cập nhật phiên T ngay lúc
16:00 (đóng cửa 14:45).

**Auto-detect intraday vs EOD** dựa trên giờ UTC (< 9 = intraday, ≥ 9 = EOD).

**Concurrency group** ngăn 2 lần chạy chồng nhau:
```yaml
concurrency:
  group: daily-scan
  cancel-in-progress: false
```

**Push retry với rebase** chống race condition giữa 2 lần chạy.

**Commit message phân biệt:**
- `chore: update signals YYYY-MM-DD [intraday HH:MM]`
- `chore: update signals YYYY-MM-DD [EOD HH:MM]`

**Excel artifact chỉ tạo cho EOD** (tiết kiệm storage).

**Cache key bumped v1 → v2** để invalidate cache cũ chứa data sai phiên.

### Cải tiến 2 — Tag JSON output với metadata run type

Workflow patch JSON bằng jq sau khi `run_daily.py` chạy xong:

```json
{
  "metadata": {
    ...,
    "run_type": "intraday" | "eod",
    "run_time_ict": "HH:MM",
    "run_date_ict": "YYYY-MM-DD"
  }
}
```

Không cần sửa Python — keeping the change minimal.

### Cải tiến 3 — Badge UI cho frontend (intraday vs EOD)

**Files: `web/index.html`, `web/styles.css`, `web/app.js`**

Thêm `<span class="run-badge" id="run-badge" hidden>` vào topbar.

3 trạng thái:
- **Cam nhấp nháy** `● INTRADAY 12:18` — data giữa phiên, chưa final
- **Teal tĩnh** `● EOD 17:03` — giá đóng cửa chính thức
- **Không badge** — archive cũ trước khi workflow tag metadata

Hover badge → tooltip giải thích chi tiết.

JS: thêm `state.runMetadata`, helper `extractRunMetadata()`, function
`renderRunBadge()`. 3 chỗ load JSON (`loadLatestFirst`, `loadDateData`,
`loadCombinedData`) đều đọc metadata.

---

## Lưu ý sau deploy

### 1. Xoá cache cũ (đã làm qua cache key bump v1→v2)

GitHub Actions cache sẽ tự miss lần đầu sau bump → workflow refetch toàn bộ
500 mã từ vnstock (~25-40 phút). Các lần sau dùng cache → nhanh 1-3 phút.

### 2. Giá KHÔNG khớp 100% với CafeF/SSI là BÌNH THƯỜNG

Đã verify với CRE và ABS ngày 26/05/2026:
- CRE: VN-SCANNER 8.00 vs CafeF 7.96 (chênh 0.5%)
- ABS: VN-SCANNER 3.09 vs CafeF 3.07 (chênh 0.65%)

Đây là **intraday timing divergence** — 2 nguồn snapshot ở thời điểm khác nhau
trong cùng phiên. Sau 17:00 (EOD), data sẽ khớp ~99% với CafeF vì cả 2 đều
dùng giá đóng cửa chính thức từ HOSE.

Với mã có cổ tức gần đây, chênh **đúng bằng số cổ tức** là expected
(adjusted price).

### 3. CI usage tăng gấp đôi

Từ ~440 phút/tháng → ~880 phút/tháng. Vẫn an toàn dưới quota GitHub free tier
(2000 phút/tháng).

---

## Test

- 39/39 unit tests pass (`pytest backend/tests/`)
- Smoke test source validation: invalid source raise RuntimeError (fast-fail)
- Smoke test `_last_trading_session`: T2/T7/CN/T4 đều đúng phiên gần nhất
- Frontend: `node --check app.js` syntax OK
- HTML: `run-badge` element + CSS class đầy đủ
- Workflow YAML: parse hợp lệ, 2 cron schedule đúng

---

## Files thay đổi

```
.github/workflows/daily-scan.yml  (rewrite)
backend/scanner/data_fetcher.py   (rewrite, 692 → 538 dòng)
backend/scanner/strategies/ichimoku.py     (+8 dòng sanity check)
backend/scanner/strategies/golden_cross.py (+4 dòng sanity check)
web/index.html  (+3 dòng badge element)
web/styles.css  (+41 dòng badge CSS)
web/app.js      (+70 dòng badge logic)
PUSH_GUIDE.md   (REMOVED — contained wrong diagnosis)
CHANGELOG.md    (this file — replaces PUSH_GUIDE)
```
