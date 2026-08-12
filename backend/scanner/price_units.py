"""
ĐƠN VỊ GIÁ — nguồn chân lý duy nhất cho việc quy đổi.
================================================================================
Vấn đề đã gây lỗi 1000× trong valuation engine:

  - vnstock (VCI) trả giá OHLCV theo **nghìn VND**: ACB = 24.30, MCH = 137.3
  - Bảng ratio của vnstock trả EPS/BVPS theo **VND**: EPS = 3.500, BVPS = 20.000
  - BCTC (balance sheet / income statement) theo **tỷ VND**

Trước fix này, `fair_value = P/B × BVPS ≈ 24.000 (VND)` bị so với
`current_price = 24.3 (nghìn VND)` → upside +98.600%, market_cap nhỏ hơn thực tế
1000 lần → WACC sai → toàn bộ định giá vô nghĩa.

QUY ƯỚC SAU FIX:
  - Pipeline **technical** (scanner, web/data/*.json) giữ nguyên đơn vị quote
    (nghìn VND) — nhất quán với bảng điện và với toàn bộ dữ liệu lịch sử đã lưu.
  - Pipeline **valuation** làm việc hoàn toàn bằng **VND**. Mọi giá lấy từ
    vnstock/cache phải đi qua `quote_to_vnd()` trước khi vào engine.
  - `assert_price_is_vnd()` chặn dữ liệu sai đơn vị ngay tại biên, thay vì để
    lỗi lan xuống báo cáo định giá.
"""
from __future__ import annotations

# vnstock quote 1 đơn vị = 1.000 VND
VND_PER_QUOTE_UNIT = 1_000

# Dải giá hợp lệ (VND/cp) cho cổ phiếu niêm yết VN.
# Sàn thấp nhất thực tế ~400đ (penny UPCoM), cao nhất lịch sử ~1.000.000đ (VCF, THM).
MIN_PLAUSIBLE_PRICE_VND = 300
MAX_PLAUSIBLE_PRICE_VND = 2_000_000


def quote_to_vnd(price_quote: float | None) -> float | None:
    """Giá vnstock (nghìn VND) → VND. None giữ nguyên None."""
    if price_quote is None:
        return None
    return float(price_quote) * VND_PER_QUOTE_UNIT


def vnd_to_quote(price_vnd: float | None) -> float | None:
    """VND → đơn vị quote (nghìn VND), dùng khi hiển thị cạnh dữ liệu technical."""
    if price_vnd is None:
        return None
    return float(price_vnd) / VND_PER_QUOTE_UNIT


def assert_price_is_vnd(price: float, ticker: str = '?', field: str = 'current_price') -> float:
    """
    Chặn lỗi đơn vị tại biên valuation engine.

    Raise ValueError nếu giá nằm ngoài dải hợp lý cho VND/cp — trường hợp hay gặp
    nhất là quên nhân 1.000 (giá 24.3 thay vì 24.300).
    """
    if price is None:
        raise ValueError(f"{ticker}: {field} bị None")
    p = float(price)
    if p < MIN_PLAUSIBLE_PRICE_VND:
        raise ValueError(
            f"{ticker}: {field}={p:,.2f} quá thấp cho đơn vị VND/cp. "
            f"Nhiều khả năng đang dùng đơn vị quote của vnstock (nghìn VND) — "
            f"hãy đưa qua price_units.quote_to_vnd() trước khi vào valuation engine."
        )
    if p > MAX_PLAUSIBLE_PRICE_VND:
        raise ValueError(
            f"{ticker}: {field}={p:,.0f} vượt dải hợp lý (>{MAX_PLAUSIBLE_PRICE_VND:,} VND/cp)."
        )
    return p
