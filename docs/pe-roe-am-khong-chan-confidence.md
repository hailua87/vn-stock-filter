# P/E với `sustainable_roe <= 0`: ĐÃ KHẢO, KHÔNG chặn `confidence`

**Ngày đo:** 16/10/2026 · **Mã nguồn:** `main` @ `e821662` (đã có cả PR #97 và #98)
**Kết luận:** **không đổi mã.** Đo trên rổ 200 mã, đề xuất ép `confidence = 0`
khi `sustainable_roe <= 0` đổi **đúng 1/180 mã** — và đó là **BVH**, mã có
`sustainable_roe = 0,0` vì **thiếu số liệu**, không phải vì lỗ. Với 8 mã lỗ
thật, và với cả **WSS** — mã đã sinh ra câu hỏi — nó là **phép vô hiệu**. Biến
thể mạnh hơn (không trả fair value) thì **có hại**: nó đưa WSS trở lại
`latest.json` với "fair value = giá, upside 0,0%".

Tài liệu này ghi cả **"đã hỏi những đâu"** theo CLAUDE.md §10, để kết quả âm này
không bị khảo lại từ đầu.

---

## 1. Câu hỏi

`calculate_pe_valuation` đã ép `confidence = 0` khi `eps_ttm <= 0` với lý do
"P/E vô nghĩa khi EPS <= 0". Docstring đầu `methods_pe.py` cũng ghi
"❌ Không phù hợp với doanh nghiệp thua lỗ", và `calculate_eps_stability` đã gắn
cờ "Có năm thua lỗ".

Vậy có nên làm **y như vậy** khi `sustainable_roe <= 0` — doanh nghiệp lỗ theo
trung bình 5 năm, dù EPS TTM đã dương?

Ba trạng thái được đo:

| | |
|---|---|
| **A** | nguyên bản `main` @ `e821662` |
| **B** | `confidence = 0` khi `sustainable_roe <= 0` ← **chính đề xuất** |
| **C** | `confidence = 0` **và** `fair_value = 0` (không trả kết quả) |

---

## 2. Vì sao cổng `confidence` gần như không chạm được tới đâu — cơ chế

`confidence` của cấu phần được đọc ở **đúng hai chỗ** trong `engine.py`, và
**cả hai đều đã loại cấu phần P/E của mã lỗ từ trước**:

```python
# engine.py:641  — chon ung vien de tron
du_dieu_kien = {... if r.fair_value_per_share > 0 and r.confidence >= 0.15}
# engine.py:646  — vong tron
if result.fair_value_per_share <= 0 or result.confidence < 0.15: continue
```

Nhưng khi **không cấu phần nào** qua được ngưỡng, engine rơi vào nhánh dự phòng
— và nhánh đó **không đọc `confidence` nữa**:

```python
# engine.py:659
if total_effective_weight == 0:
    valid_fvs = [r.fair_value_per_share for r in results.values()
                 if r.fair_value_per_share > 0]        # <-- CHI xet fv > 0
    fair_value = sum(valid_fvs)/len(valid_fvs) if valid_fvs \
                 else data["market"]["current_price"]  # <-- gia = fair value
    overall_confidence = 0.20
```

Đây là chốt của toàn bộ chuyện này:

- Với 8 mã lỗ thật, cấu phần P/E **vốn đã** dưới 0,15 (xem bảng §4) → hạ xuống
  0,0 **không đổi gì**.
- Với WSS, `methods_used = []` → engine đi nhánh dự phòng → nhánh đó chỉ lọc
  `fair_value_per_share > 0`, **bỏ qua `confidence`** → hạ 0,05 xuống 0,0
  **vẫn không đổi gì**.

Nói cách khác: **cái cần chặn là `fair_value`, không phải `confidence`.** Ngưỡng
0,15 mà engine vừa áp dụng ở trên lại bị chính nhánh dự phòng của nó bỏ qua.

---

## 3. Cặp đo WSS: `#98-only` so với `cả hai bản sửa`

Hai nhánh PR đã bị xoá khỏi origin sau khi squash-merge, nên bản `#98-only`
được **dựng lại** thay vì đi mượn số của phiên khác: `git revert -n d3dc3b3`
(tức gỡ #97) trên `e821662`, auto-merge không xung đột, rồi kiểm lại bằng nội
dung — còn `quality_factor_roe`/`roe_dung_duoc` của #98, trở về
`payout = ratios.get("payout_ratio", 0.30)` của trước #97.

Hai lượt chạy **cùng một thước**: cùng cache ấm, cùng phiên, cùng ngày.
Lệnh: `--limit 200 --snapshot-registry "" --min-confidence 0`,
`--web-data-dir` trỏ ra ngoài kho (CLAUDE.md §7).

**Chốt chặn của cặp đo: `current_price` trùng khớp trên cả 180/180 mã chung →
cặp đo SẠCH.**

### WSS: hai lượt GIỐNG NHAU từng con số

| | `#98-only` | cả hai bản sửa |
|---|---|---|
| `fair_value` | 22.671 | **22.671** |
| `current_price` | 5.900 | 5.900 |
| cổng công bố | `upside +284% > +200%` | `upside +284% > +200%` |
| có trong `latest.json`? | **không** | **không** |

**WSS KHÔNG quay lại `latest.json`, và PR #97 không làm con số của nó đổi dù
chỉ 1 đồng.** Dự đoán "hai PR gặp nhau thì WSS sẽ ra khác" là **sai**.

### Vì sao #97 không đụng được WSS

`payout_ratio` của WSS **thật sự là 0,0** — doanh nghiệp không trả cổ tức. #97
sửa trường hợp *không suy được* payout (trả `None` → loại cấu phần tường minh),
chứ không sửa trường hợp payout **suy được và bằng 0**. Nên:

```
Justified P/E = 0% / (11,2% − −0,5%) = 0,0x
```

`0.0` là **falsy**, nên bước trộn (`if v and v > 0`) vẫn bỏ nó — y như trước
#97. Khác biệt duy nhất là *lý do*, không phải con số.

### Blend target P/E của WSS — đọc từ `notes`

```
- Justified P/E = 0% / (11.2% - -0.5%) = 0.0x
- Không có historical P/E thực → loại cấu phần lịch sử khỏi blend
- Sustainable ROE = -0.5% <= 0 → không có hệ số chất lượng → loại cấu phần peer khỏi blend
- Forward P/E (PEG): growth=50.2%, PEG target=1.2, P/E=25.0x (kẹp trong 6-25x)
- Blend target P/E = 100%×forward_peg(25.0) = 25.0x
- Growth bất thường → dùng EPS TTM = 907
```

Tức **cả ba cấu phần chỉ còn một**: justified (35%) bị bỏ vì bằng 0, peer/lịch
sử (40%) bị loại tường minh, còn lại **100% × forward_peg = 25,0x** — **đúng
trần `PE_CEILING`**. `22.671 = 25,0 × 907`.

Một con số dựa hoàn toàn vào trần kẹp, trên một doanh nghiệp lỗ trung bình 5
năm, với `confidence` của cấu phần chỉ **0,05**.

### Ngoài WSS: #97 đổi số ở 129/180 mã

| | |
|---|---|
| `fair_value` đổi | **129/180** mã chung |
| trung vị \|Δ\| | 3,64% |
| \|Δ\| > 10% | 26 mã |
| \|Δ\| > 20% | 11 mã |
| lớn nhất | VMC −72,4% |
| rời `latest.json` | **CLH, DAD** (thành ngoại lai) |
| `methods_used` đổi | 3 mã (GEX, HDB, VMC) |

Mười mã đổi mạnh nhất:

| mã | fv `#98-only` | fv cả hai | Δ |
|---|---|---|---|
| VMC | 3.500 | 966 | −72,4% |
| MCH | 61.198 | 86.158 | +40,8% |
| CTB | 18.587 | 25.882 | +39,2% |
| VC7 | 2.732 | 1.731 | −36,6% |
| DHP | 10.977 | 14.483 | +31,9% |
| ADP | 42.824 | 55.842 | +30,4% |
| DAE | 15.406 | 19.880 | +29,0% |
| DHA | 81.369 | 104.695 | +28,7% |
| CMV | 7.450 | 9.392 | +26,1% |
| DTG | 26.770 | 21.033 | −21,4% |

**VMC đáng đọc riêng.** Trước #97: `methods_used = []`, `fair_value = 3.500 =
đúng giá`, `upside 0,0%` — **chính cái "con số giả dạng định giá"** mà #98 đã
gỡ cho WSS. Sau #97: `P/B-ROE Justified` vào được `methods_used`, fair value
966, upside −72,4%. Tức #97 cứu VMC ra khỏi nhánh dự phòng giá-bằng-fair-value.
Đó là bằng chứng độc lập cho thấy nhánh dự phòng ở §2 là chỗ hỏng thật.

---

## 4. Điểm danh lại cả rổ: **9** mã, không phải 8

Danh sách 8 mã mang sang từ phiên trước (VDL, WSS, DQC, DTL, VHL, DRH, HAS,
HID) **thiếu một mã**. Đếm lại trên **toàn bộ 200 mã** của lượt chạy, lấy
`sustainable_roe` **từ `key_inputs` của chính hàm thật** (không tự suy lại công
thức — CLAUDE.md §6):

| mã | `sustainable_roe` | `confidence` cấu phần P/E | `fair_value` cấu phần |
|---|---|---|---|
| DTL | −12,29% | 0,000 | 0 |
| VHL | −2,30% | 0,050 | 7.182 |
| DRH | −1,89% | 0,050 | 791 |
| VDL | −1,54% | 0,050 | 1.673 |
| HAS | −0,75% | 0,000 | 0 |
| DQC | −0,64% | 0,050 | 739 |
| WSS | −0,53% | 0,050 | 22.671 |
| HID | −0,12% | 0,000 | 0 |
| **BVH** | **0,00%** | **0,550** | **24.795** |

`sustainable_roe > 0`: 191 mã. Không mã nào không đo được.

**Tám mã đầu có `confidence` 0,000 hoặc 0,050 — đều đã dưới ngưỡng 0,15 của
engine.** Với chúng, hạ `confidence` xuống 0 là phép vô hiệu, vì engine đã loại
cấu phần P/E từ trước.

### BVH là chỗ đề xuất thật sự có tác dụng — và là chỗ nó SAI

BVH lọt vào danh sách vì `<= 0` bắt cả **đúng bằng 0**. Nhưng đọc đầu vào:

```
roe_ttm = 0.0
roe_5y  = [0.0, 0.0, 0.0, 0.0, 0.0]
eps_ttm = 3,935.7          <-- DUONG
```

**Năm năm ROE đúng bằng 0,0 với EPS 3.936 là không thể xảy ra.** Đó là **số
liệu thiếu bị ghi thành 0**, không phải doanh nghiệp lỗ. BVH là Bảo Việt
Holdings — nhóm **Bảo hiểm**, mà `docs/securities-insurance-source-survey.md`
đã ghi là **ngoài phạm vi định giá**.

Nên tác dụng thật duy nhất của đề xuất là: gỡ một phiếu P/E **độ tin cậy 55%**
khỏi blend của BVH **vì một lỗ hổng dữ liệu**, rồi dán cho nó nhãn
"doanh nghiệp lỗ" — một nhãn **sai sự thật**.

Lưu ý: mã đã merge của #98 **hiện đã** dán nhãn đó cho BVH:

```
! Sustainable ROE <= 0 (doanh nghiệp lỗ) → loại cấu phần peer P/E khỏi blend;
  P/E không phù hợp với doanh nghiệp thua lỗ
```

Chỗ đáng sửa là **normalizer** (thiếu số thì trả `None`, không trả `0.0`), chứ
không phải thêm một cổng `confidence` ở `methods_pe`. Xem §7.

---

## 5. Chế độ C (không trả fair value) — đo trên rổ thật: **có hại**

Biến thể mạnh hơn: khi `sustainable_roe <= 0` thì `confidence = 0` **và**
`fair_value = 0`. Lượt chạy đủ 200 mã, cùng cache, so với lượt `cả hai bản sửa`.
`current_price` trùng khớp **180/180** mã chung → cặp đo sạch.

| | |
|---|---|
| số tín hiệu | 180 → **181** |
| `fair_value` đổi | 1/180 (BVH, +25,2%) |
| **mã VÀO THÊM `latest.json`** | **WSS** |

**WSS quay lại `latest.json` — và quay lại bằng đúng con số giả:**

```json
{"ticker": "WSS", "current_price": 5900.0, "fair_value": 5900.0,
 "upside_pct": 0.0, "confidence": 17.0, "verdict": "HOLD", "methods_used": []}
```

```
- ✓ P/B-ROE Justified: fair=-929, conf=60%
- ✓ P/E Multiple: fair=0, conf=0%
- ✓ Historical Multiple: fair=0, conf=0%
```

Mọi cấu phần đều `fair_value <= 0`, nên `valid_fvs` rỗng và nhánh dự phòng
(§2) lấy **`current_price` làm fair value** → upside **0,0%**.

Và đây là chỗ trở nên **tệ hơn hiện trạng**: `+284%` **bị** cổng
`MAX_PUBLISHED_UPSIDE` chặn, còn **`0,0%` thì lọt**. Tức chế độ C **biến một mã
bị chặn thành một dòng được công bố với "fair value = giá, upside 0,0%"** —
đúng cái "con số giả dạng định giá" mà PR #98 vừa gỡ. Đổi ngược chiều.

Thêm nữa, dòng WSS đó còn mang sẵn cảnh báo tự phủ định:

```
! Nhóm tài chính (Securities): chưa tách được dư nợ margin quá hạn nên
  chưa đưa ra kết luận định giá
```

Công bố một "kết luận định giá" cho mã mà chính nó nói là chưa kết luận được.

---

## 6. Chế độ B (chính đề xuất) — đo trên rổ thật: đổi **đúng một mã**, và là mã SAI

Lượt chạy đủ 200 mã, cùng cache, so với lượt `cả hai bản sửa`.
`current_price` trùng khớp **180/180** mã chung → cặp đo sạch.

| | |
|---|---|
| số tín hiệu | 180 → **180** (không đổi) |
| mã vào/ra `latest.json` | **không có** |
| `fair_value` đổi | **1/180** |
| `methods_used` đổi | **1/180** |

Mã duy nhất đổi:

| mã | fv trước | fv sau | Δ | conf | `methods_used` |
|---|---|---|---|---|---|
| **BVH** | 37.770 | 47.285 | **+25,2%** | 25 → 27 | mất `P/E Multiple` |

**WSS không đổi gì cả:**

| | cả hai bản sửa | chế độ B |
|---|---|---|
| `fair_value` | 22.671 | **22.671** |
| cổng công bố | `upside +284% > +200%` | `upside +284% > +200%` |

Tức đề xuất **không chạm được vào chính mã đã sinh ra câu hỏi**, vì nhánh dự
phòng của engine không đọc `confidence` (§2). Tám mã lỗ thật thì không đổi gì
vì `confidence` của chúng vốn đã dưới ngưỡng. Tác dụng duy nhất đo được là
**BVH** — mà `sustainable_roe = 0,0` của BVH là **số liệu thiếu**, không phải
lỗ (§4).

### Kết luận

**KHÔNG thêm cổng `confidence = 0` khi `sustainable_roe <= 0`.** Bốn lý do, đều
đo được:

1. **Với 8 mã lỗ thật: phép vô hiệu.** `confidence` cấu phần P/E của chúng đã
   là 0,000 hoặc 0,050 — dưới ngưỡng 0,15 — nên engine đã loại từ trước.
2. **Với WSS: phép vô hiệu.** Nhánh dự phòng `engine.py:659` chỉ lọc
   `fair_value > 0` và **bỏ qua `confidence`**. Hạ 0,05 xuống 0,0 không đổi gì.
3. **Tác dụng thật duy nhất là BVH — và sai hướng.** Nó gỡ một phiếu P/E độ tin
   cậy 55% khỏi blend vì `roe_5y = [0,0,0,0,0]`, tức **vì một lỗ hổng dữ liệu**,
   rồi dán nhãn "doanh nghiệp lỗ" cho một công ty có EPS 3.936.
4. **Biến thể mạnh hơn (chế độ C) có hại thật.** Đo được: nó đưa WSS **trở lại**
   `latest.json` với `fair value = giá, upside 0,0%` — đúng con số giả mà #98
   vừa gỡ — vì `0,0%` lọt cổng `MAX_PUBLISHED_UPSIDE` mà `+284%` thì không.

Thêm một lý do không đo mà đọc ra: `eps_ttm <= 0` và `sustainable_roe <= 0`
**không cùng loại vô hiệu**. Với EPS ≤ 0 thì `target_pe × fwd_eps` là phép tính
vô nghĩa về mặt số học (ra số âm). Với EPS TTM dương mà ROE 5 năm âm thì phép
tính vẫn xác định; chỉ có cấu phần Gordon và hệ số chất lượng là vô nghĩa — và
**#98 đã loại cả hai, tường minh, kèm `notes` và `warnings`**. Việc cần làm đã
được làm rồi.

Chỗ đáng sửa nằm ở §7, không nằm ở cổng này.

---

## 7. Chỗ hỏng thật — ĐÃ TÌM RA, chưa sửa ở đây

Ba việc tách riêng, mỗi việc rộng hơn câu hỏi ban đầu:

### 7.1. Nhánh dự phòng của engine bỏ qua chính ngưỡng của nó

`engine.py:659`: khi không cấu phần nào qua `confidence >= 0.15`, engine lấy
**trung bình đơn thuần** mọi cấu phần có `fair_value > 0` — **không đọc
`confidence`**; nếu không còn cái nào thì lấy luôn `current_price`.

Hậu quả đo được:

- **WSS**: cấu phần P/E `confidence = 0,05` (engine vừa loại nó ở trên) vẫn
  thành fair value công bố 22.671.
- **VMC** (§3): `methods_used = []` → fair value = đúng giá, upside 0,0%.
  Tới khi #97 cho `P/B-ROE` vào blend thì mới thoát.

Đây là nguồn gốc của cả hai "con số giả dạng định giá", và nó **không nằm ở
`methods_pe`**. Sửa ở đây là sửa đúng chỗ — nhưng nó đụng mọi mã, nên cần cặp
đo riêng, không gộp vào việc này.

### 7.2. `roe_5y = [0,0,0,0,0]` là số liệu thiếu, không phải ROE bằng 0

BVH (§4). `<= 0` đang trộn lẫn **"lỗ"** với **"không có số"**. Chữa ở
`normalizer` (thiếu thì `None`) thì cả `methods_pe`, `methods_pb_roe` và mọi
chỗ đọc `roe_5y` đều đúng theo; chữa bằng một cổng ở `methods_pe` thì chỉ che
một chỗ và dán nhãn sai.

Cần khảo trước: bao nhiêu mã trong rổ có `roe_5y` toàn 0, và chúng là thiếu số
thật hay lỗ thật.

### 7.3. Chứng khoán và Bảo hiểm vẫn được định giá dù đã ghi là ngoài phạm vi

WSS (Securities) và BVH (Bảo hiểm) đều có dòng `warnings` tự nói là chưa kết
luận được, nhưng vẫn chạy hết các phương pháp và — ở chế độ C — vẫn được công
bố. Xem `docs/securities-insurance-source-survey.md`.

---

## 8. Đã hỏi những đâu (để không khảo lại)

Theo CLAUDE.md §10 — kết quả âm phải ghi kèm nơi đã hỏi.

| Đã hỏi / đã đo | Kết quả |
|---|---|
| `confidence` được đọc ở đâu trong `engine.py` | đúng 2 chỗ: `:641` chọn ứng viên, `:646` vòng trộn. Nhánh dự phòng `:659` **không** đọc |
| Ngưỡng cấu phần của engine | `0.15` (`engine.py:641`, `:646`) |
| Cổng upside công bố | `MAX_PUBLISHED_UPSIDE = 2.00` (`run_valuation.py:71`) |
| Thứ tự lọc ở PASS 2 | `min_upside` → **`min_confidence`** → `outlier_reason`. Lọc độ tin cậy chạy **trước** cổng ngoại lai |
| `--min-confidence` của production | **0,30** (mặc định; `weekly-valuation.yml:95` không truyền cờ này) |
| WSS / BVH trong `web/data/valuation/latest.json` hiện tại | **không có cả hai** (conf 17 và 25 đều dưới 0,30) |
| Rổ có bao nhiêu mã `sustainable_roe <= 0` | **9** (§4), không phải 8 |
| `sustainable_roe` của BVH từ đâu ra | `roe_5y = [0,0,0,0,0]`, `eps_ttm = 3.936` → **thiếu số**, không phải lỗ |
| Peer DB có làm lệch cặp đo không | **không** — `run_valuation.py:279` dựng lại và ghi peer DB từ chính rổ ở PASS 1, trước PASS 2 |

### Cách dựng lại cặp đo

```bash
# ban #98-only (hai nhanh PR da bi xoa khoi origin)
git worktree add <ngoai-kho>/wt98 --detach e821662
cd <ngoai-kho>/wt98 && git revert -n d3dc3b3     # auto-merge, khong xung dot
# kiem bang NOI DUNG: con quality_factor_roe/roe_dung_duoc cua #98,
# tro ve payout = ratios.get("payout_ratio", 0.30) cua truoc #97

# cache am: copy fundamentals_cache/ (304 tep), cache/ (591 tep),
# vnindex_cache.parquet tu ban checkout chinh -> ~4 phut/luot

python backend/run_valuation.py --limit 200 \
  --web-data-dir <ngoai-kho>/out --snapshot-registry "" --min-confidence 0
```

**Chốt chặn:** `current_price` phải trùng trên mọi mã chung. Lệch thì cặp đo
không sạch — nói ra, đừng bỏ qua.

**Bẫy đơn vị khi đọc `latest.json`:** `upside_pct` và `confidence` lưu theo
**phần trăm** (0–100), không phải tỷ lệ. Nhân thêm 100 là ra `-5630%`. Đã lỡ
một lần trong chính phiên đo này.

