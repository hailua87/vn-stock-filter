# Hiệu chỉnh trọng số tiêu chí

Tài liệu quy trình xác định trọng số cho 10 tiêu chí Pre-Breakout.
Code: `backend/scanner/weight_calibration.py` · CLI: `backend/run_weight_calibration.py`

---

## Nguyên tắc

**Không tối ưu hit rate hay lợi nhuận backtest.** Cả hai đều dẫn thẳng tới overfit.
Mục tiêu là tìm **w** sao cho `score = Σ wᵢ·cᵢ` có tương quan hạng chéo **cao và ổn định**
với lợi nhuận vượt trội tương lai.

| # | Nguyên tắc | Vì sao |
|---|---|---|
| 1 | Nhãn = **rank chéo** lợi nhuận vượt VN-Index | Khử beta thị trường và biến động thay đổi theo thời gian. Dùng lợi nhuận tuyệt đối thì mọi tiêu chí đều "đúng" trong bull market |
| 2 | Quét **nhiều chân trời H** trước khi chốt | H = 1–5 phiên là vùng đảo chiều (TTCK VN do cá nhân chi phối nên rất mạnh); H = 20–60 là vùng momentum. Cùng bộ tiêu chí có thể có IC trái dấu |
| 3 | Ngưỡng **t > 3,0**, không phải 2,0 | 10 tiêu chí × 4 chân trời = 40 phép thử. Bonferroni cho α = 5% ⇒ t ≈ 3,2 |
| 4 | Sai số chuẩn **Newey-West** lag = H | Nhãn H phiên khiến IC các phiên liền kề tự tương quan mạnh. Bỏ qua sẽ thổi phồng t-stat ~√H lần (H = 20 → 4,5 lần) |
| 5 | **Gom cụm** trước khi phân bổ | `atr_squeeze` và `bb_squeeze` đo cùng một hiện tượng. Không gom thì một thông tin được tính hai lần |
| 6 | **Shrinkage 50%** về prior đều nhau | Cỡ mẫu quá nhỏ (xem dưới) |
| 7 | Không dùng ML | Cỡ mẫu không cho phép, và tính giải thích được của điểm số là một tính năng sản phẩm |

---

## Ràng buộc cỡ mẫu — đọc trước khi tin bất kỳ con số nào

Để phát hiện IC = 0,03 với power 80%, α = 5%:

```
cần ICIR × √N > 2,8 ;  với IC_std ≈ 0,15 → ICIR ≈ 0,20
⇒ N > 196 kỳ ĐỘC LẬP
```

Với H = 20 phiên, một năm chỉ cho **~12 kỳ độc lập** → cần **~16 năm** để kết luận
chắc chắn về **một** tiêu chí. Hệ quả bắt buộc:

- Không ước lượng 10 tham số tự do. Mục tiêu: **3–5 tham số hiệu dụng**.
- Dùng cross-section hằng ngày + Newey-West thay vì kỳ rời rạc.
- **Cần tối thiểu 5–7 năm dữ liệu.** Cache mặc định chỉ 400 phiên (~1,6 năm) →
  chạy `backfill_history.py` trước.

---

## Quy trình

```bash
# Bước 0 — backfill (BẮT BUỘC nếu cache < 750 phiên)
python backend/backfill_history.py --years 6 --limit 400 \
       --extra-tickers delisted.txt        # tránh survivorship bias

# Bước 1-5 — chạy toàn bộ quy trình
python backend/run_weight_calibration.py --horizons 5,10,20,40 --horizon 20 \
       --json-out backend/data/results/calibration.json

# Bước 6 — chỉ áp khi kiểm định ngoài mẫu ĐẠT (CLI tự từ chối nếu không đạt)
python backend/run_weight_calibration.py --horizon 20 --apply
```

| Bước | Nội dung | Đầu ra |
|---|---|---|
| 1 | IC đơn biến + t-stat Newey-West | Bảng IC theo tiêu chí × chân trời |
| 2 | Ma trận tương quan → gom cụm (ngưỡng \|ρ\| = 0,6) | Danh sách cụm |
| 3 | Phân bổ theo ICIR ở **cấp cụm**, chia đều trong cụm | Trọng số thô |
| 4 | Shrink 50% về prior đều nhau, chuẩn hoá tổng = 10 | Trọng số đề xuất |
| 5 | Walk-forward có **purging + embargo** | IC ngoài mẫu, độ ổn định, DSR |
| 6 | Áp trọng số (có chốt chặn) | `backend/data/criteria_weights.json` |

**Purging và embargo** (bước 5) là bắt buộc: nhãn H phiên khiến quan sát train
nằm sát mốc chia "nhìn thấy" tương lai của tập test. Không purge = rò rỉ dữ liệu,
dạng lỗi tinh vi và phổ biến nhất trong backtest tài chính.

---

## Tiêu chí chấp nhận

Một tiêu chí được giữ khi **đồng thời**: `|IC| > 0,02` **và** `|ICIR| > 0,25`
**và** `|t| > 3,0`. Bộ trọng số mới chỉ được áp khi:

- IC **ngoài mẫu** > 0,02
- Ít nhất 60% số fold có IC dương
- Trọng số **không đảo dấu** giữa các fold (CV < 0,5)
- Deflated Sharpe > 0,95

`run_weight_calibration.py --apply` **tự từ chối** khi IC ngoài mẫu không đạt —
áp trọng số fit trong mẫu mà không có xác nhận ngoài mẫu chính là định nghĩa của
overfitting.

---

## Giả thuyết trước khi chạy

Viết ra trước để tránh tự hợp lý hoá sau khi thấy kết quả:

| Tiêu chí | Dự đoán | Cơ sở |
|---|---|---|
| `near_high20` | **IC dương mạnh nhất** | Hiệu ứng 52-week-high (George & Hwang 2004) — một trong số ít anomaly lặp lại ở mọi thị trường |
| `stealth_accum` | Dương vừa | Volume-price divergence |
| `vol_surge` | Dương yếu | Đã bị arbitrage nhiều |
| `pocket_pivot` | Dương yếu, mẫu nhỏ | Kacher; ít bằng chứng học thuật |
| `atr_squeeze`, `bb_squeeze` | **IC ≈ 0** | Squeeze dự báo **biên độ**, không dự báo **hướng** — hiểu lầm kinh điển |
| `ma_align` | **Có thể ÂM ở H ≤ 10** | Vùng đảo chiều ngắn hạn |
| `rsi_zone` | IC ≈ 0 | Là bộ lọc, không phải yếu tố dự báo |
| `no_gap_down` | Không đo được | ~95% mã đạt → chuyển thành **veto** |

Kết quả khớp phần lớn bảng này → mô hình đáng tin. Ngược hoàn toàn → **nghi ngờ
lỗi dữ liệu trước khi tin**.

---

## Kỷ luật vận hành

- **Đóng băng trọng số 6–12 tháng.** Hiệu chỉnh liên tục = overfit theo thời gian thực.
- **Champion/Challenger**: bộ mới chạy shadow 3 tháng trước khi thay chính thức.
- **Version hoá**: mọi tín hiệu mang `weights_version`; thiếu nó thì backtest trên
  archive về sau vô nghĩa vì không biết điểm số sinh ra bằng bộ trọng số nào.

---

## Ưu tiên cao hơn việc tinh chỉnh trọng số

Tối ưu trọng số trên 10 tiêu chí tương quan cao mang lại **ít giá trị hơn** việc
thêm một chiều thông tin thực sự mới:

1. **RS rank vs VN-Index** — đã có trong `market_regime.py`, kỳ vọng IC cao hơn 8/10 tiêu chí hiện tại
2. **Market regime làm cổng** (nhân tỷ trọng), không cộng vào điểm
3. **RS ngành** — momentum ngành mạnh ở VN
4. **Dòng tiền khối ngoại** — đặc thù VN, thực sự độc lập với nhóm tiêu chí giá/khối lượng
5. …rồi mới đến tinh chỉnh trọng số
