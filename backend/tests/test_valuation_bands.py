"""
Mức định giá công bố (blueprint §9, §16) thay cho nhãn mua/bán của engine.

  C. run_valuation gắn `valuation_band` (Hấp dẫn / Hợp lý / Đắt / Chưa có) cho
     từng mã và đếm theo mức; web chỉ hiển thị mức này.
  D. Giới hạn độ tin cậy cho phương pháp giản lược: engine đặt tên SOTP là
     'SOTP Simplified' nhưng cấu hình chỉ có 'SOTP' → giới hạn không bao giờ
     áp cho holding (VIC, REE, MSN, GEX).
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from run_valuation import signals_with_bands
from scanner.quality.status import valuation_band
from test_valuation_quality_fixes import _value, no_dispersion  # noqa: F401 (fixture)


def _sig(upside, conf, methods, conflict=False):
    return {'upside_pct': upside, 'confidence': conf, 'methods_conflict': conflict,
            'method_details': [{'method': m, 'weight': w} for m, w in methods]}


# --- D. phương pháp giản lược ------------------------------------------------

def test_sotp_simplified_primary_is_capped():
    # REE 21/09: SOTP Simplified trọng số lớn nhất. Upside +25%, conf 60 lẽ ra
    # thành "Hấp dẫn" nếu không giới hạn.
    b = valuation_band(_sig(25.0, 60.0, [('SOTP Simplified', 30), ('P/E Multiple', 20)]))
    assert b['band'] == 'NOT_AVAILABLE'
    assert 'giản lược' in b['reason']


def test_simplified_method_not_primary_is_not_capped():
    b = valuation_band(_sig(25.0, 60.0, [('P/E Multiple', 40), ('SOTP Simplified', 30)]))
    assert b['band'] == 'ATTRACTIVE'


# --- C. gắn mức vào đầu ra ---------------------------------------------------

def test_signals_with_bands_through_real_engine(no_dispersion):
    reports = [
        _value('FPT', 'Technology', 30_000.0, 1_714_326_422),   # rẻ so với fair value
        _value('FPT', 'Technology', 200_000.0, 1_714_326_422),  # đắt
    ]
    signals, counts = signals_with_bands(reports)
    # Ghi JSON đúng như run_valuation rồi đọc lại
    signals = json.loads(json.dumps(signals, ensure_ascii=False, default=str))

    bands = [s['valuation_band'] for s in signals]
    assert [b['band'] for b in bands] == ['ATTRACTIVE', 'EXPENSIVE']
    assert [b['label'] for b in bands] == ['Hấp dẫn', 'Đắt']
    assert counts == {'ATTRACTIVE': 1, 'EXPENSIVE': 1}
    # Upside trong band khớp upside của chính mã đó (cùng một nguồn số)
    assert all(b['upside_pct'] == s['upside_pct'] for b, s in zip(bands, signals))
    # verdict vẫn còn cho backtest.py
    assert all('verdict' in s for s in signals)


def test_low_confidence_signal_is_not_available(no_dispersion, monkeypatch):
    from scanner.strategies.valuation import engine
    r = _value('FPT', 'Technology', 30_000.0, 1_714_326_422)
    monkeypatch.setattr(r, 'confidence', 0.40)
    (sig,), counts = signals_with_bands([r])
    assert sig['valuation_band']['band'] == 'NOT_AVAILABLE'
    assert counts == {'NOT_AVAILABLE': 1}


# --- Web không còn hiển thị nhãn mua/bán ------------------------------------

WEB = Path(__file__).resolve().parents[2] / 'web' / 'valuation'


@pytest.mark.parametrize('name', ['index.html', 'valuation.js'])
def test_web_valuation_has_no_buy_sell_labels(name):
    text = (WEB / name).read_text(encoding='utf-8')
    for label in ('STRONG BUY', 'STRONG SELL', "'BUY'", "'SELL'", '>BUY<', '>SELL<', '>HOLD<'):
        assert label not in text, f'{name} còn nhãn {label}'


def test_web_reads_valuation_band():
    js = (WEB / 'valuation.js').read_text(encoding='utf-8')
    assert 'valuation_band' in js and 'band_counts' in js


# --- Mức định giá tôn trọng cờ hạ HOLD của engine ----------------------------

def test_bank_with_guard_is_not_attractive(no_dispersion):
    """TPB, MSB 21/09: ngân hàng upside +98%/+69%, conf 60 → từng hiện "Hấp dẫn"."""
    r = _value('VCB', 'Banks', 20_000.0, 8_355_675_094)
    (sig,), counts = signals_with_bands([r])
    assert sig['verdict'] == 'HOLD' and sig['upside_pct'] > 50
    assert sig['valuation_band']['band'] == 'NOT_AVAILABLE'
    assert 'NPL/CAR' in sig['valuation_band']['reason']


def test_single_method_is_not_available(no_dispersion, monkeypatch):
    from scanner.strategies.valuation import engine
    from scanner.strategies.valuation.industry_classifier import ValuationIndustry
    weights = dict(engine.INDUSTRY_METHOD_WEIGHTS)
    weights[ValuationIndustry.TECHNOLOGY] = {'P/E Multiple': 1.0}
    monkeypatch.setattr(engine, 'INDUSTRY_METHOD_WEIGHTS', weights)
    r = _value('FPT', 'Technology', 30_000.0, 1_714_326_422)
    (sig,), _ = signals_with_bands([r])
    assert sig['valuation_band']['band'] == 'NOT_AVAILABLE'
    assert '1 phương pháp' in sig['valuation_band']['reason']


def test_guard_reason_absent_for_normal_signal(no_dispersion):
    (sig,), _ = signals_with_bands([_value('FPT', 'Technology', 30_000.0, 1_714_326_422)])
    assert sig['guard_reason'] is None and sig['valuation_band']['band'] == 'ATTRACTIVE'


def test_bank_with_model_hold_is_still_not_available():
    """VCB 22/09: upside −3,8% → mô hình tự ra HOLD, từng nhận nhãn "Hợp lý"."""
    r = _value('VCB', 'Banks', 58_900.0, 8_355_675_094)
    (sig,), _ = signals_with_bands([r])
    assert sig['verdict'] == 'HOLD'
    assert sig['valuation_band']['band'] == 'NOT_AVAILABLE'
    assert 'NPL/CAR' in sig['valuation_band']['reason']
