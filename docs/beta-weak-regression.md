# Beta tính được nhưng vô nghĩa thống kê

*13/10/2026*

## Vấn đề

Sau khi cache OHLCV được lưu lại giữa các lượt (#73) và beta được ghi ra đầu ra
(#80), bản tổng hợp lượt weekly 11/10 nói:

```json
"beta_coverage": {"n": 84, "real": 84, "fallback": 0, "median_r_squared": 0.145}
```

Đọc nhanh thì đây là "xong việc": 84/84 mã có beta thật, không mã nào phải dùng
giá trị dự phòng. Nhưng con số thứ ba nói ngược lại — **R² trung vị 0,145**,
thấp nhất 0,006. Thị trường giải thích chưa tới 15% biến động của mã trung vị.

Hồi quy yếu thì hệ số dốc có sai số lớn. Sai số chuẩn của hệ số dốc OLS:

```
SE(β) = |β| × sqrt((1 − R²) / (R² × (n − 2)))
```

Với DGC (số thật, lượt 11/10): β_raw = 0,83, R² = 0,175, n = 96 tuần
→ SE = 0,186 → khoảng tin cậy 95% = **[0,47 ; 1,20]**.

Khoảng này **chứa 1,0**. Nghĩa là hồi quy không cung cấp bằng chứng nào để tin
0,83 hơn là tin 1,0. Con số 0,83 trông như một phép đo, nhưng nó là nhiễu.

Đo trên rổ thật: **37/83 mã (45%)** có khoảng tin cậy 95% chứa 1,0.

## Tại sao nó đổi kết quả

Beta đi vào CAPM → chi phí vốn chủ sở hữu → WACC → cả DCF lẫn P/B-ROE
justified. Nó không phải số trang trí.

Nhưng chỗ sai nghiêm trọng hơn nằm ở `methods_pb_roe.py`. Bản cũ:

```python
if market.get('beta_fallback', True):
    confidence -= 0.05
```

Tức: một beta 1,0 **vì không có dữ liệu** bị trừ 5% độ tin cậy, trong khi một
beta 0,22 với R² = 0,008 — gần như nhiễu thuần — **không bị trừ gì**, và đi
thẳng vào WACC như thể nó đáng tin.

Mã cũ **phạt sự trung thực và thưởng cho nhiễu.**

## Cách sửa

Không áp ngưỡng R² tự chọn. Ngưỡng tự chọn là một hằng số phải bảo vệ, và sẽ bị
tranh luận mãi (0,1? 0,2? tại sao?). Thay vào đó dùng **phép kiểm ý nghĩa thống
kê chuẩn** trên chính dữ liệu đã có (R², n) — không có hằng số nào phải chọn:

1. Tính `SE(β_raw)` theo công thức trên.
2. Nếu khoảng `β_raw ± 1,96·SE` chứa 1,0 → gắn cờ `weak`, **trả về beta = 1,0**
   và `method = 'weak_regression_prior'`.
3. Nếu không → dùng beta đã điều chỉnh Blume như trước.
4. `methods_pb_roe` trừ 5% cho **cả hai** trường hợp: không tính được, và tính
   được nhưng vô nghĩa.

1,0 ít nhất là một **tiên nghiệm thành thật**. 0,22 với R² = 0,008 là một con số
trông tự tin mà sai.

### Phép kiểm chạy trên `beta_raw`, không phải trên beta đã Blume

Điều chỉnh Blume (`0,67·raw + 0,33·1,0`) vốn đã co ước lượng về 1,0. Nếu kiểm
trên giá trị đã co thì phép kiểm bị co theo và gần như mã nào cũng "yếu".

Giả thuyết không của hồi quy là về **hệ số dốc thô**, nên phép kiểm phải chạy ở
đó. CSV là ví dụ tốt: beta đã Blume = 0,703 nhìn như gần 1,0, nhưng β_raw =
0,557 với SE = 0,165 cho khoảng [0,23 ; 0,88] — **không** chứa 1,0, nên đây là
ước lượng dùng được.

### Mức tin cậy 95%, thống nhất cả kho

Sổ theo dõi kết quả cũng dùng 95% (CLAUDE.md mục 11). Hạ riêng chỗ này xuống
90% là lặng lẽ nới chuẩn, và `test_nguong_la_khoang_95pc_khong_phai_90pc` canh
đúng việc đó bằng một cấu hình nằm giữa hai mức (z = 1,75).

## Ba trạng thái, không phải hai

`_tong_hop_beta` trước đây chia "thật / dự phòng". Nay ba ô:

| Ô | Nghĩa |
|---|---|
| `real` | tính được **và** khác 1,0 có ý nghĩa thống kê |
| `weak` | tính được nhưng khoảng 95% chứa 1,0 → đã rơi về 1,0 |
| `fallback` | không tính được (thiếu cache, dưới 30 tuần) |

Gộp `weak` vào `real` chính là cách bản tổng hợp 11/10 nói "84/84 thật" và làm
người đọc tin là đã xong. Thiếu khoá `weak` thì đếm vào ô **yếu** — mặc định bi
quan, cùng chiều với `methods_pb_roe` và `_beta_info`: một nguồn beta mới quên
gắn cờ phải gây ồn, không được lặng lẽ làm đẹp số liệu.

`median_r_squared` lấy trên **mọi** hồi quy chạy được, kể cả phần yếu. Lọc bỏ
phần yếu thì con số trông đẹp lên một cách giả tạo.

## Đo trước và sau

Hai lượt chạy **cùng ngày 13/10, cùng rổ 200 mã, cùng dữ liệu**, chỉ khác một
biến là phép kiểm ý nghĩa bật/tắt. Lượt "trước" chạy qua một bản bọc ngoài kho
(monkeypatch `calculate_beta`), không sửa mã.

Chốt chặn cho cặp đo: **0/82 mã lệch giá** giữa hai lượt. Nếu giá lệch thì cặp
đo không sạch và mọi hiệu số dưới đây vô nghĩa.

> **So sánh chéo với lượt 11/10 trong `web/data/` thì KHÔNG dùng được** — khác
> ngày, khác dữ liệu lấy được. Ví dụ CSV tụt 60 → 30 điểm độ tin cậy giữa hai
> lượt đó, nhưng nguyên nhân là Historical Multiple rơi 22.598 → 14.604, không
> liên quan gì tới beta. Đừng đọc hiệu hai lượt khác ngày rồi gán cho thay đổi
> này — tôi đã suýt làm đúng lỗi đó.

### Kết quả

| | TRƯỚC | SAU |
|---|---|---|
| Tín hiệu công bố | 88 | 83 |
| Độ tin cậy trung vị | 36,0 | 45,0 |
| Số mã đạt ≥ 50% | 37 | 37 |
| Beta bị thay bằng 1,0 | — | **32/82** |

Fair value của 32 mã bị thay beta: dịch **trung vị 1,6%**, lớn nhất 54,4%.

Kể cả SSI — R² = 0,493, cao nhất rổ — cũng rơi vào ô yếu: β_raw ≈ 1,167 với
SE ≈ 0,122 cho khoảng [0,93 ; 1,41], vẫn chứa 1,0.

### Vì sao mất 5 tín hiệu — hai cơ chế khác nhau, đã kiểm riêng

**Bốn mã** (BFC 30, BID 31, CTG 31, GVR 30) rụng vì khoản trừ 5% đẩy độ tin cậy
xuống dưới sàn `--min-confidence 0.30` của chính lượt chạy. Đây là tác động
trực tiếp và đúng ý định.

**Hai mã** (DRH 51, HVN 56) rụng vì lý do **khác hẳn**, và chỉ thấy được khi
chạy lại riêng từng mã cả hai chiều:

| Mã | TRƯỚC | SAU |
|---|---|---|
| DRH | chỉ Historical Multiple: 3.042 | **thêm** P/B-ROE: **474** → mâu thuẫn → conf 51 → 28 |
| HVN | EV/EBITDA 27.418, Hist 20.399 | **thêm** DCF FCFF: **77.497** → conf 54 → 29 |

Nâng beta lên 1,0 làm **mở cửa cho phương pháp trước đó bị chặn**: cửa hợp lệ
của DCF và P/B-ROE là `CoE − g > ε`, beta thấp thì `CoE` sát `g` nên phương
pháp bị loại; beta 1,0 kéo `CoE` lên vừa đủ để nó được nhận — và ngay sát mép
đó mẫu số gần triệt tiêu nên kết quả nổ, lệch 3–6 lần mọi phương pháp khác. Độ
phân tán vượt `MAX_METHOD_DISPERSION = 0,40`, và engine **chia đôi** độ tin cậy
(`overall_confidence *= 0.5`), đẩy cả hai xuống dưới sàn 0,30.

PVT là cùng một chuyện, chỉ không rụng: DCF FCFF xuất hiện với 94.998 trong khi
EV/EBITDA nói 34.179 và P/E nói 20.235 — fair value tổng hợp nhảy +54,4%.

**Đây là lỗi SẴN CÓ, bị thay đổi này phơi ra, không phải do nó gây ra.** Một
phương pháp có mẫu số gần triệt tiêu thì không nên được nhận với trọng số 20%
chỉ vì vượt qua `> ε`. Kết quả cuối (hạ độ tin cậy, gắn cờ mâu thuẫn) tình cờ
là hành vi **đúng** — định giá đó thật sự không đáng tin — nhưng đúng vì lý do
sai. Cần sửa riêng: siết cửa hợp lệ theo khoảng cách `CoE − g`, hoặc loại
phương pháp có fair value lệch quá xa trung vị các phương pháp còn lại.

Một mã (HDG) được **thêm** vào, vì lý do ngược lại: phân tán của nó tụt xuống
dưới ngưỡng nên độ tin cậy không còn bị chia đôi.

## Điều này KHÔNG sửa được

Nó làm đầu ra **thành thật hơn**, không làm beta **tốt hơn**. R² trung vị vẫn
~0,14. Muốn beta thật sự có ý nghĩa cho 45% rổ còn lại thì phải đổi cách đo, chứ
không phải đổi cách báo cáo:

- Cửa sổ dài hơn 2 năm (nhưng beta trôi theo thời gian — đánh đổi, không phải
  cải tiến).
- Beta theo ngành (shrink về trung bình ngành thay vì về 1,0) — cần phân ngành
  đủ tin và đủ mã mỗi ngành.
- Chấp nhận rằng với mã thanh khoản thấp trên thị trường VN, beta đơn lẻ **không
  đo được**, và CAPM theo mã là công cụ sai.

Chưa khảo cái nào trong ba. Ghi ra đây để lần sau không phải đoán là đã khảo.

## Nơi canh

`backend/tests/test_beta_weak.py` — 20 phép kiểm. Đã phá cho đỏ **20/20** cách
phá, gồm cả hai cách từng lọt qua ở lượt phá đầu và phải vá thước đo:

1. **`std_error` làm tròn 3 chữ số** thì chính phép kiểm công thức mất khả năng
   phân biệt `n` với `n−2` (chênh lệch ~1% bị rounding nuốt). Nay lưu 4 chữ số,
   và cấu hình fixture được chọn sao cho 2 chữ số là **không đủ** —
   `assert abs(round(se, 2) − se) > 5e-4` canh chính điều đó.
2. **Normalizer cắt dây `beta_weak`** (thay bằng `False` cứng) mà cả 11 phép
   kiểm lúc đó vẫn xanh: hai đầu dây đều đúng, chỉ dây bị cắt — và trong
   production thì khoản trừ không bao giờ nổ. Nay có phép kiểm cho từng seam:
   `market_metrics → normalizer → market → methods_pb_roe` và
   `market → _beta_info → latest.json`.

Bài học lặp lại của kho này: **kiểm chính thước đo trước khi tin kết luận**
(CLAUDE.md mục 6).
