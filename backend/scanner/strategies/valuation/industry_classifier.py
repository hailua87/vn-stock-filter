"""
INDUSTRY CLASSIFIER - PHÂN LOẠI NGÀNH CHO CỔ PHIẾU VIỆT NAM
================================================================================
Phân loại cổ phiếu vào các nhóm ngành đặc thù để áp dụng phương pháp định giá
phù hợp. Dùng kết hợp:
  1. ICB Code từ vnstock (industry, sector từ company.overview())
  2. Business characteristics (cấu trúc tài sản, dòng tiền)
  3. Override manual cho các trường hợp đặc biệt (holding, multi-business)

Output: VALUATION_INDUSTRY - mapping vào INDUSTRY_VALUATION_MAP
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List


class ValuationIndustry(str, Enum):
    """Các nhóm ngành dùng cho định giá (khác với phân ngành chính thức ICB).
    Mỗi nhóm có bộ phương pháp định giá riêng phù hợp đặc thù kinh doanh."""
    BANKING = "Banking"
    INSURANCE = "Insurance"
    SECURITIES = "Securities"
    REAL_ESTATE = "Real_Estate"
    CONSTRUCTION = "Construction"
    CONSUMER_STAPLES = "Consumer_Staples"  # Thực phẩm, đồ uống thiết yếu
    CONSUMER_DISCRETIONARY = "Consumer_Discretionary"  # Bán lẻ, du lịch
    INDUSTRIAL_MANUFACTURING = "Industrial_Manufacturing"
    STEEL_METALS = "Steel_Metals"
    CHEMICALS = "Chemicals"
    OIL_GAS = "Oil_Gas"
    UTILITIES = "Utilities"  # Điện, nước, gas
    TECHNOLOGY = "Technology"
    TELECOM = "Telecom"
    LOGISTICS_TRANSPORT = "Logistics_Transport"
    HEALTHCARE = "Healthcare"
    AGRICULTURE_LIVESTOCK = "Agriculture_Livestock"
    DIVERSIFIED_HOLDING = "Diversified_Holding"  # Tập đoàn đa ngành
    UNKNOWN = "Unknown"


# ICB Code mapping từ vnstock industry name -> ValuationIndustry
# Dựa trên ICB classification mà VCI/TCBS sử dụng
ICB_TO_VALUATION = {
    # Banks
    "Ngân hàng": ValuationIndustry.BANKING,
    "Banks": ValuationIndustry.BANKING,
    "Banking": ValuationIndustry.BANKING,

    # Insurance
    "Bảo hiểm": ValuationIndustry.INSURANCE,
    "Insurance": ValuationIndustry.INSURANCE,
    "Bảo hiểm phi nhân thọ": ValuationIndustry.INSURANCE,
    "Bảo hiểm nhân thọ": ValuationIndustry.INSURANCE,

    # Securities
    "Dịch vụ tài chính": ValuationIndustry.SECURITIES,
    "Chứng khoán": ValuationIndustry.SECURITIES,
    "Financial Services": ValuationIndustry.SECURITIES,

    # Real Estate
    "Bất động sản": ValuationIndustry.REAL_ESTATE,
    "Real Estate": ValuationIndustry.REAL_ESTATE,

    # Construction
    "Xây dựng và Vật liệu": ValuationIndustry.CONSTRUCTION,
    "Construction & Materials": ValuationIndustry.CONSTRUCTION,
    "Xây dựng": ValuationIndustry.CONSTRUCTION,

    # Consumer Staples
    "Thực phẩm và đồ uống": ValuationIndustry.CONSUMER_STAPLES,
    "Food & Beverage": ValuationIndustry.CONSUMER_STAPLES,
    "Hàng cá nhân và Gia dụng": ValuationIndustry.CONSUMER_STAPLES,
    "Personal & Household Goods": ValuationIndustry.CONSUMER_STAPLES,

    # Consumer Discretionary
    "Bán lẻ": ValuationIndustry.CONSUMER_DISCRETIONARY,
    "Retail": ValuationIndustry.CONSUMER_DISCRETIONARY,
    "Du lịch và Giải trí": ValuationIndustry.CONSUMER_DISCRETIONARY,
    "Travel & Leisure": ValuationIndustry.CONSUMER_DISCRETIONARY,

    # Steel/Metals
    "Tài nguyên Cơ bản": ValuationIndustry.STEEL_METALS,
    "Basic Resources": ValuationIndustry.STEEL_METALS,

    # Chemicals
    "Hóa chất": ValuationIndustry.CHEMICALS,
    "Chemicals": ValuationIndustry.CHEMICALS,

    # Oil & Gas
    "Dầu khí": ValuationIndustry.OIL_GAS,
    "Oil & Gas": ValuationIndustry.OIL_GAS,

    # Utilities
    "Điện, nước & xăng dầu khí đốt": ValuationIndustry.UTILITIES,
    "Utilities": ValuationIndustry.UTILITIES,
    "Tiện ích cộng đồng": ValuationIndustry.UTILITIES,

    # Technology
    "Công nghệ Thông tin": ValuationIndustry.TECHNOLOGY,
    "Technology": ValuationIndustry.TECHNOLOGY,

    # Telecom
    "Viễn thông": ValuationIndustry.TELECOM,
    "Telecommunications": ValuationIndustry.TELECOM,

    # Industrials
    "Hàng & Dịch vụ Công nghiệp": ValuationIndustry.INDUSTRIAL_MANUFACTURING,
    "Industrial Goods & Services": ValuationIndustry.INDUSTRIAL_MANUFACTURING,

    # Healthcare
    "Y tế": ValuationIndustry.HEALTHCARE,
    "Health Care": ValuationIndustry.HEALTHCARE,
    "Dược phẩm và Y tế": ValuationIndustry.HEALTHCARE,
}


# Sector-level override (ICB Level 3-4) cho các trường hợp cần phân loại chi tiết hơn
SECTOR_OVERRIDE = {
    # Trong "Industrial Goods & Services" có thể là logistics
    "Vận tải biển": ValuationIndustry.LOGISTICS_TRANSPORT,
    "Vận tải hàng không": ValuationIndustry.LOGISTICS_TRANSPORT,
    "Vận tải đường bộ": ValuationIndustry.LOGISTICS_TRANSPORT,
    "Dịch vụ vận tải": ValuationIndustry.LOGISTICS_TRANSPORT,
    "Marine Transportation": ValuationIndustry.LOGISTICS_TRANSPORT,
    "Industrial Transportation": ValuationIndustry.LOGISTICS_TRANSPORT,

    # Trong "Food & Beverage" có thể là nông nghiệp/chăn nuôi
    "Nông nghiệp": ValuationIndustry.AGRICULTURE_LIVESTOCK,
    "Chăn nuôi": ValuationIndustry.AGRICULTURE_LIVESTOCK,
    "Sản xuất Thực phẩm": ValuationIndustry.AGRICULTURE_LIVESTOCK,  # cho DBC, BAF, HAG
    "Farming & Fishing": ValuationIndustry.AGRICULTURE_LIVESTOCK,

    # Steel cụ thể
    "Sắt thép": ValuationIndustry.STEEL_METALS,
    "Iron & Steel": ValuationIndustry.STEEL_METALS,
}


# Manual ticker override cho các mã đặc thù không thể tự phân loại
# Lý do: holding company, business mix phức tạp, hoặc ICB code chưa chính xác
TICKER_OVERRIDE = {
    # Diversified holdings - cần định giá theo Sum-of-the-Parts
    "MSN": ValuationIndustry.DIVERSIFIED_HOLDING,  # Masan: tiêu dùng + tài nguyên + bank
    "PAN": ValuationIndustry.DIVERSIFIED_HOLDING,  # PAN Group: nông sản + thủy sản + bánh kẹo
    "REE": ValuationIndustry.DIVERSIFIED_HOLDING,  # cơ điện + BĐS + điện
    "GEX": ValuationIndustry.DIVERSIFIED_HOLDING,
    "VIC": ValuationIndustry.DIVERSIFIED_HOLDING,  # BĐS + ô tô + công nghệ

    # Special cases
    "FPT": ValuationIndustry.TECHNOLOGY,  # đôi khi ICB ghi là "Telecom"
    "HPG": ValuationIndustry.STEEL_METALS,  # rõ ràng là thép, không phải Basic Resources chung

    # Chăn nuôi cần override vì ICB hay xếp vào Food
    "DBC": ValuationIndustry.AGRICULTURE_LIVESTOCK,
    "BAF": ValuationIndustry.AGRICULTURE_LIVESTOCK,
    "HAG": ValuationIndustry.AGRICULTURE_LIVESTOCK,

    # Logistics
    "GMD": ValuationIndustry.LOGISTICS_TRANSPORT,
    "VSC": ValuationIndustry.LOGISTICS_TRANSPORT,
    "HAH": ValuationIndustry.LOGISTICS_TRANSPORT,
    "PHP": ValuationIndustry.LOGISTICS_TRANSPORT,
}


@dataclass
class IndustryClassification:
    """Kết quả phân loại ngành cho một mã cổ phiếu."""
    ticker: str
    valuation_industry: ValuationIndustry
    icb_industry: Optional[str] = None
    icb_sector: Optional[str] = None
    confidence: float = 1.0  # 0-1, độ tin cậy phân loại
    classification_source: str = ""  # "ticker_override" | "sector_override" | "icb_mapping" | "heuristic"
    is_holding_company: bool = False
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


class IndustryClassifier:
    """Phân loại ngành cổ phiếu Việt Nam cho mục đích định giá.

    Quy trình (priority cao → thấp):
      1. Manual ticker override (cho các mã đặc biệt)
      2. ICB Sector override (chi tiết hơn ICB Industry)
      3. ICB Industry mapping (phân loại chính)
      4. Heuristic dựa trên cấu trúc tài chính (fallback)
    """

    def classify(self, ticker: str, overview_data: Optional[Dict] = None,
                 financial_data: Optional[Dict] = None) -> IndustryClassification:
        """Phân loại ngành cho 1 ticker.

        Args:
            ticker: Mã cổ phiếu (e.g. 'VIB', 'PAN', 'DBC')
            overview_data: Dict từ vnstock company.overview() chứa các field:
                - industry: ICB Industry name (level 1-2)
                - sector / icb_name3 / icb_name4: ICB Sector (level 3-4)
                - subsector: chi tiết hơn nữa
            financial_data: Optional, dùng cho heuristic classification khi
                ICB không khả dụng (e.g. mã mới niêm yết)
        """
        ticker = ticker.upper().strip()
        notes = []

        # === Step 1: Manual ticker override ===
        if ticker in TICKER_OVERRIDE:
            industry = TICKER_OVERRIDE[ticker]
            notes.append(f"Áp dụng ticker override: {ticker} → {industry.value}")
            return IndustryClassification(
                ticker=ticker,
                valuation_industry=industry,
                icb_industry=overview_data.get("industry") if overview_data else None,
                confidence=1.0,
                classification_source="ticker_override",
                is_holding_company=(industry == ValuationIndustry.DIVERSIFIED_HOLDING),
                notes=notes,
            )

        if not overview_data:
            notes.append("Không có ICB data → fallback heuristic")
            return self._heuristic_classify(ticker, financial_data, notes)

        icb_industry = overview_data.get("industry") or overview_data.get("icb_name2")
        icb_sector = (overview_data.get("sector")
                      or overview_data.get("icb_name3")
                      or overview_data.get("icb_name4"))

        # === Step 2: Sector-level override (chi tiết hơn industry) ===
        if icb_sector and icb_sector in SECTOR_OVERRIDE:
            industry = SECTOR_OVERRIDE[icb_sector]
            notes.append(f"Áp dụng sector override: '{icb_sector}' → {industry.value}")
            return IndustryClassification(
                ticker=ticker,
                valuation_industry=industry,
                icb_industry=icb_industry,
                icb_sector=icb_sector,
                confidence=0.95,
                classification_source="sector_override",
                notes=notes,
            )

        # === Step 3: ICB Industry mapping ===
        if icb_industry and icb_industry in ICB_TO_VALUATION:
            industry = ICB_TO_VALUATION[icb_industry]
            notes.append(f"ICB mapping: '{icb_industry}' → {industry.value}")
            return IndustryClassification(
                ticker=ticker,
                valuation_industry=industry,
                icb_industry=icb_industry,
                icb_sector=icb_sector,
                confidence=0.85,
                classification_source="icb_mapping",
                notes=notes,
            )

        # === Step 4: Heuristic fallback ===
        notes.append(f"Không match ICB ('{icb_industry}') → heuristic")
        return self._heuristic_classify(ticker, financial_data, notes)

    def _heuristic_classify(self, ticker: str, financial_data: Optional[Dict],
                            notes: List[str]) -> IndustryClassification:
        """Phân loại dựa trên cấu trúc tài chính khi không có ICB code.

        Logic:
          - Nếu interest_income/total_revenue > 50% → Banking
          - Nếu investment_property + RE_inventory / total_assets > 40% → Real Estate
          - Nếu fixed_assets / total_assets > 50% → Manufacturing/Utilities
          - Còn lại → Unknown
        """
        if not financial_data:
            return IndustryClassification(
                ticker=ticker,
                valuation_industry=ValuationIndustry.UNKNOWN,
                confidence=0.0,
                classification_source="heuristic_no_data",
                notes=notes + ["Không đủ data để phân loại"],
            )

        total_assets = financial_data.get("total_assets", 0)
        total_revenue = financial_data.get("total_revenue", 0)
        interest_income = financial_data.get("interest_income", 0)
        fixed_assets = financial_data.get("fixed_assets", 0)
        re_inventory = financial_data.get("real_estate_inventory", 0)
        investment_property = financial_data.get("investment_property", 0)

        # Banking signal: interest income dominate
        if total_revenue > 0 and interest_income / total_revenue > 0.5:
            notes.append("Heuristic: interest income > 50% revenue → Banking")
            return IndustryClassification(
                ticker=ticker,
                valuation_industry=ValuationIndustry.BANKING,
                confidence=0.7,
                classification_source="heuristic",
                notes=notes,
            )

        # Real estate signal
        if total_assets > 0:
            re_ratio = (re_inventory + investment_property) / total_assets
            if re_ratio > 0.4:
                notes.append(f"Heuristic: RE assets {re_ratio:.0%} > 40% → Real Estate")
                return IndustryClassification(
                    ticker=ticker,
                    valuation_industry=ValuationIndustry.REAL_ESTATE,
                    confidence=0.7,
                    classification_source="heuristic",
                    notes=notes,
                )

            # Manufacturing/utilities signal
            if fixed_assets / total_assets > 0.5:
                notes.append(f"Heuristic: fixed assets {fixed_assets/total_assets:.0%} > 50% → Manufacturing")
                return IndustryClassification(
                    ticker=ticker,
                    valuation_industry=ValuationIndustry.INDUSTRIAL_MANUFACTURING,
                    confidence=0.6,
                    classification_source="heuristic",
                    notes=notes,
                )

        return IndustryClassification(
            ticker=ticker,
            valuation_industry=ValuationIndustry.UNKNOWN,
            confidence=0.0,
            classification_source="heuristic_failed",
            notes=notes + ["Heuristic không xác định được"],
        )


# Convenience function
def classify_ticker(ticker: str, overview_data: Optional[Dict] = None,
                    financial_data: Optional[Dict] = None) -> IndustryClassification:
    """Shortcut để phân loại nhanh 1 ticker."""
    return IndustryClassifier().classify(ticker, overview_data, financial_data)


if __name__ == "__main__":
    # Test với 3 case study
    print("=" * 70)
    print("INDUSTRY CLASSIFIER - TEST CASES")
    print("=" * 70)

    test_cases = [
        # VIB: Ngân hàng, ICB chuẩn
        ("VIB", {"industry": "Ngân hàng", "sector": "Ngân hàng"}, None),

        # PAN: Tập đoàn đa ngành → cần ticker override
        ("PAN", {"industry": "Thực phẩm và đồ uống", "sector": "Sản xuất Thực phẩm"}, None),

        # DBC: Chăn nuôi heo - ICB ghi là Food → cần sector override
        ("DBC", {"industry": "Thực phẩm và đồ uống", "sector": "Sản xuất Thực phẩm"}, None),

        # Edge case: ticker mới, không có ICB
        ("XYZ", None, {
            "total_assets": 100_000,
            "total_revenue": 50_000,
            "interest_income": 30_000,  # 60% revenue
        }),
    ]

    for ticker, overview, finance in test_cases:
        result = classify_ticker(ticker, overview, finance)
        print(f"\n📊 {ticker}:")
        print(f"   Industry        : {result.valuation_industry.value}")
        print(f"   Source          : {result.classification_source}")
        print(f"   Confidence      : {result.confidence:.0%}")
        print(f"   Holding company : {result.is_holding_company}")
        print(f"   Notes:")
        for note in result.notes:
            print(f"     • {note}")
