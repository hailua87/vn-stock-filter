"""
`check_sources.py` là chuông báo duy nhất trên API thật — phải chắc nó đổ
chuông khi lớp nguồn đọc sai, và im khi đọc đúng. Chạy offline: "API" dựng
ngược từ fixture vnstock 4.0.7 (bỏ FIXTURE_SCALE để ra số thật).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_sources as cs  # noqa: E402
from fixture_scale import FIXTURE_SCALE  # noqa: E402
from scanner.sources import vci  # noqa: E402
from test_sources import _raw_from_fixture  # noqa: E402

FIX = Path(__file__).resolve().parent / 'fixtures'


def _live(ticker, period, table, scale=1.0):
    _, records, labels = _raw_from_fixture(ticker, period, table)
    for r in records:
        for k, v in r.items():
            if k.startswith('f') and isinstance(v, (int, float)):
                r[k] = v / FIXTURE_SCALE * scale
    return vci._statement_frame(records, labels, quarterly=(period == 'quarter'))


def _fx(ticker, period, table):
    return json.loads((FIX / f'vnstock407_{ticker}_{period}.json').read_text(encoding='utf-8'))[table]


@pytest.fixture(autouse=True)
def _reset():
    cs.failures.clear()
    yield
    cs.failures.clear()


@pytest.mark.parametrize('ticker', ['FPT', 'VCB', 'SSI'])
@pytest.mark.parametrize('period', ['year', 'quarter'])
def test_silent_when_source_matches(ticker, period):
    for table in cs.TABLES:
        cs.compare_table(f'{ticker} {table}', _fx(ticker, period, table), _live(ticker, period, table))
    assert cs.failures == []


def test_rings_on_unit_error():
    cs.compare_table('FPT bs', _fx('FPT', 'year', 'balance_sheet'),
                     _live('FPT', 'year', 'balance_sheet', scale=1000))
    assert any('giá trị khớp' in f for f in cs.failures)


def test_rings_on_missing_item():
    live = _live('FPT', 'year', 'income')
    live = live[live['item_id'] != 'net_sales']
    cs.compare_table('FPT is', _fx('FPT', 'year', 'income'), live)
    assert any('đủ item_id' in f for f in cs.failures)


def test_rings_on_shifted_period_labels():
    live = _live('FPT', 'year', 'income')
    live.columns = list(live.columns[:3]) + [str(int(c) + 1) for c in live.columns[3:]]
    cs.compare_table('FPT is', _fx('FPT', 'year', 'income'), live)
    assert any('giá trị khớp' in f for f in cs.failures)
