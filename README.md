# VN-SCANNER

Multi-strategy scanner cho thị trường chứng khoán Việt Nam (HOSE/HNX/UPCOM).

Quét tự động hàng ngày, phát hiện tín hiệu theo 4 chiến lược:
- **Pre-Breakout** (sắp phá vỡ kháng cự)
- **Golden Cross Long** (MA50 cắt MA200)
- **Golden Cross Short** (MA20 cắt MA50)
- **Ichimoku Kinko Hyo** (hệ thống tín hiệu Nhật)

## Kiến trúc

```
GitHub Actions (2 lần/ngày)
        ↓
backend/run_daily.py
   ├── data_fetcher.py     ← vnstock 4.x (source='vci', adjusted)
   ├── strategies/         ← 4 chiến lược scan
   └── output JSON         ← commit lên repo
        ↓
Vercel deploy
        ↓
web/                       ← static site đọc JSON
```

**Quan trọng:** Web KHÔNG gọi API. Web chỉ đọc JSON tĩnh được commit. JSON
được cập nhật khi workflow chạy.

## Schedule

- **12:00 ICT (sau phiên sáng)**: intraday update — badge cam `INTRADAY HH:MM`
- **17:00 ICT (sau đóng cửa)**: EOD update — badge teal `EOD HH:MM`

Chỉ chạy T2-T6 (không cuối tuần).

## Setup local

```bash
# Backend
cd backend
pip install -r requirements.txt
export VNSTOCK_API_KEY=your_key_here   # đăng ký free tại vnstocks.com
python run_daily.py --min-score 5 --limit 500

# Frontend (static, serve bằng bất kỳ HTTP server nào)
cd web
python -m http.server 8000
# → http://localhost:8000
```

## Cài đặt API key

vnstock 4.x giới hạn anonymous mode rất chặt (vài req/phút). Đăng ký free tại
https://vnstocks.com/login để có 60 req/phút.

Trong GitHub Actions: Settings → Secrets → New repository secret:
- Name: `VNSTOCK_API_KEY`
- Value: API key của bạn

## Tests

```bash
cd backend
pip install pytest
pytest tests/ -v
```

39 tests, cover các strategy chính.

## Cấu trúc thư mục

```
.github/workflows/
    daily-scan.yml       — CI/CD workflow

backend/
    run_daily.py         — Pipeline chính
    generate_demo_data.py — Tạo demo data nếu vnstock fail
    scanner/
        data_fetcher.py  — Fetch OHLCV từ vnstock
        criteria.py      — Tiêu chí lọc cơ bản
        top_liquid.py    — Curated list mã liquid
        support_resistance.py — Fibonacci levels
        strategies/
            golden_cross.py
            ichimoku.py
            indicators_ext.py — Bollinger, ATR, ADX, etc.
    tests/

web/
    index.html
    app.js
    styles.css
```

## Lưu ý quan trọng

### Giá adjusted

Code dùng `source='vci'` của vnstock 4.x trả về **adjusted price** (đã trừ
cổ tức quá khứ). Hệ quả: giá có thể KHÁC CafeF/SSI cho mã có cổ tức gần đây.

Ví dụ VND chia 500đ ngày 15/07/2025:
- CafeF: 17.60 (raw, hiện tại)
- VN-SCANNER: 17.10 (= 17.60 - 0.50)

Đây là **đúng theo thiết kế** — adjusted price chính xác hơn cho phân tích kỹ
thuật. UI có badge `Giá điều chỉnh` để user hiểu.

### Intraday timing divergence

Khi xem data INTRADAY (12:00 run), giá có thể chênh 0.5-2% so với SSI/CafeF
vì vnstock và các nguồn này snapshot ở thời điểm khác nhau trong cùng phiên.
**Không phải bug.**

Sau 17:00 (EOD run), data dùng giá đóng cửa chính thức → khớp ~99% với
CafeF/SSI.

## Changelog

Xem `CHANGELOG.md` để biết history các fix và cải tiến.
