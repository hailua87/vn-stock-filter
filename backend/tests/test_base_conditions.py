"""
Điều kiện nền và dữ liệu bối cảnh cho màn Scan (blueprint v4 §7.2, §7.3).

Đơn vị: vnstock trả giá theo NGHÌN đồng. FPT phiên 22/09: giá 66,4 và khối
lượng 7.355.603 cp → GTGD = 66,4 × 1.000 × 7.355.603 ≈ 488,4 tỷ đồng.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from scanner import base_conditions as BC


def frame(closes, volumes):
    return pd.DataFrame({'Close': closes, 'Volume': volumes})


def test_avg_value_is_in_dong_not_quote_units():
    df = frame([66.4] * 20, [7_355_603] * 20)
    ctx = BC.context_metrics(df)
    assert ctx['avg_value20'] == pytest.approx(488_412_039_200, rel=1e-6)
    assert ctx['spark20'] == [66.4] * 20


def test_context_uses_only_last_20_sessions():
    df = frame([10.0] * 30 + [20.0] * 20, [1_000_000] * 50)
    ctx = BC.context_metrics(df)
    assert ctx['spark20'] == [20.0] * 20
    assert ctx['avg_value20'] == pytest.approx(20.0 * 1000 * 1_000_000)


def test_short_history_uses_what_it_has():
    ctx = BC.context_metrics(frame([10.0, 11.0, 12.0], [1_000] * 3))
    assert ctx['spark20'] == [10.0, 11.0, 12.0] and ctx['avg_value20'] is not None


def test_empty_frame_gives_none_not_zero():
    for df in (None, pd.DataFrame()):
        assert BC.context_metrics(df) == {'avg_value20': None, 'spark20': []}


@pytest.mark.parametrize('avg,keep', [
    (10_000_000_000, True),      # đúng ngưỡng: giữ
    (9_999_999_999, False),
    (488_412_039_200, True),
    (None, True),                # thiếu số liệu thì không loại
])
def test_liquidity_gate(avg, keep):
    assert BC.passes_liquidity({'avg_value20': avg}) is keep


def test_filter_universe_reports_dropped():
    by_ticker = {
        'BIG': frame([66.4] * 20, [7_000_000] * 20),     # ~465 tỷ
        'SMALL': frame([5.0] * 20, [10_000] * 20),       # 50 triệu
    }
    ctx = BC.build_context(by_ticker)
    kept, dropped = BC.filter_universe(by_ticker, ctx)
    assert list(kept) == ['BIG'] and dropped == ['SMALL']


def test_zero_threshold_disables_condition():
    by_ticker = {'SMALL': frame([5.0] * 20, [10_000] * 20)}
    kept, dropped = BC.filter_universe(by_ticker, BC.build_context(by_ticker), 0)
    assert list(kept) == ['SMALL'] and dropped == []


def test_attach_puts_context_into_metrics():
    results = [SimpleNamespace(ticker='FPT', metrics={}),
               SimpleNamespace(ticker='KHONGCO', metrics={}),
               SimpleNamespace(ticker='X', metrics=None)]
    BC.attach(results, {'FPT': {'avg_value20': 1.0, 'spark20': [1.0, 2.0]}})
    assert results[0].metrics == {'avg_value20': 1.0, 'spark20': [1.0, 2.0]}
    assert results[1].metrics == {'avg_value20': None, 'spark20': []}
    assert results[2].metrics is None


def test_default_threshold_is_ten_billion():
    """Ngưỡng §7.2 là mặc định cấu hình — đổi thì phải sửa blueprint."""
    assert BC.MIN_AVG_VALUE_20D == 10_000_000_000


def test_filter_universe_does_not_mutate_the_original():
    """
    `run_daily` giữ lại bản chưa lọc để xuất nến: ngưỡng GTGD là điều kiện
    GIAO DỊCH, không được chặn biểu đồ của mã theo dõi dài hạn. Nếu
    filter_universe sửa tại chỗ thì bản giữ lại cũng mất mã — và lỗi đó im
    lặng, chỉ lộ ra khi mở màn Chi tiết mã.
    """
    by_ticker = {
        'BIG': frame([66.4] * 20, [7_000_000] * 20),
        'SMALL': frame([5.0] * 20, [10_000] * 20),
    }
    ctx = BC.build_context(by_ticker)
    kept, dropped = BC.filter_universe(by_ticker, ctx)
    assert sorted(by_ticker) == ['BIG', 'SMALL'], 'bản gốc đã bị sửa tại chỗ'
    assert kept is not by_ticker
    assert sorted(kept) == ['BIG'] and dropped == ['SMALL']
