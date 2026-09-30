# Backtest ngưỡng Module B — vì sao chưa làm được, và cần gì để làm được

Chốt 30/09/2026.

## Câu hỏi

Ngưỡng đạt chuẩn là `quality ≥ 75, growth ≥ 70, governance ≥ 70, resilience ≥ 65`
(percentile trong universe). Chính dữ liệu xuất ra ghi *"ngưỡng là mặc định cấu
hình, chưa backtest"*. Câu hỏi: mã trên ngưỡng có thật sự tốt hơn mã dưới ngưỡng?

## Vì sao chưa trả lời được

| Cần | Có |
|---|---|
| Nhiều mốc quan sát ĐỘC LẬP, trải qua vài pha thị trường | **4 bản lưu, trong 8 ngày** |
| Chân trời 60–250 phiên (3 tháng – 1 năm) cho chỉ tiêu dài hạn | **~6 phiên** |

```
web/data/quality/archive/
  2026-09-22  100 mã
  2026-09-23  200 mã
  2026-09-24  200 mã
  2026-09-27  200 mã
```

Bốn bản lưu này còn **không độc lập** — chúng là bốn ngày liên tiếp của cùng một
kỳ BCTC, nên điểm gần như không đổi. Số quan sát thực chất là **một**.

## Vì sao KHÔNG dựng lại điểm trong quá khứ

Có 8 năm BCTC trong cache, nên về lý thuyết có thể tính điểm "như thể đang ở
cuối 2022" rồi đo lợi suất sau đó. **Không làm**, vì ba lệch không sửa được:

**Sống sót.** Cache chỉ có mã còn niêm yết và còn trong rổ top thanh khoản
*hôm nay*. Mã sụp đổ rồi mất thanh khoản không có mặt — và chúng chính là nhóm
mà một chỉ tiêu chất lượng lẽ ra phải loại. Đo trên nhóm sống sót sẽ cho kết
quả đẹp một cách giả tạo.

**Nhìn trước.** Percentile tính trong universe; universe hôm nay khác universe
2022. Nhóm so sánh, phân ngành, peer group — tất cả đều là bản *hôm nay*.

**BCTC đã bị sửa.** Cache giữ bản MỚI NHẤT của mỗi kỳ, gồm cả số đã điều chỉnh
lại. Sổ snapshot (`backend/data/snapshots/`) ghi được chuyện đó, nhưng nó chỉ
bắt đầu từ 23/09/2026 nên không nói được gì về 2022.

Một backtest mang ba lệch này sẽ ra con số **đẹp và sai**, và tệ hơn là không có
gì báo rằng nó sai.

## Cần gì để làm được

Bản lưu chấm chất lượng tích lũy theo lịch tuần. Với chân trời 250 phiên:

- **~1 năm** để có mốc quan sát đầu tiên có kết quả
- **~2–3 năm** để có đủ mốc độc lập qua nhiều pha thị trường

Không có đường tắt. Đây là loại câu hỏi chỉ thời gian trả lời được.

## Điều ĐÃ trả lời được ngay

Ngưỡng có **đạt tới được** không? Trả lời được, và không cần nhìn về tương lai.
Xem `scanner/quality/diagnostics.py` — phễu tính lại mỗi lượt chạy.

Đo ngày 27/09/2026:

```
200 mã → 184 chấm đủ 4 chiều → 3 vượt cả 4 ngưỡng → 0 đạt chuẩn

CTR  quality 92  growth 78  governance 100  resilience 66  → định giá ĐẮT
HDB  quality 86  growth 88  governance 100  resilience 66  → CHƯA CÓ định giá
FPT  quality 76  growth 76  governance 100  resilience 72  → CHƯA CÓ định giá
```

**Ngưỡng không sai.** Tỷ lệ 3/184 ≈ 1,6% đúng như phép nhân percentile gợi ý:
top 25% × 30% × 30% × 35% ≈ 0,8% nếu bốn chiều độc lập, và cao hơn chút là đúng
vì doanh nghiệp tốt thường tốt ở nhiều chiều cùng lúc.

**Nút thắt là ĐỘ PHỦ ĐỊNH GIÁ.** `classify` đòi thêm định giá Hấp dẫn hoặc Hợp
lý mới cho đạt chuẩn, mà 182/200 mã không có định giá. Cả ba mã vượt hết ngưỡng
đều rớt ở đúng bước cuối này.

Nên việc đáng làm tiếp **không phải** chỉnh ngưỡng, mà là tăng độ phủ định giá.
Hai mã HDB và FPT chỉ cần có định giá là đạt chuẩn ngay.

## Điều KHÔNG được làm

Đừng hạ ngưỡng để "có mã đạt chuẩn". Ngưỡng percentile mà hạ thì chỉ đổi nhãn
cho cùng những mã ấy, không đổi thứ hạng — và nó xoá mất thông tin rằng hiện
không có mã nào vừa tốt vừa đáng giá.
