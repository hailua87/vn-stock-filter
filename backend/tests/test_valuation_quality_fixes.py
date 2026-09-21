"""
Sửa chất lượng định giá sau lần chạy Weekly Valuation xanh đầu tiên (2026-09-21):
chỉ 7/100 mã qua bộ lọc, BAF −97%, HAG EPS 167 triệu đồng.

  1. Ngành: vnstock 4.0.7 không trả icb_name2; `sector` là ICB cấp 2 → 92 mã
     rơi về heuristic, confidence < 0,3.
  2. Số cổ phiếu: `common_shares` là vốn cổ phần (tiền), không phải số lượng.
  3. ROE, EPS/BVPS lịch sử: bảng ratio bị bỏ (chỉ có 2018) → tính từ BCTC.
  4. Cổng chặn ngoại lai trước khi công bố.

Số kỳ vọng đọc tay từ fixture thật (vnstock 4.0.7, FPT/VCB năm):
  FPT 2025: LNST mẹ 9.376,1 tỷ; VCSH 43.748,0 tỷ; vốn góp 17.035,1 tỷ
  FPT 2021: LNST mẹ 4.337,4 tỷ; vốn góp 9.075,5 tỷ
  VCB 2025: vốn góp 83.556,8 tỷ; overview trả 8.355.675.094 cp
"""
import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import pytest

from scanner import financial_fetcher as ff
from scanner import market_metrics as mm
from scanner.strategies.valuation.industry_classifier import IndustryClassifier, ValuationIndustry
from scanner.strategies.valuation.normalizer import (
    normalize_fundamentals, shares_from_paid_in_capital,
)
from run_valuation import outlier_reason
from test_fundamentals_long_format import _load


def _raw(ticker, overview=None, ratio=None):
    frames = _load(ticker)
    return {
        'ticker': ticker, 'current_price': 66_400.0, 'overview': overview or {},
        'balance_sheet': ff.statement_to_records(frames['balance_sheet']),
        'income': ff.statement_to_records(frames['income']),
        'cash_flow': ff.statement_to_records(frames['cash_flow']),
        'ratio': ratio if ratio is not None else [],
    }


# --- 1. Ngành -------------------------------------------------------------

def _overview_from_vnstock_407(monkeypatch, row):
    class _Company:
        def __init__(self, symbol, source): pass
        def overview(self): return pd.DataFrame([row])
    mod = types.ModuleType('vnstock.api.company')
    mod.Company = _Company
    monkeypatch.setitem(sys.modules, 'vnstock.api.company', mod)
    monkeypatch.setattr(ff, 'setup_api_key', lambda: False)
    return ff.fetch_company_overview('X')


def test_overview_407_sector_is_icb_level2(monkeypatch):
    # Các cột này đúng như vnstock 4.0.7 trả cho VCB
    ov = _overview_from_vnstock_407(monkeypatch, {
        'symbol': 'VCB', 'sector': 'Banks', 'icb_code_lv2': '8300',
        'icb_code_lv4': '8355', 'issue_share': 8_355_675_094})
    assert ov['industry'] == 'Banks'
    assert ov['sector'] is None
    assert ov['icb_code_lv4'] == '8355'
    c = IndustryClassifier().classify('VCB', ov)
    assert c.valuation_industry == ValuationIndustry.BANKING
    assert c.classification_source == 'icb_mapping'


def test_overview_legacy_layout_keeps_sector_as_level3(monkeypatch):
    ov = _overview_from_vnstock_407(monkeypatch, {
        'icb_name2': 'Thực phẩm và đồ uống', 'sector': 'Sản xuất Thực phẩm'})
    assert ov['industry'] == 'Thực phẩm và đồ uống'
    assert ov['sector'] == 'Sản xuất Thực phẩm'


@pytest.mark.parametrize('ticker,lv2_name,lv4,expected', [
    ('ANV', 'Food & Beverage', '3573', ValuationIndustry.AGRICULTURE_LIVESTOCK),
    ('HSG', 'Basic Resources', '1757', ValuationIndustry.STEEL_METALS),
    ('XYZ', 'Industrial Goods & Services', '2777', ValuationIndustry.LOGISTICS_TRANSPORT),
    ('DRC', 'Automobiles & Parts', '3357', ValuationIndustry.CONSUMER_DISCRETIONARY),
    ('VNM', 'Food & Beverage', '3577', ValuationIndustry.CONSUMER_STAPLES),
])
def test_classify_from_icb_level4_code(ticker, lv2_name, lv4, expected):
    ov = {'industry': lv2_name, 'sector': None, 'icb_code_lv4': lv4}
    assert IndustryClassifier().classify(ticker, ov).valuation_industry == expected


# --- 2. Số cổ phiếu --------------------------------------------------------

def test_shares_from_paid_in_capital_matches_overview_for_vcb():
    bs0 = _raw('VCB')['balance_sheet'][0]
    assert shares_from_paid_in_capital(bs0) == pytest.approx(8_355_675_094, rel=1e-4)


def test_missing_overview_uses_paid_in_capital_not_common_shares_value():
    d = normalize_fundamentals(_raw('FPT', overview={}))
    assert d['market']['shares_outstanding'] == pytest.approx(1_703_510_000, rel=1e-4)
    # 9.376,1 tỷ / 1,70351 tỷ cp ≈ 5.504 đ — không phải hàng trăm triệu
    assert d['per_share']['eps_ttm'] == pytest.approx(5_504, rel=1e-3)


# --- 3. ROE, EPS/BVPS lịch sử từ BCTC --------------------------------------

def test_roe_5y_from_statements_when_ratio_dropped():
    d = normalize_fundamentals(_raw('FPT', overview={'outstanding_share': 1_714_326_422}))
    assert len(d['income']['roe_5y']) == 5
    assert d['income']['roe_5y'][0] == pytest.approx(9_376.1 / 43_748.0, rel=1e-3)
    assert d['ratios']['roe_ttm'] == pytest.approx(9_376.1 / 43_748.0, rel=1e-3)


def test_eps_history_uses_each_years_share_count():
    hist = mm._extract_eps_bvps_history(_raw('FPT'))
    assert [h['period'] for h in hist] == ['2021', '2022', '2023', '2024', '2025']
    # 2021: 4.337,4 tỷ / (9.075,5 tỷ / 10.000) cp ≈ 4.779 đ.
    # Dùng số cp hiện tại sẽ ra ≈ 2.530 đ và P/E 2021 gấp đôi.
    assert hist[0]['eps'] == pytest.approx(4_779, rel=1e-3)
    assert hist[-1]['eps'] == pytest.approx(5_504, rel=1e-3)
    assert hist[-1]['bvps'] == pytest.approx(43_748.0 / 17_035.1 * 10_000, rel=1e-3)


def test_historical_multiples_with_empty_ratio_does_not_crash(monkeypatch):
    """Trước đây `get('ratio', [{}])[0]` ném IndexError khi ratio == []."""
    dates = pd.to_datetime([f'{y}-12-31' for y in range(2020, 2026)] + ['2026-09-18'])
    closes = [60.0, 90.0, 80.0, 95.0, 130.0, 100.0, 66.4]  # nghìn VND như cache
    monkeypatch.setattr(mm, '_load_ohlcv_from_cache',
                        lambda t, lookback_days=0: pd.DataFrame({'Date': dates, 'Close': closes}))
    res = mm.calculate_historical_multiples('FPT', _raw('FPT'))
    assert res['fallback'] is False
    assert res['pe_5y_median'] is not None and 5 < res['pe_5y_median'] < 40


# --- 4. Cổng ngoại lai -----------------------------------------------------

@pytest.mark.parametrize('upside,excluded', [
    (-0.973, True),   # BAF 2026-09-21
    (-0.886, True),   # VIC 2026-09-21
    (-0.80, False), (-0.083, False), (1.253, False),  # HAH +125% vẫn công bố
    (2.01, True),
])
def test_outlier_gate(upside, excluded):
    assert (outlier_reason(upside) is not None) == excluded


# --- 5. Nhóm tài chính luôn HOLD khi chưa có NPL/CAR ------------------------

@pytest.fixture
def no_dispersion(monkeypatch):
    """Cố định độ phân tán = 0 để engine không tự hạ HOLD vì mâu thuẫn
    phương pháp — chỉ còn cờ nhóm tài chính quyết định verdict."""
    from scanner.strategies.valuation import engine
    monkeypatch.setattr(engine, '_method_dispersion', lambda fvs: 0.0)


def _value(ticker, industry_lv2, price, shares):
    from scanner.strategies.valuation import value_ticker
    raw = _raw(ticker, overview={'industry': industry_lv2, 'outstanding_share': shares})
    raw['current_price'] = price
    return value_ticker(ticker, raw_fundamentals=raw)


def test_bank_verdict_forced_to_hold_but_upside_kept(no_dispersion):
    # VCB fair value ≈ 48.000đ (lượt chạy 21/09); giá 20.000đ → mô hình cho mua mạnh
    r = _value('VCB', 'Banks', 20_000.0, 8_355_675_094)
    assert r.upside_pct > 0.5
    assert r.verdict == 'HOLD'
    assert 'chưa có NPL/CAR' in r.warnings[0]
    assert 'STRONG BUY' in r.warnings[0]


@pytest.mark.parametrize('lv2', ['Financial Services', 'Insurance'])
def test_securities_and_insurance_also_forced(no_dispersion, lv2):
    r = _value('VCB', lv2, 20_000.0, 8_355_675_094)
    assert r.verdict == 'HOLD' and 'NPL/CAR' in r.warnings[0]


def test_non_financial_verdict_not_forced(no_dispersion):
    # FPT (Technology) giá thấp vẫn giữ kết luận mua
    r = _value('FPT', 'Technology', 30_000.0, 1_714_326_422)
    assert r.verdict in ('BUY', 'STRONG BUY')
    assert not any('NPL/CAR' in w for w in r.warnings)
