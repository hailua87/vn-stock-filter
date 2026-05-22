"""Tests for corporate_actions module."""
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.corporate_actions import (
    CorporateAction, has_recent_event, has_upcoming_event,
    event_summary, _classify
)


def _mk(ticker='TEST', days_offset=0, event_type='cash_dividend', ratio=1000):
    """Make a CorporateAction relative to today."""
    ex_date = (date.today() + timedelta(days=days_offset)).isoformat()
    return CorporateAction(ticker=ticker, ex_date=ex_date, event_type=event_type, ratio=ratio)


def test_cash_dividend_not_dilutive():
    e = _mk(event_type='cash_dividend')
    assert not e.is_dilutive
    assert e.price_impact_pct == 0  # depends on price, computed at call site


def test_stock_dividend_is_dilutive():
    e = _mk(event_type='stock_dividend', ratio=0.10)
    assert e.is_dilutive
    # 10% stock dividend → price drops by 10/110 = -9.09%
    assert abs(e.price_impact_pct - (-100/11)) < 0.5


def test_split_is_dilutive():
    e = _mk(event_type='split', ratio=2.0)
    assert e.is_dilutive
    # 1:2 split → price halves, so -50%
    assert abs(e.price_impact_pct - (-50)) < 0.5


def test_has_recent_event_finds_dilutive():
    events = [
        _mk(event_type='cash_dividend', days_offset=-3),       # not dilutive
        _mk(event_type='stock_dividend', days_offset=-2, ratio=0.10),  # ✓
    ]
    recent = has_recent_event(events, days=5)
    assert recent is not None
    assert recent.event_type == 'stock_dividend'


def test_has_recent_event_ignores_cash_div():
    events = [_mk(event_type='cash_dividend', days_offset=-3)]
    assert has_recent_event(events, days=5) is None


def test_has_recent_event_ignores_old():
    events = [_mk(event_type='split', days_offset=-30, ratio=2.0)]
    assert has_recent_event(events, days=5) is None


def test_has_upcoming_event():
    events = [
        _mk(event_type='cash_dividend', days_offset=8, ratio=2000),
    ]
    upcoming = has_upcoming_event(events, days=10)
    assert upcoming is not None
    assert upcoming.event_type == 'cash_dividend'


def test_has_upcoming_event_returns_soonest():
    events = [
        _mk(ticker='A', event_type='cash_dividend', days_offset=15),
        _mk(ticker='B', event_type='stock_dividend', days_offset=5, ratio=0.05),
        _mk(ticker='C', event_type='cash_dividend', days_offset=10),
    ]
    upcoming = has_upcoming_event(events, days=20)
    assert upcoming.ticker == 'B'  # soonest within window


def test_event_summary_empty():
    summary = event_summary([])
    assert summary['count'] == 0
    assert summary['latest'] is None
    assert summary['upcoming'] is None


def test_event_summary_full():
    events = [
        _mk(event_type='stock_dividend', days_offset=-3, ratio=0.10),
        _mk(event_type='cash_dividend', days_offset=20, ratio=1500),
    ]
    summary = event_summary(events)
    assert summary['count'] == 2
    assert summary['latest'] is not None
    assert summary['latest']['event_type'] == 'stock_dividend'
    assert summary['upcoming'] is not None
    assert summary['upcoming']['event_type'] == 'cash_dividend'


def test_classify_vietnamese_text():
    # Stock dividend
    t, r = _classify('Cổ tức bằng cổ phiếu', 10, 'tỷ lệ 10%')
    assert t == 'stock_dividend'
    assert abs(r - 0.10) < 0.01

    # Split
    t, r = _classify('Chia tách cổ phiếu', 2, '')
    assert t == 'split'

    # Cash dividend
    t, r = _classify('Cổ tức bằng tiền', 1500, '')
    assert t == 'cash_dividend'
    assert r == 1500

    # Rights issue
    t, _ = _classify('Phát hành thêm', 20, 'chào bán')
    assert t == 'rights_issue'


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
