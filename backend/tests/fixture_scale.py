"""
Hệ số biến đổi fixture BCTC (tests/fixtures/vnstock407_*.json).

Repo public, blueprint v3 §4.2 không cho phân phối lại dữ liệu thô của bên thứ
ba, nên fixture KHÔNG phải BCTC thô: chỉ giữ các dòng code dùng tới (216/1.682
dòng) và mọi giá trị tiền trong 3 bảng BCTC đã nhân với FIXTURE_SCALE.

Hệ quả cho test:
  - Số tuyệt đối (tổng tài sản, doanh thu, số CP suy từ vốn góp): kỳ vọng = số
    đọc tay từ BCTC thật × FIXTURE_SCALE.
  - Tỷ lệ (biên, CAGR, ROE, EPS/BVPS từ vốn góp, tỷ lệ pha loãng, percentile):
    KHÔNG đổi, vì tử và mẫu cùng nhân hệ số.
  - Bảng ratio chỉ giữ year, quarter, npl (không nhân hệ số).
"""
FIXTURE_SCALE = 0.85
