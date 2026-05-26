"""
VALUATION ENGINE - ORCHESTRATOR CHÍNH
================================================================================
Đầu vào: ticker (mã cổ phiếu)
Đầu ra : ValuationReport tổng hợp đa phương pháp với recommendation

QUY TRÌNH:
  1. Load data (production: vnstock API; demo: sample_data)
  2. Phân loại ngành qua IndustryClassifier
  3. AI Recommendation Engine quyết định methods nào áp dụng + weights
  4. Run các methods → results
  5. Aggregate weighted fair value + verdict
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from .industry_classifier import (
    IndustryClassifier,
    ValuationIndustry,
    IndustryClassification,
)
from .normalizer import normalize_fundamentals
from .methods_pb_roe import calculate_pb_roe_valuation, ValuationResult
from .methods_pe import calculate_pe_valuation
from .methods_ev_ebitda import calculate_ev_ebitda_valuation
from .methods_dcf_ddm import calculate_dcf_fcff, calculate_ddm
from .methods_rnav_sotp import calculate_rnav_simplified, calculate_sotp_simplified


# ============================================================================
# INDUSTRY → METHODS MAPPING
# ============================================================================
INDUSTRY_METHOD_WEIGHTS: Dict[ValuationIndustry, Dict[str, float]] = {
    ValuationIndustry.BANKING: {
        "P/B-ROE Justified": 0.45,
        "P/E Multiple": 0.25,
        "DDM": 0.15,                  # banking thường có cổ tức ổn định
        "Historical Multiple": 0.15,
        # DCF FCFF: không áp dụng (không tách được capex)
        # EV/EBITDA: không áp dụng
    },
    ValuationIndustry.SECURITIES: {
        "P/B-ROE Justified": 0.50,
        "P/E Multiple": 0.35,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.INSURANCE: {
        "P/B-ROE Justified": 0.45,
        "P/E Multiple": 0.25,
        "DDM": 0.15,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.REAL_ESTATE: {
        "RNAV": 0.50,                 # Primary: RNAV (revalued asset)
        "P/B-ROE Justified": 0.20,
        "P/E Multiple": 0.10,
        "Historical Multiple": 0.20,
    },
    ValuationIndustry.CONSUMER_STAPLES: {
        "DCF FCFF": 0.30,             # ổn định → DCF rất tốt
        "P/E Multiple": 0.35,
        "EV/EBITDA": 0.20,
        "P/B-ROE Justified": 0.05,
        "Historical Multiple": 0.10,
    },
    ValuationIndustry.CONSUMER_DISCRETIONARY: {
        "P/E Multiple": 0.40,
        "DCF FCFF": 0.20,
        "EV/EBITDA": 0.25,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.STEEL_METALS: {
        "EV/EBITDA": 0.50,            # mid-cycle, primary
        "P/B-ROE Justified": 0.25,
        "P/E Multiple": 0.10,
        "Historical Multiple": 0.15,
        # DCF FCFF: không phù hợp (FCFF biến động mạnh theo cycle)
    },
    ValuationIndustry.CHEMICALS: {
        "EV/EBITDA": 0.45,
        "P/B-ROE Justified": 0.20,
        "P/E Multiple": 0.15,
        "Historical Multiple": 0.20,
    },
    ValuationIndustry.AGRICULTURE_LIVESTOCK: {
        "EV/EBITDA": 0.50,
        "P/B-ROE Justified": 0.25,
        "P/E Multiple": 0.10,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.UTILITIES: {
        "DCF FCFF": 0.35,             # dòng tiền ổn định nhất → DCF tối ưu
        "DDM": 0.25,                  # cổ tức cao đều
        "EV/EBITDA": 0.20,
        "P/E Multiple": 0.10,
        "Historical Multiple": 0.10,
    },
    ValuationIndustry.TECHNOLOGY: {
        "P/E Multiple": 0.40,
        "DCF FCFF": 0.25,             # FPT có FCFF tốt
        "EV/EBITDA": 0.20,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.LOGISTICS_TRANSPORT: {
        "EV/EBITDA": 0.40,
        "DCF FCFF": 0.20,
        "P/E Multiple": 0.20,
        "Historical Multiple": 0.20,
    },
    ValuationIndustry.DIVERSIFIED_HOLDING: {
        "SOTP Simplified": 0.30,      # Primary cho holding
        "P/E Multiple": 0.25,
        "EV/EBITDA": 0.20,
        "P/B-ROE Justified": 0.10,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.OIL_GAS: {
        "EV/EBITDA": 0.45,
        "P/B-ROE Justified": 0.25,
        "P/E Multiple": 0.10,
        "Historical Multiple": 0.20,
    },
    ValuationIndustry.HEALTHCARE: {
        "P/E Multiple": 0.40,
        "DCF FCFF": 0.25,
        "EV/EBITDA": 0.20,
        "Historical Multiple": 0.15,
    },
    ValuationIndustry.INDUSTRIAL_MANUFACTURING: {
        "P/E Multiple": 0.30,
        "EV/EBITDA": 0.30,
        "DCF FCFF": 0.15,
        "Historical Multiple": 0.25,
    },
    ValuationIndustry.CONSTRUCTION: {
        "P/E Multiple": 0.30,
        "EV/EBITDA": 0.25,
        "P/B-ROE Justified": 0.20,
        "Historical Multiple": 0.25,
    },
    ValuationIndustry.TELECOM: {
        "DCF FCFF": 0.30,
        "EV/EBITDA": 0.30,
        "P/E Multiple": 0.20,
        "DDM": 0.10,
        "Historical Multiple": 0.10,
    },
    ValuationIndustry.UNKNOWN: {
        "P/E Multiple": 0.40,
        "EV/EBITDA": 0.25,
        "P/B-ROE Justified": 0.25,
        "Historical Multiple": 0.10,
    },
}


@dataclass
class ValuationReport:
    """Báo cáo định giá tổng hợp."""
    ticker: str
    industry: IndustryClassification
    current_price: float
    fair_value: float
    fair_value_low: float
    fair_value_high: float
    upside_pct: float
    verdict: str                    # STRONG BUY / BUY / HOLD / SELL / STRONG SELL
    confidence: float
    methods_used: List[str]
    method_results: Dict[str, ValuationResult] = field(default_factory=dict)
    method_weights: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    recommendation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Chuyển thành dict JSON-serializable, tương thích web frontend pattern."""
        return {
            'ticker': self.ticker,
            'industry': self.industry.valuation_industry.value,
            'industry_source': self.industry.classification_source,
            'is_holding': self.industry.is_holding_company,
            'current_price': round(self.current_price, 0),
            'fair_value': round(self.fair_value, 0),
            'fair_value_low': round(self.fair_value_low, 0),
            'fair_value_high': round(self.fair_value_high, 0),
            'upside_pct': round(self.upside_pct * 100, 1),
            'verdict': self.verdict,
            'confidence': round(self.confidence * 100, 0),
            'methods_used': self.methods_used,
            'method_details': [
                {
                    'method': m,
                    'weight': round(self.method_weights[m] * 100, 0),
                    'fair_value': round(self.method_results[m].fair_value_per_share, 0),
                    'upside_pct': round(self.method_results[m].upside_pct * 100, 1),
                    'confidence': round(self.method_results[m].confidence * 100, 0),
                }
                for m in self.methods_used
            ],
            'warnings': list(dict.fromkeys(self.warnings))[:5],  # dedupe + cap
            'notes': self.recommendation_notes[:8],
        }


def _historical_multiple_valuation(data: Dict[str, Any]) -> ValuationResult:
    """Phương pháp đơn giản: định giá theo P/E và P/B historical median.
    Đây là 'sanity check' bổ sung cho các methods chính."""
    ticker = data["ticker"]
    market = data["market"]
    ratios = data["ratios"]
    per_share = data["per_share"]

    pe_median = ratios.get("pe_5y_median")
    pb_median = ratios.get("pb_5y_median")
    eps = per_share["eps_ttm"]
    bvps = per_share["bvps"]

    fair_pe = pe_median * eps if pe_median and eps > 0 else None
    fair_pb = pb_median * bvps if pb_median else None

    if fair_pe and fair_pb:
        fair_value = (fair_pe + fair_pb) / 2
        notes = [f"Hist P/E×EPS = {fair_pe:,.0f}", f"Hist P/B×BVPS = {fair_pb:,.0f}", "Trung bình hai"]
    elif fair_pb:
        fair_value = fair_pb
        notes = [f"Chỉ dùng P/B×BVPS = {fair_pb:,.0f}"]
    elif fair_pe:
        fair_value = fair_pe
        notes = [f"Chỉ dùng P/E×EPS = {fair_pe:,.0f}"]
    else:
        return ValuationResult(
            method="Historical Multiple",
            ticker=ticker,
            fair_value_per_share=0,
            current_price=market["current_price"],
            upside_pct=0,
            confidence=0.0,
            warnings=["Không có historical multiple data"],
        )

    return ValuationResult(
        method="Historical Multiple",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=market["current_price"],
        upside_pct=(fair_value - market["current_price"]) / market["current_price"],
        confidence=0.60,
        notes=notes,
    )


def _determine_verdict(upside_pct: float, confidence: float) -> str:
    """Chuyển upside + confidence thành verdict."""
    # Discount upside theo confidence
    effective_upside = upside_pct * (0.5 + 0.5 * confidence)

    if effective_upside > 0.25:
        return "STRONG BUY"
    elif effective_upside > 0.10:
        return "BUY"
    elif effective_upside > -0.10:
        return "HOLD"
    elif effective_upside > -0.25:
        return "SELL"
    else:
        return "STRONG SELL"


def value_ticker(ticker: str, raw_fundamentals: Optional[Dict] = None,
                 enrich_market_metrics: bool = True) -> Optional[ValuationReport]:
    """END-TO-END VALUATION cho 1 ticker.

    Args:
        ticker: Mã cổ phiếu (e.g., 'VIB', 'PAN', 'DBC')
        raw_fundamentals: Output từ financial_fetcher.fetch_fundamentals().
                          Nếu None, sẽ tự fetch (cần network + API key).
        enrich_market_metrics: Nếu True, tính beta + historical multiples từ
                               OHLCV cache. Set False trong unit test khi không
                               có cache.

    Returns:
        ValuationReport tổng hợp, hoặc None nếu không đủ data.
    """
    # === 1. Load data ===
    if raw_fundamentals is None:
        # Lazy import để tránh circular dependency
        from ...financial_fetcher import fetch_fundamentals
        raw_fundamentals = fetch_fundamentals(ticker, period='year')
        if raw_fundamentals is None:
            return None

    # === 1.5. Enrich với beta thực + historical multiples từ OHLCV cache ===
    if enrich_market_metrics:
        try:
            from ...market_metrics import enrich_with_market_metrics
            raw_fundamentals = enrich_with_market_metrics(ticker, raw_fundamentals)
        except Exception as e:
            # Không fatal — vẫn có thể chạy với fallback
            import logging
            logging.getLogger(__name__).debug(
                f"  {ticker} market_metrics enrich failed: {e} (using fallback)"
            )

    # Normalize raw vnstock data thành format engine cần
    data = normalize_fundamentals(raw_fundamentals)
    if data is None:
        return None

    overview = data.get("overview", {})

    # === 2. Classify industry ===
    classifier = IndustryClassifier()
    classification = classifier.classify(ticker, overview)

    # Inject industry vào data để peer DB lookup hoạt động trong methods
    data['_industry'] = classification.valuation_industry.value

    # === 3. Pick methods ===
    method_weights = INDUSTRY_METHOD_WEIGHTS.get(
        classification.valuation_industry,
        INDUSTRY_METHOD_WEIGHTS[ValuationIndustry.UNKNOWN]
    )
    methods_to_run = [m for m, w in method_weights.items() if w > 0]

    # === 4. Determine if cyclical ===
    is_cyclical = classification.valuation_industry in [
        ValuationIndustry.STEEL_METALS,
        ValuationIndustry.CHEMICALS,
        ValuationIndustry.AGRICULTURE_LIVESTOCK,
        ValuationIndustry.OIL_GAS,
    ] or data.get("cyclical_info", {}).get("is_cyclical", False)

    # === 5. Run methods ===
    results: Dict[str, ValuationResult] = {}
    rec_notes: List[str] = []

    rec_notes.append(
        f"Ngành định giá: {classification.valuation_industry.value} "
        f"(nguồn: {classification.classification_source}, "
        f"confidence: {classification.confidence:.0%})"
    )
    if is_cyclical:
        rec_notes.append("Phát hiện CYCLICAL business → áp dụng mid-cycle adjustment")
    if classification.is_holding_company:
        rec_notes.append("HOLDING COMPANY → khuyến nghị Sum-of-the-Parts (chưa implement đầy đủ)")

    method_runners = {
        "P/B-ROE Justified": lambda d: calculate_pb_roe_valuation(d),
        "P/E Multiple": lambda d: calculate_pe_valuation(d),
        "EV/EBITDA": lambda d: calculate_ev_ebitda_valuation(d, is_cyclical=is_cyclical),
        "DCF FCFF": lambda d: calculate_dcf_fcff(d),
        "DDM": lambda d: calculate_ddm(d),
        "RNAV": lambda d: calculate_rnav_simplified(d),
        "SOTP Simplified": lambda d: calculate_sotp_simplified(d),
        "Historical Multiple": lambda d: _historical_multiple_valuation(d),
    }

    for method_name in methods_to_run:
        try:
            runner = method_runners.get(method_name)
            if runner:
                results[method_name] = runner(data)
                rec_notes.append(
                    f"✓ {method_name}: fair={results[method_name].fair_value_per_share:,.0f}, "
                    f"conf={results[method_name].confidence:.0%}"
                )
        except Exception as e:
            rec_notes.append(f"✗ {method_name} failed: {e}")

    # === 6. Aggregate ===
    weighted_sum = 0
    total_effective_weight = 0
    all_fair_values = []
    used_methods = []

    for method_name, result in results.items():
        if result.fair_value_per_share <= 0 or result.confidence < 0.15:
            continue  # Skip không tin cậy
        base_weight = method_weights[method_name]
        # Adjust weight bởi confidence của method này
        effective_weight = base_weight * result.confidence
        weighted_sum += result.fair_value_per_share * effective_weight
        total_effective_weight += effective_weight
        all_fair_values.append(result.fair_value_per_share)
        used_methods.append(method_name)

    if total_effective_weight == 0:
        # Fallback: trung bình đơn thuần các fair values > 0
        valid_fvs = [r.fair_value_per_share for r in results.values() if r.fair_value_per_share > 0]
        fair_value = sum(valid_fvs) / len(valid_fvs) if valid_fvs else data["market"]["current_price"]
        overall_confidence = 0.20
    else:
        fair_value = weighted_sum / total_effective_weight
        overall_confidence = total_effective_weight / sum(method_weights[m] for m in used_methods)

    # Adjust confidence theo industry classification confidence
    overall_confidence *= classification.confidence

    # Bands: dùng phân vị 25/75 nếu có nhiều methods
    if len(all_fair_values) >= 3:
        sorted_fvs = sorted(all_fair_values)
        n = len(sorted_fvs)
        fv_low = sorted_fvs[max(0, n // 4)]
        fv_high = sorted_fvs[min(n - 1, 3 * n // 4)]
    else:
        fv_low = min(all_fair_values) if all_fair_values else fair_value * 0.85
        fv_high = max(all_fair_values) if all_fair_values else fair_value * 1.15

    # Đảm bảo low ≤ fair ≤ high (có thể lệch khi confidence chênh lệch lớn)
    fv_low = min(fv_low, fair_value)
    fv_high = max(fv_high, fair_value)

    current_price = data["market"]["current_price"]
    upside = (fair_value - current_price) / current_price
    verdict = _determine_verdict(upside, overall_confidence)

    # Collect warnings
    all_warnings = []
    for r in results.values():
        all_warnings.extend(r.warnings)

    return ValuationReport(
        ticker=ticker,
        industry=classification,
        current_price=current_price,
        fair_value=fair_value,
        fair_value_low=fv_low,
        fair_value_high=fv_high,
        upside_pct=upside,
        verdict=verdict,
        confidence=overall_confidence,
        methods_used=used_methods,
        method_results=results,
        method_weights={m: method_weights[m] for m in used_methods},
        warnings=all_warnings,
        recommendation_notes=rec_notes,
    )


def print_report(report: ValuationReport) -> None:
    """In báo cáo định giá ra console với format đẹp."""
    print("\n" + "=" * 78)
    print(f"  BÁO CÁO ĐỊNH GIÁ CỔ PHIẾU: {report.ticker}")
    print("=" * 78)

    print(f"\n  📊 PHÂN LOẠI NGÀNH")
    print(f"     Ngành định giá   : {report.industry.valuation_industry.value}")
    print(f"     Nguồn phân loại  : {report.industry.classification_source}")
    print(f"     Holding company  : {'Có' if report.industry.is_holding_company else 'Không'}")

    print(f"\n  💰 KẾT QUẢ ĐỊNH GIÁ TỔNG HỢP")
    print(f"     Giá hiện tại     : {report.current_price:>12,.0f} VND/cp")
    print(f"     Fair value       : {report.fair_value:>12,.0f} VND/cp")
    print(f"     Khoảng tin cậy   : {report.fair_value_low:>12,.0f} - {report.fair_value_high:,.0f} VND/cp")
    print(f"     Upside           : {report.upside_pct:>12.1%}")
    print(f"     Verdict          : {report.verdict:>12}")
    print(f"     Confidence       : {report.confidence:>12.0%}")

    print(f"\n  🔬 CHI TIẾT TỪNG PHƯƠNG PHÁP")
    print(f"     {'Method':<28} {'Weight':>7} {'Fair Value':>12} {'Upside':>8} {'Conf':>6}")
    print(f"     {'-' * 28} {'-' * 7} {'-' * 12} {'-' * 8} {'-' * 6}")
    for method_name in report.methods_used:
        result = report.method_results[method_name]
        weight = report.method_weights[method_name]
        print(
            f"     {method_name:<28} {weight:>6.0%}  "
            f"{result.fair_value_per_share:>12,.0f} "
            f"{result.upside_pct:>7.1%} "
            f"{result.confidence:>5.0%}"
        )

    if report.recommendation_notes:
        print(f"\n  📝 GHI CHÚ HỆ THỐNG")
        for note in report.recommendation_notes:
            print(f"     • {note}")

    if report.warnings:
        unique_warnings = list(dict.fromkeys(report.warnings))  # dedupe preserving order
        print(f"\n  ⚠️  CẢNH BÁO ({len(unique_warnings)})")
        for w in unique_warnings[:5]:  # max 5
            print(f"     • {w}")

    print("\n" + "=" * 78 + "\n")


