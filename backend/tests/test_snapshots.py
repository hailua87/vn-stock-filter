"""
Sổ đăng ký snapshot BCTC (audit F3, blueprint §5.2 mục 3–4).

Dữ liệu là record theo kỳ của FPT (fixture vnstock 4.0.7 đã biến đổi, 8 năm 2018–2025).
"""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import financial_fetcher as ff
from scanner.snapshots import load_registry, period_hashes, record_snapshot
from test_fundamentals_long_format import _load

YEARS = [str(y) for y in range(2018, 2026)]


def _fpt(drop_latest=False):
    frames = _load('FPT')
    res = {'ticker': 'FPT', 'period': 'year', 'vnstock_version': '4.0.7'}
    for t in ('balance_sheet', 'income', 'cash_flow'):
        recs = ff.statement_to_records(frames[t])
        res[t] = recs[1:] if drop_latest else recs
    return res


def test_first_run_registers_every_period(tmp_path):
    reg_path = tmp_path / 'reg.json'
    assert record_snapshot(_fpt(), reg_path, today='2026-09-21') == {'new': 8, 'revised': 0}
    e = load_registry(reg_path)['tickers']['FPT']['year']
    assert sorted(e) == YEARS
    assert all(v['first_seen'] == '2026-09-21' for v in e.values())
    assert e['2025']['revisions'][0]['vnstock'] == '4.0.7'


def test_same_content_later_only_moves_last_seen(tmp_path):
    reg_path = tmp_path / 'reg.json'
    record_snapshot(_fpt(), reg_path, today='2026-09-21')
    assert record_snapshot(_fpt(), reg_path, today='2026-09-28') == {'new': 0, 'revised': 0}
    e = load_registry(reg_path)['tickers']['FPT']['year']['2024']
    assert (e['first_seen'], e['last_seen'], len(e['revisions'])) == ('2026-09-21', '2026-09-28', 1)


def test_new_period_gets_its_own_first_seen(tmp_path):
    """Cơ sở cho cờ 'công bố chậm' và veto 'thiếu hai quý'."""
    reg_path = tmp_path / 'reg.json'
    record_snapshot(_fpt(drop_latest=True), reg_path, today='2026-03-01')
    assert record_snapshot(_fpt(), reg_path, today='2026-04-05') == {'new': 1, 'revised': 0}
    e = load_registry(reg_path)['tickers']['FPT']['year']
    assert e['2025']['first_seen'] == '2026-04-05'
    assert e['2024']['first_seen'] == '2026-03-01'


def test_restated_figures_are_detected(tmp_path):
    reg_path = tmp_path / 'reg.json'
    record_snapshot(_fpt(), reg_path, today='2026-09-21')
    restated = _fpt()
    rec_2024 = next(r for r in restated['income'] if r['period'] == '2024')
    rec_2024['net_sales'] *= 1.25  # sửa số hồi tố 25%
    assert record_snapshot(restated, reg_path, today='2026-09-28') == {'new': 0, 'revised': 1}
    e = load_registry(reg_path)['tickers']['FPT']['year']
    assert [r['date'] for r in e['2024']['revisions']] == ['2026-09-21', '2026-09-28']
    assert len(e['2023']['revisions']) == 1


def test_float_noise_does_not_look_like_a_restatement():
    a = _fpt()
    b = copy.deepcopy(a)
    b['income'][0]['net_sales'] += 1e-9  # < 1 đồng khi đơn vị là tỷ
    assert period_hashes(a) == period_hashes(b)


def test_registry_holds_no_financial_figures(tmp_path):
    """Repo public, blueprint §4.2: không phân phối lại số liệu thô."""
    reg_path = tmp_path / 'reg.json'
    record_snapshot(_fpt(), reg_path, today='2026-09-21')
    text = reg_path.read_text(encoding='utf-8')
    assert '70112' not in text and 'net_sales' not in text  # doanh thu FPT 2025
    entry = json.loads(text)['tickers']['FPT']['year']['2025']
    assert set(entry) == {'first_seen', 'last_seen', 'hash', 'revisions'}
