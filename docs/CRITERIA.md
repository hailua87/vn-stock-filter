# 10 Tiêu chí Pre-Breakout (Chi tiết kỹ thuật)

> Mỗi tiêu chí trả về **0 hoặc 1**. Tổng điểm tối đa = **10**.
> Có thể tùy chỉnh threshold trong `DEFAULT_CONFIG` ở `criteria.py`.

## Lý thuyết nền

Một nhịp **break** thường có 3 giai đoạn:
1. **Tích lũy (Accumulation)**: smart money mua âm thầm, giá đi ngang, volume thấp
2. **Khởi động (Pre-Breakout)** ← *Vùng scanner cần phát hiện*: dấu hiệu rò rỉ xuất hiện 2-5 phiên trước khi break
3. **Bứt phá (Breakout)**: giá vượt kháng cự với volume lớn → quá muộn để vào với giá tối ưu

Các tiêu chí được nhóm thành 3 cụm bổ trợ cho nhau:

```
   ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
   │  NÉN NĂNG LƯỢNG     │  │  DÒNG TIỀN ÂM THẦM  │  │  XÁC NHẬN XU HƯỚNG  │
   ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
   │ C1: ATR Squeeze     │  │ C4: Stealth Accum   │  │ C7: MA Alignment    │
   │ C2: BB Squeeze      │  │ C5: Volume Surge    │  │ C8: RSI 50-65       │
   │ C3: Near High20     │  │ C6: Upper Close     │  │ C10: No Gap Down    │
   │                     │  │ C9: Pocket Pivot    │  │                     │
   └─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

---

## C1: ATR Squeeze — Biên độ siết lại

**Logic**: Trước break, biến động ngắn hạn thường giảm xuống dưới biến động trung bình → "lò xo bị nén".

**Công thức**:
```
ATR_pct(t) = ATR(14)(t) / Close(t) × 100
ATR_pct_avg_20 = mean(ATR_pct[t-21 : t-1])

C1 = 1  if ATR_pct(t) < ATR_pct_avg_20 × 0.85
   = 0  otherwise
```

**Tham số mặc định**: `atr_squeeze_ratio = 0.85` (biên độ hiện tại < 85% trung bình 20 phiên)

**Khi nào fail**: Mã có volatility cao mãn tính (penny stocks) hoặc đang downtrend mạnh.

---

## C2: Bollinger Squeeze

**Logic**: Bollinger Band thu hẹp → standard deviation thấp → giá tích lũy chặt. Lý thuyết của John Bollinger: "low volatility precedes high volatility".

**Công thức**:
```
BB_width(t) = (Upper - Lower) / MA20 = 4σ / MA20

C2 = 1  if BB_width(t) <= quantile_25(BB_width[t-60 : t])
   = 0  otherwise
```

**Tham số**: `bbw_squeeze_quantile = 0.25` (top 25% nén nhất trong 60 phiên)

**Ưu điểm so với C1**: BB nhạy hơn với chu kỳ dài (60 phiên thay vì 20).

---

## C3: Gần đỉnh 20 phiên (chưa break)

**Logic**: Giá đang test kháng cự — nến cuối nằm sát đỉnh nhưng chưa vượt. Đây là vùng có **risk/reward tốt nhất** vì stop-loss có thể đặt ngay dưới đỉnh.

**Công thức**:
```
High20(t) = max(High[t-19 : t])
dist_pct = (High20(t) - Close(t)) / High20(t) × 100

C3 = 1  if 0 < dist_pct <= 3.0
   = 0  otherwise
```

**Tham số**: `near_high_pct = 3.0` (cách đỉnh ≤ 3%)

**Quan trọng**: `> 0` để loại các mã đã break rồi (giá hiện tại = đỉnh).

---

## C4: Stealth Accumulation (OBV leads price)

**Logic**: **On-Balance Volume** tăng nhanh hơn giá → có "ai đó" gom hàng âm thầm. Nguyên lý: tay to thường mua vào những phiên đỏ.

**Công thức**:
```
OBV(t) = OBV(t-1) + sign(Close(t) - Close(t-1)) × Volume(t)

obv_chg_10d = (OBV(t) - OBV(t-10)) / |OBV(t-10)|
price_chg_10d = (Close(t) - Close(t-10)) / Close(t-10)

C4 = 1  if obv_chg_10d > 0.05
       AND price_chg_10d < 0.03
       AND obv_chg_10d > 2 × price_chg_10d
   = 0  otherwise
```

**Tham số**: `stealth_obv_chg_min = 0.05`, `stealth_price_chg_max = 0.03`

**Đây là tiêu chí mạnh nhất** — khi C4 = 1, xác suất break thường cao hơn các tiêu chí khác.

---

## C5: Volume Surge âm thầm

**Logic**: Volume trung bình 5 phiên gần nhất cao hơn MA20 → dòng tiền đang vào, nhưng không quá đột biến (đột biến quá là đã break rồi).

**Công thức**:
```
vol_5d = mean(Volume[t-4 : t])
vol_ma20 = mean(Volume[t-19 : t])

C5 = 1  if vol_5d > vol_ma20 × 1.15
   = 0  otherwise
```

**Tham số**: `vol_surge_ratio = 1.15`

---

## C6: Đóng cửa nửa trên biên độ ngày

**Logic**: Mỗi phiên, vị trí đóng cửa trong biên độ ngày cho biết ai thắng. Đóng ở nửa trên ≥ 3/5 phiên = bên mua đang dần kiểm soát.

**Công thức**:
```
close_position(i) = (Close(i) - Low(i)) / (High(i) - Low(i))

count = số phiên i trong [t-4, t] có close_position(i) >= 0.6

C6 = 1  if count >= 3
   = 0  otherwise
```

**Tham số**: `upper_close_threshold = 0.6`, `upper_close_min_days = 3`

---

## C7: MA Alignment (xu hướng ngắn-trung hạn)

**Logic**: MA10 cắt lên MA20 và MA20 đang hướng lên → xu hướng tăng đã xác lập.

**Công thức**:
```
C7 = 1  if MA10(t) > MA20(t)
       AND MA20(t) >= MA20(t-5)
   = 0  otherwise
```

**Tại sao MA20 phải hướng lên?** Tránh trường hợp golden cross giả khi cả 2 MA đều xuống.

---

## C8: RSI trong vùng "khỏe nhưng chưa quá mua"

**Logic**: RSI 50-65 là vùng "vàng" — đủ động lực để break nhưng còn dư địa tăng. RSI > 70 dễ pullback ngay sau break.

**Công thức**:
```
RSI(14) tính theo Wilder's smoothing (xấp xỉ bằng SMA)

C8 = 1  if 50 <= RSI(14) <= 65
   = 0  otherwise
```

---

## C9: Pocket Pivot (Chris Kacher)

**Logic**: Tín hiệu kinh điển từ sách *Trade Like an O'Neil Disciple* (Kacher & Morales).
> "A pocket pivot is an up day where volume exceeds the highest volume of any down day in the prior 10 days."

Đây là dấu hiệu mạnh rằng phiên tăng đó được hỗ trợ bởi dòng tiền mới, không chỉ là technical bounce.

**Công thức**:
```
last10 = data[t-10 : t-1]
down_days = phiên trong last10 mà Close < Close trước đó
max_down_vol = max(Volume của down_days)

C9 = 1  if Close(t) > Close(t-1)
       AND Volume(t) > max_down_vol
   = 0  otherwise
```

---

## C10: Không gap down mạnh trong 5 phiên

**Logic**: Tránh các mã đang trong cú sập bất ngờ (tin xấu, scandal, etc.). Một gap down >4% là red flag.

**Công thức**:
```
C10 = 1  if Open(i) >= Close(i-1) × 0.96 với mọi i trong [t-4, t]
    = 0  if có bất kỳ gap down > 4%
```

**Tham số**: `gap_down_threshold = 0.04`

---

## Tổng điểm & xếp loại

```python
total_score = sum(C1..C10)  # 0 to 10

rating = 'A+'  if score >= 8
       = 'A'   if score >= 6
       = 'B'   if score >= 4
       = 'C'   otherwise (loại bỏ)
```

**Khuyến nghị thực hành**:
- **A+**: Watch list ưu tiên, có thể nhập 1/3 vị thế trước khi break để optimize entry
- **A**: Theo dõi sát, chờ thêm 1-2 phiên xác nhận
- **B**: Cảnh báo, nhưng cần tín hiệu break thực sự mới vào
- **C**: Loại bỏ

## Tối ưu hóa qua backtest

Các threshold trong `DEFAULT_CONFIG` được hiệu chỉnh sơ bộ. Để tối ưu cho cổ phiếu VN:

```python
from scanner.backtest import backtest, print_report

# Grid search trên historical data
for atr_ratio in [0.75, 0.80, 0.85, 0.90]:
    for vol_ratio in [1.10, 1.15, 1.20, 1.25]:
        cfg = {'atr_squeeze_ratio': atr_ratio, 'vol_surge_ratio': vol_ratio}
        result = backtest(df_history, config=cfg, lookahead_days=5,
                          breakout_threshold=0.05, min_score=6)
        print(f"ATR={atr_ratio}, VOL={vol_ratio}: hit_rate={result.hit_rate}%, "
              f"avg_ret={result.avg_return_pct}%")
```

Xem chi tiết tại [BACKTEST.md](BACKTEST.md).

## Tài liệu tham khảo

1. Bollinger, J. (2002). *Bollinger on Bollinger Bands*. McGraw-Hill.
2. Kacher, C. & Morales, G. (2010). *Trade Like an O'Neil Disciple*. Wiley.
3. Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*.
4. Murphy, J. J. (1999). *Technical Analysis of the Financial Markets*. NYIF.
