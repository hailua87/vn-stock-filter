"""
Lớp lấy dữ liệu thị trường, gọi thẳng API công khai của Vietcap (VCI) và KBS.

Vì sao có lớp này (26/09/2026): PyPI cách ly (quarantine) `vnstock` và `vnai`
từ 24–25/09/2026, `pip install -r requirements.txt` hỏng và cả Daily Scan lẫn
CI đỏ. Theo CHANGELOG 4.0.9 của chính vnstock, các bản trước ghi một khối chỉ
dẫn vào tệp cấu hình của trợ lý AI (`AGENTS.md`, `~/.claude/CLAUDE.md`, …) mỗi
lần `import vnstock` — đúng hành vi mà `backend/conftest.py` đã ghi nhận.

Dự án chỉ dùng 5 việc của vnstock, nên thay bằng ~400 dòng code riêng thay vì
kéo lại cả thư viện (và `vnai`) từ một nguồn cài khác:

    Việc                               Hàm ở đây
    ---------------------------------  -----------------------------------
    Danh sách mã theo sàn              kbs.listing()
    Giá ngày (OHLCV) và VN-Index       vci.ohlcv()
    Tổng quan công ty (ngành ICB …)    vci.company_overview()
    BCTC năm/quý dạng dài              vci.financial_statement()
    Sự kiện quyền                      vci.events()
    NIM ngân hàng                      kbs.bank_nim()

Đầu ra GIỮ ĐÚNG hình dạng vnstock 4.0.7 trả về (tên cột, đơn vị, item_id),
để mọi phần phía sau — adapter chất lượng, normalizer định giá, fixture
`tests/fixtures/vnstock407_*.json`, sổ snapshot BCTC — không phải đổi.

Code ở đây viết mới, không chép từ vnstock: giấy phép vnstock (license-2026.09)
không cho phân phối lại phần mềm. Thứ dùng lại chỉ là sự thật về API công khai
(đường dẫn, tên trường) — và dữ liệu vẫn thuộc Vietcap/KBS, repo không lưu dữ
liệu thô (BLUEPRINT_v4 §4.2).
"""
from .http import SOURCE_VERSION, SourceError, RateLimitError  # noqa: F401
