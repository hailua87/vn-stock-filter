# Câu hỏi thường gặp (FAQ) & Troubleshooting

## Mục lục
- [Về phương pháp](#về-phương-pháp)
- [Về dữ liệu](#về-dữ-liệu)
- [Về sử dụng tín hiệu](#về-sử-dụng-tín-hiệu)
- [Lỗi kỹ thuật thường gặp](#lỗi-kỹ-thuật-thường-gặp)
- [Câu hỏi về web app](#câu-hỏi-về-web-app)

---

## Về phương pháp

### Q: Tín hiệu "pre-breakout" nghĩa là gì? Khác gì với "đã breakout"?

**A:** Một nhịp tăng giá thường có 3 giai đoạn:

1. **Tích lũy** — Giá đi ngang, volume thấp, smart money gom hàng âm thầm
2. **Pre-breakout** ← *chỗ scanner tìm* — Có dấu hiệu rò rỉ: ATR siết lại, volume nhích lên, giá test đỉnh nhiều lần. **2-5 phiên trước break thực sự.**
3. **Breakout** — Giá phá kháng cự với volume lớn → giá đã lên 5-15% rồi

Mua ở giai đoạn 2 cho **risk/reward tốt hơn** vì:
- Stop-loss đặt sát hơn (vùng tích lũy có biên độ hẹp)
- Lợi nhuận tiềm năng lớn hơn (chưa bị FOMO đẩy giá)

Đổi lại, có **xác suất sai** — không phải mọi tín hiệu pre-breakout đều dẫn đến break thật. Đó là lý do cần stop-loss.

### Q: Hit rate (tỷ lệ đúng) của scanner là bao nhiêu?

**A:** Phụ thuộc vào nhiều yếu tố. Theo backtest mẫu (không phải con số thực, vì phụ thuộc giai đoạn thị trường):
- Rating **A+** (≥8/10 điểm): ~70% break trong 5 phiên tới
- Rating **A** (≥6/10): ~60%
- Rating **B** (≥4/10): ~50%

**Cách hiểu đúng:** Hit rate 70% nghĩa là **30% sẽ sai**. Stop-loss vì thế là bắt buộc.

Chạy backtest trên dữ liệu của bạn để có con số chính xác — xem [BACKTEST.md](BACKTEST.md).

### Q: Tại sao chỉ 10 tiêu chí? Có thể thêm RSI divergence, MACD, Fibonacci không?

**A:** Có thể, nhưng có lý do giữ ở 10:

- **10 tiêu chí đã phủ 3 yếu tố chính**: nén năng lượng + dòng tiền + xu hướng — đủ cho pre-breakout
- **Thêm tiêu chí có thể overfit** (curve fitting): tinh chỉnh để fit lịch sử nhưng không generalise được
- **Đơn giản dễ debug**: nếu tín hiệu sai, dễ xác định tiêu chí nào "gây nhiễu"

Nếu muốn thêm, chỉnh sửa `backend/scanner/criteria.py`:
```python
# Thêm vào hàm evaluate():
scores['my_new_criterion'] = int(my_logic_returns_true)
```

### Q: Mã penny (giá thấp, vốn nhỏ) có được scan không?

**A:** Có, nhưng có filter:
- Volume trung bình 20 phiên < 10,000 cp → **loại** (không đủ thanh khoản)
- Lịch sử < 60 phiên → **loại** (mới niêm yết)

Penny stock thực sự thanh khoản tốt vẫn vào tín hiệu. Tuy nhiên cẩn trọng:
- Spread (chênh lệch mua/bán) rộng → khó vào đúng giá
- Dễ bị làm giá (manipulation) → tín hiệu kỹ thuật kém tin cậy

### Q: Có hỗ trợ chứng quyền (CW), ETF, derivatives không?

**A:** Hiện tại chỉ cổ phiếu (stock). Lý do:
- CW có expiry → logic khác hoàn toàn
- ETF phụ thuộc NAV của tài sản cơ sở
- Derivatives (VN30F) khung thời gian intraday

Có thể mở rộng trong tương lai.

---

## Về dữ liệu

### Q: Dữ liệu lấy từ đâu? Có chính xác không?

**A:** Qua **vnstock** (Python library) → gọi public API của **VCI (Vietcap)**, **TCBS**, **SSI**. Đây cũng chính là nguồn data mà các website như cafef.vn, fireant.vn dùng.

Độ chính xác: **Khớp 100% với data của Sở GDCK** (HOSE, HNX, UPCOM). Nếu thấy lệch, kiểm tra:
- Bạn so với giá **đã điều chỉnh** hay **chưa điều chỉnh**?
- So với phiên nào? (cùng date)
- Đơn vị: nghìn VND (vd: 138.5 = 138,500 VND)

Xem [DATA_SOURCES.md](DATA_SOURCES.md) chi tiết.

### Q: Tại sao giá demo trong screenshot khác giá thật?

**A:** Bản demo dùng dữ liệu **fake** sinh bởi `backend/generate_demo_data.py` để minh họa UI. Khi bạn chạy `python backend/run_daily.py` thật, code sẽ fetch giá thật từ vnstock.

Để xác nhận đang chạy data thật, kiểm tra:
- `metadata.demo` trong `web/data/latest.json` phải là `false` (hoặc không có)
- Banner trên dashboard **không** hiện "DEMO DATA"

### Q: Dữ liệu có realtime không?

**A:** **Không** — chỉ end-of-day (EOD). Sau 15:00 ICT đóng cửa, cron chạy lúc 16:00 → dữ liệu sẵn sàng ~16:05.

Trong giờ thị trường, dashboard hiện dữ liệu của **phiên trước**. Realtime cần WebSocket data feed (trả phí ~$500-2000/tháng) — không nằm trong phạm vi free.

### Q: Lịch sử bao nhiêu năm?

**A:** Mặc định fetch 180 phiên (~9 tháng). Đủ cho:
- MA50 ✓
- MA200 cần ít nhất 200 phiên → cần `--lookback 300`
- Backtest dài hạn: chỉnh `lookback_days=730` trong `run_daily.py`

vnstock hỗ trợ lấy lịch sử **đến 10+ năm** cho mã có lịch sử dài.

### Q: Giá tôi thấy có phải là giá điều chỉnh không?

**A:** **Có**. `data_fetcher.fetch_ohlcv(adjusted=True)` mặc định. Nghĩa là:
- Sau khi chia tách 1:2, giá lịch sử trước đó được nhân 0.5
- Sau cổ tức cổ phiếu 10%, giá trước đó chia 1.10

Để tắt và dùng giá raw: `fetch_ohlcv(adjusted=False)`.

### Q: Cache dữ liệu nằm ở đâu? Có cần xóa định kỳ không?

**A:** Tại `backend/data/cache/*.parquet`. Mỗi mã 1 file ~50-100KB. Tổng: ~150MB cho 1,600 mã, 1 năm history.

**Không cần xóa định kỳ** — code chỉ fetch incremental. Trừ khi:
- Bạn thay đổi `adjusted` flag → cache cũ là raw, mới là adjusted, khác nhau
- Bạn nghi ngờ data sai → xóa cache rồi chạy lại
- Hết disk space

Lệnh xóa:
```bash
rm -rf backend/data/cache/*.parquet
```

---

## Về sử dụng tín hiệu

### Q: Tôi nên mua khi thấy tín hiệu A+ chứ?

**A:** **Không nên vào lệnh ngay**. Quy trình đúng:

1. Tín hiệu xuất hiện → đưa vào watchlist
2. Đặt cảnh báo giá khi break vùng đỉnh 20 phiên trên app môi giới
3. **Chỉ khi giá thực sự break** (đóng cửa trên đỉnh + volume > 1.5× MA20) mới vào lệnh
4. Đặt stop-loss ngay dưới vùng tích lũy (mất ~3-5%)

Lý do: 30% tín hiệu A+ vẫn sai. Vào quá sớm = vào ngược.

### Q: Stop-loss đặt ở đâu?

**A:** Hai lựa chọn:

**A. Stop-loss kỹ thuật** (tốt cho mã có volatility thấp):
- Đặt dưới MA20 hoặc đáy vùng tích lũy 2-3%
- Phù hợp khi giá break đã chạy được ~5%

**B. Stop-loss % cố định**:
- Mất 5-7% vốn → cắt
- Phù hợp khi mới học, kỷ luật chưa cao

Quan trọng: **đặt ngay khi vào lệnh, không "để xem"**.

### Q: Có nên ALL-IN vào 1 mã A+?

**A:** **TUYỆT ĐỐI KHÔNG**.

Lý do:
- 30% A+ vẫn sai → mất nhiều nếu all-in vào lệnh sai
- Diversification giảm volatility portfolio
- Tránh tin xấu công ty riêng lẻ

Quy tắc đề xuất:
- Mỗi vị thế: **không quá 10-15% vốn**
- Cùng ngành: **không quá 30% vốn**
- Watchlist: **5-10 mã**, vào ~3-5 mã

### Q: Khi nào nên chốt lời?

**A:** Tùy chiến lược:

- **Swing trade (2-3 tuần)**: chốt khi giá +15% hoặc gặp kháng cự lớn
- **Position trade (1-3 tháng)**: chốt theo trailing stop (vd: dưới MA10)
- **Chốt từng phần** (đề xuất): 1/3 ở +10%, 1/3 ở +20%, 1/3 cho chạy theo trend

### Q: Lệnh sai nên cắt liền hay đợi hồi?

**A:** **CẮT NGAY khi chạm stop-loss**. Lý do:

- "Đợi hồi" → mất kỷ luật, mất nhiều hơn
- Cắt sớm 5% còn dễ hơn cắt lỗ 20% sau
- Tâm lý "hy vọng" là kẻ thù của trader

Nếu sau đó giá tăng lại? OK, bạn có thể vào lại với tín hiệu mới. Đừng tiếc.

---

## Lỗi kỹ thuật thường gặp

### Lỗi: `vnstock not installed`

```
ModuleNotFoundError: No module named 'vnstock'
```

**Cách khắc phục:**
```bash
pip install vnstock
# hoặc nếu lỗi quyền:
pip install --user vnstock
```

### Lỗi: `HTTPError 429 Too Many Requests`

API VCI/TCBS bị rate limit.

**Cách khắc phục:**
1. Đợi 5-10 phút, chạy lại
2. Giảm concurrency trong `data_fetcher.py`:
   ```python
   fetch_universe(..., max_workers=2, delay=0.5)
   ```
3. Chuyển source:
   ```python
   fetch_ohlcv(..., source='TCBS')  # thay vì 'VCI'
   ```

### Lỗi: `ConnectionError` khi fetch

Có thể do:
- **Mất internet** → kiểm tra mạng
- **Firewall doanh nghiệp** chặn vnstock → thử mạng khác
- **API VCI down tạm thời** → đợi 30 phút

Test nhanh:
```bash
curl https://trading.vietcap.com.vn
```

### Lỗi: GitHub Actions không chạy đúng giờ

**Triệu chứng**: Cron đặt 09:00 UTC nhưng chạy lúc 09:15-09:30

**Lý do**: GitHub Actions có **độ trễ 5-30 phút** cho scheduled workflows, đặc biệt giờ cao điểm.

**Cách khắc phục**: Bình thường, không cần làm gì. Nếu cần đúng giờ chính xác:
- Chuyển sang VPS với crontab thật
- Dùng Cloudflare Workers cron (đúng giờ hơn nhưng phức tạp setup)

### Lỗi: Web dashboard hiện "Failed to fetch"

**Nguyên nhân**: File `web/data/latest.json` không tồn tại hoặc đường dẫn sai.

**Cách khắc phục**:
```bash
# Tạo data bằng cách chạy scan
python backend/run_daily.py

# Hoặc sinh demo data
python backend/generate_demo_data.py
```

Kiểm tra:
```bash
ls -la web/data/latest.json   # phải tồn tại
```

### Lỗi: `ModuleNotFoundError: No module named 'scanner'`

**Nguyên nhân**: Chạy từ thư mục sai.

**Cách khắc phục**: Chạy từ **thư mục gốc project**:
```bash
cd vn-breakout-scanner   # ← phải ở đây
python backend/run_daily.py
```

KHÔNG chạy:
```bash
cd backend
python run_daily.py   # ❌ sẽ lỗi
```

### Lỗi: `pip not found` (Windows)

**Nguyên nhân**: Python không được add vào PATH lúc cài.

**Cách khắc phục**:
1. Cách 1: Cài lại Python, tick "Add to PATH"
2. Cách 2: Dùng `py -m pip install ...` thay vì `pip install ...`

### Lỗi: Tests fail

```bash
python -m pytest backend/tests/ -v
```

Nếu fail:
1. Cài lại dependencies: `pip install -r backend/requirements.txt`
2. Xem stack trace để biết test nào fail
3. Mở issue trên GitHub kèm output đầy đủ

### Cache parquet bị corrupted

```
pyarrow.lib.ArrowInvalid: ...
```

**Cách khắc phục**:
```bash
rm -rf backend/data/cache/
python backend/run_daily.py   # sẽ fetch lại từ đầu
```

---

## Câu hỏi về web app

### Q: Web có thể chạy offline không?

**A:** Sau khi load lần đầu, dashboard chạy hoàn toàn offline (Service Worker chưa implement nhưng có thể thêm). Tuy nhiên không cập nhật được data mới.

### Q: Có app mobile không?

**A:** Chưa có app native. Nhưng dashboard web đã responsive — mở trên trình duyệt mobile cũng dùng được.

Để add như "app" trên iOS/Android:
- iOS: Safari → nút Share → "Add to Home Screen"
- Android: Chrome → menu 3 chấm → "Add to Home screen"

### Q: Tại sao có 2 nút điều hướng ngày `‹ ›`?

**A:**
- `‹` = lùi 1 phiên (ngày cũ hơn)
- `›` = tiến 1 phiên (ngày mới hơn)
- `↺ Mới nhất` = về phiên hiện tại

Hữu ích để xem tín hiệu tuần trước có break không.

### Q: Cờ ⚑ bên cạnh mã nghĩa là gì?

**A:** Có sự kiện corporate action sắp tới (chia tách, cổ tức, phát hành).
- ⚑ **vàng**: sự kiện > 5 ngày tới → chú ý
- ⚑ **đỏ**: ≤ 5 ngày → cần thận trọng cao, giá có thể biến động bất thường

Hover lên flag để xem chi tiết. Click vào row để xem cảnh báo đầy đủ trong drawer.

### Q: Export CSV có tất cả dữ liệu không?

**A:** Có. CSV chứa **chính xác** số tín hiệu đang hiển thị (sau filter), với toàn bộ:
- Thông tin cơ bản (ticker, exchange, giá, %change, vol ratio, RSI, etc.)
- 10 cờ tiêu chí (0/1)
- Tổng điểm và rating
- Thông tin sự kiện sắp tới (nếu có)

### Q: Có thể custom các threshold không (vd: RSI 45-70 thay vì 50-65)?

**A:** Có. Edit `backend/scanner/criteria.py`:
```python
DEFAULT_CONFIG = {
    ...
    'rsi_lower': 45,    # ← thay đổi ở đây
    'rsi_upper': 70,
    'near_high_pct': 5.0,   # ví dụ nới rộng
    ...
}
```

Hoặc truyền config khi gọi:
```python
custom = {'rsi_lower': 45, 'rsi_upper': 70}
scanner = BreakoutScanner(config=custom)
```

### Q: Tôi muốn thêm tiêu chí của riêng tôi vào scanner?

**A:** Mở `backend/scanner/criteria.py`, trong hàm `evaluate()`, thêm:

```python
# Ví dụ: thêm tiêu chí MACD > 0
from .indicators import macd  # phải tự implement trong indicators.py
macd_line, signal_line = macd(close)
scores['macd_positive'] = int(macd_line.iloc[-1] > 0)
```

Sau đó chạy lại tests:
```bash
python -m pytest backend/tests/ -v
```

Note: thêm tiêu chí thứ 11 → max score = 11, rating thresholds cần update tương ứng.

---

## Vẫn còn câu hỏi?

- GitHub Issues: https://github.com/hailua87/vn-stock-filter/issues
- Đọc thêm: [ARCHITECTURE.md](ARCHITECTURE.md), [CRITERIA.md](CRITERIA.md), [DATA_SOURCES.md](DATA_SOURCES.md)
