"""
PHƯƠNG PHÁP ĐỊNH GIÁ P/B - ROE JUSTIFIED
================================================================================
Phương pháp định giá chuyên dụng cho ngân hàng và công ty tài chính.

CƠ SỞ LÝ LUẬN:
    Justified P/B = (ROE - g) / (Cost_of_Equity - g)

    Suy từ Gordon Growth Model với:
      - Doanh nghiệp tạo ra ROE trên vốn chủ sở hữu
      - Tỷ lệ tăng trưởng bền vững g
      - Chi phí vốn chủ sở hữu (CoE) tính theo CAPM

    Trực giác: Nếu ROE > CoE → tạo giá trị → P/B > 1
              Nếu ROE = CoE → giao dịch tại 1.0
              Nếu ROE < CoE → P/B < 1 (phá giá trị)

ÁP DỤNG CHO:
    ✅ Banking (VIB, VCB, BID, CTG...) - phù hợp nhất
    ✅ Securities (SSI, VND, HCM...)
    ✅ Insurance (BVH, BMI...)
    ⚠️  Có thể dùng cho Industrial nhưng kém hiệu quả hơn P/E

INPUT QUAN TRỌNG:
    - ROE bền vững (sustainable ROE, không phải ROE đỉnh chu kỳ)
    - Book value growth rate (thường thấp hơn EPS growth do cổ tức)
    - Cost of Equity (qua CAPM)
    - Asset quality adjustment cho banking (NPL, coverage ratio)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .normalizer import MARKET_PARAMS


@dataclass
class ValuationResult:
    """Kết quả định giá chuẩn (dùng chung cho mọi phương pháp)."""
    method: str
    ticker: str
    fair_value_per_share: float          # VND/cp
    current_price: float
    upside_pct: float                    # (fair - current) / current
    confidence: float                    # 0-1
    key_inputs: Dict[str, Any] = field(default_factory=dict)
    key_outputs: Dict[str, Any] = field(default_factory=dict)
    sensitivity: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def calculate_cost_of_equity(beta: float, country_risk_premium: float = 0.0) -> Dict[str, float]:
    """Tính chi phí vốn chủ sở hữu theo CAPM cho thị trường VN.

    CoE = Rf + β × (ERP + Country Risk Premium)

    Args:
        beta: Hệ số beta của cổ phiếu (regression với VN-Index)
        country_risk_premium: Phụ phí rủi ro quốc gia (default 0 vì đã tính trong ERP)

    Returns:
        Dict với rf, erp, beta, coe và các thành phần
    """
    rf = MARKET_PARAMS["risk_free_rate"]
    erp = MARKET_PARAMS["market_risk_premium"]
    coe = rf + beta * (erp + country_risk_premium)
    return {
        "risk_free_rate": rf,
        "market_risk_premium": erp,
        "country_risk_premium": country_risk_premium,
        "beta": beta,
        "cost_of_equity": coe,
    }


def calculate_sustainable_growth(roe: float, payout_ratio: float) -> float:
    """Tính tăng trưởng bền vững (g) theo Sustainable Growth Rate formula.

        g = ROE × (1 - payout_ratio) = ROE × retention_ratio

    Đây là tăng trưởng có thể duy trì mà không cần huy động vốn ngoài.
    """
    retention = max(0, min(1, 1 - payout_ratio))
    return roe * retention


def calculate_asset_quality_adjustment(data: Dict[str, Any]) -> Dict[str, Any]:
    """Điều chỉnh P/B mục tiêu cho ngân hàng dựa trên chất lượng tài sản.

    Điều chỉnh dựa trên:
      - NPL ratio: < 1.5% (premium), 1.5-3% (neutral), > 3% (discount)
      - Coverage ratio (LLR/NPL): > 150% (premium), 100-150% (neutral), < 100% (discount)
      - CAR: > 13% (premium), 10-13% (neutral), < 10% (discount)

    Returns multiplier áp dụng cho justified P/B (e.g., 0.85 = discount 15%).
    """
    if "asset_quality" not in data:
        return {"multiplier": 1.0, "components": {}, "notes": ["Không có data chất lượng tài sản"]}

    aq = data["asset_quality"]
    bs = data["balance_sheet"]
    components = {}
    multiplier = 1.0

    # NPL adjustment
    npl = aq.get("npl_ratio", 0.025)
    if npl < 0.015:
        npl_adj = 1.10
        components["npl"] = f"NPL {npl:.1%} < 1.5% → +10%"
    elif npl > 0.030:
        npl_adj = 0.85
        components["npl"] = f"NPL {npl:.1%} > 3.0% → -15%"
    else:
        npl_adj = 1.0
        components["npl"] = f"NPL {npl:.1%} trung tính"

    # Coverage adjustment
    coverage = aq.get("npl_coverage_ratio", 1.0)
    if coverage > 1.5:
        cov_adj = 1.05
        components["coverage"] = f"Coverage {coverage:.0%} > 150% → +5%"
    elif coverage < 1.0:
        cov_adj = 0.92
        components["coverage"] = f"Coverage {coverage:.0%} < 100% → -8%"
    else:
        cov_adj = 1.0
        components["coverage"] = f"Coverage {coverage:.0%} trung tính"

    # CAR adjustment
    car = bs.get("car", 0.115)
    if car > 0.13:
        car_adj = 1.03
        components["car"] = f"CAR {car:.1%} > 13% → +3%"
    elif car < 0.10:
        car_adj = 0.90
        components["car"] = f"CAR {car:.1%} < 10% → -10%"
    else:
        car_adj = 1.0
        components["car"] = f"CAR {car:.1%} trung tính"

    multiplier = npl_adj * cov_adj * car_adj
    return {
        "multiplier": multiplier,
        "components": components,
        "npl_adj": npl_adj,
        "coverage_adj": cov_adj,
        "car_adj": car_adj,
    }


def run_sensitivity_pb(roe_base: float, g_base: float, coe_base: float,
                       bvps: float, current_price: float) -> Dict[str, Any]:
    """Bảng độ nhạy cho P/B với ROE và CoE thay đổi.

    Returns: Dict chứa table và summary
    """
    roe_range = [roe_base - 0.03, roe_base - 0.015, roe_base, roe_base + 0.015, roe_base + 0.03]
    coe_range = [coe_base - 0.01, coe_base - 0.005, coe_base, coe_base + 0.005, coe_base + 0.01]

    table = []  # rows = ROE, cols = CoE
    for roe in roe_range:
        row = []
        for coe in coe_range:
            # Đảm bảo coe > g
            g = min(g_base, coe - 0.01)
            if coe - g < 0.001:
                row.append(None)
                continue
            justified_pb = (roe - g) / (coe - g)
            fair_value = justified_pb * bvps
            upside = (fair_value - current_price) / current_price
            row.append({
                "pb": justified_pb,
                "fair_value": fair_value,
                "upside_pct": upside,
            })
        table.append(row)

    return {
        "roe_range": roe_range,
        "coe_range": coe_range,
        "table": table,
        "base_case_index": (2, 2),  # center
    }


def calculate_pb_roe_valuation(data: Dict[str, Any]) -> ValuationResult:
    """ĐỊNH GIÁ CHÍNH BẰNG P/B-ROE JUSTIFIED.

    Quy trình:
      1. Tính sustainable ROE (trung bình 3-5 năm, không phải ROE đỉnh)
      2. Tính sustainable growth g
      3. Tính Cost of Equity qua CAPM
      4. Tính justified P/B = (ROE - g) / (CoE - g)
      5. Điều chỉnh theo chất lượng tài sản (cho banking)
      6. Tính fair value = justified P/B × BVPS
      7. Thêm sensitivity analysis
    """
    ticker = data["ticker"]
    market = data["market"]
    bs = data["balance_sheet"]
    ratios = data["ratios"]
    growth = data["growth"]
    per_share = data["per_share"]
    warnings = []
    notes = []

    # --- 1. Sustainable ROE ---
    # Dùng trung bình 3-5 năm để loại bỏ outlier
    roe_5y = data["income"].get("roe_5y", [])
    roe_ttm = ratios.get("roe_ttm", 0.15)

    # Kiểm tra ngành có phải cyclical không (qua overview industry)
    overview_industry = data.get("overview", {}).get("industry", "")
    is_cyclical_for_roe = any(kw in overview_industry.lower() for kw in [
        "thực phẩm", "food", "hóa chất", "chemical", "thép", "steel",
        "tài nguyên", "resources", "dầu khí", "oil", "sản xuất thực phẩm"
    ]) or data.get("cyclical_info", {}).get("is_cyclical", False)
    # Ticker-level cyclical override (DBC, BAF, HAG, HPG, ...)
    if ticker in ["DBC", "BAF", "HAG", "HPG", "HSG", "NKG", "DGC", "DCM", "DPM"]:
        is_cyclical_for_roe = True

    if roe_5y and len(roe_5y) >= 3:
        if is_cyclical_for_roe:
            # CYCLICAL: dùng trung vị (median) thay vì mean - robust hơn với outliers
            # và cap về 15% (giới hạn ROE thực tế cho cyclical industries)
            sorted_roe = sorted(roe_5y)
            median_roe = sorted_roe[len(sorted_roe) // 2]
            sustainable_roe = min(median_roe, 0.15)
            notes.append(
                f"CYCLICAL → Sustainable ROE = min(median 5y={median_roe:.1%}, 15% cap) "
                f"= {sustainable_roe:.1%}"
            )
            warnings.append(
                f"Ngành cyclical: dùng median ROE để định giá P/B (raw 5y range "
                f"{min(roe_5y):.1%}-{max(roe_5y):.1%})"
            )
        else:
            # NON-CYCLICAL: trimmed mean (loại max + min)
            sorted_roe = sorted(roe_5y)
            trimmed = sorted_roe[1:-1] if len(sorted_roe) >= 5 else sorted_roe
            sustainable_roe = sum(trimmed) / len(trimmed)
            notes.append(f"Sustainable ROE = trung bình trimmed 5y = {sustainable_roe:.1%}")
    else:
        sustainable_roe = roe_ttm
        notes.append(f"Dùng ROE TTM = {sustainable_roe:.1%} (không đủ 5y history)")

    # Floor sustainable ROE để tránh trường hợp ROE âm/0
    if sustainable_roe < 0.03:
        sustainable_roe = 0.03
        warnings.append(f"Sustainable ROE quá thấp, ép lên 3% (floor)")

    # Cảnh báo nếu ROE TTM lệch nhiều
    if abs(roe_ttm - sustainable_roe) / sustainable_roe > 0.30:
        warnings.append(
            f"ROE TTM ({roe_ttm:.1%}) lệch >30% so với trung bình 5y ({sustainable_roe:.1%}). "
            f"Có thể đang ở đỉnh/đáy chu kỳ - cần xem xét lại."
        )

    # --- 2. Sustainable growth ---
    payout = ratios.get("payout_ratio", 0.30)
    g_sustainable = calculate_sustainable_growth(sustainable_roe, payout)
    g_historical = growth.get("book_value_growth_3y", g_sustainable)

    # Lấy min(g_sustainable, g_historical) để bảo thủ
    g = min(g_sustainable, g_historical)
    # Cap g về long-term GDP growth (terminal growth của nền kinh tế)
    # Banking không thể tăng trưởng nhanh hơn GDP mãi mãi
    g_cap = MARKET_PARAMS["long_term_gdp_growth"]  # ~6% cho VN
    if g > g_cap:
        notes.append(f"g raw = {g:.1%} → cap về long-term GDP growth {g_cap:.1%}")
        g = g_cap
    else:
        notes.append(f"g = min(sustainable={g_sustainable:.1%}, historical={g_historical:.1%}) = {g:.1%}")

    # --- 3. Cost of Equity ---
    beta = market.get("beta_2y", 1.0)
    coe_data = calculate_cost_of_equity(beta)
    coe = coe_data["cost_of_equity"]
    notes.append(f"CoE = {coe_data['risk_free_rate']:.1%} + {beta:.2f} × {coe_data['market_risk_premium']:.1%} = {coe:.1%}")

    # Sanity check
    if coe - g < 0.01:
        warnings.append(f"CoE - g = {coe-g:.1%} quá nhỏ → kết quả không ổn định. Buộc g = CoE - 1.5%")
        g = coe - 0.015

    # --- 4. Justified P/B (2-STAGE GROWTH MODEL) ---
    # Lý do dùng 2-stage cho banking VN: ROE bền vững cao bất thường (20-25%)
    # do đòn bẩy cao và NIM cao. ROE này không duy trì mãi - sẽ fade về DM levels
    # (15-17%) trong 10-15 năm khi thị trường tài chính trưởng thành.
    #
    # 2-stage logic:
    #   Stage 1 (high growth): N năm tăng trưởng g1 với ROE cao
    #   Stage 2 (terminal):   tăng trưởng terminal g2 với ROE bình thường hóa
    #
    # Justified P/B = Σ(BV_t × ROE_t × payout_t / (1+CoE)^t)
    #                 + Terminal P/B × BV_N / (1+CoE)^N
    # Đơn giản hóa cho banking:
    #   = Stage1_value_factor + Terminal_value_factor

    high_growth_years = 8
    g1 = g  # đã được cap
    roe_terminal = min(sustainable_roe, MARKET_PARAMS["long_term_gdp_growth"] / (1 - payout) + 0.08)
    # roe_terminal max ~ 14-15% (fade về DM-bank levels)
    g2 = MARKET_PARAMS["long_term_gdp_growth"] * 0.7  # ~4.2% terminal growth

    # Stage 1: PV of excess return creation
    # Mỗi năm, value added = (ROE - CoE) × BV / CoE đối với perpetual
    # Stage 1 dùng formula: sum of dividends + terminal book value at year N
    pv_dividends = 0
    bv_factor = 1.0  # BV(t) / BV(0)
    for t in range(1, high_growth_years + 1):
        # Cuối năm t-1, BV = bv_factor × BVPS
        # Dividend năm t = ROE × BV(t-1) × payout
        div_per_bvps = sustainable_roe * bv_factor * payout
        pv_dividends += div_per_bvps / (1 + coe) ** t
        # BV update: BV(t) = BV(t-1) × (1 + ROE × retention)
        bv_factor *= (1 + sustainable_roe * (1 - payout))

    # Terminal P/B at year N (Gordon)
    terminal_pb = (roe_terminal - g2) / (coe - g2) if coe - g2 > 0.005 else 1.0
    pv_terminal = terminal_pb * bv_factor / (1 + coe) ** high_growth_years

    raw_pb = pv_dividends + pv_terminal

    notes.append(
        f"2-stage P/B: Stage1 ({high_growth_years}y, ROE={sustainable_roe:.1%}, g={g1:.1%}) "
        f"contributes {pv_dividends:.2f}x"
    )
    notes.append(
        f"Stage2 terminal: ROE_T={roe_terminal:.1%}, g_T={g2:.1%}, "
        f"terminal P/B={terminal_pb:.2f}x → PV contribution={pv_terminal:.2f}x"
    )
    notes.append(f"Raw justified P/B (2-stage) = {raw_pb:.2f}x")

    # --- 5. Asset quality adjustment (cho banking) ---
    aq_adj = calculate_asset_quality_adjustment(data)
    aq_multiplier = aq_adj["multiplier"]
    adjusted_pb = raw_pb * aq_multiplier
    notes.append(f"Asset quality adjustment: {aq_multiplier:.2f}x → adjusted P/B = {adjusted_pb:.2f}x")
    for comp, msg in aq_adj.get("components", {}).items():
        notes.append(f"  ▸ {msg}")

    # --- 6. Cross-check với historical band ---
    pb_5y_median = ratios.get("pb_5y_median", adjusted_pb)
    pb_5y_p25 = ratios.get("pb_5y_p25", adjusted_pb * 0.85)
    pb_5y_p75 = ratios.get("pb_5y_p75", adjusted_pb * 1.15)

    # Weighted blend: 70% justified, 30% historical median
    final_pb = 0.70 * adjusted_pb + 0.30 * pb_5y_median
    notes.append(f"Blend final P/B = 70% × {adjusted_pb:.2f} + 30% × hist_median {pb_5y_median:.2f} = {final_pb:.2f}x")

    # --- 7. Fair Value ---
    bvps = per_share["bvps"]
    fair_value = final_pb * bvps
    current_price = market["current_price"]
    upside = (fair_value - current_price) / current_price

    # --- 8. Confidence scoring ---
    confidence = 0.85  # base cho banking
    if not roe_5y or len(roe_5y) < 3:
        confidence -= 0.15
    if len(warnings) > 0:
        confidence -= 0.10 * len(warnings)
    if data.get("overview", {}).get("industry") not in ["Ngân hàng", "Banks", "Dịch vụ tài chính"]:
        confidence -= 0.20
        warnings.append("P/B-ROE không phải phương pháp tối ưu cho ngành này")
    confidence = max(0.1, min(1.0, confidence))

    # --- 9. Sensitivity ---
    sensitivity = run_sensitivity_pb(sustainable_roe, g, coe, bvps, current_price)

    return ValuationResult(
        method="P/B-ROE Justified",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            "sustainable_roe": sustainable_roe,
            "roe_ttm": roe_ttm,
            "sustainable_growth_g": g,
            "cost_of_equity": coe,
            "beta": beta,
            "bvps": bvps,
            "payout_ratio": payout,
        },
        key_outputs={
            "raw_justified_pb": raw_pb,
            "asset_quality_multiplier": aq_multiplier,
            "adjusted_pb": adjusted_pb,
            "historical_pb_median": pb_5y_median,
            "final_target_pb": final_pb,
            "current_pb": ratios.get("pb_current"),
            "fair_value": fair_value,
            "upside_pct": upside,
        },
        sensitivity=sensitivity,
        warnings=warnings,
        notes=notes,
    )


