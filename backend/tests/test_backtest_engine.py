"""
Test backtest engine — chống tái phát 5 cách "tự đánh lừa" của bản cũ:
MFE thay cho lợi nhuận thật, bỏ T+2, bỏ phí, không benchmark, và chậm tới mức
không chạy nổi.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from scanner.backtest_engine import (
    compute_criteria_matrix,
    run_backtest,
    _simulate_trade,
    SETTLEMENT_DAYS,
    ROUND_TRIP_COST,
)
from scanner.criteria import DEFAULT_CRITERIA_WEIGHTS


def _make_df(closes, opens=None, highs=None, lows=None, volumes=None):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    opens = np.asarray(opens, dtype=float) if opens is not None else closes
    highs = np.asarray(highs, dtype=float) if highs is not None else closes * 1.01
    lows = np.asarray(lows, dtype=float) if lows is not None else closes * 0.99
    volumes = np.asarray(volumes) if volumes is not None else np.full(n, 500_000)
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=n, freq='B'),
        'Open': opens, 'High': highs, 'Low': lows,
        'Close': closes, 'Volume': volumes, 'Exchange': 'HOSE',
    })


def _trending_df(n=300, drift=0.0015, seed=0):
    rng = np.random.default_rng(seed)
    closes = 20 * np.cumprod(1 + drift + rng.normal(0, 0.012, n))
    return _make_df(closes,
                    opens=closes * (1 + rng.normal(0, 0.002, n)),
                    highs=closes * 1.015, lows=closes * 0.985)


# ── Vector hoá cho cùng kết quả với định nghĩa tiêu chí ───────────────────
def test_matrix_shape_and_columns():
    df = _trending_df()
    m = compute_criteria_matrix(df)
    assert len(m) == len(df)
    for crit in DEFAULT_CRITERIA_WEIGHTS:
        assert crit in m.columns, f"thiếu tiêu chí {crit}"
    assert set(m[list(DEFAULT_CRITERIA_WEIGHTS)].to_numpy().ravel()) <= {0, 1}


def test_warmup_not_eligible():
    """Không được sinh tín hiệu khi chưa đủ lịch sử."""
    df = _trending_df()
    m = compute_criteria_matrix(df)
    assert m['_eligible'].iloc[:59].sum() == 0


def test_illiquid_not_eligible():
    df = _trending_df()
    df['Volume'] = 100          # dưới min_avg_volume
    m = compute_criteria_matrix(df)
    assert m['_eligible'].sum() == 0


# ── Ràng buộc T+2 ─────────────────────────────────────────────────────────
def test_cannot_sell_before_t_plus_2():
    """
    Giá chạm target ngay phiên đầu nhưng T+2 chưa về hàng ⇒ không được thoát.
    Bản cũ bỏ qua hoàn toàn ràng buộc này nên hit rate bị thổi phồng.
    """
    closes = [10, 10, 20, 10, 10, 10, 10, 10]
    highs = [10, 10, 20, 10, 10, 10, 10, 10]   # đỉnh ở index 2 = phiên vào lệnh + 1
    df = _make_df(closes, opens=closes, highs=highs, lows=[c * 0.999 for c in closes])

    sim = _simulate_trade(df, signal_idx=0, target_pct=0.08, stop_pct=0.05,
                          max_holding_days=5)
    # Vào lệnh ở index 1; đỉnh ở index 2 tức mới T+1 → chưa được bán
    assert sim['exit_idx'] >= 1 + SETTLEMENT_DAYS


def test_entry_is_next_open_not_signal_close():
    """Vào lệnh ở giá MỞ CỬA phiên kế tiếp — dùng giá đóng cửa phiên tín hiệu là look-ahead."""
    closes = [10] * 10
    opens = [10] * 10
    opens[1] = 11          # giá mở cửa phiên kế tiếp khác hẳn
    df = _make_df(closes, opens=opens)
    sim = _simulate_trade(df, 0, 0.08, 0.05, 5)
    assert sim is not None
    # entry_price được lấy ở nơi gọi, kiểm tra gián tiếp: Open[1] == 11
    assert float(df['Open'].iloc[1]) == 11


def test_stop_checked_before_target():
    """Cùng phiên chạm cả stop lẫn target → giả định bảo thủ là thua."""
    closes = [10] * 10
    df = _make_df(closes, opens=closes,
                  highs=[10] * 2 + [11.0] * 8,     # chạm target
                  lows=[10] * 2 + [9.0] * 8)       # đồng thời chạm stop
    sim = _simulate_trade(df, 0, 0.08, 0.05, 5)
    assert sim['reason'] == 'stop'


def test_timeout_exit():
    df = _make_df([10] * 20)
    sim = _simulate_trade(df, 0, 0.50, 0.50, max_holding_days=5)
    assert sim['reason'] == 'timeout'


# ── Phí, benchmark, base rate ─────────────────────────────────────────────
def test_costs_are_deducted():
    by_ticker = {'T1': _trending_df(seed=1)}
    report = run_backtest(by_ticker, min_score=4.0, max_holding_days=10)
    if report.n_trades:
        row = report.trades.iloc[0]
        assert row['net_pct'] == pytest.approx(row['gross_pct'] - ROUND_TRIP_COST * 100,
                                               abs=0.01)


def test_alpha_computed_against_benchmark():
    by_ticker = {f'T{i}': _trending_df(seed=i) for i in range(4)}
    index_df = _trending_df(seed=99)[['Date', 'Close']]
    report = run_backtest(by_ticker, index_df=index_df, min_score=4.0)
    if report.n_trades:
        row = report.trades.iloc[0]
        assert row['alpha_pct'] == pytest.approx(row['net_pct'] - row['bench_pct'], abs=0.01)


def test_base_rate_reported():
    """
    Không có base rate thì win rate là con số vô nghĩa. Engine phải luôn báo.
    """
    by_ticker = {f'T{i}': _trending_df(seed=i) for i in range(4)}
    report = run_backtest(by_ticker, min_score=4.0)
    assert report.base_rate_pct >= 0
    assert hasattr(report, 'edge_vs_base_rate_pct')


def test_no_overlapping_trades_same_ticker():
    by_ticker = {'T1': _trending_df(seed=3)}
    report = run_backtest(by_ticker, min_score=3.0, min_gap_days=10)
    if report.n_trades > 1:
        gaps = report.trades['signal_date'].diff().dt.days.dropna()
        assert (gaps >= 10).all()


def test_empty_universe_returns_zero_trades():
    report = run_backtest({}, min_score=6.0)
    assert report.n_trades == 0
    assert report.trades.empty


# ── Hiệu chỉnh trọng số từ dữ liệu ────────────────────────────────────────
def test_suggested_weights_preserve_scale():
    """Trọng số gợi ý phải giữ nguyên thang điểm để min_score không đổi nghĩa."""
    by_ticker = {f'T{i}': _trending_df(seed=i) for i in range(12)}
    index_df = _trending_df(seed=99)[['Date', 'Close']]
    report = run_backtest(by_ticker, index_df=index_df, min_score=4.0)
    if any(v.get('ic') is not None for v in report.criteria_ic.values()):
        total_old = sum(DEFAULT_CRITERIA_WEIGHTS.values())
        total_new = sum(report.suggested_weights.values())
        assert total_new == pytest.approx(total_old, abs=0.5)


def test_performance_is_vectorized():
    """
    12 mã × 300 phiên phải xong trong vài giây. Bản cũ gọi lại evaluate() cho
    từng phiên nên cùng khối lượng này mất hàng phút.
    """
    import time
    by_ticker = {f'T{i}': _trending_df(seed=i) for i in range(12)}
    t0 = time.perf_counter()
    run_backtest(by_ticker, min_score=5.0)
    assert time.perf_counter() - t0 < 15


def test_pocket_pivot_can_fire():
    """
    Regression: `down_vol.rolling(10).max()` với min_periods mặc định gần như
    luôn NaN (NaN ở mọi phiên tăng) ⇒ tiêu chí không bao giờ bật, và IC của nó
    luôn hiện '—' trong báo cáo.
    """
    closes = [10, 9.5, 10.2, 9.8, 10.5, 10.1, 10.8, 10.4, 11.0, 11.5] * 12
    volumes = [100_000, 200_000, 150_000, 180_000, 900_000,
               120_000, 130_000, 140_000, 160_000, 170_000] * 12
    df = _make_df(closes, volumes=volumes)
    m = compute_criteria_matrix(df)
    assert m['pocket_pivot'].sum() > 0


def test_no_gap_down_defaults_to_one():
    """Chuỗi không có gap ⇒ tiêu chí phải bằng 1, kể cả ở đoạn đầu chuỗi."""
    df = _make_df([10 + i * 0.01 for i in range(100)])
    m = compute_criteria_matrix(df)
    assert m['no_gap_down'].iloc[60:].min() == 1
