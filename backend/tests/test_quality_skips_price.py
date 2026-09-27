"""
Module B không lấy giá (28/09/2026).

Đo lượt 27/09: 275 trong 276 cảnh báo của bước chấm chất lượng là `gap-chart`
— đúng lượt gọi lấy giá — và KHÔNG một lỗi nào từ `financial-statement`. Tức
cache BCTC ấm hoàn toàn, còn 1,67 lần timeout mỗi mã × 10 s ≈ 46 trong 70 phút
ngân sách là tiền trả cho một con số Module B không bao giờ đọc. Chính vì hết
giờ mà nó dừng ở 165/200 mã và percentile bị tính trên rổ cụt.

Chú thích cũ tại chỗ đó ghi lượt gọi này là "cheap". Đúng ở máy cá nhân, sai
trên runner.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import financial_fetcher as FF


@pytest.fixture
def warm_cache(tmp_path, monkeypatch):
    """Một mã đã có cache còn hạn, đúng schema — tức đường trúng cache."""
    import json
    p = tmp_path / 'AAA_year.json'
    p.write_text(json.dumps({
        'schema': FF.CACHE_SCHEMA, 'ticker': 'AAA', 'period': 'year',
        'current_price': 12345.0, 'overview': {'industry': 'Technology'},
        'balance_sheet': [], 'income': [], 'cash_flow': [],
    }), encoding='utf-8')
    monkeypatch.setattr(FF, '_cache_path', lambda t, per: tmp_path / f'{t}_{per}.json')
    calls = []
    monkeypatch.setattr(FF, 'fetch_current_price',
                        lambda t, **k: calls.append(t) or 99.0)
    return calls


def test_cache_hit_skips_the_price_call_when_asked(warm_cache):
    out = FF.fetch_fundamentals('AAA', refresh_price=False)
    assert out is not None
    assert warm_cache == [], 'không được gọi mạng lấy giá khi đã nói là không cần'
    assert out['current_price'] == 12345.0, 'giữ nguyên giá trong cache'


def test_cache_hit_still_refreshes_by_default(warm_cache):
    """Mặc định phải y như cũ — định giá tính upside từ giá, không được đổi."""
    out = FF.fetch_fundamentals('AAA')
    assert warm_cache == ['AAA']
    assert out['current_price'] == 99.0


def test_cold_path_also_honours_the_flag(tmp_path, monkeypatch):
    """Không chỉ đường trúng cache: mã chưa có cache cũng không được gọi giá."""
    import pandas as pd
    calls = []
    monkeypatch.setattr(FF, '_cache_path', lambda t, per: tmp_path / f'{t}_{per}.json')
    monkeypatch.setattr(FF, 'fetch_company_overview', lambda t, **k: {})
    monkeypatch.setattr(FF, 'fetch_financial_statements',
                        lambda t, **k: {'balance_sheet': pd.DataFrame(), 'income': pd.DataFrame()})
    monkeypatch.setattr(FF, 'fetch_current_price', lambda t, **k: calls.append(t) or 99.0)

    out = FF.fetch_fundamentals('BBB', use_cache=False, refresh_price=False)
    assert out is not None and calls == []
    assert out['current_price'] is None


def test_run_quality_actually_passes_the_flag(monkeypatch, tmp_path):
    """
    Tham số đúng mà nơi gọi không truyền thì vô nghĩa — và lần trước tôi đã
    chốt việc này bằng cách đọc mã nguồn, rồi test xanh nhờ khớp với dòng chú
    thích. Nay gọi thẳng `main` và xem nó truyền gì.
    """
    import run_quality
    seen = {}

    def fake_fetch(t, period='year', refresh_price=True, **k):
        seen['refresh_price'] = refresh_price
        return None                       # đủ để dừng sớm, ta chỉ cần cờ

    monkeypatch.setattr('scanner.financial_fetcher.fetch_fundamentals', fake_fetch)
    monkeypatch.setattr('scanner.financial_fetcher.fetch_quarterly_statements',
                        lambda t, **k: None)
    monkeypatch.setattr('scanner.financial_fetcher.fetch_bank_ratios', lambda t: None)
    monkeypatch.setattr('scanner.data_fetcher.setup_api_key', lambda *a, **k: None)
    import pandas as pd
    monkeypatch.setattr('scanner.data_fetcher.get_ticker_universe',
                        lambda ex, limit=None: pd.DataFrame({'ticker': ['AAA']}))

    run_quality.main(['--web-data-dir', str(tmp_path), '--snapshot-registry', ''])
    assert seen.get('refresh_price') is False, (
        'run_quality phải truyền refresh_price=False — nếu không nó trả tiền '
        'cho một lượt gọi mạng mà nó không bao giờ đọc kết quả')


def test_the_quality_path_really_never_reads_the_price():
    """
    Cơ sở của cả thay đổi này. Nếu có ngày Module B cần giá, test này đỏ và
    người sửa sẽ thấy ngay là phải bỏ `refresh_price=False` đi.
    """
    root = Path(__file__).resolve().parent.parent
    files = list((root / 'scanner' / 'quality').glob('*.py')) + [root / 'run_quality.py']
    hits = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            code = line.split('#')[0]
            if 'current_price' in code:
                hits.append(f'{f.name}:{n}')
    assert not hits, f'Module B đã bắt đầu đọc giá ({hits}) — xem lại refresh_price=False'
