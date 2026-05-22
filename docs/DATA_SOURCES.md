# Nguồn dữ liệu & Cách thu thập

## 1. Tổng quan các nguồn dữ liệu thị trường Việt Nam

| Nguồn | Loại | Miễn phí | Lịch sử | API chính thức | Ghi chú |
|---|---|---|---|---|---|
| **vnstock** (Python lib) | Wrapper | ✅ | 10+ năm | Không, dùng public endpoints | **Khuyến nghị #1** |
| **VCI (Vietcap)** | REST | ✅ | 10+ năm | Public | Backend chính của vnstock |
| **TCBS** | REST | ✅ | 5+ năm | Public | Có data ngành, financial statements |
| **SSI iBoard** | REST | ✅ | 5+ năm | Public | Hơi giới hạn rate |
| **FiinPro** | API trả phí | ❌ | 15+ năm | Có | Chuyên nghiệp, đắt (~$3,000/năm) |
| **CafeF / VietStock** | Web scrape | ✅ | 10+ năm | Không | Không khuyến khích (vi phạm ToS) |
| **HOSE/HNX/UPCOM official** | File download | ✅ | EOD | Không API | Phải parse Excel hằng ngày |

## 2. Khuyến nghị: dùng `vnstock`

### Cài đặt
```bash
pip install vnstock
```

### Lấy danh sách mã (universe)
```python
from vnstock import Listing
listing = Listing()

# Toàn bộ symbol
all_symbols = listing.all_symbols()

# Theo sàn
hose = listing.symbols_by_exchange('hose')
hnx = listing.symbols_by_exchange('hnx')
upcom = listing.symbols_by_exchange('upcom')
```

### Lấy OHLCV lịch sử
```python
from vnstock import Vnstock

stock = Vnstock().stock(symbol='FPT', source='VCI')
df = stock.quote.history(
    start='2024-01-01',
    end='2026-05-16',
    interval='1D'      # '1D', '1W', '1M', '1H', '15m', '5m', '1m'
)
```

**Output schema:**
| Column | Type | Mô tả |
|---|---|---|
| `time` | datetime | Ngày giao dịch |
| `open` | float | Giá mở cửa (×1000 VND) |
| `high` | float | Giá cao nhất |
| `low` | float | Giá thấp nhất |
| `close` | float | Giá đóng cửa |
| `volume` | int | KLGD khớp lệnh |

> **Lưu ý**: Giá đã chia 1000 — đơn vị là **nghìn VND**. Một giá `12.5` nghĩa là 12,500 VND.

### Source options
- `'VCI'` (Vietcap) — nhanh nhất, ổn định nhất → **default**
- `'TCBS'` (Techcombank Securities) — có thêm financial data
- `'MSN'` (Mirae Asset) — backup
- `'VND'` (VNDirect)

## 3. Rate limiting & best practices

### Giới hạn (quan sát thực tế, không được công bố chính thức)
- VCI: ~10-20 req/s nhưng có thể bị ban nếu burst >50/s liên tục
- TCBS: ~5-10 req/s, kén với traffic bất thường

### Best practices
```python
import time
from concurrent.futures import ThreadPoolExecutor

def fetch_with_delay(ticker):
    time.sleep(0.2)  # 200ms giữa request
    return fetch_ohlcv(ticker, '2024-01-01', '2026-05-16')

with ThreadPoolExecutor(max_workers=4) as ex:
    results = list(ex.map(fetch_with_delay, tickers))
```

**Quy tắc:**
- 4 worker threads max
- 200ms delay giữa request mỗi thread
- Retry 2 lần với exponential backoff khi gặp lỗi
- KHÔNG chạy 1,600 mã liên tục — chia batch 200 mã, nghỉ 5s giữa batch

### Caching để giảm tải
- Lưu parquet local sau mỗi lần fetch
- Chỉ fetch incrementally (từ `last_cached_date + 1`)
- Lần chạy thứ 2 sẽ nhanh hơn 10x

## 4. Phạm vi dữ liệu

### Sàn được hỗ trợ
| Sàn | Số mã (xấp xỉ 2026) | Khối lượng GD/ngày |
|---|---|---|
| **HOSE** (Sở GDCK TP.HCM) | ~400 | ~80% tổng giá trị |
| **HNX** (Sở GDCK Hà Nội) | ~350 | ~10% |
| **UPCOM** | ~850 | ~10% |
| **Tổng** | ~1,600 | |

### Loại bỏ
Scanner tự động bỏ qua:
- Mã có volume trung bình 20 phiên < 10,000 cổ phiếu (mã chết)
- Mã có lịch sử < 60 phiên (mới niêm yết)
- Mã ETF/CW (nếu có pattern tên đặc biệt — có thể bật/tắt qua config)

### Khung thời gian
- **Lịch sử cần lookback**: 180 phiên (~9 tháng) — đủ cho MA50, BB(20), pattern recognition
- **Đầu ra**: tín hiệu cho **phiên gần nhất**
- **Tần suất**: 1 lần/ngày sau 15:00 ICT

## 5. Mã ICT timezone

Tất cả timestamp đều theo **Asia/Ho_Chi_Minh (UTC+7)**:
- 09:00 — Mở cửa
- 11:30 — Nghỉ trưa
- 13:00 — Mở phiên chiều
- 14:30 (HNX/UPCOM) / 14:45 (HOSE) — Đóng cửa ATC
- 15:00 — Đóng cửa hoàn toàn
- **16:00 — Scanner chạy** (cron trigger)

## 6. Fallback khi nguồn dữ liệu lỗi

```python
def fetch_with_fallback(ticker, start, end):
    for source in ['VCI', 'TCBS', 'MSN']:
        try:
            return fetch_ohlcv(ticker, start, end, source=source)
        except Exception as e:
            log.warning(f"{ticker} via {source} failed: {e}")
    return None
```

## 7. Tài nguyên tham khảo

- vnstock docs: https://docs.vnstock.site
- VCI API explorer: https://trading.vietcap.com.vn (xem Network tab)
- Wong, B. (2023). *Vietnamese stock market data engineering*. Medium.
- HOSE official data: https://www.hsx.vn/Modules/Listed/Web/Datadownload
