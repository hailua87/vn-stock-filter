"""
PHƯƠNG PHÁP EV/EBITDA - VỚI MID-CYCLE EBITDA CHO CYCLICAL STOCKS
================================================================================
EV/EBITDA = (Market Cap + Net Debt) / EBITDA

ƯU ĐIỂM:
  - Loại bỏ ảnh hưởng cấu trúc vốn (so sánh được công ty nhiều/ít nợ)
  - Loại bỏ ảnh hưởng khấu hao (phù hợp với capital-intensive businesses)
  - Có thể dùng cho doanh nghiệp thua lỗ (EBITDA > 0)

ÁP DỤNG TỐT CHO:
  ✅ Steel/Metals (HPG, HSG, NKG)
  ✅ Chemicals (DGC, DCM, DPM)
  ✅ Oil & Gas (GAS, BSR, PVS)
  ✅ Logistics, Cảng biển (GMD, VSC, HAH)
  ✅ Utilities (POW, REE, NT2)
  ✅ Agriculture/Livestock cyclical (DBC, BAF, HAG)
  ⚠️ KHÔNG dùng cho banking/insurance/securities

KỸ THUẬT MID-CYCLE EBITDA:
  Doanh nghiệp chu kỳ có EBITDA biến động mạnh theo giá hàng hóa.
  Dùng EBITDA năm tệ nhất → overprice
  Dùng EBITDA năm tốt nhất → underprice
  → Phải dùng EBITDA trung bình chu kỳ (3-5 năm)
"""

from dataclasses import dataclass
from typing import Dict, Any, List

from .methods_pb_roe import ValuationResult


def calculate_ev_ebitda_valuation(data: Dict[str, Any], is_cyclical: bool = False) -> ValuationResult:
    """Định giá theo EV/EBITDA.

    Args:
        data: Sample data dict
        is_cyclical: Nếu True, dùng EBITDA trung bình 5 năm (mid-cycle).
                     Nếu False, dùng EBITDA TTM.
    """
    ticker = data["ticker"]
    market = data["market"]
    bs = data["balance_sheet"]
    ratios = data["ratios"]
    cash_flow = data.get("cash_flow", {})
    warnings = []
    notes = []

    current_price = market["current_price"]
    shares = market["shares_outstanding"]

    # --- 1. Chọn EBITDA: mid-cycle hay TTM? ---
    ebitda_ttm = cash_flow.get("ebitda_ttm", 0)
    ebitda_5y_avg = cash_flow.get("ebitda_5y_avg", ebitda_ttm)

    if is_cyclical:
        # Mid-cycle EBITDA cho cyclical: dùng cách thận trọng hơn
        # Lấy max giữa: trung bình 5y, và (revenue TTM × normalized EBITDA margin)
        revenue_ttm = data.get("income", {}).get("revenue", 0)
        # Normalized EBITDA margin = trung bình margin các năm "bình thường"
        # Heuristic: 10% revenue cho hầu hết cyclicals (có thể tùy chỉnh theo ngành)
        normalized_margin = data.get("cyclical_info", {}).get("normalized_ebitda_margin", 0.10)
        ebitda_from_revenue = revenue_ttm * normalized_margin

        # Lấy max của 3 approaches để tránh deflate
        ebitda_candidates = {
            "5y_avg": ebitda_5y_avg,
            "ttm_blended": 0.50 * ebitda_5y_avg + 0.50 * ebitda_ttm,
            "revenue_normalized": ebitda_from_revenue,
        }
        ebitda_used = max(ebitda_candidates.values())
        chosen = max(ebitda_candidates, key=ebitda_candidates.get)
        notes.append(
            f"CYCLICAL → EBITDA candidates: 5y_avg={ebitda_5y_avg:,.0f}, "
            f"ttm_blend={ebitda_candidates['ttm_blended']:,.0f}, "
            f"rev×margin={ebitda_from_revenue:,.0f}"
        )
        notes.append(f"Chọn max → {chosen}: {ebitda_used:,.0f} tỷ")

        if ebitda_ttm / ebitda_5y_avg > 1.5:
            warnings.append(f"EBITDA TTM ({ebitda_ttm:,.0f}) cao hơn 50% so với 5y avg → có thể đang ở đỉnh chu kỳ")
        elif ebitda_ttm / ebitda_5y_avg < 0.6:
            warnings.append(f"EBITDA TTM ({ebitda_ttm:,.0f}) thấp <60% so với 5y avg → có thể đang ở đáy chu kỳ")
    else:
        ebitda_used = ebitda_ttm
        notes.append(f"STABLE → EBITDA TTM = {ebitda_used:,.0f} tỷ")

    if ebitda_used <= 0:
        warnings.append("EBITDA <= 0 → không định giá được bằng EV/EBITDA")
        return ValuationResult(
            method="EV/EBITDA",
            ticker=ticker,
            fair_value_per_share=0,
            current_price=current_price,
            upside_pct=-1.0,
            confidence=0.0,
            warnings=warnings,
            notes=notes,
        )

    # --- 2. Chọn EV/EBITDA mục tiêu ---
    current_multiple = ratios.get("ev_ebitda", 6.0)
    hist_avg = ratios.get("ev_ebitda_5y_avg", current_multiple)

    # Đối với cyclical, target multiple = trung bình lịch sử (mean reversion)
    # Nhưng điều chỉnh theo cycle position để phản ánh thực tế thị trường:
    #   - Recovery phase: trade above mid-cycle (anticipating earnings recovery)
    #   - Peak phase: trade below mid-cycle (anticipating earnings decline)
    if is_cyclical:
        cycle_pos = data.get("cyclical_info", {}).get("current_cycle_position", "mid")
        cycle_premium = {
            "trough": 1.30,           # Đáy → P/E cao do EPS thấp, multiples expand
            "recovery": 1.15,         # Phục hồi → market trả premium
            "recovery_to_peak": 1.05, # Gần đỉnh → nhẹ premium
            "mid": 1.00,
            "peak": 0.85,             # Đỉnh → discount vì sắp downtrend
        }.get(cycle_pos, 1.00)
        target_multiple = hist_avg * cycle_premium
        notes.append(
            f"Target EV/EBITDA = hist 5y avg ({hist_avg:.1f}) × cycle adj ({cycle_premium:.2f}, "
            f"phase={cycle_pos}) = {target_multiple:.1f}x"
        )
    else:
        # Stable: blend hist với peer median thực (nếu có), fallback hardcode 8.0
        peer_median = None
        try:
            from ...peer_database import get_peer_band
            industry = data.get('_industry')
            if industry:
                peer_band = get_peer_band(industry, 'ev_ebitda')
                if peer_band and peer_band.get('median'):
                    peer_median = peer_band['median']
                    notes.append(f"Peer EV/EBITDA median ({industry}, n={peer_band.get('n', '?')}): {peer_median:.1f}x")
        except Exception:
            pass

        if peer_median is None:
            peer_median = 8.0
            notes.append(f"Peer EV/EBITDA: dùng default {peer_median:.1f}x (chưa có peer DB)")

        target_multiple = 0.6 * hist_avg + 0.4 * peer_median
        notes.append(f"Target EV/EBITDA = 60%×{hist_avg:.1f} + 40%×{peer_median:.1f} = {target_multiple:.1f}x")

    # --- 3. Enterprise Value → Equity Value ---
    enterprise_value = target_multiple * ebitda_used  # tỷ đồng

    total_debt = (bs.get("short_term_debt", 0) +
                  bs.get("long_term_debt", 0))
    cash = bs.get("cash_and_equivalents", 0)
    net_debt = total_debt - cash
    minority_interest = bs.get("minority_interest", 0)

    equity_value = enterprise_value - net_debt - minority_interest
    notes.append(f"EV = {target_multiple:.1f}x × {ebitda_used:,.0f} = {enterprise_value:,.0f} tỷ")
    notes.append(f"Equity Value = EV - Net Debt ({net_debt:,.0f}) - MI ({minority_interest:,.0f}) = {equity_value:,.0f} tỷ")

    # --- 4. Per share ---
    # Convert tỷ đồng → đồng → đồng/cp
    fair_value = (equity_value * 1_000_000_000) / shares
    upside = (fair_value - current_price) / current_price

    # --- 5. Confidence ---
    confidence = 0.75
    if is_cyclical:
        confidence = 0.80  # EV/EBITDA mid-cycle là tốt nhất cho cyclical
    if cash_flow.get("ebitda_5y_avg") is None:
        confidence -= 0.20
        warnings.append("Không có EBITDA 5y avg → giảm độ tin cậy")
    confidence = max(0.1, min(1.0, confidence))

    return ValuationResult(
        method="EV/EBITDA" + (" (Mid-cycle)" if is_cyclical else ""),
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            "ebitda_ttm": ebitda_ttm,
            "ebitda_5y_avg": ebitda_5y_avg,
            "ebitda_used": ebitda_used,
            "net_debt": net_debt,
            "minority_interest": minority_interest,
        },
        key_outputs={
            "target_multiple": target_multiple,
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "fair_value": fair_value,
            "upside_pct": upside,
            "current_multiple": current_multiple,
        },
        warnings=warnings,
        notes=notes,
    )


