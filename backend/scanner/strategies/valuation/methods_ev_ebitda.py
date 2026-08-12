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


# Bội số EV/EBITDA mặc định theo ngành cho thị trường VN — chỉ dùng khi peer
# database chưa đủ mẫu (>= 3 mã cùng ngành). Đây là giá trị mid-cycle thận
# trọng, KHÔNG phải bội số hiện tại của thị trường; cần review lại định kỳ.
INDUSTRY_DEFAULT_EV_EBITDA = {
    'Steel_Metals':             5.5,
    'Chemicals':                6.0,
    'Oil_Gas':                  5.5,
    'Agriculture_Livestock':    6.0,
    'Construction':             6.5,
    'Telecom':                  6.5,
    'Industrial_Manufacturing': 7.0,
    'Logistics_Transport':      7.0,
    'Diversified_Holding':      7.5,
    'Consumer_Discretionary':   8.0,
    'Utilities':                8.0,
    'Healthcare':               8.5,
    'Real_Estate':              9.0,
    'Consumer_Staples':         9.5,
    'Technology':              10.0,
    'Unknown':                  7.0,
}


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

        # Guard chia 0: EBITDA 5y avg = 0 từng làm method ném ZeroDivisionError,
        # bị engine nuốt lặng và biến mất khỏi báo cáo mà user không biết.
        if ebitda_5y_avg > 0:
            cycle_ratio = ebitda_ttm / ebitda_5y_avg
            if cycle_ratio > 1.5:
                warnings.append(f"EBITDA TTM ({ebitda_ttm:,.0f}) cao hơn 50% so với 5y avg → có thể đang ở đỉnh chu kỳ")
            elif cycle_ratio < 0.6:
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
    #
    # FIX: bản cũ lấy `ratios.get("ev_ebitda", 6.0)` nhưng KHÔNG module nào set
    # key này ⇒ bội số mục tiêu là hằng số 6.0x (cyclical) / 6.8x (stable) cho
    # mọi doanh nghiệp. Nay normalizer tính EV/EBITDA thật, và bội số MỤC TIÊU
    # lấy từ peer median (ưu tiên) hoặc bảng mặc định theo ngành — KHÔNG lấy từ
    # bội số hiện tại của chính mã đó (sẽ là circular: fair value ≈ giá thị trường).
    current_multiple = ratios.get("ev_ebitda")
    industry = data.get('_industry') or 'Unknown'

    peer_median = None
    peer_n = None
    try:
        from ...peer_database import get_peer_band
        peer_band = get_peer_band(industry, 'ev_ebitda')
        if peer_band and peer_band.get('median'):
            peer_median = peer_band['median']
            peer_n = peer_band.get('n')
    except Exception:
        pass

    if peer_median is not None and (peer_n or 0) >= 3:
        base_multiple = peer_median
        base_source = f"peer median ngành {industry} (n={peer_n})"
        peer_backed = True
    else:
        base_multiple = INDUSTRY_DEFAULT_EV_EBITDA.get(
            industry, INDUSTRY_DEFAULT_EV_EBITDA['Unknown'])
        base_source = f"mặc định ngành {industry} (chưa đủ peer)"
        peer_backed = False
        warnings.append(
            f"Chưa có peer EV/EBITDA cho ngành {industry} (cần >= 3 mã) — "
            f"dùng bội số mặc định {base_multiple:.1f}x, độ tin cậy thấp hơn"
        )

    notes.append(f"Bội số cơ sở = {base_multiple:.1f}x ({base_source})")
    if current_multiple:
        notes.append(f"EV/EBITDA hiện tại của mã = {current_multiple:.1f}x (tham chiếu, không dùng làm mục tiêu)")

    if is_cyclical:
        # Cyclical: điều chỉnh theo vị trí chu kỳ.
        #   - Đáy chu kỳ: thị trường trả bội số cao vì EBITDA thấp tạm thời
        #   - Đỉnh chu kỳ: discount vì EBITDA sắp giảm
        cycle_pos = data.get("cyclical_info", {}).get("current_cycle_position", "mid")
        cycle_premium = {
            "trough": 1.30,
            "recovery": 1.15,
            "recovery_to_peak": 1.05,
            "mid": 1.00,
            "peak": 0.85,
        }.get(cycle_pos, 1.00)
        target_multiple = base_multiple * cycle_premium
        notes.append(
            f"Target EV/EBITDA = {base_multiple:.1f} × cycle adj ({cycle_premium:.2f}, "
            f"phase={cycle_pos}) = {target_multiple:.1f}x"
        )
    else:
        target_multiple = base_multiple
        notes.append(f"Target EV/EBITDA = {target_multiple:.1f}x")

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
    if not shares or shares <= 0:
        warnings.append("Không xác định được số cổ phiếu lưu hành")
        return ValuationResult(
            method="EV/EBITDA", ticker=ticker, fair_value_per_share=0,
            current_price=current_price, upside_pct=0, confidence=0.0,
            warnings=warnings, notes=notes,
        )
    fair_value = (equity_value * 1_000_000_000) / shares
    upside = (fair_value - current_price) / current_price if current_price else 0

    # --- 5. Confidence ---
    confidence = 0.75
    if is_cyclical:
        confidence = 0.80  # EV/EBITDA mid-cycle là tốt nhất cho cyclical
    if not peer_backed:
        # Bội số mặc định theo ngành yếu hơn nhiều so với peer thật.
        confidence -= 0.20
    if not cash_flow.get("ebitda_5y_avg"):
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


