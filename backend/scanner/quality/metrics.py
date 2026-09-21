"""
Tinh chi tieu tu schema chuan. Moi ham tra None khi khong tinh duoc: None la
"thieu", khong bao gio duoc thay bang 0 hay gia tri trung tinh.

Schema chuan (adapter tu vnstock phai tao ra dung dang nay):

    annual = {                      # CU -> MOI, moi list cung do dai
        'period_end': ['2021-12-31', ...],
        'revenue': [...], 'gross_profit': [...], 'ebit': [...],
        'net_income': [...], 'cfo': [...], 'capex': [...],
        'depreciation': [...], 'total_assets': [...], 'equity': [...],
        'debt': [...], 'cash': [...], 'current_assets': [...],
        'current_liabilities': [...], 'interest_expense': [...],
        'shares_outstanding': [...],
        # ngan hang
        'toi': [...], 'pbt': [...], 'loans': [...], 'deposits': [...],
        'nonint_income': [...], 'opex': [...], 'provision': [...],
        'nim': [...], 'npl_ratio': [...], 'npl_coverage': [...],
        # chung khoan
        'operating_revenue': [...], 'brokerage_revenue': [...],
        'margin_interest': [...], 'fvtpl_assets': [...], 'margin_loans': [...],
    }

Thu tu CU -> MOI duoc chon vi CAGR/drawdown doc tu trai sang phai; vnstock
tra MOI truoc, adapter phai dao nguoc. Dat sai chieu thi CAGR doi dau ma test
van xanh neu du lieu test cung sai chieu — nen test co ca chuoi tang ro rang.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Optional, Sequence

CIT_RATE = 0.20   # thue TNDN pho thong VN, dung cho NOPAT xap xi


def _num(x) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _series(d: dict, key: str) -> list:
    return [_num(v) for v in (d.get(key) or [])]


def _last(d: dict, key: str) -> Optional[float]:
    s = _series(d, key)
    return s[-1] if s else None


def _div(a, b) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr(values: Sequence, years: int) -> Optional[float]:
    """CAGR `years` nam, can years+1 diem. Hai dau ky phai duong: CAGR tu so am
    khong co nghia kinh te, tra None thay vi mot con so ao."""
    s = [_num(v) for v in values]
    if len(s) < years + 1:
        return None
    start, end = s[-(years + 1)], s[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def _ratio_series(num: list, den: list) -> list:
    return [_div(a, b) for a, b in zip(num, den)]


def _std_last(values: list, n: int, min_points: int) -> Optional[float]:
    s = [v for v in values[-n:] if v is not None]
    return pstdev(s) if len(s) >= min_points else None


def _avg_last(values: list, n: int, min_points: int) -> Optional[float]:
    s = [v for v in values[-n:] if v is not None]
    return mean(s) if len(s) >= min_points else None


def _avg_base(values: list) -> list:
    """Binh quan dau-cuoi ky cho mau so (ROA/ROE); ky dau tien khong co ky truoc
    nen dung chinh no."""
    out = []
    for i, v in enumerate(values):
        prev = values[i - 1] if i > 0 else v
        out.append((v + prev) / 2 if v is not None and prev is not None else None)
    return out


def profit_drawdown(values: Sequence, n: int = 6) -> Optional[float]:
    """Sut giam lon nhat so voi dinh truoc do, tinh bang ty le duong (0.3 = -30%).
    Dinh <= 0 bi bo qua vi ty le so voi dinh am khong doc duoc."""
    s = [_num(v) for v in values][-n:]
    if len([v for v in s if v is not None]) < 4:
        return None
    peak, worst = None, 0.0
    for v in s:
        if v is None:
            continue
        if peak is None or v > peak:
            peak = v
        elif peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def up_years(values: Sequence, n: int = 5) -> Optional[float]:
    s = [_num(v) for v in values]
    if len(s) < n + 1:
        return None
    pairs = list(zip(s[-(n + 1):-1], s[-n:]))
    if any(a is None or b is None for a, b in pairs):
        return None
    return sum(1 for a, b in pairs if b > a) / n


# --- Tung mo hinh -----------------------------------------------------------

def non_financial(a: dict) -> dict:
    rev, gp, ebit = _series(a, 'revenue'), _series(a, 'gross_profit'), _series(a, 'ebit')
    ni, cfo = _series(a, 'net_income'), _series(a, 'cfo')
    eq, debt, cash = _series(a, 'equity'), _series(a, 'debt'), _series(a, 'cash')
    ta = _series(a, 'total_assets')

    invested = [e + d - c if None not in (e, d, c) else None for e, d, c in zip(eq, debt, cash)]
    nopat = [e * (1 - CIT_RATE) if e is not None else None for e in ebit]
    roic = [_div(n, i) if i and i > 0 else None for n, i in zip(nopat, invested)]

    ni3, cfo3 = ni[-3:], cfo[-3:]
    cash_conv = None
    if len(ni3) == 3 and None not in ni3 and None not in cfo3 and sum(ni3) > 0:
        cash_conv = sum(cfo3) / sum(ni3)

    turnover = None
    if len(ta) >= 2 and None not in (rev[-1], ta[-1], ta[-2]):
        turnover = _div(rev[-1], (ta[-1] + ta[-2]) / 2)

    capex, dep = _last(a, 'capex'), _last(a, 'depreciation')
    ca, cl = _series(a, 'current_assets'), _series(a, 'current_liabilities')
    reinvest = None
    if len(ca) >= 2 and None not in (capex, dep, ca[-1], ca[-2], cl[-1], cl[-2], nopat[-1]) \
            and nopat[-1] > 0:
        dwc = (ca[-1] - cl[-1]) - (ca[-2] - cl[-2])
        # vnstock ghi capex la dong tien am; lay tri tuyet doi de khong phu thuoc quy uoc dau
        reinvest = (abs(capex) - dep + dwc) / nopat[-1]

    ebitda = None
    if ebit and None not in (ebit[-1], dep):
        ebitda = ebit[-1] + dep
    net_debt = None if not debt or None in (debt[-1], cash[-1]) else debt[-1] - cash[-1]
    nd_ebitda = _div(net_debt, ebitda) if ebitda and ebitda > 0 else None

    interest = _last(a, 'interest_expense')
    cover = None
    if ebit and ebit[-1] is not None and interest is not None:
        # Khong vay no: coi nhu kha nang tra lai rat cao nhung chan tran de khong
        # lam lech percentile/winsorize
        cover = 100.0 if abs(interest) < 1e-9 else min(100.0, ebit[-1] / abs(interest))

    return {
        'roic_avg5': _avg_last(roic, 5, 3),
        'gross_margin_std5': _std_last(_ratio_series(gp, rev), 5, 4),
        'ebit_margin_std5': _std_last(_ratio_series(ebit, rev), 5, 4),
        'cash_conversion3': cash_conv,
        'asset_turnover': turnover,
        'revenue_cagr5': cagr(rev, 5),
        'ebit_cagr5': cagr(ebit, 5),
        'cfo_cagr5': cagr(cfo, 5),
        'revenue_up_years5': up_years(rev, 5),
        'reinvestment_rate': reinvest,
        'net_debt_ebitda': nd_ebitda,
        'interest_coverage': cover,
        'current_ratio': _div(_last(a, 'current_assets'), _last(a, 'current_liabilities')),
        'profit_drawdown5': profit_drawdown(ni),
    }


def bank(a: dict) -> dict:
    ni, ta, eq = _series(a, 'net_income'), _series(a, 'total_assets'), _series(a, 'equity')
    toi, loans = _series(a, 'toi'), _series(a, 'loans')
    credit_cost = _ratio_series(_series(a, 'provision'), _avg_base(loans))
    return {
        'roa_avg3': _avg_last(_ratio_series(ni, _avg_base(ta)), 3, 3),
        'roe_avg3': _avg_last(_ratio_series(ni, _avg_base(eq)), 3, 3),
        'nim_std': _std_last(_series(a, 'nim'), 5, 4),
        'npl_ratio': _last(a, 'npl_ratio'),
        'cost_income': _div(_last(a, 'opex'), _last(a, 'toi')),
        'toi_cagr5': cagr(toi, 5),
        'pbt_cagr5': cagr(_series(a, 'pbt'), 5),
        'loans_cagr5': cagr(loans, 5),
        'nonint_income_cagr3': cagr(_series(a, 'nonint_income'), 3),
        'npl_coverage': _last(a, 'npl_coverage'),
        'equity_assets': _div(_last(a, 'equity'), _last(a, 'total_assets')),
        # chi phi du phong co the ghi am; do lech chuan khong phu thuoc dau
        'credit_cost_std': _std_last([abs(v) if v is not None else None for v in credit_cost], 5, 4),
        'ldr': _div(_last(a, 'loans'), _last(a, 'deposits')),
    }


def securities(a: dict) -> dict:
    ni, eq = _series(a, 'net_income'), _series(a, 'equity')
    brok, mi = _last(a, 'brokerage_revenue'), _last(a, 'margin_interest')
    recurring = None if None in (brok, mi) else _div(brok + mi, _last(a, 'operating_revenue'))
    return {
        'roe_avg3': _avg_last(_ratio_series(ni, _avg_base(eq)), 3, 3),
        'recurring_share': recurring,
        'fvtpl_equity': _div(_last(a, 'fvtpl_assets'), _last(a, 'equity')),
        'revenue_cagr5': cagr(_series(a, 'operating_revenue'), 5),
        'npat_cagr5': cagr(ni, 5),
        'margin_loans_cagr3': cagr(_series(a, 'margin_loans'), 3),
        'margin_loans_equity': _div(_last(a, 'margin_loans'), _last(a, 'equity')),
        'debt_equity': _div(_last(a, 'debt'), _last(a, 'equity')),
        'profit_drawdown5': profit_drawdown(ni),
    }


CALCULATORS = {'NON_FINANCIAL': non_financial, 'BANK': bank, 'SECURITIES': securities}


def compute(model: str, annual: dict) -> dict:
    fn = CALCULATORS.get(model)
    return fn(annual) if fn else {}
