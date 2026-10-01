# Khảo nguồn cho Chứng khoán và Bảo hiểm — 01/10/2026

Hai cổng `HOLD_ONLY_INDUSTRIES` trong `backend/scanner/strategies/valuation/engine.py`
chặn 15 mã chứng khoán và 3 mã bảo hiểm:

| Ngành | Lý do cổng ghi |
|---|---|
| Securities | `chưa tách được dư nợ margin quá hạn` |
| Insurance | `chưa có biên khả năng thanh toán` |

Tài liệu này ghi lại **nguồn có gì và không có gì**, để lần sau không phải dò lại.

Ghi vì một lý do cụ thể: ngày 24/09 kết luận "không nguồn nào có NPL ngân hàng"
đã **sai**, và nó sống sót vì không ai ghi lại đã hỏi ở đâu. Thực tế dữ liệu
nằm ngay trong section `NOTE` của VCI, và khi tìm đúng chỗ thì mở được 17/17
ngân hàng (PR #69). Một kết quả âm không được ghi là một kết quả âm sẽ được
khảo lại từ đầu — hoặc tệ hơn, được tin mà không ai kiểm.

## Đã hỏi những đâu

Cả hai nguồn đã nối, mọi bảng, **quét toàn bộ nhãn** (tiếng Việt lẫn tiếng Anh)
chứ không đoán vài từ khoá:

| Nguồn | Bảng | Kết quả |
|---|---|---|
| VCI `/financial-statement` | `NOTE` | có dữ liệu tới 2025 — CK 717 trường, BH 314 trường |
| VCI `/financial-statement/metrics` | `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `NOTE` | nhãn tiếng Việt đầy đủ (CK 642 khoản mục) |
| KBS `/stock/finance-info` | `CSTC`, `CDKT`, `KQKD` | 161–191 nhãn/mã |

Mã khảo: SSI, VND, HCM, VCI (CK); BVH, PVI, MIG (BH). Độ phủ đo trên cả 18 mã.

## Chứng khoán — có dư nợ margin, KHÔNG có phân loại quá hạn

Đo trên cả 15 mã, kỳ 2025:

| Khoản mục | Trường | Độ phủ |
|---|---|---|
| Cho vay nghiệp vụ ký quỹ (margin) | `nos446` | **15/15** |
| Các khoản cho vay và phải thu | `nos445` | 15/15 |
| Dự phòng giảm giá — các khoản cho vay và phải thu | `nos498` | **6/15** |
| Dự phòng các khoản phải thu khó đòi | `nos542` | 12/15 |

**Không có** trong bất kỳ nguồn nào:

- Phân loại tuổi nợ / quá hạn của sổ margin — tức đúng thứ cổng đang đòi.
- **Tỷ lệ an toàn tài chính** (Thông tư 91/2020), là thứ tương đương CAR của
  ngành này. Đã tìm cả theo nhãn `an toan`, `ty le`, `von kha dung`,
  `adequacy` trên cả bốn bảng của VCI và ba bảng của KBS.

### Vì sao không thay bằng tỷ lệ dự phòng

Thứ gần nhất là `nos498 / nos445` — tỷ lệ dự phòng trên sổ cho vay. Hai lý do
không dùng:

1. **Độ phủ 6/15 = 40%**, dưới chính ngưỡng `COVERAGE_MIN = 0.70` của dự án
   (`backend/scanner/quality/config.py`). Không qua được ngưỡng của chính mình.
2. **Yếu hơn hẳn trường hợp ngân hàng.** Ở ngân hàng có CẢ phân loại khách quan
   (nhóm 3–5, do Thông tư 02/2013 và 11/2021 quy định) LẪN dự phòng. Ở đây chỉ
   còn dự phòng — con số do chính công ty tự ước lượng, có độ trễ và có dư địa
   điều chỉnh. Mở cổng bằng một mình nó là hạ chuẩn chứ không phải tìm được
   bằng chứng.

## Bảo hiểm — cổng định giá KHÔNG phải chỗ đang chặn

Không có biên khả năng thanh toán ở bất kỳ nguồn nào. Thứ có:

| Khoản mục | Trường | Độ phủ (3 mã) |
|---|---|---|
| Thu phí bảo hiểm | `noi150` | 3/3 |
| Chi bồi thường bảo hiểm gốc | `noi188` | 3/3 |
| Dự phòng nghiệp vụ bảo hiểm | `noi103` | 2/3 (MIG trống) |
| Dự phòng bồi thường | `noi118` | 2/3 (MIG trống) |

Đủ tính tỷ lệ bồi thường, không đủ tính biên khả năng thanh toán.

**Nhưng ràng buộc thật nằm ở chỗ khác.** Cả 3 mã bảo hiểm hiện dừng ở trạng
thái `RES` ngay từ tầng chấm chất lượng, và **không mã nào có mặt trong đầu ra
định giá** — tức chúng chưa bao giờ đi tới cổng này. Lý do: `INSURANCE` không
nằm trong `ACTIVE_MODELS`, vì nhóm chỉ có 3 mã, dưới `MIN_PEER_GROUP = 8`.

Gỡ cổng định giá cho bảo hiểm sẽ **không đổi gì trên màn hình**. Muốn mở thật
thì phải nới universe rộng hơn nhiều, hoặc chấm bảo hiểm theo ngưỡng tuyệt đối
thay vì percentile — đúng hai việc `config.py` đã ghi là của Phase 4.

Chú thích ở `config.py` ghi "nhóm chỉ có 2 mã"; nay là 3 (BVH, MIG, PVI). Số cũ,
không ảnh hưởng kết luận vì 3 vẫn dưới 8.

## Hiện trạng 18 mã (dữ liệu 01/10/2026)

Chứng khoán: 11/15 mã mang đúng dòng chặn margin. 4 mã còn lại (FTS, VIX, ORS,
CTS) không có trong đầu ra định giá tuần này nên không mang dòng nào — chúng bị
chặn vì lý do khác, không phải vì cổng.

Trong 11 mã bị chặn có 2 mã mà mô hình đã ra kết luận có hướng rồi bị hạ:
HCM (`STRONG SELL` → `HOLD`) và TVS (`SELL` → `HOLD`). Tức cổng đang giấu đi
hai tín hiệu BÁN, không phải hai tín hiệu MUA — đáng ghi, vì nó cho thấy cổng
không thiên về phía thận trọng như trực giác tưởng.

## Kết luận

| Nhóm | Mở được không | Vì sao |
|---|---|---|
| Chứng khoán | Không | Chỉ tiêu cổng đòi không tồn tại ở nguồn nào; phương án thay thế gần nhất phủ 40%, dưới ngưỡng 70% của dự án |
| Bảo hiểm | Không, và mở cũng vô nghĩa | Chỉ tiêu không tồn tại; và cổng này không phải chỗ đang chặn — `MIN_PEER_GROUP = 8` vs 3 mã mới là |

## Muốn mở thì cần gì

Không phải việc viết thêm mã — là việc có thêm **nguồn**:

- **Chứng khoán**: báo cáo tỷ lệ an toàn tài chính theo Thông tư 91/2020, hoặc
  thuyết minh phân loại tuổi nợ sổ margin. Cả hai đều nằm trong BCTC kiểm toán
  bản đầy đủ, không nằm trong bộ dữ liệu chuẩn hoá của hai nguồn hiện có.
- **Bảo hiểm**: biên khả năng thanh toán (bản công bố của doanh nghiệp), VÀ
  universe đủ 8 mã cùng ngành — hoặc đổi cách chấm sang ngưỡng tuyệt đối.

Trước khi kết luận lại "không có nguồn", hãy đọc mục "Đã hỏi những đâu" ở trên
và hỏi thêm chỗ CHƯA có trong đó. Lặp lại đúng những phép thử này thì sẽ ra
đúng kết quả này.
