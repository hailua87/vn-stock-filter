"""
Chống tái phát: financial_fetcher import sai module Finance của vnstock.

vnstock 4.x đặt lớp Finance ở `vnstock.api.financial`. Code cũ import
`vnstock.api.finance` (không tồn tại) và nuốt ImportError với log
"vnstock not installed", nên Weekly Valuation đỏ nhiều tuần liền với
"Không có mã nào định giá được" mà không lộ nguyên nhân.
"""
import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib.util

import pandas as pd
import pytest

from scanner import financial_fetcher


class _FakeFinance:
    def __init__(self, symbol, source):
        self.symbol = symbol

    def _df(self, **_):
        return pd.DataFrame({'item_id': ['total_assets'], '2025': [1.0]})

    balance_sheet = income_statement = cash_flow = ratio = _df


def test_fetch_financial_statements_uses_vnstock_api_financial(monkeypatch):
    """Chỉ cung cấp `vnstock.api.financial` — đường import sai sẽ trả None."""
    fake = types.ModuleType('vnstock.api.financial')
    fake.Finance = _FakeFinance
    monkeypatch.setitem(sys.modules, 'vnstock.api.financial', fake)
    monkeypatch.setitem(sys.modules, 'vnstock.api.finance', None)  # import sẽ raise
    monkeypatch.setattr(financial_fetcher, 'setup_api_key', lambda: False)

    res = financial_fetcher.fetch_financial_statements('FPT', period='year')

    assert res is not None
    assert set(res) == {'balance_sheet', 'income', 'cash_flow', 'ratio'}


def test_installed_vnstock_exposes_api_financial():
    """Bản vnstock thật (requirements.txt) phải có module mà code import."""
    if importlib.util.find_spec('vnstock') is None:
        pytest.skip('vnstock chưa cài')
    from vnstock.api.financial import Finance  # noqa: F401
