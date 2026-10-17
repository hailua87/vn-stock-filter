# Nhánh dự phòng của engine định giá bỏ qua chính ngưỡng của nó

**Ngày đo:** 17/10/2026 · **Mã nguồn trước:** `main` @ `78c2383`
**Kết luận:** **đã sửa.** Engine **từ chối kết luận** (`value_ticker` trả `None`)
khi không cấu phần nào vừa có `fair_value > 0` vừa có
`confidence >= NGUONG_CONF_CAU_PHAN`, thay vì trộn lại chính những cấu phần nó
vừa loại — hoặc, tệ hơn, lấy **giá làm fair value**.

Tài liệu này ghi cả **"đã hỏi những đâu"** theo CLAUDE.md §10 và **cách phá cho
đỏ** theo §6.

Tiếp nối `docs/pe-roe-am-khong-chan-confidence.md` §7.1 — phiên đó tìm ra chỗ
hỏng trong lúc đo việc khác, và để lại vì nó rộng hơn phạm vi của PR đó.

---

## 1. Cơ chế

`value_ticker` áp ngưỡng độ tin cậy cho **từng cấu phần** ở hai chỗ — chọn ứng
viên để trộn, và vòng trộn:

```python
du_dieu_kien = {... if r.fair_value_per_share > 0 and r.confidence >= 0.15}
...
if result.fair_value_per_share <= 0 or result.confidence < 0.15: continue
```

Nhưng khi **không cấu phần nào** qua được, engine rơi vào nhánh dự phòng ngay
dưới chúng — và nhánh đó **không đọc `confidence` nữa**:

```python
if total_effective_weight == 0:
    valid_fvs = [r.fair_value_per_share for r in results.values()
                 if r.fair_value_per_share > 0]        # CHI xet fv > 0
    fair_value = sum(valid_fvs)/len(valid_fvs) if valid_fvs \
                 else data["market"]["current_price"]  # gia = fair value
    overall_confidence = 0.20
```

Tức ngưỡng engine vừa áp ở trên bị **chính engine lách ở dưới**. Nhánh đó làm
hai việc, và cả hai đều sai theo đúng một kiểu:

1. **Trộn lại cấu phần vừa bị loại** — trung bình đơn thuần mọi cấu phần có
   `fair_value > 0`, bất kể độ tin cậy.
2. **Lấy giá làm fair value** khi không còn cấu phần nào dương, kèm
   `confidence = 0,20`.

`total_effective_weight == 0` **tương đương** `du_dieu_kien` rỗng: mọi trọng số
gốc đều `> 0` (`methods_to_run` đã lọc `w > 0`) và mọi `confidence` được giữ
đều `>= 0,15 > 0`, nên tổng chỉ bằng 0 khi không còn ứng viên nào. Không có
đường nào khác vào nhánh này.

---

## 2. Đo trước — rổ 200 mã, cache ấm

```
python backend/run_valuation.py --limit 200 --web-data-dir <ngoài kho> \
    --snapshot-registry "" --min-confidence 0
```

180 tín hiệu công bố, 20 mã rụng vì cổng ngoại lai. `latest.json` **không giữ
`methods_used` của 20 mã ngoại lai**, nên phần điểm danh toàn rổ chạy thêm một
bản dò tạm **ngoài kho** (CLAUDE.md §1) gọi **chính `value_ticker`** trên cùng
cache và cùng peer DB, rồi đọc `to_dict()` của cả 200 mã — lấy số từ payload của
engine, không suy lại công thức (§6).

**Chốt chặn:** `current_price` của bản điểm danh trùng khớp `latest.json` trên
**180/180** mã công bố.

**Hai mã đi vào nhánh dự phòng, trên 200:**

| mã | cấu phần | `fair_value` | giá | upside | conf | ở `latest.json`? |
|---|---|---|---|---|---|---|
| **UNI** | `0 / −1.577 / −1.611 / 0` — **không cái nào dương** | **6.700** | 6.700 | **0,0%** | 17 | **CÓ** |
| **WSS** | P/E `conf = 0,05`, fv 22.671 | 22.671 | 5.900 | +284,2% | 17 | không (ngoại lai) |

Tức **1/200 mã** rơi tiếp vào nhánh `else current_price`, và đó là mã **được
công bố**.

### UNI là ca nguy hiểm hơn WSS

Bốn cấu phần của UNI: `P/E = 0 (conf 0,00)`, `DCF FCFF = −1.577 (conf 0,75)`,
`EV/EBITDA = −1.611 (conf 0,75)`, `Historical = 0 (conf 0,00)`. Hai cấu phần
**rất tự tin** và nói vốn chủ sở hữu **âm**. Engine công bố
`fair value = 6.700 = đúng giá, upside 0,0%`.

Và đây là chỗ phải đọc kỹ: **`upside 0,0%` LỌT cả hai cổng công bố.**
`MIN/MAX_PUBLISHED_UPSIDE` chỉ chặn `< −80%` và `> +200%`, nên "fair value =
giá" là trạng thái **được công bố**, không phải bị chặn. WSS `+284%` thì bị
chặn. Nghịch lý: mã **không có định giá nào** đi qua cổng, còn mã có một định
giá tồi thì không.

Đó chính là con số PR #98 vừa gỡ cho WSS và PR #100 vừa gỡ cho VMC — gỡ ở cửa
trước, cửa sau vẫn mở.

### Tác động thật lên production: **không có, hôm nay**

Phải nói rõ để không báo to hơn thực tế. Mã đi vào nhánh dự phòng luôn có
`overall_confidence = 0,20 × classification.confidence ≤ 0,20`, mà
`--min-confidence` của production là **0,30** (mặc định; `weekly-valuation.yml`
không truyền cờ). Nên **nhánh dự phòng không bao giờ ra tới `latest.json` của
production** — UNI xuất hiện được chỉ vì lượt đo dùng `--min-confidence 0`.

Giá trị của bản sửa này là **gỡ cơ chế**, không phải đổi con số tuần này:

- Cổng duy nhất đang chặn là `--min-confidence 0,30` của `run_valuation`, chứ
  không phải engine. Hạ cờ đó, thêm một lối công bố khác, hay một cấu phần mới
  tình cờ cho `confidence` cao hơn — là con số giả ra mặt tiền.
- Trần `0,20` đó cũng là lý do **không** chọn hướng "giữ nhánh dự phòng nhưng
  gắn cờ": nó đã là một cái cờ ngầm, và nó đã không đủ.

---

## 3. Cách sửa và vì sao chọn cách này

Ba hướng đã cân nhắc:

| hướng | vì sao không / vì sao có |
|---|---|
| Nhánh dự phòng tôn trọng cùng ngưỡng 0,15 | Tôn trọng xong thì **hết ứng viên** — không còn gì để trộn. Đây không phải một hướng khác, nó dẫn về đúng câu hỏi "rồi làm gì" |
| Giữ nhánh dự phòng, gắn cờ tường minh để `run_valuation` lọc | `confidence = 0,20` **đã là** cờ ngầm và đã không đủ. Thêm một cờ nữa là thêm một con số giả có đường ra mặt tiền, chỉ chờ ai đó quên lọc. §2 đo được `upside 0,0%` lọt cổng |
| **Không công bố mã nào không có cấu phần nào đủ điều kiện** | **Đã chọn.** Không có định giá thì không công bố con số nào |

`value_ticker` trả `None`. Cùng tinh thần `diff.mjs` **từ chối so sánh** khi
thiếu font (CLAUDE.md §8) và `kiem-nhanh-da-vao-main.sh` **thoát mã 2** khi xung
đột (§13): từ chối kết luận là một kết quả, đoán thì không.

`run_valuation.py:302` đã coi `None` là "không có định giá" từ trước, nên không
có đường nào để con số giả lọt ra.

Hai việc kèm theo:

* **Rút `0.15` thành `NGUONG_CONF_CAU_PHAN`.** Trước đây nó viết cứng ở đúng hai
  chỗ, và nhánh dự phòng ngay dưới bỏ qua nó. Một hằng số có tên để cả ba chỗ
  đọc cùng giá trị, và để phép kiểm nói được "nhánh dự phòng tôn trọng ngưỡng
  nào".
* **`run_valuation` ghi mã bị từ chối vào `metadata.khong_co_dinh_gia`** (và một
  dòng `WARNING`). Một mã lặng lẽ biến mất khỏi đầu ra thì không ai nói được là
  nó bị chặn hay bị bỏ sót — cùng lý do `methods_excluded` phải có trong đầu ra.

---

## 4. Đo sau — cùng một thước

Cặp đo: cùng cache ấm, cùng phiên, cùng ngày, cùng lệnh, cùng bản dò điểm danh.

Số liệu ở §5. **Chốt chặn:** `current_price` phải trùng trên mọi mã chung; lệch
thì cặp đo không sạch và phải nói ra.

---

## 5. Kết quả cặp đo

**Chốt chặn: cặp đo SẠCH.** `current_price` trùng khớp **200/200** mã của bản
điểm danh và **179/179** mã công bố chung. Rổ 200 mã của hai lượt **giống nhau
từng mã** (`get_ticker_universe` chọn theo thanh khoản, nên điều này phải kiểm
chứ không được giả định).

### Điểm danh toàn rổ 200

| | trước | sau |
|---|---|---|
| engine trả báo cáo | 200 | **198** |
| engine trả `None` | 0 | **2** (WSS, UNI) |
| mã có `methods_used == []` | **2** (WSS, UNI) | **0** |

### `latest.json` (`--min-confidence 0`)

| | |
|---|---|
| số tín hiệu | 180 → **179** |
| **RA khỏi `latest.json`** | **UNI** — đúng mã có `fair value = giá, upside 0,0%` |
| **VÀO `latest.json`** | **không mã nào** |
| `fair_value` đổi | **0/179** mã chung |
| `methods_used` đổi | **0/179** mã chung |
| mã ngoại lai | 20 → **19** (WSS rời danh sách: engine từ chối **trước** cổng ngoại lai) |
| `metadata.khong_co_dinh_gia` | khoá mới, `["WSS", "UNI"]` |

**Bản sửa không chạm vào mã nào khác.** `fair_value` đổi 0/179 là con số quan
trọng nhất ở đây: nhánh dự phòng chỉ chạy khi `du_dieu_kien` rỗng, nên việc gỡ
nó không được phép dịch một mã nào đang trộn bình thường — và đo được là không.

### Tác động thật lên production

**Không đổi dòng nào.** `web/data/valuation/latest.json` hiện hành (lượt
11/10/2026, `min_confidence = 0,30`, 84 tín hiệu) **không có mã nào**
`methods_used == []`, và cả WSS, UNI, VMC đều không có trong đó. Đúng như §2 dự
đoán: `conf ≤ 0,20 < 0,30`.

Nói cách khác, bản sửa này **gỡ cơ chế chứ không sửa số tuần này**. Nó đáng làm
vì cổng duy nhất đang chặn con số giả là một cờ dòng lệnh của `run_valuation`,
không phải engine.

---

## 6. Đã phá cho ĐỎ bằng những cách nào

CLAUDE.md §6: phép kiểm mới phải được phá cho đỏ mới tính là có canh. Bộ
`backend/tests/test_valuation_nhanh_du_phong.py` — **11 phép kiểm**, phá 9 cách:

| cách phá | số đỏ |
|---|---|
| 0. nguyên bản | **0** (11 xanh) |
| 1. trả lại **nguyên** nhánh dự phòng cũ | **6** |
| 2. chỉ chặn ca giá-làm-fv, vẫn trộn cấu phần dưới ngưỡng | **3** |
| 3. chỉ chặn khi không cấu phần nào chạy được | **6** |
| 4. đổi `>=` thành `>` ở biên ngưỡng | **1** |
| 5. viết cứng lại `0.15` ở chỗ chọn ứng viên | **1** |
| 6. viết cứng lại `0.15` ở vòng trộn | **2** |
| 7. `run_valuation` không ghi mã bị từ chối | **1** |
| 8. bỏ khoá `khong_co_dinh_gia` khỏi metadata | **1** |
| 9. đổi hằng số ngưỡng 0,15 → 0,25 | **1** |
| 10. hoàn nguyên | **0** (11 xanh lại) |

Hai điều đáng ghi, vì chúng là lý do bộ kiểm có **hai** loại phép kiểm chứ
không phải một:

* **Cách 2 không làm phép kiểm ca UNI đỏ** — đúng như phải vậy: biến thể đó vẫn
  trả `None` khi không cấu phần nào dương. Nó bị bắt bởi phép kiểm ca **WSS**.
  Hai ca là hai lỗ hổng khác nhau, không phải một.
* **Cách 5 chỉ bị bắt bởi phép kiểm AST, không bị phép kiểm hành vi bắt.** Khi
  chỗ chọn ứng viên viết cứng `0.15` mà vòng trộn đọc hằng số, nâng hằng số lên
  0,80 vẫn ra `None` — vì vòng trộn bỏ hết, nên `total_effective_weight` vẫn 0.
  Hành vi **không đổi**, chỉ mã nguồn hỏng. Đây đúng là trường hợp §6 nói tới:
  phép kiểm hành vi là mặc định, nhưng có chỗ chỉ cấu trúc bắt được — và khi
  dùng cấu trúc thì dùng **AST**, khoanh đúng thân `value_ticker` (bảng trọng số
  ngành ở đầu tệp có 12 con số `0.15` hợp lệ, tìm chuỗi sẽ khớp bừa).

---

## 7. Đã hỏi những đâu (để không khảo lại)

| Đã hỏi / đã đo | Kết quả |
|---|---|
| `total_effective_weight == 0` có đường vào nào khác ngoài "`du_dieu_kien` rỗng"? | **Không.** `methods_to_run` lọc `w > 0`, và `confidence` được giữ đều `>= 0,15 > 0` |
| Ai gọi `value_ticker` và có chịu được `None`? | Chỉ `run_valuation.py:301` (`continue` từ trước) và `backend/test_valuation_integration.py` (script `__main__`, đã in "returned None"). Không có chỗ nào khác |
| `_loai_phuong_phap_lac` có thể vét cạn ứng viên không? | **Không.** Vòng lặp dừng khi còn `< TOI_THIEU_DE_LOAI = 3`, nên từ 3 ứng viên trở lên luôn giữ `>= 2` |
| `_publish_guard` có đỡ được ca này không? | Đỡ một nửa: `n_methods = 0 < MIN_METHODS_FOR_DIRECTIONAL` nên có `guard_reason` → mức định giá web ra "Chưa có". Nhưng `fair_value` và `upside_pct` **vẫn vào `latest.json`**, và `backtest.py` vẫn đọc `verdict` |
| Cổng upside có chặn "fair value = giá" không? | **Không.** `MIN/MAX_PUBLISHED_UPSIDE` chỉ chặn `< −80%` và `> +200%`; `0,0%` lọt |
| `--min-confidence` của production | **0,30** (mặc định; `weekly-valuation.yml` không truyền cờ) → nhánh dự phòng (`conf ≤ 0,20`) không bao giờ ra tới production |
| Mã nào trong rổ 200 đi vào nhánh dự phòng | **UNI** và **WSS** (§2) |
| Peer DB có làm lệch cặp đo không | Không — `run_valuation` dựng lại và ghi peer DB từ chính rổ ở PASS 1, trước PASS 2. Cả hai lượt cùng rổ |

### Cách dựng lại cặp đo

```bash
# cache am: copy fundamentals_cache/ (304 tep), cache/ (591 tep),
# vnindex_cache.parquet tu ban checkout chinh -> ~4 phut/luot thay vi fetch lai
python backend/run_valuation.py --limit 200 \
  --web-data-dir <ngoai-kho>/out --snapshot-registry "" --min-confidence 0
```

**Bẫy đơn vị khi đọc `latest.json`:** `upside_pct` và `confidence` lưu theo
**phần trăm** (0–100), không phải tỷ lệ.

**Bẫy hạ tầng:** lượt chạy ghi `backend/data/peer_multiples.json`, và tệp đó làm
bộ test đỏ **chỉ ở máy người phát triển** (CLAUDE.md §6). Xoá nó trước khi chạy
`pytest`.
