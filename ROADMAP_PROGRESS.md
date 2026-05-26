# Valuation Module — Roadmap Progress

Cập nhật ngày 26/05/2026. Hoàn thành 4/5 items trong roadmap ưu tiên ban đầu.

## ✅ Item 1: Beta thực từ regression (DONE)

**File mới:** `backend/scanner/market_metrics.py` → `calculate_beta()`

**Logic:**
- Đọc OHLCV từ parquet cache đã có (`_adj.parquet`) — không re-fetch
- Resample sang weekly returns (giảm noise daily)
- OLS regression với VN-Index log returns
- Loại outliers >3σ
- **Blume adjustment**: `β_adj = 0.67 × β_raw + 0.33 × 1.0` (giảm bias mean reversion)
- Sanity cap: 0.2 ≤ β ≤ 2.5

**Test:** `test_market_metrics.py` — recover được synthetic beta 0.5/1.0/1.5 với sai số ±0.15.

## ✅ Item 2: Historical P/E, P/B chính xác (DONE)

**File mới:** `backend/scanner/market_metrics.py` → `calculate_historical_multiples()`

**Logic:**
- Lấy EPS, BVPS cho mỗi năm từ ratio history (5 năm)
- Với mỗi cuối năm (31/12), lookup giá đóng cửa từ OHLCV cache trong window ±45 ngày
- Tính P/E và P/B cho mỗi năm + điểm hiện tại (TTM)
- Sanity filter: 0.5 < P/E < 200, 0.1 < P/B < 20
- Median, P25, P75

**Trước/sau:**
- Trước: P/E_median = current × ±20% (proxy ±20% hardcoded)
- Sau: P/E_median tính từ thực tế giá × EPS từng năm

**Tích hợp:** `engine.py` gọi `enrich_with_market_metrics()` trước normalize. Normalizer
detect `historical_multiples.fallback=False` và dùng giá trị thực, ngược lại fall back proxy.

## ✅ Item 3: Peer Database (DONE)

**File mới:** `backend/scanner/peer_database.py`

**Logic 2-pass trong run_valuation.py:**
1. **Pass 1**: Fetch fundamentals + enrich + classify industry cho toàn universe.
   Extract `{ticker, industry, pe, pb, ev_ebitda, roe, npl_ratio}` → build peer DB
2. **Pass 2**: Run valuation engine với peer DB sẵn có

**Schema** (`data/peer_multiples.json`):
```json
{
  "updated_at": "2026-05-26",
  "industries": {
    "Banking": {
      "ticker_count": 18,
      "pe": {"median": 8.2, "p25": 6.5, "p75": 11.0, "n": 15},
      "pb": {"median": 1.5, "p25": 1.2, "p75": 2.0, "n": 15},
      "roe": {"median": 0.19, "p25": 0.15, "p75": 0.22, "n": 15}
    }
  }
}
```

**Filter logic:**
- Cyclical (Steel, Agriculture): KHÔNG có peer P/E (biến động quá lớn) — chỉ EV/EBITDA, P/B
- Banking: KHÔNG có peer EV/EBITDA (không áp dụng) — chỉ P/E, P/B, ROE
- Trim outliers: bỏ top/bottom 10% trước khi compute stats

**Tích hợp:** Methods P/E và EV/EBITDA tự động dùng peer median nếu peer DB có; fall back
VN-Index hoặc hardcode nếu chưa có. Quality adjustment dựa trên ROE vs peer ROE.

**Test:** `test_peer_database.py` — build, save, load, lookup đều pass.

## ✅ Item 4: DCF FCFF & DDM (DONE)

**File mới:** `backend/scanner/strategies/valuation/methods_dcf_ddm.py`

### DCF FCFF
- 2-stage: explicit forecast N năm + terminal Gordon
- **WACC** từ market cap weight + book debt weight, CAPM cho CoE, rf+spread cho CoD aftertax
- Growth fade: linear decay từ `g_initial` (CAGR 5y, cap 25%) về `g_terminal` (~4.5%)
- **Sensitivity table 5×5** cho WACC × terminal g
- **Sanity caps**: fair value bị cap 0.4× đến 3× giá hiện tại để tránh extreme outputs
- Warning nếu terminal share > 80%

### DDM
- 2-stage giống DCF nhưng dùng DPS thay vì FCFF
- Nếu DPS = 0, ước tính từ EPS × payout ratio
- Confidence boost nếu payout > 40% hoặc dividend yield > 3%
- Confidence penalty nếu growth > 25% (DDM kém phù hợp cho growth stocks)

### Industry weights mới (engine.py)

| Industry | Top method | Weight |
|---|---|---|
| Banking | P/B-ROE 45% + P/E 25% + **DDM 15%** + Hist 15% | DDM mới cho banking |
| Consumer Staples | **DCF 30%** + P/E 35% + EV/EBITDA 20% | DCF dominant cho stable |
| Utilities | **DCF 35% + DDM 25%** + EV/EBITDA 20% | DCF + DDM tổng 60% |
| Technology | P/E 40% + **DCF 25%** + EV/EBITDA 20% | DCF cho FPT |
| Telecom | **DCF 30%** + EV/EBITDA 30% + P/E 20% + DDM 10% | DCF + DDM cao |

## ⏳ Item 5: RNAV cho BĐS, SOTP cho holding (PENDING)

Còn lại theo roadmap ban đầu:
- RNAV cho real estate (VHM, NLG, KDH, NVL): cần data từng dự án từ BCTC thuyết minh
- SOTP cho holding (PAN, MSN, VIC, GEX): cần định giá từng segment riêng

Đây là 2 items đòi hỏi data segment chi tiết hơn vnstock cung cấp, nên cần parse báo cáo
thường niên hoặc dùng analyst reports làm input. Để sau khi có data source phù hợp.

## Cải tiến tổng thể cho aggregation

Sau khi thêm DCF/DDM, **mỗi method có sanity cap** ngay tại nguồn, nên aggregation
weighted average không còn bị skew bởi DCF extreme. Verdict đáng tin cậy hơn.

## Files mới được thêm

```
backend/scanner/
├── market_metrics.py              ★ Beta + Historical Multiples
├── peer_database.py               ★ Peer comparable database
└── strategies/valuation/
    └── methods_dcf_ddm.py         ★ DCF FCFF + DDM

backend/
├── test_market_metrics.py         ★ Unit tests (4 tests pass)
└── test_peer_database.py          ★ Unit tests (3 tests pass)
```

## Performance dự kiến trên universe thật

| Universe size | Pass 1 (fetch + enrich) | Pass 2 (value) | Total |
|---|---|---|---|
| 50 mã  | ~3 phút (60 req/min limit) | ~30 giây | ~4 phút |
| 100 mã | ~6 phút | ~1 phút | ~7 phút |
| 200 mã | ~12 phút | ~2 phút | ~14 phút |

Pass 1 chậm hơn vì gồm: fetch overview + 4 financial statements + price history (qua cache).
Pass 2 nhanh vì chỉ tính toán in-memory.

**Khuyến nghị**: Chạy weekly thứ 2 lúc 17h ICT (sau khi tuần kết thúc), schedule trong
`.github/workflows/daily-scan.yml`:

```yaml
on:
  schedule:
    - cron: '0 10 * * 1'  # Thứ Hai 17:00 ICT = 10:00 UTC
```
