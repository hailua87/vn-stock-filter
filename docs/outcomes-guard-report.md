# Guard Report — Sổ theo dõi kết quả tín hiệu

Ngày: 29/09/2026 | Phạm vi: `backend/scanner/outcomes.py`, nối vào `run_daily`

| Kiểm | Kết quả | Ghi chú |
|------|---------|---------|
| G1 Phép kiểm có thể đỏ | **PASS** | 7 biến đổi, mỗi lần đúng test mong đợi đỏ (bảng dưới) |
| G2 Đi qua entrypoint | **PASS** | `test_run_daily_builds_and_writes_the_ledger` đọc AST của `run_daily` |
| G3 Đẳng thức cấu trúc | **PASS** | xem mục dưới |
| G4 Số từ payload | **PASS** | `n = len(rets)`, `entries = len(rows)` — không đọc metadata |
| G5 Grain sau biến đổi | **PASS** | `test_no_duplicate_ticker_date_rows` |

## G1 — bảy phép phá hoại

| Đổi gì | Test đỏ |
|---|---|
| Đếm mọi phiên có tín hiệu là một lần vào | `a_long_streak_is_one_entry_not_many`, `leaving_and_coming_back_is_two_entries` |
| Thiếu dữ liệu → thay bằng 0 | `incomplete_horizon_is_excluded_not_zeroed` |
| Trung bình thay vì trung vị | `one_huge_winner_does_not_move_the_median` |
| Bỏ phép trừ chỉ số (`excess = ret`) | `excess_subtracts_the_index_over_the_same_dates` |
| Lấy giá vào từ bản lưu thay vì chuỗi giá | `entry_price_comes_from_the_series_not_the_archive` |
| Đếm chân trời theo ngày lịch | `horizon_counts_the_tickers_own_sessions` + 1 |
| Không có chỉ số → `excess = 0` | `no_index_means_excess_is_none_not_zero` |

Và hai phép riêng cho G2/G5:

| Đổi gì | Test đỏ |
|---|---|
| `run_daily` không gọi `OUTCOMES` | `run_daily_builds_and_writes_the_ledger` |
| Truyền `by_ticker` (đã lọc thanh khoản) thay `by_ticker_all` | như trên |
| Bỏ dedup khoá | `no_duplicate_ticker_date_rows` + 1 |

## G3 — đẳng thức: cấu trúc hay trùng hợp

| Đẳng thức | Cưỡng chế ở đâu | Kết luận |
|---|---|---|
| `incomplete = len(rows) − len(rets)` | `outcomes.py:build_strategy` — cùng một danh sách `rows`, `rets` là tập con lọc theo khoá chân trời | **cấu trúc** |
| `entries = len(rows)` | `outcomes.py:build_strategy` dòng cuối | **cấu trúc** |
| `n_excess ≤ n` | `exc` lọc thêm điều kiện `excess is not None` trên chính tập của `rets` | **cấu trúc** |

Không đẳng thức nào được dùng làm phép kiểm mà không chỉ ra được dòng cưỡng chế.

## G5 — grain

Một phép biến đổi đổi grain, và nó **cố ý**:

```
(phiên, mã)  — 5.100 dòng tín hiệu pre_breakout
    ↓ entries_from: chỉ giữ phiên ĐẦU của mỗi chuỗi liên tiếp
(mã, phiên vào) — 1.530 dòng
```

Giảm 70%. Đây chính là lý do phải chốt grain trước: đếm theo grain cũ sẽ cho
mẫu lớn gấp hơn ba lần, gồm phần lớn là **quan sát trùng nhau** (MCH giữ tín
hiệu 20 phiên liền = 1 lần vào, không phải 20).

Không có join nào trong pipeline này, nên không có rủi ro nhân dòng kiểu
1-nhiều. Khoá `(mã, phiên vào)` được kiểm trùng bằng test.

## Phát hiện

**Không có lỗi nào lọt qua.** Bốn quyết định rủi ro nhất đều được chốt bằng
test có thể đỏ: grain, gốc giá, lịch đếm phiên, và mốc so sánh.

Một điểm đáng ghi: nguồn giá phải là `by_ticker_all` (**chưa** lọc điều kiện
nền), không phải `by_ticker`. Dùng bản đã lọc thì sổ chỉ còn những mã hiện vẫn
đủ thanh khoản — một dạng **survivorship bias** làm mọi con số đẹp lên. Đã chốt
bằng test đọc AST của `run_daily`.

## Chưa kiểm được

- **Số liệu thật trên CI.** Cache OHLCV cục bộ của tôi cũ và không đều (213 mã
  dừng ở 12/08), nên `no_entry_bar` cao giả tạo. Con số thật chỉ có sau lượt
  quét CI đầu tiên.
- **Độ lớn mẫu có đủ để kết luận không.** Bản lưu chỉ từ 28/04/2026. Đây là
  giới hạn của dữ liệu, không phải của code — và nó được ghi thẳng vào `note`
  của tệp xuất ra.
