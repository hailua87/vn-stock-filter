# VN-SCANNER + Valuation Engine

Dashboard quét tín hiệu kỹ thuật + định giá đa phương pháp cho thị trường chứng khoán
Việt Nam, dựa trên vnstock 4.x.

## Tổng quan

Project có 2 module chính:

### 1. Scanner kỹ thuật (đã có sẵn từ trước)
- **Pre-Breakout**: tín hiệu nén giá sắp break
- **Golden Cross dài hạn**: MA50 cắt lên MA200
- **Golden Cross ngắn hạn**: MA10 cắt lên MA20
- **Ichimoku**: TK cross, cloud signal
- **Combined**: lọc mã thỏa nhiều chiến lược
- **Analyzer**: phân tích chi tiết 1 mã

### 2. Valuation Engine (mới — full roadmap 5/5 items)
- **Industry Classifier** (4-tier): phân ngành cho 19 ValuationIndustry
- **8 phương pháp định giá**:
  - P/B-ROE Justified (2-stage growth) — Banking
  - P/E Multiple (3-approach blend) — Consumer, Tech
  - EV/EBITDA (mid-cycle) — Cyclicals, Utilities
  - DCF FCFF (2-stage + sensitivity) — Consumer Staples, Utilities
  - DDM (2-stage Gordon) — Banking, Utilities có cổ tức
  - RNAV Simplified — Real Estate
  - SOTP Simplified — Diversified Holding
  - Historical Multiple — fallback
- **Beta calculator** từ OHLCV cache + Blume adjustment
- **Historical multiples** P/E, P/B từ price × historical EPS/BVPS
- **Peer database** median per industry/metric
- **Backtest framework** validate accuracy theo thời gian
- **Web dashboard** cho valuation tại `/web/valuation/`

## Cấu trúc thư mục

```
vn-scanner/
├── backend/
│   ├── run_daily.py                       # Scanner kỹ thuật (đã có)
│   ├── run_valuation.py                   # ★ MỚI — chạy valuation
│   ├── backtest.py                        # ★ MỚI — backtest framework
│   ├── scanner/
│   │   ├── data_fetcher.py                # OHLCV fetch (đã có)
│   │   ├── financial_fetcher.py           # ★ MỚI — fetch BCTC vnstock
│   │   ├── market_metrics.py              # ★ MỚI — beta + historical multiples
│   │   ├── peer_database.py               # ★ MỚI — peer median DB
│   │   ├── criteria.py
│   │   └── strategies/
│   │       ├── golden_cross.py
│   │       ├── ichimoku.py
│   │       ├── indicators_ext.py
│   │       └── valuation/                 # ★ MỚI — valuation module
│   │           ├── __init__.py
│   │           ├── engine.py
│   │           ├── industry_classifier.py
│   │           ├── normalizer.py
│   │           ├── methods_pb_roe.py
│   │           ├── methods_pe.py
│   │           ├── methods_ev_ebitda.py
│   │           ├── methods_dcf_ddm.py
│   │           └── methods_rnav_sotp.py
│   ├── tests/                             # Tests scanner (đã có)
│   ├── test_valuation_integration.py      # ★ MỚI
│   ├── test_market_metrics.py             # ★ MỚI
│   ├── test_peer_database.py              # ★ MỚI
│   └── test_backtest.py                   # ★ MỚI
├── web/
│   ├── index.html                         # Scanner dashboard (đã có)
│   ├── app.js
│   ├── styles.css
│   ├── data/
│   │   └── valuation/                     # ★ MỚI
│   │       └── latest.json
│   └── valuation/                         # ★ MỚI — Valuation dashboard
│       ├── index.html
│       ├── valuation.css
│       └── valuation.js
├── .github/workflows/daily-scan.yml
├── README.md                              # File này
├── CHANGELOG.md
├── VALUATION_INTEGRATION.md               # ★ Hướng dẫn integration ban đầu
├── ROADMAP_PROGRESS.md                    # ★ Roadmap items 1-4
└── ROADMAP_FINAL.md                       # ★ Roadmap hoàn thiện 5/5
```

## Quick Start

### Setup
```bash
pip install vnstock pyarrow pandas numpy
export VNSTOCK_API_KEY=your_key_here
```

### Chạy scanner kỹ thuật
```bash
cd backend
python run_daily.py
```
Output: `web/data/<strategy>/latest.json`. Mở `web/index.html` để xem.

### Chạy valuation
```bash
cd backend
# Top 100 mã thanh khoản nhất
python run_valuation.py --limit 100

# Hoặc danh sách cụ thể
python run_valuation.py --tickers VIB,PAN,DBC,FPT,VNM,HPG

# Filter
python run_valuation.py --limit 200 --min-upside 15 --min-confidence 0.5
```
Output:
- `web/data/valuation/latest.json` — dashboard data
- `web/data/valuation/archive/<date>.json` — snapshot cho backtest
- `backend/data/peer_multiples.json` — peer database

Mở `web/valuation/index.html` để xem.

### Chạy backtest (sau >= 3 tháng tích lũy snapshots)
```bash
cd backend
python backtest.py --horizon 90 --min-confidence 50
```

### Chạy tests
```bash
cd backend
python test_valuation_integration.py   # E2E với 3 mã VIB/PAN/DBC
python test_market_metrics.py          # Beta + historical multiples
python test_peer_database.py           # Peer DB build/load
python test_backtest.py                # Backtest framework
```

## Schedule Production (GitHub Actions)

Thêm vào `.github/workflows/daily-scan.yml`:

```yaml
  valuation_weekly:
    if: github.event.schedule == '0 10 * * 1'  # Thứ Hai 17:00 ICT
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: '3.10' }
      - run: pip install vnstock pyarrow pandas numpy
      - env:
          VNSTOCK_API_KEY: ${{ secrets.VNSTOCK_API_KEY }}
        run: |
          cd backend
          python run_valuation.py --limit 150 --min-confidence 0.4
      - run: |
          git config user.email "bot@valuation.vn"
          git config user.name "Valuation Bot"
          git add web/data/valuation/ backend/data/peer_multiples.json
          git commit -m "valuation: weekly $(date +%Y-%m-%d)" || true
          git push
```

## Logic định giá theo ngành

```python
INDUSTRY_METHOD_WEIGHTS = {
    "Banking":            P/B-ROE 45% + P/E 25% + DDM 15% + Hist 15%
    "Real_Estate":        RNAV 50% + P/B 20% + P/E 10% + Hist 20%
    "Diversified_Holding":SOTP 30% + P/E 25% + EV/EBITDA 20% + ...
    "Consumer_Staples":   DCF 30% + P/E 35% + EV/EBITDA 20% + ...
    "Utilities":          DCF 35% + DDM 25% + EV/EBITDA 20% + ...
    "Steel_Metals":       EV/EBITDA 50% + P/B 25% + P/E 10% + Hist 15%
    "Agriculture":        EV/EBITDA 50% + P/B 25% + P/E 10% + Hist 15%
    "Technology":         P/E 40% + DCF 25% + EV/EBITDA 20% + Hist 15%
}
```

## Tài liệu chi tiết

- **VALUATION_INTEGRATION.md** — Hướng dẫn deploy ban đầu, schema JSON, FAQ
- **ROADMAP_PROGRESS.md** — Chi tiết items 1-4 (Beta, Historical, Peer DB, DCF/DDM)
- **ROADMAP_FINAL.md** — Items 5 + Web Dashboard + Backtest, deployment guide

## Status

| Item | Status |
|---|---|
| Beta thực từ regression | ✅ Done |
| Historical P/E, P/B chính xác | ✅ Done |
| Peer database theo ICB | ✅ Done |
| DCF FCFF + DDM | ✅ Done |
| RNAV + SOTP simplified | ✅ Done |
| Web dashboard | ✅ Done |
| Backtest framework | ✅ Done |
| **Tests** | ✅ 4/4 suites pass |

## Demo kết quả với 6 mã

```
VHM   Real_Estate              STRONG BUY   +85.8% conf=45%  (RNAV)
VIB   Banking                  STRONG BUY   +44.9% conf=65%
FPT   Technology               HOLD          -4.5% conf=73%
PAN   Diversified_Holding      HOLD          -6.7% conf=60%  (SOTP)
HPG   Steel_Metals             STRONG SELL  -34.3% conf=68%
DBC   Agriculture_Livestock    STRONG SELL  -45.0% conf=65%
```

## Caveat đã biết

1. RNAV cần region data từ thuyết minh BCTC (hiện default = "other" 1.10×)
2. SOTP simplified chỉ dùng aggregate, không phải segment-by-segment full
3. Beta cần OHLCV cache → chạy `run_daily.py` ít nhất 1 lần trước
4. Peer DB cần universe >= 50 mã để có >=3 mã/ngành
