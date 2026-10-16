"""
Normalizer — Convert raw vnstock data → standardized valuation input.

vnstock 4.x trả về DataFrames với column names theo BCTC chuẩn VN, nhưng
naming convention không đồng nhất giữa các phiên bản. Module này centralize
việc map raw → standardized dict mà các valuation methods consume.

Standardized schema (xem `data/sample_data.py` của prototype để tham khảo):
{
    'ticker': str,
    'overview': {'industry': str, 'sector': str, ...},
    'market': {'current_price': float, 'shares_outstanding': int, 'beta_2y': float, ...},
    'income': {'net_profit': float, 'roe_5y': [...], ...},
    'balance_sheet': {'total_assets': float, 'shareholders_equity': float, ...},
    'ratios': {'pe_ttm', 'pb_current', 'roe_ttm', ...},
    'per_share': {'eps_ttm', 'bvps', ...},
    'growth': {...},
    'cash_flow': {'ebitda_ttm', 'fcff_ttm', ...},
}
"""
from __future__ import annotations
import logging
import math
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


# Field aliases — map từ tên cột vnstock có thể có sang field chuẩn của valuation
# vnstock có thể dùng tiếng Anh, tiếng Việt, hoặc snake_case khác nhau giữa versions
BS_ALIASES = {
    'total_assets': ['total_assets', 'TOTAL ASSETS (Bn. VND)', 'tong_tai_san'],
    'shareholders_equity': ['owner_s_equity', "OWNER'S EQUITY(Bn.VND)", 'shareholders_equity',
                            'equity', 'von_chu_so_huu', 'common_shareholder_s_equity', 'owners_equity'],
    'total_liabilities': ['liabilities', 'LIABILITIES (Bn. VND)', 'total_liabilities'],
    'short_term_debt': ['short_term_borrowings', 'short_term_debt', 'no_ngan_han'],
    'long_term_debt': ['long_term_borrowings', 'long_term_debt', 'no_dai_han'],
    'cash_and_equivalents': ['cash_and_cash_equivalents', 'cash', 'cash_and_equivalents',
                             'cash_and_precious_metals', 'tien_va_tuong_duong_tien'],
    'inventory': ['inventories', 'inventory_net', 'hang_ton_kho'],
    'fixed_assets': ['fixed_assets', 'net_fixed_assets', 'tai_san_co_dinh'],
    'investment_property': ['investment_in_properties', 'investment_properties',
                            'investment_property', 'bds_dau_tu'],
    'loans_to_customers': ['loans_to_customers', 'net_loans_to_customers',
                            'loans_and_advances_to_customers', 'cho_vay_khach_hang'],
    'customer_deposits': ['customer_deposits', 'deposits_from_customers', 'tien_gui_khach_hang'],
    'minority_interest': ['minority_interests', 'non_controlling_interests', 'loi_ich_co_dong_thieu_so'],
}

IS_ALIASES = {
    'revenue': ['revenue', 'net_revenue', 'net_sales', 'doanh_thu_thuan', 'sales'],
    'gross_profit': ['gross_profit', 'lai_gop'],
    'operating_profit': ['operating_profit', 'operating_profit_loss',
                         'profit_loss_from_operating_activities', 'lai_thuan_hd'],
    'profit_before_tax': ['profit_before_tax', 'pretax_profit',
                          'net_accounting_profit_loss_before_tax', 'loi_nhuan_truoc_thue'],
    'net_profit': ['net_profit_for_the_year', 'net_profit', 'profit_after_tax',
                   'net_profit_loss_after_tax',
                   'attributable_to_parent_company', 'loi_nhuan_sau_thue'],
    'net_profit_parent': ['attributable_to_parent_company', 'profit_after_tax_attributable_to_parent',
                          'net_profit_for_the_year', 'loi_nhuan_co_dong_cong_ty_me'],
    'interest_income': ['interest_and_similar_income', 'net_interest_income', 'thu_nhap_lai'],
    'net_interest_income': ['net_interest_income', 'thu_nhap_lai_thuan'],
}

CF_ALIASES = {
    'operating_cf': ['net_cash_inflows_outflows_from_operating_activities',
                     'net_cash_from_operating_activities', 'cf_from_operations',
                     'dong_tien_tu_hd_kinh_doanh'],
    'capex': ['purchase_of_fixed_assets', 'purchases_of_fixed_assets_and_other_long_term_assets',
              'capex', 'mua_tai_san'],
    'depreciation': ['depreciation_and_amortisation', 'depreciation_and_amortization',
                     'depreciation', 'khau_hao'],
}

RATIO_ALIASES = {
    'pe_ttm': ['pe', 'pe_ratio', 'p_e', 'priceToEarning', 'price_to_earnings'],
    'pb_current': ['pb', 'pb_ratio', 'p_b', 'priceToBook', 'price_to_book'],
    'roe_ttm': ['roe', 'return_on_equity', 'roe_percent'],
    'roa_ttm': ['roa', 'return_on_assets'],
    'eps_ttm': ['eps', 'earnings_per_share', 'basic_eps'],
    'bvps': ['bvps', 'book_value_per_share'],
    'dividend_yield': ['dividend_yield', 'dividend_yield_pct'],
    'payout_ratio': ['payout_ratio', 'dividend_payout_ratio'],
    'npl_ratio': ['npl', 'npl_ratio', 'bad_debt_ratio'],
    'car': ['car', 'capital_adequacy_ratio'],
    'nim': ['nim', 'net_interest_margin'],
    'gross_margin': ['gross_margin', 'gross_profit_margin'],
    'net_margin': ['net_margin', 'net_profit_margin'],
    'debt_to_equity': ['debt_to_equity', 'debtPerEquity', 'de_ratio'],
}


def _get_field(record: Dict, aliases: List[str], default=None):
    """Lookup field with alias fallback. Case-insensitive."""
    record_lower = {k.lower(): v for k, v in record.items()}
    for alias in aliases:
        if alias.lower() in record_lower:
            val = record_lower[alias.lower()]
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                return val
    return default


def _safe_float(v, default=0.0) -> float:
    """Safely convert to float, handling None/NaN/string."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


# Cổ tức tiền mặt đã trả trên báo cáo lưu chuyển tiền tệ (TỶ ĐỒNG, dấu âm =
# tiền ra). Dùng ở HAI chỗ — suy `payout_ratio` và suy `dps_ttm` — nên để một
# chỗ duy nhất, đừng chép lại danh sách.
DIVIDENDS_PAID_ALIASES = [
    'dividends_paid', 'dividend_paid', 'payment_of_dividends', 'co_tuc_da_tra',
]

# Mệnh giá cổ phiếu niêm yết tại Việt Nam (Luật Chứng khoán): 10.000 VND/cp
PAR_VALUE_VND = 10_000
PAID_IN_CAPITAL_ALIASES = ['paid_in_capital', 'common_shares', 'charter_capital', 'von_gop']


def shares_from_paid_in_capital(bs_record: Dict) -> float:
    """Số cổ phiếu = vốn góp (tỷ đồng) × 1e9 / mệnh giá. 0 nếu thiếu.

    Dòng `common_shares` của vnstock là VỐN CỔ PHẦN theo tiền, không phải số
    cổ phiếu — dùng nó như số lượng làm EPS của HAG thành 167 triệu đồng/cp.
    """
    capital_bn = _safe_float(_get_field(bs_record or {}, PAID_IN_CAPITAL_ALIASES))
    return capital_bn * 1_000_000_000 / PAR_VALUE_VND if capital_bn > 0 else 0.0


def roe_history_from_statements(is_records: List[Dict], bs_records: List[Dict],
                                n: int = 5) -> List[float]:
    """ROE từng năm = LNST cổ đông mẹ / vốn chủ sở hữu cuối kỳ, ghép theo 'period'."""
    equity_by_period = {r.get('period'): _safe_float(_get_field(r, BS_ALIASES['shareholders_equity']))
                        for r in bs_records}
    out = []
    for r in is_records[:n]:
        equity = equity_by_period.get(r.get('period'), 0.0)
        if equity > 0:
            out.append(_safe_float(_get_field(r, IS_ALIASES['net_profit_parent'])) / equity)
    return out


def _extract_history(records: List[Dict], aliases: List[str], n: int = 5) -> List[float]:
    """Extract historical values from list of period records (latest first)."""
    out = []
    for r in records[:n]:
        v = _get_field(r, aliases)
        out.append(_safe_float(v))
    return out


def normalize_fundamentals(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert raw vnstock fundamentals → standardized format cho valuation engine.

    Args:
        raw: Output từ fetch_fundamentals() trong financial_fetcher.py
             {'ticker', 'current_price', 'overview', 'balance_sheet', 'income',
              'cash_flow', 'ratio'}

    Returns:
        Standardized dict (xem schema ở top file)
    """
    ticker = raw.get('ticker', '?')
    bs_records = raw.get('balance_sheet', [])
    is_records = raw.get('income', [])
    cf_records = raw.get('cash_flow', [])
    ratio_records = raw.get('ratio', [])
    overview = raw.get('overview', {})
    current_price = raw.get('current_price')

    if not bs_records or not is_records:
        log.warning(f"  {ticker}: missing core financial statements")
        return None

    # === Invariant đơn vị: valuation engine chạy hoàn toàn bằng VND/cp ===
    # Chặn ngay tại biên thay vì để giá đơn vị quote (nghìn VND) lan xuống và
    # tạo ra upside +98.000%. Xem scanner/price_units.py.
    from ...price_units import assert_price_is_vnd
    if current_price is not None:
        assert_price_is_vnd(current_price, ticker, 'current_price')

    # === Latest period (year[0]) ===
    bs0 = bs_records[0] if bs_records else {}
    is0 = is_records[0] if is_records else {}
    cf0 = cf_records[0] if cf_records else {}
    r0 = ratio_records[0] if ratio_records else {}

    # === Shares outstanding ===
    shares = (_safe_float(overview.get('outstanding_share'))
              or _safe_float(_get_field(bs0, ['outstanding_share', 'issue_share']))
              or shares_from_paid_in_capital(bs0)
              or 0)
    if shares == 0:
        # Estimate từ equity / BVPS
        equity = _safe_float(_get_field(bs0, BS_ALIASES['shareholders_equity']))
        bvps_raw = _safe_float(_get_field(r0, RATIO_ALIASES['bvps']))
        if equity > 0 and bvps_raw > 0:
            shares = (equity * 1_000_000_000) / bvps_raw  # equity in tỷ → VND
            log.debug(f"  {ticker}: estimated shares = {shares:,.0f}")

    # === Balance sheet ===
    balance_sheet = {}
    for std_field, aliases in BS_ALIASES.items():
        balance_sheet[std_field] = _safe_float(_get_field(bs0, aliases))

    bvps = _safe_float(_get_field(r0, RATIO_ALIASES['bvps']))
    if bvps == 0 and balance_sheet['shareholders_equity'] > 0 and shares > 0:
        bvps = (balance_sheet['shareholders_equity'] * 1_000_000_000) / shares
    balance_sheet['book_value_per_share'] = bvps

    # CAR cho banking. Thứ tự nguồn có chủ ý:
    #   1. `bank_asset_quality` — thuyết minh BCTC, số THẬT tới 2025
    #   2. bảng ratio — dừng ở 2018 và đã gỡ khỏi hệ thống 26/09/2026
    #   3. mặc định 0,115
    # Trước 01/10/2026 chỉ có (2) và (3), nên MỌI ngân hàng dùng 0,115 — tức
    # điều chỉnh P/B theo CAR không bao giờ hoạt động.
    aq_src = raw.get('bank_asset_quality') or {}
    aq_latest = aq_src.get(max(aq_src)) if aq_src else {}
    car = _safe_float(aq_latest.get('car')) or _safe_float(_get_field(r0, RATIO_ALIASES['car']))
    if car == 0:
        car = 0.115  # default conservative cho VN banks
    balance_sheet['car'] = car
    balance_sheet['car_is_real'] = bool(_safe_float(aq_latest.get('car')))

    # === Income statement ===
    revenue = _safe_float(_get_field(is0, IS_ALIASES['revenue']))
    net_profit = _safe_float(_get_field(is0, IS_ALIASES['net_profit']))
    net_profit_parent = _safe_float(_get_field(is0, IS_ALIASES['net_profit_parent'])) or net_profit
    interest_income = _safe_float(_get_field(is0, IS_ALIASES['interest_income']))
    net_interest_income = _safe_float(_get_field(is0, IS_ALIASES['net_interest_income']))

    income = {
        'revenue': revenue,
        'net_profit': net_profit,
        'net_profit_parent': net_profit_parent,
        'interest_income': interest_income,
        'net_interest_income': net_interest_income,
        'net_profit_5y': _extract_history(is_records, IS_ALIASES['net_profit']),
        'net_profit_parent_5y': _extract_history(is_records, IS_ALIASES['net_profit_parent']),
        'revenue_5y': _extract_history(is_records, IS_ALIASES['revenue']),
    }

    # ROE history từ ratio table
    roe_5y = _extract_history(ratio_records, RATIO_ALIASES['roe_ttm'])
    # Normalize percent (vnstock có thể trả 0.21 hoặc 21.0)
    roe_5y = [r/100 if r > 1.5 else r for r in roe_5y if r > -1.0]
    if not ratio_records:
        # Bảng ratio bị bỏ (cũ hơn BCTC) → tính từ BCTC thay vì để rỗng
        roe_5y = [r for r in roe_history_from_statements(is_records, bs_records) if r > -1.0]
    income['roe_5y'] = roe_5y

    # === Ratios ===
    ratios = {}
    for std_field, aliases in RATIO_ALIASES.items():
        v = _safe_float(_get_field(r0, aliases))
        # Normalize percent to decimal
        if std_field in ['roe_ttm', 'roa_ttm', 'dividend_yield', 'payout_ratio',
                         'npl_ratio', 'car', 'nim', 'gross_margin', 'net_margin']:
            v = v / 100 if v > 1.5 else v
        ratios[std_field] = v

    if ratios.get('roe_ttm', 0) == 0 and roe_5y:
        ratios['roe_ttm'] = roe_5y[0]

    # === payout_ratio: suy từ BCTC, KHÔNG lấy mặc định 0,30 ===
    #
    # Dòng cũ ở đây là `ratios.setdefault('payout_ratio', 0.30)` — MÃ CHẾT.
    # Vòng lặp ratio ngay trên đã gán khoá này cho MỌI mã (thiếu dữ liệu thì
    # `_safe_float` trả 0.0), nên `setdefault` không bao giờ có hiệu lực. Và từ
    # 26/09/2026 bảng `ratio` của VCI không còn được lấy nữa (xem docstring của
    # `fetch_financial_statements`), nên `r0` LUÔN rỗng và payout_ratio là 0.0
    # cho 100% rổ. Đo ngày 15/10/2026 trên 200 mã: 0,0 ở tất cả. Hệ quả:
    #   - `justified_pe = payout/(coe-g) = 0` → bị loại khỏi blend ở MỌI mã,
    #     mất 30% trọng số mà không ai thấy (methods_pe.py)
    #   - `g = ROE × (1 - 0)` = TOÀN BỘ ROE → luôn đụng trần GDP growth
    #   - `dps_ttm = eps × 0 = 0` khi lưu chuyển tiền tệ không có cổ tức → DDM
    #     trả 0 và bị loại
    #
    # 0,30 KHÔNG phải mặc định đúng. Áp một chính sách cổ tức 30% cho mọi mã là
    # bịa số, và kho này đã bác đúng khuôn đó hai lần: historical multiples
    # thiếu thì để None cho method tự loại cấu phần (ngay dưới), còn DPS thì
    # "không suy từ giá" (xem FIX CIRCULARITY ở khối per_share).
    #
    # Thú vị và đáng ghi: trung vị payout 5 năm đo được là 0,287 — gần đúng
    # 0,30. Nên 0,30 là một ước lượng TRUNG TÂM tử tế, và đó chính là lý do lỗi
    # này sống sót lâu: con số không bao giờ trông vô lý. Nhưng áp trung vị cho
    # mọi mã thì xoá sạch khác biệt giữa các mã, mà khác biệt đó mới là thứ
    # định giá tương đối cần. VCB trả 11% và VNM trả 120% không thể cùng 30%.
    #
    # Cổ tức THẬT nằm ngay trong báo cáo lưu chuyển tiền tệ mà pipeline vốn đã
    # lấy, nên suy từ đó:
    #
    #     payout = tổng cổ tức tiền mặt đã trả / tổng lợi nhuận cổ đông mẹ
    #
    # Cả hai đều TỶ ĐỒNG (CLAUDE.md §2) nên tỷ số không đơn vị — và với một năm
    # thì bằng đúng `dps_ttm / eps_ttm` vì hai vế cùng chia cho số cổ phiếu.
    #
    # Số 0 ở đây là số THẬT, không phải thiếu dữ liệu: bảng lưu chuyển tiền tệ
    # luôn materialize dòng `dividends_paid` (ô trống = 0), nên mã không trả cổ
    # tức TIỀN MẶT cho 0 đúng nghĩa — đo 15/10/2026: KDH, STB, VRE, HDB, PDR,
    # NVL đều 0 và đều đúng (bốn mã đầu trả cổ tức bằng cổ phiếu).
    #
    # Chỉ khi KHÔNG tính được thì để None: lỗ (payout vô nghĩa khi mẫu số âm)
    # hoặc không có bảng lưu chuyển tiền tệ. None ≠ 0 — các method phải tự loại
    # cấu phần, và `payout_source` để kiểm lại được từ chính đầu ra.
    #
    # LẤY NHIỀU NĂM, không lấy một năm. Đo 15/10/2026 trên 200 mã cho thấy
    # payout một năm nổ ra vô nghĩa khi lợi nhuận sụt mà cổ tức vẫn trả từ lợi
    # nhuận giữ lại các năm trước:
    #
    #            payout 1 năm      payout 5 năm
    #   HAX         23,18             0,394
    #   NTL          7,00             0,652
    #   CTF          5,25             0,206
    #   số mã > 1,0    20                10
    #   số mã > 2,0     8                 1
    #   lớn nhất     23,18              2,10
    #
    # HAX payout 2.317% kéo justified_pe lên 207x — một con số như vậy vào blend
    # với 30% trọng số còn tệ hơn việc bị loại. Tổng nhiều năm là ước lượng
    # chuẩn cho tỷ lệ chi trả BỀN VỮNG, và Gordon vốn là mô hình vĩnh viễn nên
    # nó cần đúng con số bền vững ấy, không phải ảnh của một năm xấu.
    payout_reported = _get_field(r0, RATIO_ALIASES['payout_ratio'])
    if payout_reported is not None:
        ratios['payout_source'] = 'reported'
    else:
        div_5y = _extract_history(cf_records, DIVIDENDS_PAID_ALIASES)
        profit_5y = income['net_profit_parent_5y']
        n = min(len(div_5y), len(profit_5y))
        tong_co_tuc = sum(abs(x) for x in div_5y[:n])
        tong_loi_nhuan = sum(profit_5y[:n])
        if n and tong_loi_nhuan > 0:
            tho = tong_co_tuc / tong_loi_nhuan
            # Trần 1,0: payout > 100% KHÔNG duy trì được vĩnh viễn (phải rút
            # vốn chủ), nên với mô hình vĩnh viễn nó là 100%. Vẫn còn 10 mã
            # vượt 1,0 sau khi tính 5 năm, cao nhất 2,10 — trần giữ
            # justified_pe trong dải lành mạnh (1,0/CoE ≈ 9x thay vì 207x).
            # Ghi vào `payout_source` để trần không bao giờ tàng hình.
            ratios['payout_ratio'] = min(tho, 1.0)
            ratios['payout_source'] = 'cash_flow_5y_capped' if tho > 1.0 else 'cash_flow_5y'
        else:
            ratios['payout_ratio'] = None
            ratios['payout_source'] = 'unavailable'

    if ratios.get('pe_ttm', 0) == 0 and current_price and shares > 0 and net_profit_parent > 0:
        eps_calc = (net_profit_parent * 1_000_000_000) / shares
        ratios['pe_ttm'] = current_price / eps_calc

    # Historical P/E and P/B medians - dùng dữ liệu thực nếu có
    hist_mults = raw.get('historical_multiples', {})

    if hist_mults and not hist_mults.get('fallback'):
        # Dùng historical thực từ market_metrics.calculate_historical_multiples
        if hist_mults.get('pe_5y_median') is not None:
            ratios['pe_5y_median'] = hist_mults['pe_5y_median']
            ratios['pe_5y_p25'] = hist_mults['pe_5y_p25']
            ratios['pe_5y_p75'] = hist_mults['pe_5y_p75']
        if hist_mults.get('pb_5y_median') is not None:
            ratios['pb_5y_median'] = hist_mults['pb_5y_median']
            ratios['pb_5y_p25'] = hist_mults['pb_5y_p25']
            ratios['pb_5y_p75'] = hist_mults['pb_5y_p75']
        ratios['_historical_multiples_source'] = 'computed'
    else:
        # KHÔNG suy historical multiple từ multiple hiện tại.
        #
        # FIX CIRCULARITY: bản cũ đặt pe_5y_median = pe_ttm và pb_5y_median =
        # pb_current. Hệ quả: "Historical Multiple" cho fair_value = pe_ttm × EPS
        # = ĐÚNG BẰNG GIÁ THỊ TRƯỜNG (nhìn output demo: 42.215 vs 42.000,
        # 105.013 vs 105.000), mà phương pháp này lại chiếm 10-25% trọng số.
        # P/E Multiple cũng lấy 40% trọng số từ chính con số đó.
        # ⇒ "fair value" tự kéo về giá thị trường và upside bị triệt tiêu.
        #
        # Nguyên tắc: không input nào của giá trị nội tại được chứa current_price.
        # Thiếu dữ liệu lịch sử thì để None, các method sẽ tự bỏ cấu phần đó và
        # chuẩn hoá lại trọng số.
        ratios['pe_5y_median'] = None
        ratios['pe_5y_p25'] = None
        ratios['pe_5y_p75'] = None
        ratios['pb_5y_median'] = None
        ratios['pb_5y_p25'] = None
        ratios['pb_5y_p75'] = None
        ratios['_historical_multiples_source'] = 'unavailable'

    # === Per-share ===
    eps_ttm = _safe_float(_get_field(r0, RATIO_ALIASES['eps_ttm']))
    if eps_ttm == 0 and shares > 0 and net_profit_parent > 0:
        eps_ttm = (net_profit_parent * 1_000_000_000) / shares

    # === DPS: phải là số tuyệt đối, KHÔNG suy từ giá ===
    # FIX CIRCULARITY: bản cũ `dps_ttm = current_price × dividend_yield`. DDM khi
    # đó cho fair value tỷ lệ thuận với giá hiện tại → upside gần như hằng số
    # bất kể thị trường định giá cao hay thấp. Thứ tự ưu tiên mới:
    #   1. DPS công bố trong bảng ratio
    #   2. Cổ tức đã trả trên báo cáo lưu chuyển tiền tệ / số cổ phiếu
    #   3. EPS × payout ratio (thuần cơ bản, vẫn không dính giá)
    dps_ttm = _safe_float(_get_field(r0, [
        'dps', 'dividend_per_share', 'cash_dividend_per_share', 'co_tuc_tien_mat',
    ]))
    # 'reported' chỉ khi bảng ratio THẬT có DPS. Trước đây biến này khởi tạo
    # bằng 'reported' nên mã không qua được bậc nào vẫn mang nhãn "công bố" với
    # dps = 0 — nhãn nguồn sai làm bộ đếm `dps_source` nói ngược sự thật.
    dps_source = 'reported' if dps_ttm > 0 else 'unavailable'

    if dps_ttm <= 0:
        dividends_paid = abs(_safe_float(_get_field(cf0, DIVIDENDS_PAID_ALIASES)))
        if dividends_paid > 0 and shares > 0:
            dps_ttm = (dividends_paid * 1_000_000_000) / shares
            dps_source = 'cash_flow'

    # Bậc 3 chỉ còn ý nghĩa khi payout đến từ bảng ratio ('reported'): nếu payout
    # được suy từ chính `dividends_paid` ở trên thì bậc 2 đã dùng hết dữ liệu đó,
    # và eps × payout chỉ dựng lại đúng con số vừa ra 0. payout None thì bỏ hẳn
    # bậc này — nhân với 0,30 bịa ra một mức cổ tức không có trong BCTC.
    payout_for_dps = ratios.get('payout_ratio')
    if dps_ttm <= 0 and eps_ttm > 0 and payout_for_dps:
        dps_ttm = eps_ttm * payout_for_dps
        dps_source = 'eps_x_payout'

    per_share = {
        'eps_ttm': eps_ttm,
        'bvps': bvps,
        'dps_ttm': max(0.0, dps_ttm),
        'dps_source': dps_source,
    }

    # === Growth ===
    growth = {}
    profits = income['net_profit_parent_5y']
    if len(profits) >= 5 and profits[-1] > 0 and profits[0] > 0:
        cagr_5y = (profits[0] / profits[-1]) ** (1/4) - 1
        growth['profit_growth_5y_cagr'] = cagr_5y
    revenues = income['revenue_5y']
    if len(revenues) >= 5 and revenues[-1] > 0 and revenues[0] > 0:
        growth['revenue_5y_cagr'] = (revenues[0] / revenues[-1]) ** (1/4) - 1
    # Forward growth: conservative default = revenue CAGR with floor 0
    growth['eps_growth_consensus_fwd'] = max(0, growth.get('profit_growth_5y_cagr', 0.05))
    growth['book_value_growth_3y'] = growth.get('profit_growth_5y_cagr', 0.10) * 0.7  # discount cho dividend

    # === Cash flow ===
    operating_cf = _safe_float(_get_field(cf0, CF_ALIASES['operating_cf']))
    capex = abs(_safe_float(_get_field(cf0, CF_ALIASES['capex'])))
    depreciation = _safe_float(_get_field(cf0, CF_ALIASES['depreciation']))

    ebitda_ttm = _safe_float(_get_field(is0, IS_ALIASES['operating_profit'])) + depreciation
    if ebitda_ttm == 0:
        ebitda_ttm = net_profit + depreciation  # rough proxy

    # EBITDA 5y avg (proxy = avg of net_profit_5y + depreciation_ttm)
    profits_for_ebitda = [p for p in profits if p > -1e10][:5]
    if profits_for_ebitda:
        avg_profit_5y = sum(profits_for_ebitda) / len(profits_for_ebitda)
        ebitda_5y_avg = avg_profit_5y + depreciation
    else:
        ebitda_5y_avg = ebitda_ttm

    cash_flow = {
        'operating_cf': operating_cf,
        'capex': -capex,
        'fcff_ttm': operating_cf - capex,
        'ebitda_ttm': ebitda_ttm,
        'ebitda_5y_avg': ebitda_5y_avg,
        'depreciation': depreciation,
    }

    # === Market data ===
    market_cap = (current_price * shares / 1_000_000_000) if (current_price and shares) else 0

    # === EV/EBITDA hiện tại ===
    # FIX: trước đây không module nào set key này, nên methods_ev_ebitda luôn
    # rơi vào default `ratios.get("ev_ebitda", 6.0)` → bội số mục tiêu là HẰNG SỐ
    # 6.0x (cyclical) hoặc 6.8x (stable) cho MỌI doanh nghiệp — trong khi
    # EV/EBITDA giữ 45-50% trọng số cho Thép/Hoá chất/Dầu khí/Nông nghiệp.
    # Đồng thời peer_database.extract_peer_input() lấy ratios['ev_ebitda'] = None
    # nên peer band cho ev_ebitda vĩnh viễn rỗng.
    net_debt_bn = (balance_sheet['short_term_debt'] + balance_sheet['long_term_debt']
                   - balance_sheet['cash_and_equivalents'])
    enterprise_value_bn = market_cap + net_debt_bn + balance_sheet['minority_interest']
    if ebitda_ttm > 0 and enterprise_value_bn > 0:
        ratios['ev_ebitda'] = enterprise_value_bn / ebitda_ttm
    else:
        ratios['ev_ebitda'] = None
    ratios['net_debt'] = net_debt_bn
    ratios['enterprise_value'] = enterprise_value_bn if enterprise_value_bn > 0 else None

    # Beta: dùng beta thực từ regression nếu có, fallback 1.0
    beta_info = raw.get('beta_info', {})
    beta = beta_info.get('beta', 1.0) if beta_info else 1.0

    market = {
        'current_price': current_price or 0,
        'shares_outstanding': int(shares),
        'market_cap': market_cap,  # tỷ đồng
        'beta_2y': beta,
        'beta_r_squared': beta_info.get('r_squared') if beta_info else None,
        'beta_method': beta_info.get('method') if beta_info else 'default',
        'beta_fallback': beta_info.get('fallback', True) if beta_info else True,
        # `weak`: tinh duoc beta nhung khoang tin cay 95% cua no CHUA 1,0, tuc
        # hoi quy khong cho ly do nao de tin uoc luong hon tin tien nghiem.
        # Tach rieng khoi `fallback` ("khong tinh duoc") vi hai chuyen khac nhau
        # va phai dem rieng duoc.
        'beta_weak': beta_info.get('weak', True) if beta_info else True,
        'beta_std_error': beta_info.get('std_error') if beta_info else None,
    }

    # === Asset quality (cho banking) ===
    #
    # Nguồn THẬT là thuyết minh BCTC (`bank_asset_quality`, tới 2025). Bảng
    # ratio dừng ở 2018 và đã gỡ 26/09/2026, nên nhánh cũ gần như luôn rỗng —
    # và khi rỗng thì `calculate_asset_quality_adjustment` trả hệ số 1,0, tức
    # điều chỉnh P/B theo chất lượng tài sản KHÔNG BAO GIỜ chạy.
    #
    # Bao phủ nợ xấu từng bị gán cứng 1,0 ("tạm default reasonable cho VN") —
    # một con số bịa, và nó rơi đúng vào khoảng "trung tính" nên không ai thấy.
    asset_quality = {}
    if aq_latest.get('npl_ratio'):
        from ...financial_fetcher import LOAN_ALLOWANCE_ITEM, bank_npl_coverage
        asset_quality['npl_ratio'] = aq_latest['npl_ratio']
        allowance = _safe_float((bs0 or {}).get(LOAN_ALLOWANCE_ITEM))
        cov = bank_npl_coverage(aq_latest.get('npl_amount'), allowance)
        if cov is not None:
            asset_quality['npl_coverage_ratio'] = cov
    elif ratios.get('npl_ratio'):
        asset_quality['npl_ratio'] = ratios['npl_ratio']

    return {
        'ticker': ticker,
        'overview': overview,
        'market': market,
        'income': income,
        'balance_sheet': balance_sheet,
        'asset_quality': asset_quality,
        'ratios': ratios,
        'per_share': per_share,
        'growth': growth,
        'cash_flow': cash_flow,
    }


# Market params hằng số - production có thể override từ config
MARKET_PARAMS = {
    "risk_free_rate": 0.032,
    "market_risk_premium": 0.08,
    "long_term_inflation": 0.04,
    "long_term_gdp_growth": 0.06,
    "tax_rate_corporate": 0.20,
    "terminal_growth_default": 0.045,
    "vnindex_pe_current": 13.2,
    "vnindex_pb_current": 1.65,
}
