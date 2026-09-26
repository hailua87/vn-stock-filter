"""
Lớp nguồn `scanner/sources/` (thay vnstock từ 26/09/2026).

Mọi test ở đây chạy trên phản hồi dựng tay, không gọi mạng. Chúng chốt hai
điều: (1) phép biến đổi phản hồi API → DataFrame cho ra ĐÚNG hình dạng vnstock
4.0.7 (cột, đơn vị, item_id, nhãn kỳ); (2) code gọi phía sau nối đúng vào lớp
mới. Bằng chứng trên API thật nằm ở `backend/check_sources.py` (job CI
`sources-live`).
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import data_fetcher, financial_fetcher as ff  # noqa: E402
from scanner.sources import http, kbs, vci  # noqa: E402
from scanner.sources.naming import camel_to_snake, english_to_snake  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Lỡ có đường nào gọi mạng thật thì hỏng ngay thay vì treo."""
    def boom(*a, **k):
        raise AssertionError('test không được gọi mạng')
    monkeypatch.setattr(http, '_session', boom)
    vci._metrics_cache.clear()


# ── Tên trường ────────────────────────────────────────────────────────────

def test_item_ids_match_vnstock_407_fixtures():
    """item_id = english_to_snake(item_en) cho MỌI dòng fixture của vnstock 4.0.7."""
    n = 0
    for path in FIXTURES.glob('vnstock407_*.json'):
        fx = json.loads(path.read_text(encoding='utf-8'))
        for table in ('balance_sheet', 'income', 'cash_flow'):
            for item, item_en, item_id, *_ in fx[table]['data']:
                assert english_to_snake(item_en) == item_id, (path.name, item_en)
                n += 1
    assert n > 150


@pytest.mark.parametrize('raw,expected', [
    ('A. ASSETS', 'assets'),
    ('1. Revenue', 'revenue'),
    ('IV. Inventories', 'inventories'),
    ('Cash & cash equivalents', 'cash_and_cash_equivalents'),
    ("Owner's Equity", 'owners_equity'),
    ('Net profit/(loss) after tax', 'net_profit_loss_after_tax'),
    ('Net Interest Margin (NIM)', 'net_interest_margin_nim'),
    ('2022 bonds', 'n_2022_bonds'),
])
def test_english_to_snake(raw, expected):
    assert english_to_snake(raw) == expected


@pytest.mark.parametrize('raw,expected', [
    ('icbCodeLv2', 'icb_code_lv2'),
    ('numberOfSharesMktCap', 'number_of_shares_mkt_cap'),
    ('exrightDate', 'exright_date'),
    ('viOrganName', 'vi_organ_name'),
])
def test_camel_to_snake(raw, expected):
    assert camel_to_snake(raw) == expected


# ── Giá ngày ──────────────────────────────────────────────────────────────

# 00:00 ICT ngày 23 và 24/09/2026 = 17:00 UTC ngày hôm trước.
T23, T24 = 1790096400, 1790182800


def test_ohlcv_frame_stock_in_thousands_and_ict_date():
    resp = [{'symbol': 'FPT', 't': [T23, T24], 'o': [66000, 66500], 'h': [67000, 67100],
             'l': [65500, 66000], 'c': [66400, 66900], 'v': [7355603, 5000000.0]}]
    df = vci._ohlcv_frame(resp, is_index=False)
    assert list(df.columns) == ['time', 'open', 'high', 'low', 'close', 'volume']
    assert list(df['time'].dt.strftime('%Y-%m-%d')) == ['2026-09-23', '2026-09-24']
    assert df['close'].tolist() == [66.4, 66.9]
    assert df['volume'].dtype == 'int64' and df['volume'].iloc[0] == 7355603


def test_ohlcv_frame_index_not_divided():
    resp = {'data': [{'t': [T24], 'o': [1650.12], 'h': [1660.5], 'l': [1640.0],
                      'c': [1655.555], 'v': [900000000]}]}
    df = vci._ohlcv_frame(resp, is_index=True)
    assert df['close'].iloc[0] == 1655.56


@pytest.mark.parametrize('resp', [[], [{}], {'data': []}, [{'t': []}], None])
def test_ohlcv_frame_empty(resp):
    df = vci._ohlcv_frame(resp, is_index=False)
    assert df.empty and list(df.columns) == vci.OHLCV_COLUMNS


def test_ohlcv_request_payload(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return []
    monkeypatch.setattr(vci, 'request_json', fake)
    vci.ohlcv('vnindex', '2026-09-21', '2026-09-25')
    assert seen['method'] == 'POST' and seen['url'].endswith('/chart/OHLCChart/gap-chart')
    p = seen['payload']
    assert p['symbols'] == ['VNINDEX'] and p['timeFrame'] == 'ONE_DAY'
    # 21→26/09 (end + 1 ngày): 5 ngày làm việc + 1
    assert p['countBack'] == 6


def test_ohlcv_rejects_start_after_end(monkeypatch):
    monkeypatch.setattr(vci, 'request_json', lambda *a, **k: [])
    with pytest.raises(ValueError):
        vci.ohlcv('FPT', '2026-09-25', '2026-09-01')


# ── BCTC ──────────────────────────────────────────────────────────────────

def _raw_from_fixture(ticker, period, table):
    """Dựng ngược phản hồi API từ fixture: mỗi kỳ một record, mỗi khoản mục một mã trường."""
    fx = json.loads((FIXTURES / f'vnstock407_{ticker}_{period}.json').read_text(encoding='utf-8'))
    t = fx[table]
    periods = t['columns'][3:]
    labels, records = {}, []
    for i, row in enumerate(t['data']):
        labels[f'f{i:03d}'] = (row[0], row[1])
    for j, label in enumerate(periods):
        year, _, q = label.partition('-Q')
        rec = {'ticker': ticker, 'yearReport': int(year), 'lengthReport': int(q) if q else 5,
               'createDate': '2026-01-01'}
        for i, row in enumerate(t['data']):
            rec[f'f{i:03d}'] = row[3 + j]
        records.append(rec)
    return pd.DataFrame(t['data'], columns=t['columns']), records, labels


@pytest.mark.parametrize('ticker', ['FPT', 'VCB', 'SSI'])
@pytest.mark.parametrize('period', ['year', 'quarter'])
@pytest.mark.parametrize('table', ['balance_sheet', 'income', 'cash_flow'])
def test_statement_frame_reproduces_vnstock_407(ticker, period, table):
    """Cùng nội dung API → cùng record theo kỳ như vnstock 4.0.7 (đã dùng thật)."""
    expected, records, labels = _raw_from_fixture(ticker, period, table)
    got = vci._statement_frame(records, labels, quarterly=(period == 'quarter'))
    assert list(got.columns[:3]) == ['item', 'item_en', 'item_id']
    assert ff.statement_to_records(got) == ff.statement_to_records(expected)


def test_statement_frame_zero_fill_drop_empty_period_and_keep_order():
    labels = {'a': ('Vay ngắn hạn', 'Short-term borrowings'),
              'b': ('Vay ngắn hạn (2)', 'Short-term borrowings'),
              'c': ('Tổng tài sản', 'TOTAL ASSETS')}
    records = [
        {'yearReport': 2025, 'lengthReport': 5, 'a': None, 'b': 7e9, 'c': 9e9, 'x': 1},
        {'yearReport': 2024, 'lengthReport': 5, 'a': 5e9, 'b': 6e9, 'c': 8e9},
        {'yearReport': 2023, 'lengthReport': 5, 'a': 0, 'b': None, 'c': 0},
    ]
    df = vci._statement_frame(records, labels, quarterly=False)
    assert list(df.columns) == ['item', 'item_en', 'item_id', '2025', '2024']  # 2023 toàn 0
    assert list(df['item_id']) == ['short_term_borrowings', 'short_term_borrowings', 'total_assets']
    assert df.loc[0, '2025'] == 0.0      # ô trống thành 0 như vnstock
    rec = ff.statement_to_records(df)[0]
    assert rec['short_term_borrowings'] == 0.0  # dòng ĐẦU thắng, như vnstock


def test_period_labels():
    assert vci._period_label({'yearReport': 2026, 'lengthReport': 2}, quarterly=True) == '2026-Q2'
    assert vci._period_label({'yearReport': 2025, 'lengthReport': 5}, quarterly=True) == '2025'
    assert vci._period_label({'yearReport': 2025, 'lengthReport': 4}, quarterly=False) == '2025'


def test_financial_statement_requests_and_caches_labels(monkeypatch):
    calls = []

    def fake(method, url, **kw):
        calls.append((url, kw.get('params')))
        if url.endswith('/metrics'):
            return {'data': {'BALANCE_SHEET': [{'field': 'bsa1', 'titleVi': 'Tổng', 'titleEn': 'Total Assets'}],
                             'INCOME_STATEMENT': [{'field': 'isa1', 'titleVi': 'DT', 'titleEn': 'Net sales'}]}}
        return {'data': {'years': [{'yearReport': 2025, 'lengthReport': 5, 'bsa1': 1e12, 'isa1': 2e12}],
                         'quarters': []}}
    monkeypatch.setattr(vci, 'request_json', fake)
    bs = vci.financial_statement('fpt', 'balance_sheet', 'year')
    vci.financial_statement('FPT', 'income', 'year')
    assert vci.financial_statement('FPT', 'cash_flow', 'quarter').empty
    assert list(bs['item_id']) == ['total_assets', 'net_sales']
    assert sum(u.endswith('/metrics') for u, _ in calls) == 1   # nhãn chỉ lấy 1 lần/mã
    assert [p['section'] for u, p in calls if p] == ['BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW']


def test_financial_statement_rejects_bad_args():
    with pytest.raises(ValueError):
        vci.financial_statement('FPT', 'ratio')
    with pytest.raises(ValueError):
        vci.financial_statement('FPT', 'income', 'month')


# ── Tổng quan công ty ─────────────────────────────────────────────────────

def test_company_overview_shape(monkeypatch):
    monkeypatch.setattr(vci, 'request_json', lambda *a, **k: {'data': {
        'ticker': 'VCB', 'sector': 'Banks', 'sectorVn': 'Ngân hàng', 'enSector': 'Banks',
        'icbCodeLv2': '8300', 'icbCodeLv4': '8355', 'numberOfSharesMktCap': 8355675094,
        'viOrganName': 'Ngân hàng TMCP Ngoại thương', 'enOrganName': 'Vietcombank',
        '__typename': 'X'}})
    row = vci.company_overview('VCB')
    assert row['symbol'] == 'VCB' and row['sector'] == 'Banks'
    assert row['icb_code_lv2'] == '8300' and row['issue_share'] == 8355675094
    assert row['organ_name'].startswith('Ngân hàng')
    assert not {'sector_vn', 'en_sector', 'en_organ_name', '__typename'} & set(row)


def test_fetch_company_overview_maps_icb_level2(monkeypatch):
    monkeypatch.setattr(ff.vci, 'company_overview', lambda t: {
        'symbol': 'VCB', 'sector': 'Banks', 'icb_code_lv2': '8300', 'icb_code_lv4': '8355',
        'issue_share': 8_355_675_094})
    ov = ff.fetch_company_overview('VCB')
    assert ov['industry'] == 'Banks' and ov['sector'] is None
    assert ov['outstanding_share'] == 8_355_675_094


def test_fetch_company_overview_swallows_source_errors(monkeypatch):
    def boom(t):
        raise http.SourceError('HTTP 500')
    monkeypatch.setattr(ff.vci, 'company_overview', boom)
    assert ff.fetch_company_overview('VCB') is None


# ── Sự kiện ───────────────────────────────────────────────────────────────

def test_events_shape(monkeypatch):
    monkeypatch.setattr(vci, 'request_json', lambda *a, **k: {'data': {'content': [
        {'organCode': 'FPT', 'eventTitle': 'Trả cổ tức bằng tiền', 'publicDate': 1758585600000,
         'exrightDate': '2026-10-01T00:00:00', 'ratio': 0.1}]}})
    df = vci.events('FPT')
    assert 'organ_code' not in df.columns
    assert df.loc[0, 'public_date'] == '2025-09-23'
    assert df.loc[0, 'exright_date'] == '2026-10-01'
    assert df.loc[0, 'event_title'] == 'Trả cổ tức bằng tiền'


def test_events_empty(monkeypatch):
    monkeypatch.setattr(vci, 'request_json', lambda *a, **k: {'data': {'content': []}})
    assert vci.events('FPT').empty


# ── KBS ───────────────────────────────────────────────────────────────────

def test_listing_normalises(monkeypatch):
    monkeypatch.setattr(kbs, 'request_json', lambda *a, **k: [
        {'symbol': 'fpt', 'name': 'FPT Corp', 'exchange': 'hose', 'type': 'STOCK'},
        {'symbol': 'E1VFVN30', 'name': 'ETF', 'exchange': 'HOSE', 'type': 'etf'}])
    df = kbs.listing()
    assert df.to_dict('records')[0] == {'symbol': 'FPT', 'exchange': 'HOSE', 'type': 'stock',
                                        'organ_name': 'FPT Corp'}


def _nim_resp():
    return {
        'Head': [{'ID': 2, 'YearPeriod': 2024, 'TermName': 'Năm'},
                 {'ID': 1, 'YearPeriod': 2025, 'TermName': 'Năm'},
                 {'ID': 3, 'YearPeriod': 2023, 'TermName': 'Năm'}],
        'Content': {
            'Nhóm chỉ số Sinh lợi': [
                {'Name': 'ROE', 'NameEn': 'ROE', 'Value1': 18, 'Value2': 19, 'Value3': 20},
                {'Name': 'NIM', 'NameEn': 'Net Interest Margin (NIM)',
                 'Value1': 2.64, 'Value2': 2.86, 'Value3': None}],
            'Khác': [{'Name': 'x', 'NameEn': 'Net Interest Margin (NIM)', 'Value1': 99}],
        },
    }


def test_parse_nim_follows_head_order():
    # Value{i} ứng với Head thứ i SAU KHI xếp theo ID: 2025, 2024, 2023.
    assert kbs._parse_nim(_nim_resp()) == {2025: 2.64, 2024: 2.86}


def test_bank_nim_request(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(url=url, **kw)
        return _nim_resp()
    monkeypatch.setattr(kbs, 'request_json', fake)
    assert kbs.bank_nim('vcb') == {2025: 2.64, 2024: 2.86}
    assert seen['url'].endswith('/stock/finance-info/VCB')
    assert seen['params']['type'] == 'CSTC' and seen['params']['pageSize'] == 4


def test_fetch_bank_ratios(monkeypatch):
    monkeypatch.setattr(ff.kbs, 'bank_nim', lambda t: {2025: 2.64})
    assert ff.fetch_bank_ratios('VCB') == {'nim': {2025: 2.64}}
    monkeypatch.setattr(ff.kbs, 'bank_nim', lambda t: None)
    assert ff.fetch_bank_ratios('VCB') is None


# ── Nối vào data_fetcher / financial_fetcher ──────────────────────────────

def test_full_universe_keeps_real_stocks_with_exchange(monkeypatch):
    monkeypatch.setattr(kbs, 'listing', lambda: pd.DataFrame([
        {'symbol': 'ZZZ', 'exchange': 'HNX', 'type': 'stock', 'organ_name': ''},
        {'symbol': 'QQQ', 'exchange': 'UPCOM', 'type': 'stock', 'organ_name': ''},
        {'symbol': 'FUE', 'exchange': 'HOSE', 'type': 'fund', 'organ_name': ''},
        {'symbol': 'BND', 'exchange': 'BOND', 'type': 'stock', 'organ_name': ''},
    ]))
    df = data_fetcher._fetch_full_universe(('HOSE', 'HNX', 'UPCOM'))
    assert df.set_index('ticker')['exchange'].to_dict() == {'ZZZ': 'HNX', 'QQQ': 'UPCOM'}


def test_full_universe_falls_back_when_listing_fails(monkeypatch):
    def boom():
        raise http.SourceError('HTTP 503')
    monkeypatch.setattr(kbs, 'listing', boom)
    monkeypatch.setattr(data_fetcher, '_load_fallback_universe', lambda ex: 'fallback')
    assert data_fetcher._fetch_full_universe(('HOSE',)) == 'fallback'


def test_fetch_ohlcv_renames_columns(monkeypatch):
    monkeypatch.setattr(data_fetcher._vci, 'ohlcv', lambda t, s, e: vci._ohlcv_frame(
        [{'t': [T24, T23], 'o': [1, 1], 'h': [1, 1], 'l': [1, 1], 'c': [66400, 66000], 'v': [1, 2]}],
        is_index=False))
    df = data_fetcher.fetch_ohlcv('FPT', '2026-09-20', '2026-09-24')
    assert list(df.columns) == ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    assert df['Close'].tolist() == [66.0, 66.4]   # xếp tăng theo ngày


def test_fetch_ohlcv_waits_on_rate_limit_then_retries(monkeypatch):
    calls, sleeps = [], []

    def flaky(t, s, e):
        calls.append(1)
        if len(calls) == 1:
            raise http.RateLimitError('HTTP 429')
        return pd.DataFrame(columns=vci.OHLCV_COLUMNS)
    monkeypatch.setattr(data_fetcher._vci, 'ohlcv', flaky)
    monkeypatch.setattr(data_fetcher.time, 'sleep', sleeps.append)
    assert data_fetcher.fetch_ohlcv('FPT', '2026-09-20', '2026-09-24') is None
    assert len(calls) == 2 and sleeps == [65]


def test_fetch_ohlcv_bad_source_fails_fast():
    with pytest.raises(RuntimeError):
        data_fetcher.fetch_ohlcv('FPT', '2026-09-20', '2026-09-24', source='tcbs')


def test_fetch_financial_statements_tables_and_no_ratio(monkeypatch):
    asked = []

    def fake(t, table, period):
        asked.append((table, period))
        return pd.DataFrame({'item': ['x'], 'item_en': ['Total Assets'],
                             'item_id': ['total_assets'], '2025': [1e9]})
    monkeypatch.setattr(ff.vci, 'financial_statement', fake)
    res = ff.fetch_financial_statements('FPT', period='year')
    assert set(res) == {'balance_sheet', 'income', 'cash_flow'}
    asked.clear()
    ff.fetch_financial_statements('FPT', period='quarter', tables=('income', 'ratio'))
    assert asked == [('income', 'quarter')]


def test_financial_fetcher_does_not_import_vnstock():
    src = (Path(ff.__file__)).read_text(encoding='utf-8')
    src += (Path(data_fetcher.__file__)).read_text(encoding='utf-8')
    assert 'from vnstock' not in src and 'import vnstock' not in src


# ── HTTP ──────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError('no json')
        return self._body


class _Sess:
    def __init__(self, resp):
        self.resp, self.kw = resp, None

    def request(self, method, url, **kw):
        self.kw = kw
        return self.resp


@pytest.mark.parametrize('resp,exc', [
    (_Resp(429), http.RateLimitError),
    (_Resp(403), http.SourceError),
    (_Resp(200, bad_json=True), http.SourceError),
])
def test_request_json_errors(monkeypatch, resp, exc):
    monkeypatch.setattr(http, '_session', lambda: _Sess(resp))
    monkeypatch.setattr(http, 'MIN_INTERVAL', 0)
    with pytest.raises(exc):
        http.request_json('GET', 'https://x')


def test_request_json_merges_headers(monkeypatch):
    sess = _Sess(_Resp(200, {'ok': 1}))
    monkeypatch.setattr(http, '_session', lambda: sess)
    monkeypatch.setattr(http, 'MIN_INTERVAL', 0)
    assert http.request_json('GET', 'https://x', headers={'Referer': 'r'}) == {'ok': 1}
    assert sess.kw['headers']['Referer'] == 'r' and 'User-Agent' in sess.kw['headers']
