# Valuation Module — Integration Guide

Module định giá đa phương pháp tích hợp vào VN-SCANNER, tận dụng vnstock 4.x
data fetcher và pattern đã có của project.

## Cấu trúc mới được thêm vào

```
backend/
├── scanner/
│   ├── financial_fetcher.py        ★ MỚI — fetch BCTC từ vnstock 4.x
│   └── strategies/
│       └── valuation/              ★ MỚI — module định giá
│           ├── __init__.py
│           ├── industry_classifier.py
│           ├── normalizer.py        — vnstock raw → standardized
│           ├── methods_pb_roe.py    — P/B-ROE Justified (banking)
│           ├── methods_pe.py        — P/E Multiple (consumer/tech)
│           ├── methods_ev_ebitda.py — EV/EBITDA mid-cycle (cyclical)
│           └── engine.py            — orchestrator
├── run_valuation.py                 ★ MỚI — entry point (chạy 1 lần/tuần)
├── test_valuation_integration.py    ★ MỚI — test offline
└── data/
    └── fundamentals_cache/          ★ AUTO-CREATED — cache JSON per ticker

web/data/
└── valuation/                       ★ MỚI — output cho frontend
    ├── latest.json
    └── archive/
        ├── 2026-05-26.json
        └── index.json
```

## Output JSON schema (web/data/valuation/latest.json)

Tương thích với pattern hiện tại của các strategy khác (golden_cross,
ichimoku). Frontend chỉ cần đọc và render.

```json
{
  "generated_at": "2026-05-26T10:00:00",
  "strategy": "multi_method_valuation",
  "total": 50,
  "metadata": {
    "period": "year",
    "verdict_counts": {
      "STRONG BUY": 8,
      "BUY": 15,
      "HOLD": 18,
      "SELL": 7,
      "STRONG SELL": 2
    }
  },
  "signals": [
    {
      "ticker": "VIB",
      "industry": "Banking",
      "industry_source": "icb_mapping",
      "is_holding": false,
      "current_price": 18500,
      "fair_value": 28970,
      "fair_value_low": 17154,
      "fair_value_high": 36686,
      "upside_pct": 56.6,
      "verdict": "STRONG BUY",
      "confidence": 67,
      "methods_used": ["P/B-ROE Justified", "P/E Multiple", "Historical Multiple"],
      "method_details": [
        {"method": "P/B-ROE Justified", "weight": 55, "fair_value": 36686, "upside_pct": 98.3, "confidence": 85},
        ...
      ],
      "warnings": [],
      "notes": ["Ngành định giá: Banking ...", ...]
    },
    ...
  ]
}
```

## Cách chạy

### Local test (offline, dùng mock data)
```bash
cd backend
python test_valuation_integration.py
# → Xác nhận engine hoạt động trước khi gọi vnstock
```

### Local run với vnstock thật
```bash
cd backend
export VNSTOCK_API_KEY=your_key_here

# Chạy với 100 mã thanh khoản nhất HOSE+HNX
python run_valuation.py --limit 100

# Chỉ định danh sách cụ thể
python run_valuation.py --tickers VIB,PAN,DBC,FPT,HPG,VNM,MWG

# Filter
python run_valuation.py --limit 200 --min-upside 15 --min-confidence 0.5
```

### Tích hợp vào GitHub Actions workflow

Trong `.github/workflows/daily-scan.yml`, thêm 1 job mới chạy **hàng tuần**
(không cần daily vì BCTC ra hàng quý):

```yaml
  valuation:
    runs-on: ubuntu-latest
    if: github.event.schedule == '0 17 * * 1'  # Mỗi thứ 2 lúc 17:00 UTC
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r backend/requirements.txt
      - run: |
          cd backend
          python run_valuation.py --limit 150
      - run: |
          git config user.email "bot@valuation.vn"
          git config user.name "Valuation Bot"
          git add web/data/valuation/
          git commit -m "valuation: weekly update $(date +%Y-%m-%d)" || true
          git push
```

## Mức độ tin cậy theo ngành

| Ngành | Confidence điển hình | Phương pháp dominant |
|---|---|---|
| Banking (VIB, VCB, MBB...) | 70-85% | P/B-ROE 55% + P/E 30% |
| Consumer Staples (VNM, MSN, SAB...) | 75-85% | P/E 45% + EV/EBITDA 35% |
| Technology (FPT) | 70-80% | P/E 50% + EV/EBITDA 25% |
| Utilities (REE, POW, GEG) | 70-80% | EV/EBITDA 40% + P/E 30% |
| Real Estate (VHM, NLG, KDH) | 50-65% | Historical 50% (chưa có RNAV) |
| **Cyclical** (HPG, DGC, DBC) | **50-65%** | EV/EBITDA mid-cycle 50% |
| **Holding** (PAN, MSN, VIC) | **55-70%** | Blend 4 methods (chưa có SOTP) |

## Logic cảnh báo tự động

Engine sẽ phát ra **warnings** khi phát hiện:
- ROE TTM lệch >30% so với 5y avg → có thể ở đỉnh/đáy chu kỳ
- Có năm thua lỗ trong 5 năm → P/E không phù hợp
- EPS có cú nhảy >100% giữa 2 năm liên tiếp → cyclical signal
- EPS CV > 0.6 → khuyến nghị dùng EV/EBITDA
- Industry không match với method (e.g., P/B cho công ty công nghệ)

Mỗi warning **giảm 10-25% confidence** của method tương ứng.

## Roadmap mở rộng

### Việc cần làm để chạy production tốt hơn

1. **Historical P/E, P/B chính xác**: Hiện tại đang dùng current ± 20% làm proxy.
   Cần tính từ price history × historical EPS/BVPS.

2. **Beta thực**: Hiện hardcode = 1.0. Cần regression 2 năm với VN-Index từ
   OHLCV (đã có sẵn trong cache!).

3. **Peer database**: Hiện chỉ so với VN-Index. Lý tưởng có bảng peer median P/E,
   P/B, EV/EBITDA theo ICB code → định giá chính xác hơn.

4. **DCF FCFF**: Chưa implement. Cần cho utilities và stable industries.

5. **DDM cho utilities**: REE, POW có dividend ổn định, DDM rất phù hợp.

6. **RNAV approximation cho BĐS**: Cần data hàng tồn kho dự án + region multiplier.

7. **SOTP cho holding**: PAN, MSN, VIC, GEX cần định giá theo segment riêng.

### Khi nào cần tăng quality?

- **Tuần đầu deploy**: chạy `--tickers` với 20-30 mã blue-chip, validate fair value
  vs analyst consensus (SSI, VCSC, HSC) để calibrate weights.
- **Sau 1 tháng**: backtest fair value vs giá thực tế 6 tháng sau cho 50-100 mã.
- **Sau 3 tháng**: dùng backtest data để fine-tune `INDUSTRY_METHOD_WEIGHTS` và
  các parameter trong `MARKET_PARAMS`.

## FAQ

**Q: Tại sao fair value của DBC âm/khác xa thị trường?**
A: DBC là cyclical leverage cao. EV/EBITDA mid-cycle dùng EBITDA trung bình 5
năm — bao gồm năm 2022 lỗ. Đây là **conservative ON PURPOSE** để cảnh báo
"không mua ở đỉnh chu kỳ". Khi giá heo điều chỉnh, fair value sẽ sát thị
trường hơn.

**Q: Có nên trust confidence < 50%?**
A: Không. Coi như tham khảo, không phải actionable. Confidence < 50% = engine
biết rằng nó không có data tốt cho ticker này.

**Q: Verdict STRONG BUY có nghĩa là phải mua?**
A: **KHÔNG**. Đây chỉ là output của model định giá. Cần combine với:
- Tín hiệu kỹ thuật (golden cross, ichimoku)
- Yếu tố vĩ mô và ngành
- Catalyst sắp tới (earning report, M&A, regulatory change)

Verdict chỉ là 1 input trong quyết định đầu tư.

**Q: Có thể thay đổi weights theo phong cách đầu tư cá nhân?**
A: Có. Edit `INDUSTRY_METHOD_WEIGHTS` trong `engine.py`. Ví dụ:
- Value investor: tăng weight P/B, giảm P/E
- Growth investor: tăng weight PEG, P/S (chưa implement)
- Income investor: tăng weight DDM (chưa implement)
