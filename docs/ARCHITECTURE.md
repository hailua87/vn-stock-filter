# Kiến trúc hệ thống

## Tổng quan

```
┌─────────────────────────────────────────────────────────────────┐
│                       VN BREAKOUT SCANNER                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   DATA SOURCES   │    │   SCANNER CORE   │    │    PRESENTATION  │
├──────────────────┤    ├──────────────────┤    ├──────────────────┤
│ vnstock (VCI)    │───>│  data_fetcher   │───>│  Excel (analyst) │
│ TCBS REST        │    │       ↓          │    │  JSON (web/API)  │
│ SSI iBoard       │    │  indicators     │    │  HTML (report)   │
│                  │    │       ↓          │    │  Web Dashboard   │
│ ~1,600 tickers   │    │  criteria(10)   │    │                  │
│ HOSE/HNX/UPCOM   │    │       ↓          │    │  FastAPI REST    │
│                  │    │  scanner.score  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
        ↑                       ↑                       ↑
        │                       │                       │
        │              ┌────────┴─────────┐             │
        │              │  Parquet Cache    │             │
        │              │  (incremental)    │             │
        │              └───────────────────┘             │
        │                                                 │
        └────── GitHub Actions cron @16:00 ICT ──────────┘
```

## Data Flow chi tiết

### 1. Thu thập dữ liệu (16:00 - 16:02)
- Cron trigger sau khi thị trường đóng cửa (HOSE đóng 15:00)
- `data_fetcher.get_ticker_universe()` lấy danh sách mã 3 sàn
- Với mỗi mã: kiểm tra parquet cache, chỉ fetch ngày bị thiếu (incremental)
- Concurrency: 4 worker threads, delay 0.2s giữa request → tránh rate-limit

### 2. Tính chỉ báo & chấm điểm (16:02 - 16:05)
- Mỗi ticker chạy qua 10 hàm criteria trong `criteria.evaluate()`
- Mỗi tiêu chí trả về 0/1 → tổng điểm 0-10
- Lọc bỏ:
  - Lịch sử < 60 phiên
  - Trung bình volume 20 phiên < 10,000 (mã thanh khoản kém)

### 3. Xuất kết quả (16:05 - 16:06)
- **Excel**: `signals_YYYY-MM-DD.xlsx` (cho phân tích sâu)
- **JSON**: `signals_YYYY-MM-DD.json` + `web/data/latest.json` (cho dashboard)
- **HTML**: standalone report
- Cache parquet được cập nhật → lần chạy sau chỉ fetch ngày mới

### 4. Publish (16:06 - 16:08)
- Backend API serve `latest.json` qua `/api/signals/latest`
- Web frontend (static) fetch JSON và render dashboard
- GitHub Actions commit `web/data/latest.json` → trigger Vercel rebuild

## Component Diagram

```
backend/
├── scanner/
│   ├── indicators.py    ─── pure functions, no I/O
│   │   ├── atr()
│   │   ├── rsi()
│   │   ├── obv()
│   │   └── bollinger_width()
│   │
│   ├── criteria.py      ─── evaluate(df) → CriteriaResult
│   │   └── DEFAULT_CONFIG dict (tunable thresholds)
│   │
│   ├── data_fetcher.py  ─── I/O layer (network + disk cache)
│   │   ├── get_ticker_universe()
│   │   ├── fetch_ohlcv()       (single ticker)
│   │   ├── fetch_with_cache()  (with parquet cache)
│   │   └── fetch_universe()    (parallel)
│   │
│   ├── scanner.py       ─── BreakoutScanner orchestrator
│   │   ├── scan_live()         (fetch + evaluate)
│   │   └── scan_from_dataframe()
│   │
│   ├── backtest.py      ─── walk-forward backtest
│   │   └── backtest()
│   │
│   └── exporter.py      ─── to_excel(), to_json(), to_html()
│
├── api.py               ─── FastAPI REST server
└── run_daily.py         ─── CLI entrypoint for cron
```

## Tại sao dùng các công nghệ này?

| Choice | Lý do |
|---|---|
| **vnstock** | Thư viện Python phổ biến nhất cho thị trường VN, wrap nhiều nguồn (VCI/TCBS/SSI), miễn phí |
| **pandas + numpy** | Chuẩn ngành cho time-series analysis |
| **parquet cache** | Nhanh hơn CSV 10x, nhỏ hơn 5x, hỗ trợ append |
| **FastAPI** | Type-safe, auto OpenAPI docs, async, performance cao |
| **Static JSON cho web** | Không cần server live → deploy free trên Vercel/Netlify |
| **GitHub Actions** | Cron miễn phí, log đầy đủ, retry tự động |

## Performance

| Metric | Value |
|---|---|
| Universe size | ~1,600 mã (HOSE 400, HNX 350, UPCOM 850) |
| Cold fetch (no cache) | ~15-20 phút |
| Warm fetch (incremental) | ~2-3 phút |
| Scoring all 1,600 mã | ~30 giây |
| Tổng thời gian daily run | < 5 phút (warm) |
| RAM peak | ~500 MB |
| Disk (cache) | ~150 MB cho 1 năm |

## Scalability roadmap

- **Phase 1** (hiện tại): Single machine, file-based cache, manual config
- **Phase 2**: Postgres backend cho lịch sử tín hiệu + user accounts
- **Phase 3**: Real-time intraday scan (mỗi 15 phút) — cần WebSocket data feed
- **Phase 4**: ML overlay — học weight tối ưu cho 10 tiêu chí từ backtest

## Bảo mật & ToS

- vnstock dùng public APIs → không cần API key
- Cẩn trọng rate limit: max 10 req/s
- KHÔNG redistribute raw OHLCV (tuân thủ điều khoản của VCI/TCBS/SSI)
- Chỉ publish OUTPUT tín hiệu (đã qua xử lý) và metadata công khai
