# Backtest Framework

## Mục đích

Đo lường **hit rate** thực tế của scanner trên lịch sử để:
1. Validate logic 10 tiêu chí
2. Tối ưu các threshold (grid search)
3. Tính kỳ vọng (expectancy) cho chiến lược trading

## Định nghĩa "thành công"

> Một tín hiệu xuất hiện tại ngày `t` với điểm ≥ `min_score` được coi là **thành công**
> nếu giá đóng cửa của bất kỳ phiên nào trong `[t+1, t+lookahead_days]` ≥ `Close(t) × (1 + breakout_threshold)`.

**Tham số mặc định**:
- `lookahead_days = 5` (window 5 phiên tới)
- `breakout_threshold = 0.05` (5% tăng)
- `min_score = 6`

## Cách chạy

```python
from scanner.data_fetcher import fetch_universe, get_ticker_universe
from scanner.backtest import backtest, print_report

# Lấy dữ liệu lịch sử (ít nhất 1 năm để có đủ sample)
universe = get_ticker_universe()
df = fetch_universe(universe, lookback_days=365)

# Chạy backtest
result = backtest(
    df,
    lookahead_days=5,
    breakout_threshold=0.05,
    min_score=6,
    warmup_days=60,
)

print_report(result)

# Xem chi tiết từng trade
print(result.trades.head(20))
result.trades.to_csv('backtest_trades.csv', index=False)
```

## Output mẫu

```
============================================================
BACKTEST REPORT
============================================================
Total signals:       847
Successful:          512
Failed:              335
Hit rate:            60.45%
Avg return:          7.82%
Avg days to break:   2.83

By rating:
  A+: n=124, hit=71.0%, avg_ret=11.20%
  A:  n=389, hit=63.5%, avg_ret=8.10%
  B:  n=334, hit=53.0%, avg_ret=5.80%
============================================================
```

> Số liệu mẫu, kết quả thực tế tùy vào dữ liệu lịch sử cụ thể.

## Diễn giải

### Hit rate
- **>60%** trên toàn bộ tín hiệu = tốt
- **>70%** cho rating A+ = rất tốt
- Hit rate < 50% nghĩa là tệ hơn coin flip → cần debug logic

### Expectancy
```
E = (P_win × avg_win) - (P_loss × avg_loss)
```

Với hit rate 60% và avg_return 7.82%, giả sử stop-loss -3%:
```
E = 0.60 × 7.82 - 0.40 × 3.00 = 4.69 - 1.20 = +3.49% per trade
```

→ Trên 100 lệnh, kỳ vọng lợi nhuận ~349% (chưa tính phí, slippage).

## Grid search tối ưu threshold

```python
import itertools

param_grid = {
    'atr_squeeze_ratio': [0.75, 0.80, 0.85, 0.90],
    'vol_surge_ratio': [1.10, 1.15, 1.20, 1.25],
    'near_high_pct': [2.0, 3.0, 4.0],
}

best = None
for combo in itertools.product(*param_grid.values()):
    cfg = dict(zip(param_grid.keys(), combo))
    r = backtest(df, config=cfg, min_score=6)
    score = r.hit_rate * r.avg_return_pct  # composite metric
    if best is None or score > best[1]:
        best = (cfg, score, r)
    print(f"{cfg}: hit={r.hit_rate}%, ret={r.avg_return_pct}%")

print(f"\nBEST: {best[0]} → composite score {best[1]:.2f}")
```

## Cảnh báo về backtest

1. **Survivorship bias**: Backtest chỉ chạy trên các mã hiện tại còn tồn tại, không tính các mã đã hủy niêm yết. Kết quả thực tế sẽ thấp hơn.

2. **Look-ahead bias**: Hàm `backtest()` chỉ dùng `df_all[df_all['Date'] <= t]` tại mỗi điểm thời gian — KHÔNG có look-ahead. Nhưng nếu bạn dùng MA50 thì cần 50 phiên history trước đó.

3. **Slippage & phí**: Backtest giả định mua được đúng giá Close. Thực tế phí HOSE ~0.15% + slippage 0.1-0.3%. Trừ ~0.5% khỏi avg_return để có con số thực tế.

4. **Regime change**: Hit rate trong uptrend (như 2021) khác xa downtrend (2022). Backtest qua cả bull + bear market.

5. **Multiple testing**: Grid search trên 100 combo dễ overfit. Dùng walk-forward validation:
   - Train period: 2020-2023
   - Validation: 2024-2025
   - Test (out-of-sample): 2026

---

# REST API Documentation

API server chạy bằng FastAPI tại `http://localhost:8000` (dev) hoặc URL Railway/Render (prod).

## Authentication

Hiện tại không có auth (public read-only). Thêm API key nếu cần:
```python
from fastapi.security import APIKeyHeader
api_key = APIKeyHeader(name='X-API-Key')
```

## Endpoints

### GET `/`
Thông tin tổng quan API.

```bash
curl http://localhost:8000/
```

### GET `/api/health`
Health check + metadata lần scan gần nhất.

```bash
curl http://localhost:8000/api/health
# {"status":"ok","last_scan":"2026-05-16T16:05:00","signal_count":42}
```

### GET `/api/signals/latest`
Tín hiệu mới nhất với filters.

**Query params**:
| Param | Type | Default | Mô tả |
|---|---|---|---|
| `min_score` | int (0-10) | 0 | Điểm tối thiểu |
| `rating` | string | null | `A+`, `A`, `B`, `C` |
| `exchange` | string | null | `HOSE`, `HNX`, `UPCOM` |
| `limit` | int (1-1000) | 100 | Số kết quả |

```bash
# Top 10 tín hiệu A+ trên HOSE
curl "http://localhost:8000/api/signals/latest?rating=A%2B&exchange=HOSE&limit=10"
```

Response:
```json
{
  "generated_at": "2026-05-16T16:05:00",
  "total": 10,
  "filters": {"min_score": 0, "rating": "A+", "exchange": "HOSE"},
  "signals": [
    {
      "ticker": "FPT",
      "exchange": "HOSE",
      "date": "2026-05-16",
      "close": 137.50,
      "volume": 2847000,
      "total_score": 9,
      "rating": "A+",
      "c1_atr_squeeze": 1,
      "c2_bb_squeeze": 1,
      ...
      "m_dist_to_high20_pct": 0.74,
      "m_vol_ratio": 1.27
    }
  ]
}
```

### GET `/api/signals/{date}`
Tín hiệu của ngày cụ thể.

```bash
curl http://localhost:8000/api/signals/2026-05-16
```

### GET `/api/signals/ticker/{ticker}`
Lịch sử xuất hiện của 1 mã trong scan.

```bash
curl "http://localhost:8000/api/signals/ticker/FPT?days=30"
```

### GET `/api/excel/latest`
Download file Excel mới nhất.

```bash
curl -O http://localhost:8000/api/excel/latest
```

## OpenAPI / Swagger UI

Truy cập `http://localhost:8000/docs` để có interactive API explorer (tự động sinh bởi FastAPI).

## Code examples

### Python
```python
import requests
r = requests.get('https://your-api.railway.app/api/signals/latest',
                 params={'rating': 'A+', 'exchange': 'HOSE'})
for s in r.json()['signals']:
    print(f"{s['ticker']}: score {s['total_score']}")
```

### JavaScript
```javascript
const res = await fetch('/api/signals/latest?min_score=6');
const data = await res.json();
data.signals.forEach(s => console.log(s.ticker, s.total_score));
```
