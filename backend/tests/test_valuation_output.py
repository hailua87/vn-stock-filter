"""
Đầu ra định giá sau lượt Weekly Valuation 2026-09-21 (run 35606414672):

  1. `methods_conflict` lẫn kiểu: 17 chuỗi "True", 12 chuỗi "False", 7 bool.
     numpy.bool_ qua json.dump(default=str) thành chuỗi, nên bước kiểm tra
     của workflow đếm "False" là có mâu thuẫn và báo 29/36 thay vì 17/36.
  2. Kết luận có hướng dựa trên MỘT phương pháp (CNA −80%, CII, PVD chỉ có
     EV/EBITDA): độ phân tán = 0 nên không phát hiện được mâu thuẫn.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from scanner.strategies.valuation import engine
from scanner.strategies.valuation.industry_classifier import ValuationIndustry
from test_valuation_quality_fixes import _value, no_dispersion  # noqa: F401 (fixture)


# --- 1. methods_conflict luôn là bool trong JSON ---------------------------

@pytest.mark.parametrize('price', [30_000.0, 66_400.0, 200_000.0])
def test_methods_conflict_is_json_bool(price):
    r = _value('FPT', 'Technology', price, 1_714_326_422)
    # Đúng cách run_valuation.py ghi latest.json
    out = json.loads(json.dumps(r.to_dict(), ensure_ascii=False, default=str))
    assert isinstance(out['methods_conflict'], bool)
    assert out['methods_conflict'] == (r.method_dispersion > engine.MAX_METHOD_DISPERSION)


# --- 2. Không kết luận có hướng khi chỉ có một phương pháp ------------------

@pytest.mark.parametrize('verdict,industry,n,expected,warn', [
    ('STRONG SELL', ValuationIndustry.AGRICULTURE_LIVESTOCK, 1, 'HOLD', '1 phương pháp'),  # CNA
    ('SELL', ValuationIndustry.OIL_GAS, 1, 'HOLD', '1 phương pháp'),                        # PVD
    ('STRONG BUY', ValuationIndustry.CHEMICALS, 3, 'STRONG BUY', None),                     # DCM
    ('SELL', ValuationIndustry.CONSUMER_DISCRETIONARY, 2, 'SELL', None),                    # BCV
    ('STRONG SELL', ValuationIndustry.BANKING, 3, 'HOLD', 'NPL/CAR'),
    ('HOLD', ValuationIndustry.OIL_GAS, 1, 'HOLD', None),
])
def test_publish_guard(verdict, industry, n, expected, warn):
    v, w = engine._publish_guard(verdict, industry, n)
    assert v == expected
    assert (w is None) if warn is None else (warn in w and verdict in w)


def test_single_method_end_to_end(monkeypatch, no_dispersion):
    """FPT giá thấp, chỉ cho phép P/E Multiple → mô hình mua nhưng công bố HOLD."""
    weights = dict(engine.INDUSTRY_METHOD_WEIGHTS)
    weights[ValuationIndustry.TECHNOLOGY] = {'P/E Multiple': 1.0}
    monkeypatch.setattr(engine, 'INDUSTRY_METHOD_WEIGHTS', weights)

    r = _value('FPT', 'Technology', 30_000.0, 1_714_326_422)
    assert r.methods_used == ['P/E Multiple']
    assert r.upside_pct > 0.3
    assert r.verdict == 'HOLD'
    assert 'Chỉ có 1 phương pháp' in r.warnings[0]
