"""
Test loi cham diem Module B (scanner/quality). Du lieu tong hop, khong can mang.

Moi test kiem mot quy tac trong docs/BLUEPRINT_v3.md; ten test noi quy tac do.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner.quality import config as C
from scanner.quality import governance as G
from scanner.quality import metrics as M
from scanner.quality import scoring as S
from scanner.quality import status as ST


# --- metrics ---------------------------------------------------------------

def test_cagr_can_du_years_cong_1_diem():
    # 5 diem chi du 4 nam: financial_fetcher hien cat head(5) nen CAGR 5 nam luon None
    assert M.cagr([100, 110, 121, 133.1, 146.41], 5) is None
    assert M.cagr([100, 110, 121, 133.1, 146.41, 161.051], 5) == pytest.approx(0.10)


def test_cagr_dau_ky_am_hoac_bang_0_la_thieu():
    assert M.cagr([-10, 5, 8, 9, 10, 12], 5) is None
    assert M.cagr([0, 5, 8, 9, 10, 12], 5) is None


def test_cagr_doc_theo_chieu_cu_sang_moi():
    # Chuoi giam ro rang: neu adapter quen dao chieu vnstock (moi truoc) CAGR se doi dau
    assert M.cagr([200, 180, 160, 140, 120, 100], 5) < 0


def test_profit_drawdown_bo_qua_dinh_am():
    assert M.profit_drawdown([100, 120, 90, 130, 140]) == pytest.approx(0.25)
    assert M.profit_drawdown([-50, -80, -20, -10]) == 0.0
    # dinh bang 0 khong duoc lam chia cho 0
    assert M.profit_drawdown([0, -10, 5, 4]) == pytest.approx(0.2)
    assert M.profit_drawdown([100, 90]) is None


def _annual(n=6, g=0.1):
    base = [1000 * (1 + g) ** i for i in range(n)]
    return {
        'period_end': [f'{2020 + i}-12-31' for i in range(n)],
        'revenue': base,
        'gross_profit': [v * 0.3 for v in base],
        'ebit': [v * 0.15 for v in base],
        'net_income': [v * 0.1 for v in base],
        'cfo': [v * 0.12 for v in base],
        'capex': [-v * 0.05 for v in base],
        'depreciation': [v * 0.03 for v in base],
        'total_assets': [v * 1.2 for v in base],
        'equity': [v * 0.6 for v in base],
        'debt': [v * 0.2 for v in base],
        'cash': [v * 0.1 for v in base],
        'current_assets': [v * 0.5 for v in base],
        'current_liabilities': [v * 0.3 for v in base],
        'interest_expense': [v * 0.01 for v in base],
        'shares_outstanding': [100] * n,
    }


def test_non_financial_du_6_nam_tinh_du_chi_tieu():
    m = M.non_financial(_annual())
    assert m['revenue_cagr5'] == pytest.approx(0.10)
    assert m['revenue_up_years5'] == 1.0
    assert m['gross_margin_std5'] == pytest.approx(0.0, abs=1e-12)
    assert m['cash_conversion3'] == pytest.approx(1.2)
    assert m['interest_coverage'] == pytest.approx(15.0)
    assert all(v is not None for v in m.values())


def test_non_financial_5_nam_thi_growth_thieu():
    m = M.non_financial(_annual(n=5))
    assert m['revenue_cagr5'] is None and m['ebit_cagr5'] is None and m['cfo_cagr5'] is None


def test_khong_vay_no_thi_interest_coverage_chan_tran():
    a = _annual()
    a['interest_expense'] = [0] * 6
    assert M.non_financial(a)['interest_coverage'] == 100.0


# --- scoring ---------------------------------------------------------------

def test_nhom_nho_hon_min_peer_khong_co_percentile():
    vals = {f'T{i}': float(i) for i in range(C.MIN_PEER_GROUP - 1)}
    assert all(v is None for v in S.percentiles(vals, True).values())


def test_percentile_dao_chieu_khi_thap_hon_tot_hon():
    vals = {f'T{i}': float(i) for i in range(10)}
    hi, lo = S.percentiles(vals, True), S.percentiles(vals, False)
    assert hi['T9'] == 100 and hi['T0'] == 0
    assert lo['T9'] == 0 and lo['T0'] == 100


def test_gia_tri_bang_nhau_nhan_hang_trung_binh():
    vals = {f'T{i}': (5.0 if i < 2 else float(i)) for i in range(10)}
    p = S.percentiles(vals, True)
    # ba gia tri 5.0 (T0, T1, T5) o vi tri 3,4,5 trong 10 -> hang trung binh 4 -> 44.4
    assert p['T0'] == p['T1'] == p['T5'] == pytest.approx(4 / 9 * 100, abs=0.1)


def test_thieu_gia_tri_van_la_none_khong_bi_gan_trung_tinh():
    vals = {f'T{i}': float(i) for i in range(10)}
    vals['X'] = None
    assert S.percentiles(vals, True)['X'] is None


def test_do_phu_tinh_theo_trong_so():
    spec = [('a', 60, True), ('b', 30, True), ('c', 10, True)]
    ok = S.dimension({'a': 80, 'b': None, 'c': 40}, spec)
    assert ok['coverage'] == 0.7 and ok['score'] == pytest.approx((60 * 80 + 10 * 40) / 70, abs=0.1)
    under = S.dimension({'a': None, 'b': 90, 'c': 90}, spec)
    assert under['score'] is None and under['missing'] == ['a']


# --- governance ------------------------------------------------------------

AS_OF = date(2026, 9, 21)


def test_quy_le_ra_phai_co():
    assert G.expected_latest_quarter(AS_OF) == date(2026, 6, 30)
    # 10/08: Q2 chua qua han 45 ngay -> van la Q1
    assert G.expected_latest_quarter(date(2026, 8, 10)) == date(2026, 3, 31)


def test_dem_quy_thieu():
    assert G.quarters_missing(date(2026, 6, 30), AS_OF) == 0
    assert G.quarters_missing(date(2026, 3, 31), AS_OF) == 1
    assert G.quarters_missing(date(2025, 12, 31), AS_OF) == 2
    assert G.quarters_missing(None, AS_OF) is None


def test_co_tat_khong_nam_trong_mau_so_do_phu():
    inp = {'shares_annual': [100, 100, 100, 100], 'ni_annual': [10, 10, 10],
           'cfo_annual': [12, 12, 12], 'latest_quarter_end': date(2026, 6, 30)}
    r = G.score(inp, AS_OF)
    # warning_status, qualified_opinion dang tat -> 3/3 co bat deu tinh duoc
    assert r['coverage'] == 1.0 and r['score'] == 100 and r['flags'] == []


def test_ma_thieu_du_lieu_bi_giam_do_phu_khong_duoc_coi_la_sach():
    r = G.score({'latest_quarter_end': date(2026, 6, 30)}, AS_OF)
    assert r['score'] is None and set(r['missing']) == {'dilution', 'earnings_cash_gap'}


def test_pha_loang_va_lech_dong_tien_bi_phat():
    inp = {'shares_annual': [100, 115, 132, 152], 'ni_annual': [10, 10, 10],
           'cfo_annual': [2, 3, 4], 'latest_quarter_end': date(2026, 3, 31)}
    r = G.score(inp, AS_OF)
    assert set(r['flags']) == {'dilution_strong', 'earnings_cash_gap', 'late_filing'}
    assert r['score'] == 100 - 20 - 25 - 10


def test_veto_hai_quy_va_huy_niem_yet():
    assert G.veto('AAA', {'latest_quarter_end': date(2025, 12, 31)}, AS_OF, set()) \
        == 'Không có BCTC hai quý liên tiếp'
    assert G.veto('AAA', {}, AS_OF, {'AAA'}).startswith('Hủy niêm yết')
    assert G.veto('AAA', {'latest_quarter_end': date(2026, 3, 31)}, AS_OF, set()) is None


# --- valuation band + status -------------------------------------------------

def _sig(upside, conf, method='P/E Multiple', conflict=False):
    return {'upside_pct': upside, 'confidence': conf, 'methods_conflict': conflict,
            'method_details': [{'method': method, 'weight': 60}, {'method': 'Historical Multiple', 'weight': 40}]}


def test_upside_lon_tu_rnav_gian_luoc_khong_thanh_hap_dan():
    # Dung ca demo VHM: +85.8%, conf 45, RNAV trong so lon nhat
    assert ST.valuation_band(_sig(85.8, 45, 'RNAV'))['band'] == 'NOT_AVAILABLE'
    assert ST.valuation_band(_sig(85.8, 90, 'RNAV'))['band'] == 'NOT_AVAILABLE'


def test_quy_doi_bon_muc():
    assert ST.valuation_band(_sig(25, 60))['band'] == 'ATTRACTIVE'
    assert ST.valuation_band(_sig(5, 60))['band'] == 'FAIR'
    assert ST.valuation_band(_sig(-15, 60))['band'] == 'EXPENSIVE'
    assert ST.valuation_band(_sig(25, 40))['band'] == 'NOT_AVAILABLE'
    assert ST.valuation_band(_sig(25, 60, conflict=True))['band'] == 'NOT_AVAILABLE'
    assert ST.valuation_band(None)['band'] == 'NOT_AVAILABLE'


GOOD = {'quality': 80, 'growth': 75, 'governance': 80, 'resilience': 70}
FAIR = {'band': 'FAIR'}


def test_veto_thang_diem_cao():
    assert ST.classify(GOOD, FAIR, veto_reason='X')['status'] == 'EXC'


def test_thieu_mot_chieu_la_thieu_du_lieu_truoc_khi_xet_nguong():
    dims = {**GOOD, 'governance': None, 'quality': 40}
    r = ST.classify(dims, FAIR)
    assert r['status'] == 'RES' and 'Quản trị' in r['reason']


def test_mo_hinh_chua_kich_hoat():
    assert ST.classify(GOOD, FAIR, model_active=False)['status'] == 'RES'


def test_can_xem_lai_theo_nguong_duoi():
    r = ST.classify({**GOOD, 'resilience': 45}, FAIR)
    assert r['status'] == 'REV' and 'Chống chịu 45' in r['reason']


def test_du_chuan_chi_khi_dinh_gia_hap_dan_hoac_hop_ly():
    assert ST.classify(GOOD, {'band': 'ATTRACTIVE'})['status'] == 'QUAL'
    assert ST.classify(GOOD, FAIR)['status'] == 'QUAL'
    assert ST.classify(GOOD, {'band': 'EXPENSIVE'})['status'] == 'MON'
    # Khac blueprint v1: "Chua co" khong con lot vao Du chuan
    assert ST.classify(GOOD, {'band': 'NOT_AVAILABLE'})['status'] == 'MON'


def test_chua_dat_nguong_tren_la_theo_doi_kem_ly_do():
    r = ST.classify({**GOOD, 'growth': 66}, FAIR)
    assert r['status'] == 'MON' and r['reason'] == 'Tăng trưởng 66 dưới 70'


def test_giam_manh_chi_la_co_phu():
    assert ST.sharp_drops({**GOOD, 'quality': 60}, GOOD) == ['quality']
    assert ST.sharp_drops(GOOD, None) == []


def test_anh_xa_nganh_sang_mo_hinh():
    assert ST.model_for('Banking') == 'BANK'
    assert ST.model_for('Technology') == 'NON_FINANCIAL'
    assert ST.model_for('Unknown') is None
    assert 'REAL_ESTATE' not in C.ACTIVE_MODELS


def test_score_group_end_to_end_mot_mo_hinh():
    group = {}
    for i in range(10):
        a = _annual(g=0.02 * (i + 1))
        group[f'T{i}'] = M.compute('NON_FINANCIAL', a)
    res = S.score_group('NON_FINANCIAL', group)
    # tang truong cao nhat phai dung dau chieu growth
    assert res['T9']['growth']['score'] > res['T0']['growth']['score']
    assert res['T9']['growth']['coverage'] >= C.COVERAGE_MIN
