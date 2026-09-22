# Fixture BCTC (`vnstock407_*.json`)

Lấy từ `scanner.financial_fetcher.fetch_financial_statements` (vnstock 4.0.7, bản cộng đồng, 21–22/09/2026) cho FPT (phi tài chính), VCB (ngân hàng), SSI (chứng khoán), kỳ năm và quý.

**Không phải BCTC thô.** Repo public và `docs/BLUEPRINT_v3.md` §4.2 không cho phân phối lại dữ liệu thô của bên thứ ba, nên các file đã được biến đổi:

- Chỉ giữ các dòng có `item_id` được code hoặc test tham chiếu (216/1.682 dòng).
- Mọi giá trị tiền trong `balance_sheet`, `income`, `cash_flow` đã nhân với `FIXTURE_SCALE` (`tests/fixture_scale.py`).
- Bảng `ratio` chỉ giữ `year`, `quarter`, `npl`.

Cấu trúc (dòng = khoản mục, cột = kỳ, kỳ mới trước, giá trị theo đồng) giữ nguyên như vnstock trả về. Test so số tuyệt đối thì nhân kỳ vọng với `FIXTURE_SCALE`; tỷ lệ (biên, CAGR, ROE, EPS/BVPS từ vốn góp) không đổi.

Thêm fixture mới: lấy bằng `fetch_financial_statements`, rồi áp cùng phép biến đổi trước khi commit.
