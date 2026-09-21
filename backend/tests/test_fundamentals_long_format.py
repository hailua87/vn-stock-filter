"""
Chuyển BCTC dạng dài của vnstock 4.x → record theo kỳ cho normalizer.

vnstock 4.0.7 trả mỗi bảng với dòng = khoản mục (item, item_en, item_id),
cột = kỳ (mới trước), giá trị theo ĐỒNG. Code cũ coi dòng là kỳ
(`df.head(5).to_dict('records')`) nên normalizer không tìm thấy khoản mục
nào và mọi trường rơi về 0.

Fixture là output thật của `fetch_financial_statements` (vnstock 4.0.7, bản
cộng đồng, lấy 2026-09-21) cho FPT và VCB, period='year'. Số kỳ vọng trong
test đọc tay từ payload, không tính lại từ fixture.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner import financial_fetcher as ff
from scanner.strategies.valuation.normalizer import normalize_fundamentals

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def _load(ticker):
    raw = json.loads((FIXTURES / f'vnstock407_{ticker}_year.json').read_text(encoding='utf-8'))
    return {k: pd.DataFrame(v['data'], columns=v['columns']) for k, v in raw.items()}


def _fetch(monkeypatch, tmp_path, ticker, shares, price):
    """Chạy fetch_fundamentals thật, chỉ thay phần gọi mạng."""
    frames = _load(ticker)
    monkeypatch.setattr(ff, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(ff, 'fetch_financial_statements', lambda t, period='year': frames)
    monkeypatch.setattr(ff, 'fetch_company_overview',
                        lambda t: {'ticker': t, 'outstanding_share': shares})
    monkeypatch.setattr(ff, 'fetch_current_price', lambda t: price)
    return ff.fetch_fundamentals(ticker, period='year', use_cache=True)


# --- statement_to_records -------------------------------------------------

def test_statement_records_are_periods_latest_first_in_bn():
    recs = ff.statement_to_records(_load('FPT')['balance_sheet'])
    assert [r['period'] for r in recs] == ['2025', '2024', '2023', '2022', '2021']
    assert recs[0]['total_assets'] == pytest.approx(88_141.991634625)
    assert recs[-1]['period'] == '2021'


def test_statement_records_sort_quarters_and_keep_first_duplicate():
    df = pd.DataFrame({
        'item': ['a', 'b', 'b'], 'item_en': ['A', 'B', 'B'],
        'item_id': ['x', 'dup', 'dup'],
        '2025-Q3': [1e9, None, 7e9], '2026-Q1': [2e9, 3e9, 9e9],
    })
    recs = ff.statement_to_records(df)
    assert [r['period'] for r in recs] == ['2026-Q1', '2025-Q3']
    assert recs[0]['dup'] == 3.0   # dòng đầu tiên
    assert recs[1]['dup'] == 7.0   # dòng đầu rỗng → lấy dòng sau


# --- ratio_to_records -----------------------------------------------------

def test_ratio_table_from_2018_is_dropped_as_stale():
    """Bản 4.0.7: 16 cột cùng tên '2018' = Q1–Q4 2018 lặp 4 lần."""
    ratio = _load('VCB')['ratio']
    assert ff.ratio_to_records(ratio, latest_statement_year=2025) == []


def test_ratio_records_dedup_by_year_quarter_when_fresh():
    ratio = _load('VCB')['ratio']
    recs = ff.ratio_to_records(ratio, latest_statement_year=2019)
    assert [(r['year'], r['quarter']) for r in recs] == [(2018, 4), (2018, 3), (2018, 2), (2018, 1)]
    assert recs[-1]['npl'] == pytest.approx(0.01367, rel=1e-4)


# --- fetch_fundamentals → normalize_fundamentals (đường chạy thật) ----------

def test_fpt_end_to_end_normalized_values(monkeypatch, tmp_path):
    raw = _fetch(monkeypatch, tmp_path, 'FPT', shares=1_714_326_422, price=66_400.0)
    assert raw['schema'] == ff.CACHE_SCHEMA
    assert raw['ratio'] == []

    d = normalize_fundamentals(raw)
    bs, inc = d['balance_sheet'], d['income']
    assert bs['total_assets'] == pytest.approx(88_141.991634625)
    assert inc['revenue'] == pytest.approx(70_112.825100710)
    assert len(inc['revenue_5y']) == 5 and inc['revenue_5y'][0] > inc['revenue_5y'][-1] > 0
    assert bs['shareholders_equity'] > 0
    assert bs['cash_and_equivalents'] > 0
    assert d['cash_flow']['capex'] < 0 and d['cash_flow']['depreciation'] > 0
    # EPS VND/cp suy từ LNST cổ đông mẹ (tỷ) / số cp: cỡ nghìn đồng, không phải 0 hay tỷ
    assert 1_000 < d['per_share']['eps_ttm'] < 20_000
    assert 5 < d['ratios']['pe_ttm'] < 60
    # Vốn hóa tỷ đồng = 66.400 × 1,714 tỷ cp
    assert d['market']['market_cap'] == pytest.approx(66_400 * 1_714_326_422 / 1e9)


def test_vcb_end_to_end_bank_fields(monkeypatch, tmp_path):
    raw = _fetch(monkeypatch, tmp_path, 'VCB', shares=8_355_675_094, price=58_900.0)
    d = normalize_fundamentals(raw)
    assert d['balance_sheet']['total_assets'] == pytest.approx(2_442_279.166)
    assert d['income']['net_interest_income'] == pytest.approx(58_771.41)
    assert d['balance_sheet']['loans_to_customers'] > 0
    assert d['balance_sheet']['customer_deposits'] > 0
    assert 1_000 < d['per_share']['bvps'] < 100_000


def test_cache_roundtrip_and_old_schema_ignored(monkeypatch, tmp_path):
    raw = _fetch(monkeypatch, tmp_path, 'FPT', shares=1_714_326_422, price=66_400.0)
    cache = tmp_path / 'FPT_year.json'
    assert cache.exists()

    # Cache schema cũ (dòng = khoản mục) phải bị bỏ qua và fetch lại
    cache.write_text(json.dumps({'ticker': 'FPT', 'balance_sheet': [{'item_id': 'x'}]}),
                     encoding='utf-8')
    again = ff.fetch_fundamentals('FPT', period='year', use_cache=True)
    assert again['schema'] == ff.CACHE_SCHEMA
    assert again['balance_sheet'][0]['total_assets'] == raw['balance_sheet'][0]['total_assets']
