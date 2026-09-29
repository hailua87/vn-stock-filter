# Hợp đồng dữ liệu — Sổ theo dõi kết quả tín hiệu

Chốt ngày 29/09/2026, TRƯỚC khi viết `backend/scanner/outcomes.py`.

Sổ này trả lời một câu duy nhất: **tín hiệu của một chiến lược, sau N phiên,
lãi hay lỗ so với thị trường?** Mọi quyết định dưới đây đều nhằm giữ cho câu trả
lời không bị bóp méo bởi chính cách đếm.

---

## Grain — một dòng là gì

**Một dòng = (chiến lược, mã, phiên VÀO).**

"Phiên vào" là phiên **ĐẦU TIÊN của một chuỗi liên tiếp**, không phải mọi phiên
mã có tín hiệu.

Vì sao quan trọng: MCH có tín hiệu 20 phiên liên tiếp trong pre_breakout. Đếm
mỗi phiên là một lần vào thì một mã duy nhất chiếm 20 quan sát, và nó lấn át
thống kê — 20 quan sát đó gần như cùng một tình huống, không phải 20 bằng chứng
độc lập. Đây là lỗi *overlapping observations*, và nó luôn làm kết quả trông
chắc chắn hơn thực tế.

Mã ra rồi vào lại sau vài phiên thì tính là **hai** lần vào — đó là hai lần
tín hiệu thật sự phát ra.

## Lịch — đếm phiên theo cái gì

**Phiên giao dịch trong CHÍNH chuỗi giá của mã đó**, không phải ngày lịch, cũng
không phải danh sách phiên có bản lưu.

Vì sao: mã nghỉ giao dịch vài phiên thì đếm theo ngày lịch sẽ lấy giá của một
thời điểm khác hẳn với mã bình thường. Đếm theo chuỗi của chính nó giữ cho "sau
5 phiên" có cùng nghĩa với mọi mã.

## Giá vào và giá ra — lấy từ đâu

**Cả hai lấy từ CÙNG MỘT chuỗi giá đã điều chỉnh** (`by_ticker_all` trong
`run_daily`). **KHÔNG** dùng trường `close` lưu trong bản lưu phiên.

Vì sao: `close` trong bản lưu là giá **tại thời điểm đó**, chưa điều chỉnh cho
sự kiện quyền xảy ra SAU đó. Chuỗi giá của VCI thì điều chỉnh hồi tố. Lấy giá
vào từ bản lưu và giá ra từ chuỗi là **trộn hai gốc khác nhau** — một mã chia
cổ tức 10% sau khi vào lệnh sẽ hiện thành lỗ 10% dù người cầm không mất gì.

## Measure

| Tên | Công thức | Ghi chú |
|---|---|---|
| `ret` | `(giá_ra − giá_vào) / giá_vào` | lãi/lỗ thô |
| `excess` | `ret − ret_VNINDEX cùng khoảng` | phần hơn/kém thị trường |

**Bắt buộc có `excess`.** "Sau 20 phiên +3%" là con số vô nghĩa nếu thị trường
cùng kỳ +5%. Không có mốc so sánh thì sổ này chỉ đo thị trường chứ không đo
chiến lược.

VN-Index lấy theo **cùng hai ngày lịch** (ngày vào → ngày ra của mã đó), không
theo số phiên của index — vì hai bên có thể lệch phiên.

## Chân trời

`5, 10, 20` phiên. Ba mốc để thấy tín hiệu tắt dần hay còn hiệu lực.

## Loại trừ

| Trường hợp | Xử lý |
|---|---|
| Chưa đủ N phiên sau ngày vào | **Loại**, đếm riêng vào `incomplete` |
| Không có chuỗi giá cho mã | **Loại**, đếm riêng vào `no_price` |
| Không tìm thấy ngày vào trong chuỗi giá | **Loại**, đếm riêng vào `no_entry_bar` |

**Không** thay giá trị thiếu bằng 0. Một tín hiệu chưa đủ thời gian không phải
là một tín hiệu hoà vốn.

## Thống kê báo cáo

- `n` — số quan sát THẬT SỰ tính được (sau loại trừ)
- `median_ret`, `median_excess` — **trung vị**, không phải trung bình
- `hit_rate` — tỷ lệ `excess > 0`

Vì sao trung vị: một mã tăng 300% kéo trung bình lên và làm cả chiến lược trông
tốt, trong khi trung vị cho biết mã điển hình ra sao.

## Điều sổ này KHÔNG nói

- **Không phải backtest.** Không mô phỏng vào/ra lệnh, không phí, không trượt
  giá, không quản lý vốn.
- **Không đủ mẫu để kết luận.** Bản lưu chỉ có từ 28/04/2026 — khoảng 5 tháng,
  và với chân trời 20 phiên thì phần cuối bị loại. Một chiến lược "thắng" ở đây
  có thể chỉ là thắng trong một pha thị trường.
- **Không tính sự kiện quyền ngoài giá.** Cổ tức tiền mặt đã nằm trong chuỗi
  điều chỉnh; quyền mua thì không.

Mọi con số sổ này xuất ra đều phải đọc kèm ba giới hạn trên.
