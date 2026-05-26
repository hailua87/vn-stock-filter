"""
Valuation module — multi-method stock valuation cho VN market.

Phương pháp tích hợp:
  - Industry Classifier (4-tier priority)
  - P/B-ROE Justified (2-stage growth) cho banking
  - P/E Multiple (3-approach blend) cho consumer/tech
  - EV/EBITDA (mid-cycle) cho cyclicals
  - Historical Multiple fallback

Entry point:
  from scanner.strategies.valuation import value_ticker
  report = value_ticker('VIB', fundamentals_dict)
"""
from .engine import value_ticker, ValuationReport
from .industry_classifier import (
    IndustryClassifier,
    ValuationIndustry,
    classify_ticker,
)

__all__ = [
    'value_ticker',
    'ValuationReport',
    'IndustryClassifier',
    'ValuationIndustry',
    'classify_ticker',
]
