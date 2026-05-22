# Corporate Actions (Sự kiện doanh nghiệp)

> Tài liệu này giải thích cách scanner xử lý các sự kiện như chia tách, cổ tức tiền, cổ tức cổ phiếu, phát hành thêm — và tại sao chúng quan trọng.

## Vấn đề

Khi một cổ phiếu trải qua corporate action, giá thị trường thay đổi không phải vì cung cầu mà vì cơ học:

| Sự kiện | Ảnh hưởng giá ngày GDKHQ |
|---|---|
| Cổ tức tiền 2,000đ/cp (giá 100k) | Giá giảm còn 98k (-2%) |
| Cổ tức cổ phiếu 10% | Giá giảm còn 90.91k (-9.09%) |
| Chia tách 1:2 | Giá giảm còn 50k (-50%) |
| Phát hành thêm 20% giá 80k (giá 100k) | Giá tham chiếu ~96.7k (-3.3%) |

**Nếu không xử lý:**
- ATR đột biến → C1 (ATR squeeze) sai
- Bollinger Band giãn mạnh → C2 sai
- Giá "tụt" khỏi MA20 → C7 sai
- RSI nhảy xuống → C8 ra ngoài vùng 50-65 → C8 sai
- OBV đổi hướng do nến đỏ giả → C4 sai
- Gap down xuất hiện → C10 sai

Tóm lại: **mọi tiêu chí đều bị bóp méo** trong 5-10 phiên quanh ngày sự kiện.

## Giải pháp 2 lớp

### Lớp 1: Adjusted prices (giá đã điều chỉnh)

vnstock với source `VCI` mặc định trả về giá đã được hồi tố điều chỉnh. Cụ thể:

- Khi có chia tách 1:2, **toàn bộ giá lịch sử trước đó** được nhân 0.5
- Khi có cổ tức cổ phiếu 10%, giá trước đó chia 1.10
- Khi có cổ tức tiền, không điều chỉnh giá lịch sử (chỉ giảm tại ngày GDKHQ)

`data_fetcher.fetch_ohlcv(..., adjusted=True)` truyền flag này xuống vnstock. Cache parquet được tách thành 2 file: `TICKER_adj.parquet` và `TICKER_raw.parquet` để tránh trộn 2 loại dữ liệu.

**Khi cache đã có nhưng phát hiện sự kiện mới**: refresh 30 ngày gần nhất vì giá có thể được hồi tố lại.

### Lớp 2: Lọc tín hiệu quanh ngày sự kiện

Ngay cả với adjusted prices, vẫn có 2 vấn đề còn lại:

1. **Cổ tức tiền không điều chỉnh giá lịch sử**: Giá vẫn tụt vào ngày GDKHQ → có thể tạo gap down giả
2. **Volume bất thường** quanh ngày sự kiện: nhiều người mua/bán để hưởng/né quyền → volume signals nhiễu

Module `corporate_actions.py` fetch lịch sự kiện từ vnstock và:

- **`has_recent_event(events, days=5)`**: Nếu có chia tách hoặc cổ tức cổ phiếu trong N ngày qua → `evaluate()` trả về `None` (loại khỏi tín hiệu)
- **`has_upcoming_event(events, days=5)`**: Nếu có sự kiện trong N ngày tới → tín hiệu vẫn được sinh nhưng gắn flag `m_upcoming_event` để UI cảnh báo

### Lớp 3: Sanity check

Phòng trường hợp adjusted price vẫn lỗi (vnstock API không hoàn hảo):

```python
# trong criteria.py
recent_30d = df.tail(30)
overnight_change = recent_30d['Close'].pct_change()
if (overnight_change < -0.15).any():
    # Single-day drop > 15% in last 30 days → suspect un-adjusted data
    suspicious_data = True
```

Khi `suspicious_data=True`, tín hiệu vẫn được sinh nhưng cờ `m_suspicious_data` được set → UI có thể warn hoặc loại bỏ tuỳ ý.

## Schema dữ liệu

### Event object (từ `fetch_events()`)
```python
@dataclass
class CorporateAction:
    ticker: str              # "FPT"
    ex_date: str             # "2026-05-28" (YYYY-MM-DD)
    event_type: str          # cash_dividend | stock_dividend | split | rights_issue | unknown
    ratio: float             # Tỷ lệ:
                             #   cash_dividend: VND/cp (e.g. 2000)
                             #   stock_dividend: decimal (e.g. 0.10 = 10%)
                             #   split: số phần (e.g. 2.0 = 1:2 split)
                             #   rights_issue: decimal
    description: str         # Mô tả gốc từ TCBS
```

### Cache
Events được cache 24h tại `backend/data/cache/events/{TICKER}.json`. Lý do:
- Lịch sự kiện ít thay đổi (vài lần/năm)
- Giảm 1,600 API calls mỗi ngày

### Trong tín hiệu output
```json
{
  "ticker": "FPT",
  ...
  "m_upcoming_event": {
    "type": "cash_dividend",
    "ex_date": "2026-05-28",
    "ratio": 2000
  },
  "m_suspicious_data": false
}
```

## Hiển thị trong UI

### Bảng signals
- Mã có sự kiện sắp tới: hiển thị flag ⚑ bên cạnh ticker
- Hover flag → tooltip với loại sự kiện, ngày GDKHQ, tỷ lệ
- Flag màu **vàng (accent)** nếu sự kiện > 5 ngày tới
- Flag màu **đỏ** nếu ≤ 5 ngày (cận ngày, rủi ro cao)

### Side drawer
Khi click vào row có sự kiện, drawer hiển thị section riêng:
- Loại sự kiện đầy đủ tên (e.g. "Cổ tức bằng tiền")
- Ngày GDKHQ + số ngày còn lại
- Tỷ lệ chi trả
- Cảnh báo đỏ nếu ≤ 5 ngày

### Banner ngày phân tích
Cố định ở đầu bảng, hiển thị:
- Ngày phân tích
- "Phiên mới nhất" hoặc "Dữ liệu lịch sử"
- Badge "✓ GIÁ ĐÃ ĐIỀU CHỈNH"
- Badge "✓ LỌC CORPORATE ACTIONS"

## Configuration

Trong `criteria.DEFAULT_CONFIG`:

| Tham số | Default | Ý nghĩa |
|---|---|---|
| `corporate_action_lookback_days` | 5 | Bỏ tín hiệu nếu có sự kiện chia tách/cổ tức cổ phiếu trong N ngày qua |
| `corporate_action_lookahead_days` | 5 | Cảnh báo nếu có sự kiện sắp tới trong N ngày |
| `sanity_max_single_day_drop` | 0.15 | Single-day drop > 15% → cờ suspicious_data |

## Tham khảo

- VSD (Trung tâm Lưu ký): https://vsd.vn — nguồn dữ liệu chính thức
- TCBS company events: `vnstock.Vnstock().stock(symbol='X', source='TCBS').company.events()`
- Investopedia: [Ex-Dividend Date](https://www.investopedia.com/terms/e/ex-dividend.asp), [Stock Split](https://www.investopedia.com/terms/s/stocksplit.asp)
