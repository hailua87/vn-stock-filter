"""
PHƯƠNG PHÁP RNAV (Revalued Net Asset Value) - SIMPLIFIED
================================================================================
Định giá đặc thù cho real estate. Phiên bản đầy đủ cần data từng dự án từ
thuyết minh BCTC, phiên bản simplified này dùng aggregate:

  RNAV = Investment Property (revalued) +
         Real Estate Inventory (× revaluation factor) +
         Other Net Assets (book value) -
         Total Liabilities -
         Minority Interest

Revaluation factor được áp cho:
  - Inventory (dự án dở dang): × (1 + project_margin) — projects sẽ bán trên cost
  - Investment property (đã hoàn thành cho thuê): × regional_multiplier — đất tăng giá

Áp dụng tốt nhất cho: VHM, NLG, KDH, NVL, DXG, PDR
Limitations:
  - Không capture được giá trị đất bank chưa develop
  - Region multiplier hardcode (lý tưởng từ CBRE/Savills index)
  - Margin lấy historical, có thể không phản ánh dự án mới
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List

from .methods_pb_roe import ValuationResult


# Revaluation multipliers - heuristic dựa trên báo cáo CBRE/Savills VN 2024
# Production: load từ data source thực, cập nhật quý
DEFAULT_REGIONAL_REVAL = {
    'hochiminh':   1.40,  # Đất TP.HCM tăng nhanh, đặc biệt khu Đông
    'hanoi':       1.30,
    'binhduong':   1.25,
    'danang':      1.20,
    'haiphong':    1.15,
    'other':       1.10,
}

# Project margin defaults (gross margin lịch sử cho realty projects)
DEFAULT_PROJECT_MARGIN = 0.25  # 25% gross margin trên cost


def calculate_rnav_simplified(data: Dict[str, Any]) -> ValuationResult:
    """
    RNAV approximation từ aggregate balance sheet items.

    Inputs cần thiết từ normalized data:
      - balance_sheet.investment_property
      - balance_sheet.inventory (proxy cho RE_inventory)
      - balance_sheet.total_assets, total_liabilities, minority_interest
      - market.shares_outstanding
    """
    ticker = data['ticker']
    market = data['market']
    bs = data['balance_sheet']
    ratios = data['ratios']
    warnings = []
    notes = []

    current_price = market['current_price']
    shares = market['shares_outstanding']

    if shares <= 0:
        return ValuationResult(
            method="RNAV",
            ticker=ticker,
            fair_value_per_share=0,
            current_price=current_price,
            upside_pct=-1.0,
            confidence=0.0,
            warnings=["Không có shares outstanding"],
        )

    # === Tài sản RE chính ===
    investment_property = bs.get('investment_property', 0)
    re_inventory = bs.get('inventory', 0)  # toàn bộ inventory, proxy cho RE inventory
    total_assets = bs.get('total_assets', 0)
    total_liabilities = bs.get('total_liabilities', 0)
    minority = bs.get('minority_interest', 0)
    shareholders_equity = bs.get('shareholders_equity', 0)

    if investment_property + re_inventory < total_assets * 0.20:
        warnings.append(
            f"Inventory + investment property chỉ {(investment_property + re_inventory)/total_assets:.0%} "
            f"tổng tài sản. RNAV có thể không phù hợp (không phải pure RE)."
        )

    # === Region revaluation ===
    # Heuristic: nếu không có data region cụ thể, dùng average của HCM+HN
    region = data.get('overview', {}).get('primary_region', 'other')
    reval_mult = DEFAULT_REGIONAL_REVAL.get(region, DEFAULT_REGIONAL_REVAL['other'])
    notes.append(f"Region revaluation: '{region}' → ×{reval_mult:.2f}")

    # === Project margin từ historical gross margin ===
    project_margin = ratios.get('gross_margin', DEFAULT_PROJECT_MARGIN)
    if project_margin <= 0:
        project_margin = DEFAULT_PROJECT_MARGIN
    notes.append(f"Project margin: {project_margin:.0%} (historical gross margin)")

    # === Revalue ===
    rnav_inv_prop = investment_property * reval_mult
    rnav_inventory = re_inventory * (1 + project_margin)

    notes.append(
        f"Investment property: {investment_property:,.0f} × {reval_mult:.2f} = {rnav_inv_prop:,.0f}"
    )
    notes.append(
        f"RE inventory: {re_inventory:,.0f} × (1 + {project_margin:.0%}) = {rnav_inventory:,.0f}"
    )

    # Other assets = total - investment_property - inventory
    other_assets = max(0, total_assets - investment_property - re_inventory)

    revalued_total_assets = rnav_inv_prop + rnav_inventory + other_assets
    rnav_total = revalued_total_assets - total_liabilities - minority

    notes.append(
        f"RNAV total = {revalued_total_assets:,.0f} - liab {total_liabilities:,.0f} - "
        f"MI {minority:,.0f} = {rnav_total:,.0f}"
    )

    # === Convert to VND per share ===
    fair_value = (rnav_total * 1_000_000_000) / shares if shares > 0 else 0
    upside = (fair_value - current_price) / current_price if current_price > 0 else 0

    # Sanity caps - RNAV có thể extreme nếu data lệch
    extreme_factor = fair_value / current_price if current_price > 0 else 0
    if extreme_factor > 4.0:
        warnings.append(f"RNAV cao bất thường ({extreme_factor:.1f}× giá). Capped tại 3×.")
        fair_value = current_price * 3.0
        upside = (fair_value - current_price) / current_price
    elif 0 < extreme_factor < 0.25:
        warnings.append(f"RNAV thấp bất thường ({extreme_factor:.2f}× giá). Floor tại 0.4×.")
        fair_value = current_price * 0.4
        upside = (fair_value - current_price) / current_price

    # === Cross-check với P/B ===
    pb_implied = fair_value * shares / (shareholders_equity * 1_000_000_000) if shareholders_equity > 0 else 0
    if pb_implied > 5.0:
        warnings.append(f"RNAV implies P/B = {pb_implied:.1f}× — quá cao, kiểm tra inputs")

    # === Confidence ===
    confidence = 0.60
    if re_inventory + investment_property < total_assets * 0.30:
        confidence -= 0.20  # không phải pure RE
    if region == 'other':
        confidence -= 0.10  # không biết region cụ thể
    if data.get('overview', {}).get('industry') in ['Bất động sản', 'Real Estate']:
        confidence += 0.10  # đúng ngành
    confidence = max(0.1, min(1.0, confidence))

    return ValuationResult(
        method="RNAV",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            'investment_property': investment_property,
            're_inventory': re_inventory,
            'total_liabilities': total_liabilities,
            'minority_interest': minority,
            'region_multiplier': reval_mult,
            'project_margin': project_margin,
        },
        key_outputs={
            'rnav_investment_property': rnav_inv_prop,
            'rnav_inventory': rnav_inventory,
            'revalued_total_assets': revalued_total_assets,
            'rnav_total': rnav_total,
            'rnav_per_share': fair_value,
            'implied_pb': pb_implied,
        },
        warnings=warnings,
        notes=notes,
    )


def calculate_sotp_simplified(data: Dict[str, Any]) -> ValuationResult:
    """
    Sum-of-the-Parts SIMPLIFIED cho holding companies.

    Phiên bản đầy đủ cần data từng segment (revenue, EBITDA, asset breakdown).
    Phiên bản simplified:
      1. Áp dụng holding discount 15-20% lên blended fair value của methods khác
      2. Adjust cho minority interest lớn

    Chỉ dùng cho: PAN, MSN, VIC, GEX, REE (xác định bởi industry_classifier override)
    """
    ticker = data['ticker']
    market = data['market']
    bs = data['balance_sheet']
    ratios = data['ratios']
    per_share = data['per_share']

    current_price = market['current_price']
    shares = market['shares_outstanding']
    notes = []
    warnings = []

    if shares <= 0 or current_price <= 0:
        return ValuationResult(
            method="SOTP Simplified",
            ticker=ticker,
            fair_value_per_share=0,
            current_price=current_price,
            upside_pct=-1.0,
            confidence=0.0,
            warnings=["Missing market data"],
        )

    # Calculate "naive equity value" từ book + earnings power
    bvps = per_share.get('bvps', 0)
    eps_ttm = per_share.get('eps_ttm', 0)

    # 2 estimators:
    # (a) Book value × adjustment (cho ngành mixed = ~1.0-1.2x)
    book_estimate = bvps * 1.10
    # (b) Earnings × moderate multiple (P/E 10x)
    earnings_estimate = eps_ttm * 10 if eps_ttm > 0 else 0

    if earnings_estimate > 0:
        gross_fair_value = (book_estimate + earnings_estimate) / 2
    else:
        gross_fair_value = book_estimate

    notes.append(f"Gross estimate: book×1.1 = {book_estimate:,.0f}, "
                 f"P/E10 = {earnings_estimate:,.0f} → avg {gross_fair_value:,.0f}")

    # Holding discount: 15-25%
    minority = bs.get('minority_interest', 0)
    total_equity = bs.get('shareholders_equity', 1)
    mi_ratio = minority / max(total_equity, 1)

    # Discount lớn hơn nếu MI lớn (vì parent có ít quyền hơn)
    if mi_ratio > 0.5:
        holding_discount = 0.25
    elif mi_ratio > 0.3:
        holding_discount = 0.20
    else:
        holding_discount = 0.15

    fair_value = gross_fair_value * (1 - holding_discount)
    notes.append(f"Holding discount: {holding_discount:.0%} (MI ratio {mi_ratio:.0%})")

    upside = (fair_value - current_price) / current_price if current_price > 0 else 0

    confidence = 0.50  # Simplified SOTP: low confidence
    if mi_ratio > 0.4:
        confidence -= 0.10
    if not data.get('income', {}).get('revenue_5y'):
        confidence -= 0.10
    confidence = max(0.2, min(0.7, confidence))

    return ValuationResult(
        method="SOTP Simplified",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            'bvps': bvps,
            'eps_ttm': eps_ttm,
            'minority_ratio': mi_ratio,
            'holding_discount': holding_discount,
        },
        key_outputs={
            'gross_fair_value': gross_fair_value,
            'fair_value': fair_value,
        },
        warnings=warnings,
        notes=notes,
    )
