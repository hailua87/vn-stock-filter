"""
Chieu Quan tri = 100 - tong diem phat tu cac co tu dong (blueprint 8.5).

Phan biet hai loai "khong biet":
  - Co TAT trong config (chua co nguon): loai khoi mau so, khong phat.
  - Co BAT nhung ma nay thieu du lieu: van o mau so -> do phu giam.
Gop hai loai lam mot thi hoac Quan tri rong cho ca universe, hoac mot ma thieu
du lieu duoc coi nhu "khong co van de".
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Sequence

from . import config as C
from .metrics import cagr, _num


def quarter_end_before(d: date) -> date:
    """Ngay ket thuc quy gan nhat <= d."""
    q_month = ((d.month - 1) // 3) * 3  # 0,3,6,9 = thang cuoi cua quy truoc
    if q_month == 0:
        return date(d.year - 1, 12, 31)
    nxt = date(d.year, q_month + 1, 1)
    return nxt - timedelta(days=1)


def expected_latest_quarter(as_of: date, lag_days: int = C.FILING_LAG_DAYS) -> date:
    """Quy gan nhat ma den as_of le ra phai co so lieu (ket thuc quy + lag)."""
    q = quarter_end_before(as_of)
    while q + timedelta(days=lag_days) > as_of:
        q = quarter_end_before(q - timedelta(days=1))
    return q


def quarters_missing(latest_period_end: Optional[date], as_of: date) -> Optional[int]:
    """So quy dang thieu so voi ky ma le ra phai co. None neu khong biet ky moi nhat."""
    if latest_period_end is None:
        return None
    exp = expected_latest_quarter(as_of)
    n, q = 0, exp
    while q > latest_period_end:
        n += 1
        q = quarter_end_before(q - timedelta(days=1))
    return n


def dilution_flag(shares_annual: Sequence) -> Optional[str]:
    g = cagr(shares_annual, 3)
    if g is None:
        return None
    if g > C.DILUTION_STRONG:
        return 'strong'
    if g > C.DILUTION_MILD:
        return 'mild'
    return 'none'


def earnings_cash_gap(ni_q: Sequence, cfo_q: Sequence,
                      ni_a: Sequence, cfo_a: Sequence) -> Optional[bool]:
    """LN duong nhung CFO am o >= 3/4 quy gan nhat, hoac CFO/LN 3 nam < 0.5.
    Can it nhat mot trong hai phep kiem tinh duoc, neu khong tra None."""
    results = []
    q = [(_num(n), _num(c)) for n, c in zip(list(ni_q)[-4:], list(cfo_q)[-4:])]
    if len(q) == 4 and all(n is not None and c is not None for n, c in q):
        results.append(sum(1 for n, c in q if n > 0 and c < 0) >= 3)
    n3 = [_num(v) for v in list(ni_a)[-3:]]
    c3 = [_num(v) for v in list(cfo_a)[-3:]]
    if len(n3) == 3 and None not in n3 and None not in c3 and sum(n3) > 0:
        results.append(sum(c3) / sum(n3) < 0.5)
    if not results:
        return None
    return any(results)


def score(inputs: dict, as_of: date) -> dict:
    """
    inputs = {
      'shares_annual': [...], 'ni_q': [...], 'cfo_q': [...],
      'ni_annual': [...], 'cfo_annual': [...],
      'latest_quarter_end': date|None,
    }

    `warning_status` va `qualified_opinion` da go khoi bo co ngay 23/09/2026:
    khong co nguon nao cung cap duoc chung (§14.2). Xem C.GOVERNANCE_NOT_EVALUATED.
    
    """
    evaluated, flags, penalty = {}, [], 0

    if C.GOVERNANCE_FLAGS['dilution']['enabled']:
        d = dilution_flag(inputs.get('shares_annual') or [])
        evaluated['dilution'] = d
        if d == 'strong':
            flags.append('dilution_strong'); penalty += C.PENALTY['dilution_strong']
        elif d == 'mild':
            flags.append('dilution_mild'); penalty += C.PENALTY['dilution_mild']

    if C.GOVERNANCE_FLAGS['earnings_cash_gap']['enabled']:
        g = earnings_cash_gap(inputs.get('ni_q') or [], inputs.get('cfo_q') or [],
                              inputs.get('ni_annual') or [], inputs.get('cfo_annual') or [])
        evaluated['earnings_cash_gap'] = g
        if g:
            flags.append('earnings_cash_gap'); penalty += C.PENALTY['earnings_cash_gap']

    if C.GOVERNANCE_FLAGS['late_filing']['enabled']:
        m = quarters_missing(inputs.get('latest_quarter_end'), as_of)
        evaluated['late_filing'] = None if m is None else m >= 1
        if m is not None and m >= 1:
            flags.append('late_filing'); penalty += C.PENALTY['late_filing']

    enabled = [k for k, v in C.GOVERNANCE_FLAGS.items() if v['enabled']]
    known = [k for k in enabled if evaluated.get(k) is not None]
    coverage = len(known) / len(enabled) if enabled else 0.0
    value = max(0, 100 - penalty) if coverage >= C.COVERAGE_MIN else None
    return {
        'score': value,
        'coverage': round(coverage, 3),
        'flags': flags,
        'missing': [k for k in enabled if evaluated.get(k) is None],
    }


def veto(ticker: str, inputs: dict, as_of: date, delisted: set) -> Optional[str]:
    """Tra ly do veto dau tien gap, hoac None. Chuoi ly do hien thang len UI nen co dau."""
    if C.VETO_ENABLED['delisted'] and ticker in delisted:
        return 'Hủy niêm yết hoặc đình chỉ'
    if C.VETO_ENABLED['missing_two_quarters']:
        m = quarters_missing(inputs.get('latest_quarter_end'), as_of)
        if m is not None and m >= 2:
            return 'Không có BCTC hai quý liên tiếp'
    return None
