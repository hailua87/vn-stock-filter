"""
Phase 1 — adapter BCTC → schema chỉ tiêu và pipeline run_quality.build_quality.

Fixture lấy từ BCTC vnstock 4.0.7 (năm và quý) của FPT (phi tài chính), VCB
(ngân hàng), SSI (chứng khoán), ĐÃ BIẾN ĐỔI theo fixture_scale.py. Số đọc tay
từ BCTC thật (số tuyệt đối trong test nhân thêm FIXTURE_SCALE, tỷ lệ giữ nguyên):
  FPT 2025: LN trước thuế 13.043,63; chi phí lãi vay −809,76 → EBIT 13.853,39
            vay ngắn hạn 19.169,7 + dài hạn 1.903,8 = 21.073,5
  SSI 2025: môi giới 2.344,72 + lãi cho vay 3.562,01 trên doanh thu HĐ 12.930,74
  VCB 2025: tổng TN hoạt động 72.454,62 − TN lãi thuần 58.771,41 = 13.683,21
"""
import copy
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_scale import FIXTURE_SCALE  # fixture đã biến đổi, xem fixture_scale.py

from run_quality import build_quality, write_outputs
from scanner.financial_fetcher import statement_to_records
from scanner.quality import adapter, governance, metrics
from scanner.quality import config as C

FIX = Path(__file__).resolve().parent / 'fixtures'
AS_OF = date(2026, 9, 22)


def raw(ticker, period):
    r = json.loads((FIX / f'vnstock407_{ticker}_{period}.json').read_text(encoding='utf-8'))
    out = {k: statement_to_records(pd.DataFrame(v['data'], columns=v['columns']))
           for k, v in r.items() if k != 'ratio'}
    out.update({'ticker': ticker, 'period': period, 'fetched_at': '2026-09-22T10:00:00'})
    return out


# --- Adapter ----------------------------------------------------------------

def test_annual_schema_is_old_to_new_with_eight_years():
    a = adapter.annual_schema(raw('FPT', 'year'))
    assert a['period_end'] == [f'{y}-12-31' for y in range(2018, 2026)]
    assert a['revenue'][0] < a['revenue'][-1]            # chuỗi tăng: đúng chiều
    assert a['ebit'][-1] == pytest.approx((13_043.63 + 809.76) * FIXTURE_SCALE, abs=0.01)
    assert a['debt'][-1] == pytest.approx((19_169.7 + 1_903.8) * FIXTURE_SCALE, abs=0.1)


def test_revenue_cagr_through_adapter_matches_hand_calc():
    m = metrics.compute('NON_FINANCIAL', adapter.annual_schema(raw('FPT', 'year')))
    assert m['revenue_cagr5'] == pytest.approx((70_112.8 / 29_830.4) ** 0.2 - 1, abs=1e-3)


def test_bank_fields_and_missing_nim_are_none_not_zero():
    a = adapter.annual_schema(raw('VCB', 'year'))
    assert a['nonint_income'][-1] == pytest.approx((72_454.62 - 58_771.41) * FIXTURE_SCALE, abs=0.01)
    # NIM không có trong 3 bảng BCTC; phải đổ vào từ nguồn KBS (D24).
    assert a['nim'] == [None] * 8
    m = metrics.compute('BANK', a)
    assert m['nim_std'] is None
    assert m['equity_assets'] is not None


def test_npl_fields_are_gone_from_the_bank_model():
    """
    Tỷ lệ nợ xấu và bao phủ nợ xấu đã gỡ 24/09/2026 (D24): không nguồn nào có.
    Để chúng lại với giá trị None vĩnh viễn là kéo độ phủ xuống dưới ngưỡng và
    khóa cả 18 ngân hàng ở "Thiếu dữ liệu" — mà không nói vì sao.
    """
    keys = {k for specs in C.MODELS['BANK'].values() for k, _, _ in specs}
    assert 'npl_ratio' not in keys and 'npl_coverage' not in keys
    m = metrics.compute('BANK', adapter.annual_schema(raw('VCB', 'year')))
    assert 'npl_ratio' not in m and 'npl_coverage' not in m
    # Gỡ mà không ghi lại thì lần sau có người tưởng là quên làm.
    assert set(C.BANK_NOT_EVALUATED) == {'npl_ratio', 'npl_coverage'}


def test_attaching_kbs_nim_makes_the_quality_dimension_scoreable():
    """
    Trước khi nối KBS: độ phủ Chất lượng của ngân hàng là 3/4 chỉ tiêu vì thiếu
    nim_std. Sau khi nối: đủ 4/4.

    KBS trả PHẦN TRĂM (2,64 = 2,64%); mọi chỉ tiêu khác trong hệ thống là tỷ lệ,
    nên adapter phải chia 100 — không thì NIM hiện thành 264% trên màn hình.
    """
    a = adapter.annual_schema(raw('VCB', 'year'))
    years = [int(str(p)[:4]) for p in a['period_end'] if p]
    kbs = {'nim': {y: 2.5 + i * 0.3 for i, y in enumerate(years[-4:])}}
    adapter.attach_bank_ratios(a, kbs)

    assert a['nim'][-1] == pytest.approx((2.5 + 3 * 0.3) / 100)   # đã đổi sang tỷ lệ
    assert a['nim'][0] is None                                     # năm KBS không phủ
    assert metrics.compute('BANK', a)['nim_std'] is not None


def test_attach_bank_ratios_is_a_no_op_without_data():
    a = adapter.annual_schema(raw('VCB', 'year'))
    for empty in (None, {}, {'nim': {}}):
        adapter.attach_bank_ratios(a, empty)
        assert a['nim'] == [None] * 8


def test_securities_recurring_share():
    m = metrics.compute('SECURITIES', adapter.annual_schema(raw('SSI', 'year')))
    assert m['recurring_share'] == pytest.approx((2_344.72 + 3_562.01) / 12_930.74, abs=1e-3)


@pytest.mark.parametrize('ticker', ['FPT', 'VCB', 'SSI'])
def test_quarterly_values_are_per_quarter_not_cumulative(ticker):
    """Tổng 4 quý 2025 phải bằng số năm 2025 — nếu vnstock trả lũy kế thì lệch."""
    a = adapter.annual_schema(raw(ticker, 'year'))
    gi = adapter.governance_inputs(a, raw(ticker, 'quarter'))
    q = raw(ticker, 'quarter')['income']
    ni_2025 = [adapter._pick(r, adapter.ITEMS['net_income'][1]) for r in q
               if r['period'].startswith('2025')]
    assert len(ni_2025) == 4
    assert sum(ni_2025) == pytest.approx(a['net_income'][-1], rel=1e-6)
    assert gi['latest_quarter_end'] == date(2026, 6, 30)
    assert len(gi['ni_q']) == len(gi['cfo_q']) == 8


def test_governance_full_coverage_needs_quarterly_data():
    """Không có BCTC quý thì chỉ tính được 2/3 cờ bật → 67% < 70% → Quản trị trống."""
    a = adapter.annual_schema(raw('FPT', 'year'))
    with_q = governance.score(adapter.governance_inputs(a, raw('FPT', 'quarter')), AS_OF)
    without_q = governance.score(adapter.governance_inputs(a, None), AS_OF)
    assert with_q['coverage'] == 1.0 and with_q['score'] is not None
    assert without_q['score'] is None and 'late_filing' in without_q['missing']


# --- Pipeline ----------------------------------------------------------------

def _scaled(base, ticker, factor):
    """Bản sao BCTC FPT nhân hệ số để có nhóm ≥ 8 mã với giá trị khác nhau."""
    r = copy.deepcopy(base)
    r['ticker'] = ticker
    for table in ('income', 'balance_sheet', 'cash_flow'):
        for rec in r[table]:
            for k, v in list(rec.items()):
                if k != 'period' and isinstance(v, float):
                    # doanh thu và LN tăng theo hệ số khác nhau → biên, CAGR khác nhau
                    rec[k] = v * (factor if k in ('net_sales', 'gross_profit') else 1.0)
    r['overview'] = {'industry': 'Technology'}
    return r


@pytest.fixture
def universe():
    fpt_y, fpt_q = raw('FPT', 'year'), raw('FPT', 'quarter')
    years = {f'T{i:02d}': _scaled(fpt_y, f'T{i:02d}', 1 + i * 0.05) for i in range(10)}
    quarters = {t: dict(fpt_q, ticker=t) for t in years}
    vcb = raw('VCB', 'year'); vcb['overview'] = {'industry': 'Banks'}
    years['VCB'], quarters['VCB'] = vcb, raw('VCB', 'quarter')
    # Ma thu duong "mo hinh nganh chua kich hoat". Truoc 23/09/2026 dung
    # 'Real Estate'; nay nganh do da co mo hinh nen phai doi sang Insurance —
    # nganh duy nhat con lai chua bat. Khong doi thi test nay im lang chuyen
    # sang do mot duong khac han.
    ins = copy.deepcopy(fpt_y); ins['overview'] = {'industry': 'Insurance'}
    years['REX'], quarters['REX'] = ins, fpt_q
    years['FLC'], quarters['FLC'] = _scaled(fpt_y, 'FLC', 1.0), fpt_q    # có trong danh sách hủy niêm yết
    return years, quarters


def _run(universe, valuation=None, previous=None, drop_quarter=()):
    years, quarters = universe
    tickers = list(years) + ['NODATA']
    seen = []
    payload = build_quality(
        tickers,
        fetch_year=lambda t: years.get(t),
        fetch_quarter=lambda t: None if t in drop_quarter else quarters.get(t),
        valuation_signals=valuation or {}, as_of=AS_OF,
        delisted={'FLC'}, previous=previous or {},
        on_fetched=seen.append)
    return {it['ticker']: it for it in payload['items']}, payload, seen


def test_pipeline_statuses_and_reasons(universe):
    items, payload, seen = _run(universe)
    assert payload['metadata']['failures'] == [{'ticker': 'NODATA', 'reason': 'Không lấy được BCTC năm'}]
    assert items['FLC']['status'] == 'EXC' and 'Hủy niêm yết' in items['FLC']['reason']
    assert items['REX']['status'] == 'RES' and items['REX']['reason'] == 'Mô hình ngành chưa kích hoạt'
    # Ngân hàng đứng một mình: nhóm < 8 mã và thiếu NPL/NIM → thiếu dữ liệu
    assert items['VCB']['model'] == 'BANK' and items['VCB']['status'] == 'RES'
    # Nhóm phi tài chính 11 mã (T00–T09 + FLC) có percentile và điểm
    t = items['T05']
    assert t['model'] == 'NON_FINANCIAL'
    assert all(t['dims'][d]['score'] is not None for d in ('quality', 'growth', 'resilience', 'governance'))
    assert t['status'] in ('QUAL', 'MON', 'REV')
    assert t['latest_annual'] == '2025-12-31' and t['latest_quarter'] == '2026-06-30'
    # Mỗi mã có dữ liệu được báo lại 2 lần (năm + quý) để ghi sổ snapshot
    assert len(seen) == 2 * (len(universe[0]))


def test_percentile_direction_follows_metric(universe):
    """Doanh thu nhân hệ số 1,00 → 1,45 còn tổng tài sản giữ nguyên, nên vòng quay
    tài sản tăng dần T00 → T09: percentile phải tăng đúng chiều (cao hơn tốt hơn)."""
    items, _, _ = _run(universe)
    turnover = [items[f'T{i:02d}']['metrics']['asset_turnover'] for i in range(10)]
    assert turnover == sorted(turnover)
    pct = [items[f'T{i:02d}']['percentiles']['asset_turnover'] for i in range(10)]
    assert pct == sorted(pct) and pct[0] < pct[-1]


def test_missing_quarterly_blanks_governance(universe):
    items, _, _ = _run(universe, drop_quarter={'T03'})
    assert items['T03']['dims']['governance']['score'] is None
    assert items['T03']['status'] == 'RES' and 'Quản trị' in items['T03']['reason']


def test_valuation_band_feeds_status(universe):
    val = {'T05': {'ticker': 'T05', 'upside_pct': 30.0, 'confidence': 70.0,
                   'methods_conflict': False, 'guard_reason': None,
                   'method_details': [{'method': 'P/E Multiple', 'weight': 40}]}}
    items, _, _ = _run(universe, valuation=val)
    assert items['T05']['valuation']['band'] == 'ATTRACTIVE'
    assert items['T06']['valuation']['band'] == 'NOT_AVAILABLE'
    assert items['T06']['valuation']['reason'] == 'Không có trong đầu ra định giá tuần này'


def test_sharp_drop_flag_against_previous(universe):
    items, _, _ = _run(universe)
    q = items['T05']['dims']['quality']['score']
    items2, _, _ = _run(universe, previous={'T05': {'quality': q + 20}})
    assert items2['T05']['sharp_drops'] == ['quality']


def test_write_outputs_latest_archive_index(universe, tmp_path):
    _, payload, _ = _run(universe)
    write_outputs(payload, tmp_path)
    latest = json.loads((tmp_path / 'quality' / 'latest.json').read_text(encoding='utf-8'))
    assert latest['as_of'] == '2026-09-22' and latest['schema'] == 1
    assert (tmp_path / 'quality' / 'archive' / '2026-09-22.json').exists()
    idx = json.loads((tmp_path / 'quality' / 'archive' / 'index.json').read_text(encoding='utf-8'))
    assert idx['latest'] == '2026-09-22' and idx['dates'] == ['2026-09-22']
    assert 'không phải toàn thị trường' in latest['metadata']['note']


# --- Pha loãng chỉ tính phát hành lấy tiền (v3 D18) --------------------------

@pytest.mark.parametrize('ticker,expected_cagr,flag', [
    # VCB 2025: vốn góp 55.891 → 83.557 tỷ, tiền thu phát hành 0 → cổ tức CP, không pha loãng
    ('VCB', 0.0, 'none'),
    # FPT 2023–25: vốn tăng 1.729 / 2.011 / 2.324 tỷ, tiền thu 73,1 / 163,3 / 1.196,2 tỷ
    #   → (1+73,1/10.970,3)(1+163,3/12.699,7)(1+1.196,2/14.710,7) ≈ 1,1025 → 3,31%/năm
    ('FPT', 0.0331, 'none'),
    # SSI 2023–25: tiền thu 100 / 2.363,7 / 3.356,1 (năm 2025 vượt phần vốn tăng 1.140 → tính đủ)
    ('SSI', 0.0723, 'mild'),
])
def test_dilution_counts_only_cash_issuance(ticker, expected_cagr, flag):
    from scanner.quality.metrics import cagr
    a = adapter.annual_schema(raw(ticker, 'year'))
    gi = adapter.governance_inputs(a, raw(ticker, 'quarter'))
    assert cagr(gi['shares_annual'], 3) == pytest.approx(expected_cagr, abs=5e-4)
    assert governance.dilution_flag(gi['shares_annual']) == flag
    # Tổng số CP (gồm cổ tức cổ phiếu) tăng mạnh hơn nhiều — cờ cũ sẽ bắt nhầm
    assert cagr(a['shares_outstanding'], 3) > 0.10


def test_missing_proceeds_in_year_with_capital_increase_is_unknown():
    out = adapter.cash_issued_shares([100.0, 120.0], [1.0, 1.2], [0.0, None])
    assert out == [100.0, None]


def test_buyback_reduces_shares():
    out = adapter.cash_issued_shares([100.0, 90.0], [1.0, 0.9], [0.0, 0.0])
    assert out == [100.0, pytest.approx(90.0)]


def test_metadata_exports_model_specs_for_web(universe):
    """Web đọc ngưỡng và danh sách chỉ tiêu từ JSON, không chép lại cấu hình."""
    from scanner.quality import config as C
    _, payload, _ = _run(universe)
    m = payload['metadata']
    assert m['thresholds']['qualify'] == C.QUALIFY
    spec = m['model_specs']['NON_FINANCIAL']['quality']
    assert [s['key'] for s in spec] == [k for k, _, _ in C.MODELS['NON_FINANCIAL']['quality']]
    assert set(m['model_specs']) == C.ACTIVE_MODELS
    json.dumps(m)                                   # ghi được ra JSON
