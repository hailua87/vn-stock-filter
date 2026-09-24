"""
Chọn universe theo thanh khoản (blueprint §7.2, §8.1).

Lỗi gốc, phát hiện 24/09/2026: mã ART/TTB/SJF ngừng giao dịch từ 07/2024 vẫn
lọt vào rổ 200 mã của Module B. Hai khuyết tật chồng nhau:

  1. `df.tail(20)` không hỏi 20 dòng đó TỪ BAO GIỜ. Tệp cache của mã đã ngừng
     giao dịch vẫn còn nguyên các phiên cũ.
  2. Điểm của danh sách curated là `(623 − hạng) × 1e9`, tức 1–623 tỷ, đem so
     thẳng với thanh khoản đo được — mà số đo cao nhất chỉ là 4,3e8 vì quên đổi
     NGHÌN đồng sang đồng. Nên MỌI mã curated đứng trên MỌI mã đo được, và số đo
     thật chưa bao giờ được dùng để xếp hạng.

Khuyết tật 2 làm khuyết tật 1 vô hình: dù có sửa hạn dùng, thứ hạng vẫn không đổi.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner import data_fetcher as D

TODAY = date(2026, 9, 24)


def ohlcv(last_day: str, n: int = 20, close: float = 66.4, volume: float = 7_355_603):
    """n phiên liên tiếp kết thúc ở `last_day`."""
    end = pd.Timestamp(last_day)
    return pd.DataFrame({
        'Date': pd.date_range(end=end, periods=n, freq='D'),
        'Close': [close] * n,
        'Volume': [volume] * n,
    })


# ─── Đo thanh khoản ────────────────────────────────────────────────────────

def test_result_is_in_dong_not_quote_units():
    """vnstock báo giá theo NGHÌN đồng. FPT phiên 22/09: 66,4 × 7.355.603 cổ
    phiếu = 488,4 tỷ đồng — cùng con số với base_conditions."""
    got = D.measure_liquidity(ohlcv('2026-09-22'), TODAY)
    assert got == pytest.approx(488_412_039_200, rel=1e-6)


def test_stale_cache_gives_none_not_a_number():
    """
    ART/TTB/SJF: phiên cuối 2024-07-25, cũ 14 tháng. Trả về một con số ở đây —
    dù là 0 — là nói rằng mã đó CÓ thanh khoản đo được. Nó không có.
    """
    assert D.measure_liquidity(ohlcv('2024-07-25'), TODAY) is None


@pytest.mark.parametrize('last_day,measured', [
    ('2026-09-24', True),    # hôm nay
    ('2026-09-01', True),    # 23 ngày — trong hạn
    ('2026-08-20', False),   # 35 ngày — quá hạn
    ('2024-07-25', False),   # 14 tháng
])
def test_age_limit(last_day, measured):
    assert (D.measure_liquidity(ohlcv(last_day), TODAY) is not None) is measured


def test_zero_volume_is_not_liquidity():
    """Mã bị đình chỉ có thể còn phiên gần đây với khối lượng 0."""
    assert D.measure_liquidity(ohlcv('2026-09-24', volume=0), TODAY) is None


def test_missing_or_broken_frame_gives_none():
    assert D.measure_liquidity(None, TODAY) is None
    assert D.measure_liquidity(pd.DataFrame(), TODAY) is None
    assert D.measure_liquidity(pd.DataFrame({'Close': [1.0]}), TODAY) is None


def test_uses_only_the_last_window_sessions():
    df = ohlcv('2026-09-24', n=60, close=10.0, volume=1_000_000)
    df.loc[df.index[:40], 'Volume'] = 99_000_000        # phiên cũ, phải bị bỏ qua
    got = D.measure_liquidity(df, TODAY, window=20)
    assert got == pytest.approx(10.0 * 1000 * 1_000_000)


# ─── Xếp hạng ──────────────────────────────────────────────────────────────

def universe(*tickers):
    return pd.DataFrame([{'ticker': t, 'exchange': 'HOSE'} for t in tickers])


def test_measured_beats_curated(monkeypatch):
    """
    Đây là khuyết tật gốc. 'CUR' đứng đầu danh sách curated nhưng không có số đo;
    'REAL' có số đo thật. Bản cũ cho CUR điểm 623e9 và REAL điểm 4,3e8 nên CUR
    luôn thắng — kể cả khi REAL là mã thanh khoản nhất sàn.
    """
    monkeypatch.setattr(D, '_cached_liquidity', lambda today=None: {'REAL': 4.3e11})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers',
                        lambda: [('CUR', 0), ('REAL', 1)])
    out = D._sort_by_liquidity(universe('CUR', 'REAL'), 2, today=TODAY)
    assert list(out['ticker']) == ['REAL', 'CUR']


def test_suspended_ticker_drops_out_of_the_cut(monkeypatch):
    """ART không có số đo nên phải nằm sau mọi mã có số đo, và rơi khỏi top N."""
    monkeypatch.setattr(D, '_cached_liquidity',
                        lambda today=None: {'A': 3e11, 'B': 2e11, 'C': 1e11})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers',
                        lambda: [('ART', 0), ('A', 1), ('B', 2), ('C', 3)])
    out = D._sort_by_liquidity(universe('ART', 'A', 'B', 'C'), 3, today=TODAY)
    assert list(out['ticker']) == ['A', 'B', 'C']
    assert 'ART' not in set(out['ticker'])


def test_measured_are_ordered_by_actual_value(monkeypatch):
    monkeypatch.setattr(D, '_cached_liquidity',
                        lambda today=None: {'LOW': 1e10, 'HIGH': 9e11, 'MID': 5e10})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers', lambda: [])
    out = D._sort_by_liquidity(universe('LOW', 'HIGH', 'MID'), 3, today=TODAY)
    assert list(out['ticker']) == ['HIGH', 'MID', 'LOW']


def test_unmeasured_fall_back_to_curated_order(monkeypatch):
    """Chưa có số đo thì danh sách curated vẫn là thứ duy nhất để dựa vào —
    nó chỉ mất quyền đứng trên mã đã đo, không bị vứt đi."""
    monkeypatch.setattr(D, '_cached_liquidity', lambda today=None: {})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers',
                        lambda: [('P', 0), ('Q', 1), ('R', 2)])
    out = D._sort_by_liquidity(universe('R', 'Q', 'P'), 3, today=TODAY)
    assert list(out['ticker']) == ['P', 'Q', 'R']


def test_ticker_outside_both_goes_last(monkeypatch):
    monkeypatch.setattr(D, '_cached_liquidity', lambda today=None: {'A': 1e11})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers', lambda: [('B', 0)])
    out = D._sort_by_liquidity(universe('LA', 'A', 'B'), 3, today=TODAY)
    assert list(out['ticker']) == ['A', 'B', 'LA']


def test_limit_is_respected(monkeypatch):
    monkeypatch.setattr(D, '_cached_liquidity',
                        lambda today=None: {c: 1e11 for c in 'ABCDE'})
    monkeypatch.setattr('scanner.top_liquid.get_top_liquid_tickers', lambda: [])
    out = D._sort_by_liquidity(universe(*'ABCDE'), 2, today=TODAY)
    assert len(out) == 2 and list(out.columns) == ['ticker', 'exchange']
