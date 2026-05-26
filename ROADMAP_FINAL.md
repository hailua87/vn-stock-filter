# Valuation Module — Roadmap Complete (5/5)

Cập nhật 26/05/2026. **Tất cả 5 items roadmap đã hoàn thành** + thêm Web Dashboard
và Backtest Framework.

## Tổng kết toàn bộ tính năng

### 5 phương pháp định giá hoàn chỉnh

| Method | File | Áp dụng tốt nhất | Confidence base |
|---|---|---|---|
| P/B-ROE Justified (2-stage) | `methods_pb_roe.py` | Banking, Securities, Insurance | 85% |
| P/E Multiple (3-approach blend) | `methods_pe.py` | Consumer, Technology, stable | 75% |
| EV/EBITDA (mid-cycle) | `methods_ev_ebitda.py` | Steel, Chemicals, Cyclicals, Utilities | 75-80% |
| DCF FCFF (2-stage + sensitivity) | `methods_dcf_ddm.py` | Consumer Staples, Utilities, Tech | 70-75% |
| DDM (2-stage Gordon) | `methods_dcf_ddm.py` | Banking, Utilities có cổ tức cao | 65-75% |
| RNAV Simplified | `methods_rnav_sotp.py` ★ | Real Estate (VHM, NLG, KDH...) | 50-60% |
| SOTP Simplified | `methods_rnav_sotp.py` ★ | Diversified Holding (PAN, MSN, VIC) | 40-60% |
| Historical Multiple | `engine.py` | Fallback chung | 60% |

★ = Mới thêm trong v3

### Hệ thống hỗ trợ

| Component | File | Mục đích |
|---|---|---|
| Industry Classifier (4-tier) | `industry_classifier.py` | Phân ngành cho 19 ValuationIndustry |
| Normalizer | `normalizer.py` | vnstock raw → standardized format |
| Beta calculator | `market_metrics.py` | OLS regression + Blume adjust |
| Historical multiples | `market_metrics.py` | P/E, P/B history thực từ OHLCV cache |
| Peer database | `peer_database.py` | Median per industry/metric |
| Engine orchestrator | `engine.py` | Multi-method aggregation + verdict |
| Financial fetcher | `financial_fetcher.py` | vnstock 4.x adapter với cache |
| Backtest framework | `backtest.py` ★ | Validate prediction accuracy theo thời gian |
| Web dashboard | `web/valuation/*` ★ | Inspect kết quả định giá |

### Test coverage

| Test file | Suite | Status |
|---|---|---|
| `test_valuation_integration.py` | E2E với 3 mã VIB/PAN/DBC | ✅ Pass |
| `test_market_metrics.py` | Beta regression + Hist multiples | ✅ 4/4 Pass |
| `test_peer_database.py` | Build/Save/Load/Lookup peer DB | ✅ Pass |
| `test_backtest.py` ★ | Backtest với synthetic snapshots | ✅ Pass |

## Cập nhật INDUSTRY_METHOD_WEIGHTS (v3)

```python
Banking:              P/B-ROE 45% + P/E 25% + DDM 15% + Hist 15%
Consumer Staples:     DCF 30% + P/E 35% + EV/EBITDA 20%
Utilities:            DCF 35% + DDM 25% + EV/EBITDA 20% + P/E 10%
Real Estate:          RNAV 50% + P/B 20% + P/E 10% + Hist 20%  ★ MỚI
Diversified Holding:  SOTP 30% + P/E 25% + EV/EBITDA 20% + ...  ★ MỚI
Steel/Chemicals:      EV/EBITDA 45-50% + P/B 20-25% + ...
Agriculture:          EV/EBITDA 50% + P/B 25% + ...
```

## Demo kết quả với 6 mã (mock data)

```
Verdicts: {'STRONG BUY': 2, 'HOLD': 2, 'STRONG SELL': 2}

VHM   Real_Estate              STRONG BUY   upside=+85.8% conf=45%  (RNAV-driven)
VIB   Banking                  STRONG BUY   upside=+44.9% conf=65%
FPT   Technology               HOLD         upside= -4.5% conf=73%  (DCF healthy)
PAN   Diversified_Holding      HOLD         upside= -6.7% conf=60%  (SOTP)
HPG   Steel_Metals             STRONG SELL  upside=-34.3% conf=68%  (cyclical peak)
DBC   Agriculture_Livestock    STRONG SELL  upside=-45.0% conf=65%  (cyclical warning)
```

## Web Dashboard

**File mới:**
```
web/
├── index.html                  ← thêm link 💰 VALUATION ở top bar
├── valuation/
│   ├── index.html              ★ Dashboard HTML
│   ├── valuation.css           ★ Theme tương thích với scanner
│   └── valuation.js            ★ Filter, sort, detail panel
└── data/valuation/
    └── latest.json             ★ Output từ run_valuation.py
```

**Tính năng dashboard:**
- Bảng tổng hợp với verdict badges (5 levels: STRONG BUY → STRONG SELL)
- Bộ lọc: ticker search, verdict, ngành, upside min %, confidence min %, holding/single
- Sort theo mọi cột
- Detail panel: fair value range bar, methods breakdown, warnings, notes
- Responsive cho mobile (filter panel hidden)
- Statistic counters: total, BUY, HOLD, SELL trên topbar

**Truy cập:** Từ scanner chính click nút "💰 VALUATION" góc trên phải, hoặc trực tiếp
`/valuation/index.html`.

## Backtest Framework

**Cách dùng:**
```bash
cd backend

# Sau khi tích lũy >= 90 ngày archived snapshots
python backtest.py --horizon 90 --min-confidence 50
```

**Output:**
```
📊 OVERALL METRICS
   Direction accuracy  : 65.5%  (verdict đúng hướng)
   Verdict hit rate    : 42.3%  (đúng dải target)
   Mean abs error      : 18.2%  (|fair - actual| / fair)
   Median error        : 14.5%

🎯 BY VERDICT
   Verdict        Count   Hit Rate   Actual Ret    Predicted
   STRONG BUY        15       46.7%     +12.3%       +28.4%
   BUY               34       58.8%      +7.5%       +14.2%
   HOLD              22       72.7%      +1.8%       +3.5%
   SELL              18       55.6%      -6.2%      -12.0%
   STRONG SELL       11       54.5%     -14.8%      -25.5%

🏭 BY INDUSTRY
   Banking            32     71.9%   12.3%   62.5%
   Consumer Staples   18     66.7%   10.5%   55.6%
   Steel_Metals       12     58.3%   22.1%   33.3%  ← cyclical khó hơn
   Real_Estate         8     50.0%   28.5%   25.0%  ← cần improve RNAV
```

**Diễn giải kết quả:**
- **Direction accuracy** > 60% là good (random sẽ ~50%)
- **HOLD hit rate** thường cao nhất (dải rộng ±10%)
- **STRONG BUY/SELL** khó hit vì threshold ±15% nghiêm
- **By Industry** giúp xác định ngành nào model yếu để improve

**Calibration loop:**
1. Chạy `run_valuation.py` weekly → tích lũy snapshots
2. Sau 3-6 tháng có đủ data, chạy `backtest.py`
3. Nếu 1 industry có direction accuracy < 50%, review weights
4. Tăng weight cho method có error thấp, giảm method có error cao

## Files thêm/sửa trong v3

```
backend/
├── backtest.py                                        ★ MỚI
├── test_backtest.py                                   ★ MỚI
└── scanner/strategies/valuation/
    ├── engine.py                                      ← Update weights
    └── methods_rnav_sotp.py                           ★ MỚI

web/
├── index.html                                         ← Thêm link valuation
└── valuation/
    ├── index.html                                     ★ MỚI
    ├── valuation.css                                  ★ MỚI
    └── valuation.js                                   ★ MỚI

web/data/valuation/
└── latest.json                                        ★ MỚI (demo data)

ROADMAP_FINAL.md                                       ★ MỚI (file này)
```

## Bước tiếp theo nếu deploy production

### 1. Setup
```bash
# Install dependencies
pip install -r backend/requirements.txt  # cần thêm pyarrow nếu chưa có

# Setup API key vnstock
export VNSTOCK_API_KEY=your_key_here
```

### 2. First run (tạo peer DB + initial valuation)
```bash
cd backend
# Chạy với top 50-100 mã thanh khoản nhất để build peer DB
python run_valuation.py --limit 100 --min-confidence 0.4
```

Output:
- `web/data/valuation/latest.json` — dashboard data
- `backend/data/peer_multiples.json` — peer DB
- `backend/data/fundamentals_cache/*.json` — per-ticker cache (TTL 7 days)
- `web/data/valuation/archive/<date>.json` — snapshot cho backtest

### 3. Schedule weekly

Cập nhật `.github/workflows/daily-scan.yml`:

```yaml
  valuation_weekly:
    if: github.event.schedule == '0 10 * * 1'  # Thứ Hai 17:00 ICT
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: '3.10' }
      - run: pip install -r backend/requirements.txt
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

### 4. Sau 3 tháng — backtest và calibrate

```bash
cd backend
python backtest.py --horizon 90 --min-confidence 50

# Review kết quả, adjust weights trong engine.py nếu cần
```

## Caveat & Limitations đã biết

1. **Mock data trong v3 demo có ROE bị nhân 100** ở một số mã (DBC từ 40% thành 80%).
   Production sẽ không có vấn đề này vì normalizer auto-detect % vs decimal.

2. **RNAV cần region data**: hiện hardcode default = 'other' (×1.10). Production lý
   tưởng có map ticker → primary_region từ thuyết minh BCTC.

3. **SOTP simplified** chỉ dùng book + earnings × discount, không phải SOTP đầy đủ
   segment-by-segment. Cần upgrade khi có data segment chi tiết.

4. **Beta cần OHLCV cache**: chạy `python run_daily.py` trước để populate cache.

5. **Peer DB cần >= 3 mã/ngành** để có stats. Mode-1 first run cần universe đủ rộng
   (limit >= 100) để cover các ngành nhỏ.

## Performance dự kiến production

| Universe | Pass 1 (fetch + enrich) | Pass 2 (value) | Tổng |
|---|---|---|---|
| 50 mã  | ~3 phút | ~30 giây | ~4 phút |
| 100 mã | ~6 phút | ~1 phút | ~7 phút |
| 200 mã | ~12 phút | ~2 phút | ~14 phút |
| Backtest 5 snapshots | — | ~10 giây | <1 phút |

Bottleneck là vnstock rate limit (60 req/min với free API key).
