"""
Cắt lỗ / mục tiêu / R:R (blueprint v3 §7.3, §14.4 — audit F5).

Số kiểm tay lấy từ TIP phiên 22/09/2026 trong web/data/latest.json:
  giá 16,35 · hỗ trợ 16,21 và 15,60 · kháng cự 16,59 / 16,90 / 17,21
  → cắt lỗ 16,21; mục tiêu 16,59; R:R = (16,59 − 16,35) / (16,35 − 16,21) = 1,71
"""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner import trade_levels as TL

SUP = [{'price': 16.21}, {'price': 15.60}]
RES = [{'price': 16.59}, {'price': 16.90}, {'price': 17.21}]


def test_nearest_levels_and_rr_from_real_signal():
    out = TL.levels_for(16.35, SUP, RES)
    assert (out['stop'], out['target']) == (16.21, 16.59)
    assert out['rr'] == pytest.approx(1.71, abs=0.01)
    assert out['levels_note'] is None and out['suppress_signal'] is False


def test_levels_ignore_wrong_side_even_if_closer():
    """Hỗ trợ phải DƯỚI giá, kháng cự phải TRÊN giá — kể cả khi mức sai phía gần hơn."""
    out = TL.levels_for(16.35, [{'price': 16.34}, {'price': 16.50}], [{'price': 16.30}, {'price': 16.59}])
    assert out['stop'] == 16.34 and out['target'] == 16.59


@pytest.mark.parametrize('sup,res,missing', [
    ([], RES, 'hỗ trợ dưới giá'),
    (SUP, [], 'kháng cự trên giá'),
    ([{'price': 17.0}], RES, 'hỗ trợ dưới giá'),     # chỉ có hỗ trợ nằm trên giá
])
def test_missing_side_gives_no_rr_and_says_why(sup, res, missing):
    out = TL.levels_for(16.35, sup, res)
    assert out['rr'] is None and missing in out['levels_note']


def test_ceiling_has_no_levels():
    out = TL.levels_for(16.35, SUP, RES, limit_status='ceiling')
    assert out['stop'] is None and out['target'] is None and out['rr'] is None
    assert out['levels_note'] == TL.CEILING_NOTE and out['suppress_signal'] is False


def test_floor_marks_signal_suppressed():
    out = TL.levels_for(16.35, SUP, RES, limit_status='floor')
    assert out['suppress_signal'] is True and out['levels_note'] == TL.FLOOR_NOTE


def test_zero_risk_gives_no_rr():
    """Giá bằng đúng hỗ trợ: chia cho 0 → R:R để trống, không phải vô cực."""
    out = TL.levels_for(16.21, [{'price': 16.21}], RES)
    assert out['stop'] is None and out['rr'] is None


def test_attach_updates_metrics_of_each_result():
    results = [
        SimpleNamespace(ticker='TIP', close=16.35,
                        metrics={'supports': SUP, 'resistances': RES, 'limit_status': 'normal'}),
        SimpleNamespace(ticker='XXX', close=10.0,
                        metrics={'supports': [], 'resistances': [], 'limit_status': 'ceiling'}),
        SimpleNamespace(ticker='NOMETRICS', close=1.0, metrics=None),
    ]
    TL.attach(results)
    assert results[0].metrics['rr'] == pytest.approx(1.71, abs=0.01)
    assert results[1].metrics['levels_note'] == TL.CEILING_NOTE
    assert results[2].metrics is None                      # không làm hỏng kết quả lạ


def test_scanner_attaches_levels_to_dataframe(monkeypatch):
    """Đi qua BreakoutScanner: metrics → cột m_stop / m_target / m_rr trong JSON."""
    import pandas as pd
    from scanner import scanner as sc

    class R:
        def __init__(self):
            self.ticker, self.close, self.total_score = 'TIP', 16.35, 7
            self.metrics = {'supports': SUP, 'resistances': RES, 'limit_status': 'normal'}

        def to_dict(self):
            return {'ticker': self.ticker, 'close': self.close,
                    'total_score': self.total_score,
                    **{f'm_{k}': v for k, v in self.metrics.items()}}

    monkeypatch.setattr(sc, 'evaluate', lambda df, tk, cfg: R())
    df = pd.DataFrame({'Ticker': ['TIP'], 'Date': ['2026-09-22']})
    out = sc.BreakoutScanner(fetch_corporate_actions=False).scan_from_dataframe(df)
    assert out.iloc[0]['m_stop'] == 16.21
    assert out.iloc[0]['m_target'] == 16.59
    assert out.iloc[0]['m_rr'] == pytest.approx(1.71, abs=0.01)
