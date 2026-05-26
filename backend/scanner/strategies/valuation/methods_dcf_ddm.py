"""
PHƯƠNG PHÁP DCF FCFF & DDM
================================================================================
Hai phương pháp định giá dùng dòng tiền tương lai chiết khấu về hiện tại.

DCF FCFF (Free Cash Flow to Firm):
    EV = Σ(FCFF_t / (1+WACC)^t) + Terminal Value
    Equity Value = EV - Net Debt - Minority Interest

    Áp dụng:
      ✅ Consumer Staples ổn định (VNM, SAB)
      ✅ Utilities (POW, NT2, REE)
      ✅ Technology (FPT)
      ⚠️  Cyclicals (cần dùng normalized FCFF, không phải TTM)
      ❌ Banks/Insurance (không tách được CapEx)

DDM (Dividend Discount Model):
    Value = Σ(DPS_t / (1+CoE)^t) + Terminal DPS / (CoE - g)

    Áp dụng:
      ✅ Utilities có cổ tức ổn định (REE, NT2, POW)
      ✅ Banks chia cổ tức đều (VCB, MBB)
      ❌ Growth companies không chia cổ tức (FPT phần lớn)
      ❌ Cyclicals (cổ tức thay đổi mạnh)

CẢNH BÁO QUAN TRỌNG:
  Terminal value thường chiếm 60-80% giá trị DCF → rất nhạy với
  (WACC - g). Engine phải tự cảnh báo nếu terminal share > 75%.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import math

from .normalizer import MARKET_PARAMS
from .methods_pb_roe import (
    ValuationResult,
    calculate_cost_of_equity,
)


# ============================================================================
# WACC CALCULATION
# ============================================================================

def calculate_wacc(data: Dict[str, Any]) -> Dict[str, float]:
    """
    WACC = (E/V) × CoE + (D/V) × CoD × (1 - tax)

    Args:
        data: Normalized data với 'market', 'balance_sheet'
    """
    market = data['market']
    bs = data['balance_sheet']

    equity_value = market.get('market_cap', 0)  # tỷ đồng
    short_debt = bs.get('short_term_debt', 0)
    long_debt = bs.get('long_term_debt', 0)
    total_debt = short_debt + long_debt
    cash = bs.get('cash_and_equivalents', 0)
    net_debt = max(0, total_debt - cash)  # floor 0 (không thể negative cho WACC)

    total_capital = equity_value + total_debt
    if total_capital < 1e-6:
        # Fallback: dùng book value
        equity_value = bs.get('shareholders_equity', 1)
        total_capital = equity_value + total_debt

    weight_equity = equity_value / total_capital if total_capital > 0 else 1.0
    weight_debt = 1 - weight_equity

    # Cost of equity (CAPM)
    beta = market.get('beta_2y', 1.0)
    coe_info = calculate_cost_of_equity(beta)
    coe = coe_info['cost_of_equity']

    # Cost of debt: ước tính = rf + spread
    # Spread VN corporate: AAA ~ 1.5%, BB ~ 4-5%, default ~ 3%
    # Heuristic: tỷ lệ debt/equity càng cao → spread càng cao
    de_ratio = total_debt / max(equity_value, 1)
    if de_ratio < 0.3:
        debt_spread = 0.020
    elif de_ratio < 1.0:
        debt_spread = 0.030
    elif de_ratio < 2.0:
        debt_spread = 0.040
    else:
        debt_spread = 0.055
    cod_pretax = MARKET_PARAMS['risk_free_rate'] + debt_spread
    tax_rate = MARKET_PARAMS['tax_rate_corporate']
    cod_aftertax = cod_pretax * (1 - tax_rate)

    wacc = weight_equity * coe + weight_debt * cod_aftertax

    return {
        'wacc': wacc,
        'cost_of_equity': coe,
        'cost_of_debt_pretax': cod_pretax,
        'cost_of_debt_aftertax': cod_aftertax,
        'weight_equity': weight_equity,
        'weight_debt': weight_debt,
        'debt_to_equity': de_ratio,
        'beta': beta,
    }


# ============================================================================
# DCF FCFF
# ============================================================================

def _build_fade_growth_curve(initial: float, terminal: float, years: int) -> List[float]:
    """Linear fade từ initial → terminal growth rate."""
    if years <= 1:
        return [terminal]
    step = (initial - terminal) / (years - 1)
    return [initial - step * i for i in range(years)]


def calculate_dcf_fcff(data: Dict[str, Any],
                      forecast_years: int = 8) -> ValuationResult:
    """
    DCF FCFF 2-stage: explicit forecast + terminal Gordon.

    Inputs từ data:
      - cash_flow.fcff_ttm: FCFF gần nhất
      - growth.profit_growth_5y_cagr: tăng trưởng quá khứ (proxy cho năm đầu)
      - market.market_cap, balance_sheet.* để tính WACC
    """
    ticker = data['ticker']
    market = data['market']
    bs = data['balance_sheet']
    cf = data['cash_flow']
    growth = data['growth']
    warnings = []
    notes = []

    current_price = market['current_price']
    shares = market['shares_outstanding']
    fcff_ttm = cf.get('fcff_ttm', 0)

    # Sanity check: FCFF dương
    if fcff_ttm <= 0:
        warnings.append(f"FCFF TTM <= 0 ({fcff_ttm:.0f} tỷ) → DCF không khả thi")
        # Thử dùng normalized FCFF từ 5y avg
        ebitda_5y = cf.get('ebitda_5y_avg', 0)
        if ebitda_5y > 0:
            # Approximate FCFF từ EBITDA: FCFF ≈ EBITDA × 0.6 (after tax, capex)
            fcff_ttm = ebitda_5y * 0.6
            notes.append(f"Fallback: FCFF estimate = 60% × EBITDA 5y avg = {fcff_ttm:.0f} tỷ")
        else:
            return ValuationResult(
                method="DCF FCFF",
                ticker=ticker,
                fair_value_per_share=0,
                current_price=current_price,
                upside_pct=-1.0,
                confidence=0.0,
                warnings=warnings + ["Không thể chạy DCF: không có FCFF khả thi"],
            )

    # WACC
    wacc_info = calculate_wacc(data)
    wacc = wacc_info['wacc']
    notes.append(f"WACC = {wacc:.1%} "
                 f"(CoE={wacc_info['cost_of_equity']:.1%}×{wacc_info['weight_equity']:.0%} + "
                 f"CoD(at)={wacc_info['cost_of_debt_aftertax']:.1%}×{wacc_info['weight_debt']:.0%})")

    # Growth assumptions
    g_initial = growth.get('profit_growth_5y_cagr', 0.10)
    # Cap initial growth: không quá 25% (siêu tăng trưởng không bền)
    g_initial = max(0.0, min(0.25, g_initial))
    g_terminal = MARKET_PARAMS['terminal_growth_default']  # ~4.5%

    # Sanity: terminal < wacc
    if g_terminal >= wacc - 0.01:
        g_terminal = wacc - 0.020
        warnings.append(f"Terminal g ép xuống {g_terminal:.1%} để < WACC - 2%")

    growth_curve = _build_fade_growth_curve(g_initial, g_terminal, forecast_years)
    notes.append(f"Growth fade: Y1={g_initial:.1%} → Y{forecast_years}={g_terminal:.1%}")

    # === STAGE 1: Explicit forecast ===
    pv_explicit = 0
    fcff_curve = []
    fcff = fcff_ttm
    for t, g in enumerate(growth_curve, 1):
        fcff = fcff * (1 + g)
        pv = fcff / (1 + wacc) ** t
        pv_explicit += pv
        fcff_curve.append({'year': t, 'fcff': fcff, 'pv': pv, 'g': g})

    # === STAGE 2: Terminal value ===
    last_fcff = fcff_curve[-1]['fcff']
    terminal_fcff = last_fcff * (1 + g_terminal)
    terminal_value = terminal_fcff / (wacc - g_terminal)
    pv_terminal = terminal_value / (1 + wacc) ** forecast_years
    notes.append(f"Terminal value = {terminal_fcff:.0f} / ({wacc:.1%} - {g_terminal:.1%}) = {terminal_value:,.0f} tỷ")
    notes.append(f"PV terminal = {terminal_value:,.0f} / (1+{wacc:.1%})^{forecast_years} = {pv_terminal:,.0f} tỷ")

    # === Enterprise → Equity Value ===
    enterprise_value = pv_explicit + pv_terminal
    terminal_share = pv_terminal / enterprise_value if enterprise_value > 0 else 0
    if terminal_share > 0.80:
        warnings.append(
            f"Terminal value chiếm {terminal_share:.0%} của EV (>80%) → "
            f"kết quả phụ thuộc nhiều vào terminal g, kém ổn định"
        )

    total_debt = bs.get('short_term_debt', 0) + bs.get('long_term_debt', 0)
    cash = bs.get('cash_and_equivalents', 0)
    net_debt = total_debt - cash
    minority = bs.get('minority_interest', 0)

    equity_value = enterprise_value - net_debt - minority
    notes.append(f"Equity Value = EV ({enterprise_value:,.0f}) - Net Debt ({net_debt:,.0f}) - "
                 f"MI ({minority:,.0f}) = {equity_value:,.0f} tỷ")

    fair_value = (equity_value * 1_000_000_000) / shares if shares > 0 else 0
    upside = (fair_value - current_price) / current_price if current_price > 0 else 0

    # Sanity check: DCF rất nhạy với growth và WACC.
    # Nếu fair value > 4× current price → quá optimistic, cap lại để aggregation không bị skew
    extreme_factor = fair_value / current_price if current_price > 0 else 0
    if extreme_factor > 4.0:
        warnings.append(
            f"DCF fair value cao bất thường ({extreme_factor:.1f}× giá hiện tại). "
            f"Có thể do growth/WACC assumption quá lạc quan. Capped tại 3× giá."
        )
        fair_value = current_price * 3.0
        upside = (fair_value - current_price) / current_price
    elif extreme_factor < 0.25 and extreme_factor > 0:
        warnings.append(
            f"DCF fair value thấp bất thường ({extreme_factor:.2f}× giá hiện tại). "
            f"Có thể do FCFF âm/quá thấp. Floor tại 0.4× giá."
        )
        fair_value = current_price * 0.4
        upside = (fair_value - current_price) / current_price

    # === Sensitivity table cho WACC × terminal g ===
    sens_table = []
    wacc_range = [wacc - 0.010, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.010]
    g_range = [g_terminal - 0.010, g_terminal - 0.005, g_terminal,
               g_terminal + 0.005, g_terminal + 0.010]
    for w in wacc_range:
        row = []
        for g in g_range:
            if w - g < 0.005:
                row.append(None)
                continue
            # Re-discount với WACC mới
            pv_exp = 0
            f = fcff_ttm
            for t, gr in enumerate(growth_curve, 1):
                f = f * (1 + gr)
                pv_exp += f / (1 + w) ** t
            term = (f * (1 + g)) / (w - g)
            pv_term = term / (1 + w) ** forecast_years
            ev = pv_exp + pv_term
            ev_per_share = ((ev - net_debt - minority) * 1_000_000_000) / shares if shares > 0 else 0
            row.append({'fair_value': ev_per_share})
        sens_table.append(row)

    # Confidence
    confidence = 0.75
    if fcff_ttm <= 0:
        confidence -= 0.20
    if terminal_share > 0.80:
        confidence -= 0.10
    if g_initial > 0.20:
        confidence -= 0.10  # high growth assumption rủi ro
    if wacc_info['debt_to_equity'] > 2.0:
        confidence -= 0.10  # leverage cao → WACC kém tin cậy
    confidence = max(0.1, min(1.0, confidence))

    return ValuationResult(
        method="DCF FCFF",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            'fcff_ttm': fcff_ttm,
            'wacc': wacc,
            'g_initial': g_initial,
            'g_terminal': g_terminal,
            'forecast_years': forecast_years,
            'net_debt': net_debt,
            'minority_interest': minority,
        },
        key_outputs={
            'pv_explicit': pv_explicit,
            'pv_terminal': pv_terminal,
            'enterprise_value': enterprise_value,
            'terminal_share': terminal_share,
            'equity_value': equity_value,
            'fair_value': fair_value,
        },
        sensitivity={
            'wacc_range': wacc_range,
            'g_range': g_range,
            'table': sens_table,
        },
        warnings=warnings,
        notes=notes,
    )


# ============================================================================
# DDM (Dividend Discount Model)
# ============================================================================

def calculate_ddm(data: Dict[str, Any], forecast_years: int = 8) -> ValuationResult:
    """
    DDM 2-stage Gordon: dùng cho doanh nghiệp có dividend ổn định.

    Stage 1: dự phóng DPS tăng theo g_initial trong N năm
    Stage 2: terminal value theo Gordon Growth
    """
    ticker = data['ticker']
    market = data['market']
    ratios = data['ratios']
    per_share = data['per_share']
    growth = data['growth']
    warnings = []
    notes = []

    current_price = market['current_price']
    dps_ttm = per_share.get('dps_ttm', 0)

    # Nếu không có DPS, ước tính từ payout × EPS
    if dps_ttm <= 0:
        eps = per_share.get('eps_ttm', 0)
        payout = ratios.get('payout_ratio', 0.30)
        dps_ttm = eps * payout
        notes.append(f"DPS TTM ước tính = EPS ({eps:.0f}) × payout ({payout:.0%}) = {dps_ttm:.0f}")

    if dps_ttm <= 0:
        return ValuationResult(
            method="DDM",
            ticker=ticker,
            fair_value_per_share=0,
            current_price=current_price,
            upside_pct=-1.0,
            confidence=0.0,
            warnings=["DPS <= 0 → DDM không khả thi"],
        )

    # Cost of equity
    beta = market.get('beta_2y', 1.0)
    coe_info = calculate_cost_of_equity(beta)
    coe = coe_info['cost_of_equity']

    # Growth của dividend (thường thấp hơn earnings growth do payout ratio thay đổi)
    g_initial = growth.get('profit_growth_5y_cagr', 0.08) * 0.85  # dividend conservative hơn 15%
    g_initial = max(0.0, min(0.20, g_initial))
    g_terminal = MARKET_PARAMS['terminal_growth_default']

    if g_terminal >= coe - 0.01:
        g_terminal = coe - 0.020
        warnings.append(f"Terminal g ép xuống {g_terminal:.1%} (< CoE - 2%)")

    growth_curve = _build_fade_growth_curve(g_initial, g_terminal, forecast_years)
    notes.append(f"DPS growth fade: Y1={g_initial:.1%} → Y{forecast_years}={g_terminal:.1%}")
    notes.append(f"CoE = {coe:.1%} (β={beta:.2f})")

    # Stage 1: PV of explicit dividends
    pv_explicit = 0
    dps = dps_ttm
    for t, g in enumerate(growth_curve, 1):
        dps = dps * (1 + g)
        pv_explicit += dps / (1 + coe) ** t

    # Stage 2: Terminal
    last_dps = dps_ttm * math.prod([1 + g for g in growth_curve])
    terminal_dps = last_dps * (1 + g_terminal)
    terminal_value = terminal_dps / (coe - g_terminal)
    pv_terminal = terminal_value / (1 + coe) ** forecast_years

    fair_value = pv_explicit + pv_terminal
    upside = (fair_value - current_price) / current_price if current_price > 0 else 0

    # Sanity check
    extreme_factor = fair_value / current_price if current_price > 0 else 0
    if extreme_factor > 4.0:
        warnings.append(
            f"DDM fair value cao bất thường ({extreme_factor:.1f}× giá). Capped tại 3×."
        )
        fair_value = current_price * 3.0
        upside = (fair_value - current_price) / current_price
    elif extreme_factor < 0.25 and extreme_factor > 0:
        warnings.append(
            f"DDM fair value thấp bất thường ({extreme_factor:.2f}×). Floor tại 0.4×."
        )
        fair_value = current_price * 0.4
        upside = (fair_value - current_price) / current_price

    terminal_share = pv_terminal / fair_value if fair_value > 0 else 0
    if terminal_share > 0.85:
        warnings.append(f"Terminal value chiếm {terminal_share:.0%} (>85%) → kém ổn định")

    # Confidence
    confidence = 0.65  # DDM base lower than DCF (chỉ dùng được cho stable divider)
    if ratios.get('payout_ratio', 0) > 0.40:
        confidence += 0.10  # high payout → DDM phù hợp hơn
    if ratios.get('dividend_yield', 0) > 0.03:
        confidence += 0.05
    if growth.get('profit_growth_5y_cagr', 0) > 0.25:
        confidence -= 0.20  # high growth → DDM kém phù hợp (low payout)
    if terminal_share > 0.85:
        confidence -= 0.10
    confidence = max(0.1, min(1.0, confidence))

    return ValuationResult(
        method="DDM",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            'dps_ttm': dps_ttm,
            'cost_of_equity': coe,
            'g_initial': g_initial,
            'g_terminal': g_terminal,
            'payout_ratio': ratios.get('payout_ratio'),
        },
        key_outputs={
            'pv_explicit': pv_explicit,
            'pv_terminal': pv_terminal,
            'terminal_share': terminal_share,
            'fair_value': fair_value,
        },
        warnings=warnings,
        notes=notes,
    )
