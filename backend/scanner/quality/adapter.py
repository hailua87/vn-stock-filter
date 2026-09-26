"""
Adapter: BCTC vnstock (record theo kỳ, tỷ đồng — xem financial_fetcher.
statement_to_records) → schema chuẩn của metrics.py và đầu vào governance.py.

Hai điều adapter phải làm đúng, vì metrics.py không tự kiểm được:
  1. Thứ tự CŨ → MỚI. vnstock trả kỳ mới trước; CAGR/drawdown đọc trái sang
     phải nên sai chiều là CAGR đổi dấu.
  2. None là "thiếu", không bao giờ thay bằng 0. Khoản mục không có trong BCTC
     của doanh nghiệp đó thì để None, metrics.py sẽ trả None và độ phủ giảm.

Đã xác thực trên dữ liệu thật (vnstock 4.0.7, 2026-09-22): BCTC QUÝ là số
riêng từng quý, không lũy kế — tổng 4 quý 2025 khớp đúng số năm cho cả CFO và
LNST của FPT, VCB, SSI. Nên CFO/LNST quý dùng thẳng.

Ánh xạ item_id lấy từ fixture thật FPT (phi tài chính), VCB (ngân hàng), SSI
(chứng khoán). Khoản mục ngân hàng NIM, tỷ lệ nợ xấu, bao phủ nợ xấu KHÔNG có
trong 3 bảng BCTC (bảng ratio bản cộng đồng chỉ có 2018) → để None.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

from ..strategies.valuation.normalizer import shares_from_paid_in_capital

# field chuẩn → (bảng, [item_id theo thứ tự ưu tiên])
ITEMS: Dict[str, tuple] = {
    # chung
    'revenue':             ('income', ['net_sales', 'revenue', 'net_revenue']),
    'gross_profit':        ('income', ['gross_profit']),
    'operating_profit':    ('income', ['operating_profit_loss']),
    'pbt':                 ('income', ['net_accounting_profit_loss_before_tax']),
    'net_income':          ('income', ['net_profit_loss_after_tax', 'attributable_to_parent_company']),
    'interest_expense':    ('income', ['interest_expenses', 'interests_expenses']),
    'cfo':                 ('cash_flow', ['net_cash_inflows_outflows_from_operating_activities',
                                         'net_cash_from_operating_activities']),
    'capex':               ('cash_flow', ['purchases_of_fixed_assets_and_other_long_term_assets']),
    'depreciation':        ('cash_flow', ['depreciation_and_amortization']),
    'share_issue_proceeds': ('cash_flow', ['proceeds_from_issue_of_shares']),
    'paid_in_capital':     ('balance_sheet', ['paid_in_capital', 'common_shares', 'charter_capital']),
    'total_assets':        ('balance_sheet', ['total_assets']),
    'equity':              ('balance_sheet', ['owners_equity', 'shareholders_equity']),
    'short_debt':          ('balance_sheet', ['short_term_borrowings']),
    'long_debt':           ('balance_sheet', ['long_term_borrowings']),
    'cash':                ('balance_sheet', ['cash_and_cash_equivalents', 'cash_and_precious_metals']),
    'current_assets':      ('balance_sheet', ['current_assets']),
    'current_liabilities': ('balance_sheet', ['current_liabilities']),
    # ngân hàng
    'toi':                 ('income', ['total_operating_income']),
    'net_interest_income': ('income', ['net_interest_income']),
    'opex':                ('income', ['general_and_admin_expenses']),
    'provision':           ('income', ['provision_for_credit_losses']),
    'loans':               ('balance_sheet', ['loans_and_advances_to_customers']),
    'deposits':            ('balance_sheet', ['deposits_from_customers']),
    # bất động sản
    # `inventories_net` là hàng tồn kho SAU trích lập; với chủ đầu tư BĐS đây
    # chính là quỹ đất và dự án dở dang, khoản mục lớn nhất bảng cân đối.
    'inventories':         ('balance_sheet', ['inventories_net', 'inventories']),
    # KHÔNG lấy 'advances_from_customers' (người mua trả tiền trước): đã thử
    # chấm và bỏ — xem metrics.real_estate. Không nạp thứ không ai dùng.
    # chứng khoán
    'operating_revenue':   ('income', ['operating_sales']),
    'brokerage_revenue':   ('income', ['revenue_in_brokerage_services']),
    'margin_interest':     ('income', ['income_from_loans_and_receivables']),
    'fvtpl_assets':        ('balance_sheet', ['financial_assets_at_fair_value_through_profit_or_loss_fvtpl']),
    'margin_loans':        ('balance_sheet', ['loans']),
}


def _pick(rec: Optional[dict], ids: Sequence[str]) -> Optional[float]:
    if not rec:
        return None
    for i in ids:
        v = rec.get(i)
        if v is not None:
            return float(v)
    return None


def _by_period(records: Sequence[dict]) -> Dict[str, dict]:
    return {str(r.get('period')): r for r in records or [] if r.get('period')}


def _period_end(label: str) -> Optional[str]:
    """'2025' → '2025-12-31'; '2026-Q2' → '2026-06-30'."""
    year, _, q = str(label).partition('-Q')
    try:
        y = int(year)
    except ValueError:
        return None
    if not q:
        return f'{y}-12-31'
    return {'1': f'{y}-03-31', '2': f'{y}-06-30', '3': f'{y}-09-30', '4': f'{y}-12-31'}.get(q)


def _add(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def annual_schema(raw: dict) -> dict:
    """raw = kết quả fetch_fundamentals(period='year'). Trả schema metrics.py, CŨ → MỚI."""
    tables = {t: _by_period(raw.get(t)) for t in ('income', 'balance_sheet', 'cash_flow')}
    periods = sorted({p for recs in tables.values() for p in recs},
                     key=lambda p: _period_end(p) or '')
    out: Dict[str, List[Optional[float]]] = {'period_end': [_period_end(p) for p in periods]}

    for field, (table, ids) in ITEMS.items():
        out[field] = [_pick(tables[table].get(p), ids) for p in periods]

    # EBIT = LN trước thuế + chi phí lãi vay (lãi vay là số âm trên BCTC VN). Khi
    # không có dòng lãi vay thì dùng LN thuần từ HĐKD — gần đúng, gồm cả thu chi tài chính.
    out['ebit'] = [
        (pbt + abs(ie)) if pbt is not None and ie is not None else op
        for pbt, ie, op in zip(out['pbt'], out['interest_expense'], out['operating_profit'])
    ]
    out['debt'] = [_add(s, l) for s, l in zip(out.pop('short_debt'), out.pop('long_debt'))]
    out['nonint_income'] = [
        (t - n) if t is not None and n is not None else None
        for t, n in zip(out['toi'], out['net_interest_income'])
    ]
    out['opex'] = [abs(v) if v is not None else None for v in out['opex']]
    out['shares_outstanding'] = [
        (shares_from_paid_in_capital(tables['balance_sheet'].get(p)) or None) for p in periods
    ]
    # Không có trong 3 bảng BCTC (§5.4 blueprint v4). `nim` được đổ vào sau
    # bằng attach_bank_ratios() cho riêng nhóm ngân hàng; `npl_ratio` và
    # `npl_coverage` đã gỡ khỏi mô hình BANK (D24) vì không nguồn nào có.
    out['nim'] = [None] * len(periods)
    return out


def attach_bank_ratios(annual: dict, ratios: Optional[dict]) -> dict:
    """
    Đổ NIM từ nguồn KBS vào `annual`, căn theo năm của từng kỳ.

    KBS trả PHẦN TRĂM (2,64 nghĩa là 2,64%). Mọi chỉ tiêu khác trong hệ thống
    là TỶ LỆ (0,0264), và giao diện nhân 100 khi hiển thị — không chia ở đây
    thì NIM hiện thành 264%. Đổi đúng một chỗ, tại đây.

    Năm nào KBS không có thì để None: `_std_last` bỏ qua None và vẫn tính được
    nếu còn đủ 4 điểm. KBS phủ 2022–2025, tức 4 điểm trên cửa sổ 5 năm.
    """
    nim = (ratios or {}).get('nim') or {}
    if not nim:
        return annual
    out = []
    for pe in annual.get('period_end') or []:
        year = None
        if pe:
            try:
                year = int(str(pe)[:4])
            except ValueError:
                year = None
        v = nim.get(year)
        out.append(v / 100.0 if v is not None else None)
    annual['nim'] = out
    return annual


def cash_issued_shares(shares: Sequence, paid_in: Sequence, proceeds: Sequence) -> List[Optional[float]]:
    """
    Chuỗi số CP chỉ tính phần tăng do PHÁT HÀNH LẤY TIỀN (v3 D18), cũ → mới.

    Cổ tức bằng cổ phiếu / cổ phiếu thưởng làm tăng vốn góp mà không có tiền vào
    (VCB 2025: vốn góp 55.891 → 83.557 tỷ, tiền thu phát hành 0) — không làm mỏng
    phần sở hữu nên không phải pha loãng. Mỗi năm: phần CP tăng × min(1, tiền thu
    phát hành / phần vốn góp tăng). Dùng dòng tiền chứ không dùng thặng dư vốn vì
    phát hành quyền mua theo mệnh giá (hay gặp ở ngân hàng) có tiền vào nhưng
    không tạo thặng dư. Giảm CP (mua lại) tính đủ. Thiếu số tiền thu ở năm có
    tăng vốn → None từ đó (không đoán).
    """
    out: List[Optional[float]] = []
    for i, s in enumerate(shares):
        if i == 0:
            out.append(s)
            continue
        prev_adj, prev_s = out[-1], shares[i - 1]
        if None in (prev_adj, prev_s, s) or not prev_s:
            out.append(None)
            continue
        delta = s - prev_s
        if delta <= 0:
            out.append(prev_adj * s / prev_s)
            continue
        cap_up = (paid_in[i] or 0) - (paid_in[i - 1] or 0)
        cash = proceeds[i]
        if cash is None or cap_up <= 0:
            out.append(None)
            continue
        frac = min(1.0, max(0.0, cash) / cap_up)
        out.append(prev_adj * (1 + delta * frac / prev_s))
    return out


def governance_inputs(annual: dict, raw_quarter: Optional[dict]) -> dict:
    """Đầu vào governance.score / veto. `raw_quarter` = BCTC quý (record theo kỳ)."""
    q_income = _by_period((raw_quarter or {}).get('income'))
    q_cf = _by_period((raw_quarter or {}).get('cash_flow'))
    q_periods = sorted(set(q_income) | set(q_cf), key=lambda p: _period_end(p) or '')
    ni_ids, cfo_ids = ITEMS['net_income'][1], ITEMS['cfo'][1]
    latest = _period_end(q_periods[-1]) if q_periods else None
    return {
        # Cờ pha loãng chỉ xét CP phát hành lấy tiền (v3 D18), xem cash_issued_shares
        # Chỉ 4 điểm cuối (CAGR 3 năm): năm cũ thiếu số liệu không làm hỏng cả chuỗi.
        'shares_annual': cash_issued_shares((annual.get('shares_outstanding') or [])[-4:],
                                            (annual.get('paid_in_capital') or [])[-4:],
                                            (annual.get('share_issue_proceeds') or [])[-4:]),
        'ni_annual': annual.get('net_income') or [],
        'cfo_annual': annual.get('cfo') or [],
        'ni_q': [_pick(q_income.get(p), ni_ids) for p in q_periods],
        'cfo_q': [_pick(q_cf.get(p), cfo_ids) for p in q_periods],
        'latest_quarter_end': date.fromisoformat(latest) if latest else None,
    }
