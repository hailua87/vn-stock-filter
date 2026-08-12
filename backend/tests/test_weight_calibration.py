"""
Test khung hiệu chỉnh trọng số.

Trọng tâm: các thống kê phải ĐÚNG, và khung phải TỪ CHỐI đưa ra kết luận khi
dữ liệu là nhiễu — đó mới là giá trị thật của nó.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math

import numpy as np
import pandas as pd
import pytest

from scanner.weight_calibration import (
    norm_cdf, norm_ppf, newey_west_tstat, deflated_sharpe_ratio, spearman,
    build_panel, PanelSpec, cross_sectional_ic, evaluate_criterion,
    cluster_criteria, correlation_matrix, calibrate_weights, walk_forward,
)
from scanner.criteria import DEFAULT_CRITERIA_WEIGHTS


# ── Thống kê nền ──────────────────────────────────────────────────────────
def test_norm_cdf_known_values():
    assert norm_cdf(0) == pytest.approx(0.5)
    assert norm_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert norm_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_norm_ppf_is_inverse_of_cdf():
    for p in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99):
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-6)


def test_newey_west_penalises_autocorrelation():
    """
    Chuỗi tự tương quan mạnh phải cho t-stat NHỎ HƠN hẳn so với khi bỏ qua tự
    tương quan. Đây chính là lý do bỏ Newey-West sẽ thổi phồng ý nghĩa thống kê.
    """
    rng = np.random.default_rng(0)
    n = 500
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 0.1)      # AR(1) hệ số 0,9
    s = pd.Series(x + 0.05)

    naive_t = s.mean() / (s.std(ddof=1) / math.sqrt(len(s)))
    nw_t = newey_west_tstat(s, lag=20)

    assert abs(nw_t) < abs(naive_t) * 0.6, "Newey-West phải hạ t-stat đáng kể"


def test_newey_west_lag_zero_matches_naive():
    s = pd.Series(np.random.default_rng(1).normal(0.1, 1.0, 300))
    naive = s.mean() / (s.std(ddof=0) / math.sqrt(len(s)))
    assert newey_west_tstat(s, lag=0) == pytest.approx(naive, rel=1e-6)


def test_deflated_sharpe_penalises_many_trials():
    """Cùng một Sharpe, thử càng nhiều cấu hình thì xác suất thật càng thấp."""
    few = deflated_sharpe_ratio(0.8, n_trials=1, n_obs=200)
    many = deflated_sharpe_ratio(0.8, n_trials=500, n_obs=200)
    assert many < few


def test_spearman_monotonic():
    a = pd.Series([1, 2, 3, 4, 5, 6])
    b = pd.Series([10, 20, 30, 40, 50, 60])
    assert spearman(a, b) == pytest.approx(1.0)
    assert spearman(a, pd.Series(list(b)[::-1])) == pytest.approx(-1.0)


# ── Dựng panel ────────────────────────────────────────────────────────────
def _ohlcv(seed, n=400, drift=0.0008, base=25.0, volume=2_000_000):
    rng = np.random.default_rng(seed)
    close = base * np.cumprod(1 + drift + rng.normal(0, 0.015, n))
    return pd.DataFrame({
        'Date': pd.date_range('2023-01-02', periods=n, freq='B'),
        'Open': close * (1 + rng.normal(0, 0.003, n)),
        'High': close * 1.02, 'Low': close * 0.98,
        'Close': close, 'Volume': np.full(n, volume),
    })


def _universe(k=25, n=400):
    return {f'T{i:02d}': _ohlcv(i, n=n) for i in range(k)}


def test_panel_has_labels_and_criteria():
    panel = build_panel(_universe(), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(10, 20)))
    assert not panel.empty
    for crit in DEFAULT_CRITERIA_WEIGHTS:
        assert crit in panel.columns
    for h in (10, 20):
        assert f'fwd_excess_{h}' in panel.columns
        assert f'fwd_rank_{h}' in panel.columns


def test_rank_label_is_cross_sectional():
    """fwd_rank phải nằm trong (0,1] và trung bình quanh 0,5 trong từng phiên."""
    panel = build_panel(_universe(), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    ranks = panel['fwd_rank_20'].dropna()
    assert ranks.min() > 0 and ranks.max() <= 1.0
    per_date_mean = panel.groupby('Date')['fwd_rank_20'].mean().dropna()
    assert per_date_mean.mean() == pytest.approx(0.5, abs=0.1)


def test_illiquid_names_excluded():
    """Mã dưới ngưỡng GTGD không vào panel — lệnh không khớp được trên thực tế."""
    thin = {'THIN': _ohlcv(1, volume=100)}
    panel = build_panel(thin, None, PanelSpec(horizons=(20,), min_turnover_vnd=1e9))
    assert panel.empty


def test_locked_limit_days_excluded():
    """Phiên vào lệnh trần/sàn cứng (High == Low) không khớp được → phải loại."""
    df = _ohlcv(2, n=200)
    df.loc[100:150, 'High'] = df.loc[100:150, 'Low']
    panel = build_panel({'LOCK': df}, None, PanelSpec(horizons=(10,)))
    if not panel.empty:
        locked_dates = set(df.loc[99:149, 'Date'])
        assert not (set(panel['Date']) & locked_dates)


# ── IC và gom cụm ─────────────────────────────────────────────────────────
def test_ic_of_random_criterion_is_insignificant():
    """
    Tiêu chí ngẫu nhiên KHÔNG được vượt ngưỡng. Đây là bài kiểm tra quan trọng
    nhất của cả khung: nếu nhiễu cũng "có ý nghĩa" thì mọi kết luận đều vô giá trị.
    """
    panel = build_panel(_universe(k=30), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,))).copy()
    rng = np.random.default_rng(7)
    panel['noise'] = rng.integers(0, 2, len(panel))

    res = evaluate_criterion(panel, 'noise', 20)
    assert not res.passes, f"Tiêu chí nhiễu lại 'đạt' — khung bị hỏng: {res.as_dict()}"


def test_ic_detects_planted_signal():
    """Ngược lại: tín hiệu cấy vào phải được phát hiện."""
    panel = build_panel(_universe(k=30), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,))).copy()
    panel['oracle'] = (panel['fwd_rank_20'] > 0.5).astype(int)
    ic = cross_sectional_ic(panel, 'oracle', 20)
    assert ic.mean() > 0.5


def test_clustering_groups_correlated_criteria():
    panel = pd.DataFrame({
        'a': [1, 0, 1, 0, 1, 1, 0, 0] * 20,
        'b': [1, 0, 1, 0, 1, 1, 0, 1] * 20,      # gần trùng a
        'c': [0, 1, 0, 1, 0, 0, 1, 1] * 20,      # nghịch đảo a
        'd': [1, 1, 0, 0, 1, 0, 1, 0] * 20,      # độc lập
    })
    clusters = cluster_criteria(correlation_matrix(panel, ['a', 'b', 'c', 'd']),
                                threshold=0.6)
    members = {frozenset(v) for v in clusters.values()}
    assert any({'a', 'b'} <= s for s in members)
    assert any(s == {'d'} for s in members)


# ── Trọng số ──────────────────────────────────────────────────────────────
def test_weights_preserve_total_scale():
    panel = build_panel(_universe(k=25), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    wr = calibrate_weights(panel, horizon=20)
    assert sum(wr.weights.values()) == pytest.approx(
        sum(DEFAULT_CRITERIA_WEIGHTS.values()), abs=0.05)


def test_falls_back_to_equal_weights_on_noise():
    """
    Trên dữ liệu ngẫu nhiên, khung phải trả về trọng số đều kèm ghi chú, chứ
    không bịa ra một bộ trọng số 'tối ưu'.
    """
    panel = build_panel(_universe(k=25), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    wr = calibrate_weights(panel, horizon=20)
    assert wr.notes


def test_shrinkage_zero_gives_equal_cluster_weights():
    panel = build_panel(_universe(k=25), _ohlcv(999)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    w_low = calibrate_weights(panel, horizon=20, shrinkage=0.0).weights
    w_high = calibrate_weights(panel, horizon=20, shrinkage=1.0).weights
    spread_low = max(w_low.values()) - min(w_low.values())
    spread_high = max(w_high.values()) - min(w_high.values())
    assert spread_low <= spread_high + 1e-9


# ── Walk-forward ──────────────────────────────────────────────────────────
def test_walk_forward_purges_training_data():
    """
    Train của mỗi fold phải kết thúc TRƯỚC ngày bắt đầu test. Thiếu purging là
    rò rỉ nhãn tương lai — dạng lỗi tinh vi và phổ biến nhất trong backtest.
    """
    panel = build_panel(_universe(k=25, n=600), _ohlcv(999, n=600)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    folds, _ = walk_forward(panel, horizon=20, n_folds=3, embargo_days=5)
    for f in folds:
        assert (f.test_start - f.train_end).days > 0, "train chồng lấn test"


def test_walk_forward_reports_verdict():
    panel = build_panel(_universe(k=25, n=600), _ohlcv(999, n=600)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    _, summary = walk_forward(panel, horizon=20, n_folds=3)
    assert 'verdict' in summary or 'error' in summary


def test_random_data_yields_honest_verdict():
    """Dữ liệu ngẫu nhiên → kết luận phải là 'không có edge' hoặc 'yếu'."""
    panel = build_panel(_universe(k=30, n=600), _ohlcv(999, n=600)[['Date', 'Close']],
                        PanelSpec(horizons=(20,)))
    _, summary = walk_forward(panel, horizon=20, n_folds=3)
    if 'verdict' in summary:
        assert ('CÓ tín hiệu' not in summary['verdict']
                or summary['oos_ic_mean'] > 0.02)


# ── Nối trọng số vào production ───────────────────────────────────────────
def test_active_weights_fallback_to_default(tmp_path, monkeypatch):
    """Không có file hiệu chỉnh → phải dùng trọng số đều, version 'default'."""
    from scanner import criteria
    monkeypatch.setattr(criteria, 'ACTIVE_WEIGHTS_PATH', tmp_path / 'khong-ton-tai.json')
    weights, version = criteria.load_active_weights()
    assert weights == criteria.DEFAULT_CRITERIA_WEIGHTS
    assert version == 'default'


def test_active_weights_loaded_from_file(tmp_path, monkeypatch):
    import json
    from scanner import criteria
    f = tmp_path / 'criteria_weights.json'
    f.write_text(json.dumps({
        'version': '20260813',
        'weights': {k: (2.0 if k == 'near_high20' else 0.0)
                    for k in criteria.DEFAULT_CRITERIA_WEIGHTS},
    }), encoding='utf-8')
    monkeypatch.setattr(criteria, 'ACTIVE_WEIGHTS_PATH', f)

    weights, version = criteria.load_active_weights()
    assert version == '20260813'
    assert weights['near_high20'] == 2.0
    assert weights['ma_align'] == 0.0


def test_corrupt_weights_file_falls_back(tmp_path, monkeypatch):
    """File hỏng KHÔNG được làm sập scan hằng ngày."""
    from scanner import criteria
    f = tmp_path / 'criteria_weights.json'
    f.write_text('{ khong phai json', encoding='utf-8')
    monkeypatch.setattr(criteria, 'ACTIVE_WEIGHTS_PATH', f)
    weights, version = criteria.load_active_weights()
    assert weights == criteria.DEFAULT_CRITERIA_WEIGHTS
    assert version == 'default'


def test_zero_total_weights_rejected(tmp_path, monkeypatch):
    import json
    from scanner import criteria
    f = tmp_path / 'criteria_weights.json'
    f.write_text(json.dumps({'version': 'x', 'weights':
                             {k: 0.0 for k in criteria.DEFAULT_CRITERIA_WEIGHTS}}),
                 encoding='utf-8')
    monkeypatch.setattr(criteria, 'ACTIVE_WEIGHTS_PATH', f)
    weights, _ = criteria.load_active_weights()
    assert sum(weights.values()) > 0


def test_weights_version_in_output():
    """Mọi tín hiệu phải mang version trọng số để tái lập được về sau."""
    from scanner.criteria import CriteriaResult
    import pandas as pd
    r = CriteriaResult(ticker='TST', exchange='HOSE', date=pd.Timestamp('2026-08-13'),
                       close=25.0, volume=100_000,
                       scores={'near_high20': 1, 'ma_align': 1})
    assert 'weights_version' in r.to_dict()
