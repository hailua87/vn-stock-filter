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
                            'equity', 'von_chu_so_huu', 'common_shareholder_s_equity'],
    'total_liabilities': ['liabilities', 'LIABILITIES (Bn. VND)', 'total_liabilities'],
    'short_term_debt': ['short_term_borrowings', 'short_term_debt', 'no_ngan_han'],
    'long_term_debt': ['long_term_borrowings', 'long_term_debt', 'no_dai_han'],
    'cash_and_equivalents': ['cash', 'cash_and_equivalents', 'tien_va_tuong_duong_tien'],
    'inventory': ['inventories', 'inventory_net', 'hang_ton_kho'],
    'fixed_assets': ['fixed_assets', 'net_fixed_assets', 'tai_san_co_dinh'],
    'investment_property': ['investment_in_properties', 'investment_property', 'bds_dau_tu'],
    'loans_to_customers': ['loans_to_customers', 'net_loans_to_customers',
                            'loans_and_advances_to_customers', 'cho_vay_khach_hang'],
    'customer_deposits': ['customer_deposits', 'deposits_from_customers', 'tien_gui_khach_hang'],
    'minority_interest': ['minority_interests', 'non_controlling_interests', 'loi_ich_co_dong_thieu_so'],
}

IS_ALIASES = {
    'revenue': ['revenue', 'net_revenue', 'net_sales', 'doanh_thu_thuan', 'sales'],
    'gross_profit': ['gross_profit', 'lai_gop'],
    'operating_profit': ['operating_profit', 'profit_loss_from_operating_activities', 'lai_thuan_hd'],
    'profit_before_tax': ['profit_before_tax', 'pretax_profit', 'loi_nhuan_truoc_thue'],
    'net_profit': ['net_profit_for_the_year', 'net_profit', 'profit_after_tax',
                   'attributable_to_parent_company', 'loi_nhuan_sau_thue'],
    'net_profit_parent': ['attributable_to_parent_company', 'profit_after_tax_attributable_to_parent',
                          'net_profit_for_the_year', 'loi_nhuan_co_dong_cong_ty_me'],
    'interest_income': ['interest_and_similar_income', 'net_interest_income', 'thu_nhap_lai'],
    'net_interest_income': ['net_interest_income', 'thu_nhap_lai_thuan'],
}

CF_ALIASES = {
    'operating_cf': ['net_cash_inflows_outflows_from_operating_activities', 'cf_from_operations',
                     'dong_tien_tu_hd_kinh_doanh'],
    'capex': ['purchase_of_fixed_assets', 'capex', 'mua_tai_san'],
    'depreciation': ['depreciation_and_amortisation', 'depreciation', 'khau_hao'],
}

RATIO_ALIASES = {
    'pe_ttm': ['pe', 'p_e', 'priceToEarning', 'price_to_earnings'],
    'pb_current': ['pb', 'p_b', 'priceToBook', 'price_to_book'],
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
    'debt_to_equity': ['debt_to_equity', 'de_ratio'],
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
              or _safe_float(_get_field(bs0, ['outstanding_share', 'issue_share', 'common_shares']))
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

    # CAR cho banking (đôi khi nằm ở ratio table, đôi khi BS)
    car = _safe_float(_get_field(r0, RATIO_ALIASES['car']))
    if car == 0:
        car = 0.115  # default conservative cho VN banks
    balance_sheet['car'] = car

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

    # Default values nếu missing
    ratios.setdefault('payout_ratio', 0.30)
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
    dps_source = 'reported'

    if dps_ttm <= 0:
        dividends_paid = abs(_safe_float(_get_field(cf0, [
            'dividends_paid', 'dividend_paid', 'payment_of_dividends',
            'co_tuc_da_tra',
        ])))
        if dividends_paid > 0 and shares > 0:
            dps_ttm = (dividends_paid * 1_000_000_000) / shares
            dps_source = 'cash_flow'

    if dps_ttm <= 0 and eps_ttm > 0:
        dps_ttm = eps_ttm * ratios.get('payout_ratio', 0.30)
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
    }

    # === Asset quality (cho banking) ===
    asset_quality = {}
    if ratios.get('npl_ratio'):
        asset_quality['npl_ratio'] = ratios['npl_ratio']
        # Coverage ratio: cần loan_loss_reserves / NPL
        # Tạm default reasonable cho VN
        asset_quality['npl_coverage_ratio'] = 1.0

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
