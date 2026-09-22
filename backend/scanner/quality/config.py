"""
Cau hinh Module B. Moi nguong o day la MAC DINH, chua phai ket qua backtest.

Dung module Python thay vi YAML (blueprint v2 ghi .yml) de khong them phu
thuoc PyYAML chi cho mot file cau hinh; comment giai thich ly do tung nguong
nam ngay canh gia tri.
"""

# --- Chuan hoa va do phu (blueprint 8.6) -----------------------------------
COVERAGE_MIN = 0.70        # duoi nguong thi chieu de trong, khong gan diem
MIN_PEER_GROUP = 8         # nhom nho hon: percentile qua nhieu, khong cong bo
WINSOR_MIN_GROUP = 20      # winsorize p5/p95 tren nhom nho se cat mat du lieu that
WINSOR_P = (5, 95)
STALE_MAX_PERIODS = 2      # chi tieu cu hon 2 ky so voi ky moi nhat -> coi la thieu

# --- Nguong trang thai watchlist (blueprint 10) ----------------------------
QUALIFY = {'quality': 75, 'growth': 70, 'governance': 70, 'resilience': 65}
REVIEW_BELOW = {'governance': 60, 'quality': 60, 'resilience': 50}
SHARP_DROP_POINTS = 15     # co phu "Giam manh", khong doi trang thai

# --- Quy doi dinh gia (blueprint 9) ----------------------------------------
VALUATION_MIN_CONFIDENCE = 50.0   # engine tra confidence thang 0-100
VALUATION_ATTRACTIVE_UPSIDE = 20.0
VALUATION_EXPENSIVE_UPSIDE = -10.0
# Phuong phap dang gian luoc: neu la phuong phap trong so lon nhat thi ep
# confidence xuong duoi nguong, tranh upside cuc lon (vd RNAV he so vung mac
# dinh) bien thanh muc "Hap dan".
# Ten phai TRUNG KHOP ten phuong phap engine tra ve: engine goi la
# 'SOTP Simplified', nen ban cu chi co 'SOTP' khien gioi han khong bao gio ap
# cho VIC/REE/MSN/GEX (holding lay SOTP lam phuong phap chinh).
SIMPLIFIED_METHODS = {'RNAV', 'SOTP', 'SOTP Simplified'}

# --- Anh xa 19 nhom nganh cua valuation engine -> 5 mo hinh cham diem -------
INDUSTRY_TO_MODEL = {
    'Banking': 'BANK',
    'Securities': 'SECURITIES',
    'Insurance': 'INSURANCE',
    'Real_Estate': 'REAL_ESTATE',
    # Holding da nganh gom ca BDS; tam xep phi tai chinh, can xac thuc tung ma
    'Diversified_Holding': 'NON_FINANCIAL',
    'Unknown': None,
}
DEFAULT_MODEL = 'NON_FINANCIAL'
ACTIVE_MODELS = {'NON_FINANCIAL', 'BANK', 'SECURITIES'}

# --- Chi tieu theo mo hinh (blueprint 8.4) ----------------------------------
# (metric_key, trong_so, cao_hon_tot_hon)
MODELS = {
    'NON_FINANCIAL': {
        'quality': [
            ('roic_avg5', 25, True),
            ('gross_margin_std5', 20, False),
            ('ebit_margin_std5', 20, False),
            ('cash_conversion3', 20, True),
            ('asset_turnover', 15, True),
        ],
        'growth': [
            ('revenue_cagr5', 30, True),
            ('ebit_cagr5', 25, True),
            ('cfo_cagr5', 20, True),
            ('revenue_up_years5', 15, True),
            ('reinvestment_rate', 10, True),
        ],
        'resilience': [
            ('net_debt_ebitda', 35, False),
            ('interest_coverage', 30, True),
            ('current_ratio', 15, True),
            ('profit_drawdown5', 20, False),
        ],
    },
    'BANK': {
        'quality': [
            ('roa_avg3', 25, True),
            ('roe_avg3', 15, True),
            ('nim_std', 20, False),
            ('npl_ratio', 20, False),
            ('cost_income', 20, False),
        ],
        'growth': [
            ('toi_cagr5', 30, True),
            ('pbt_cagr5', 30, True),
            ('loans_cagr5', 20, True),
            ('nonint_income_cagr3', 20, True),
        ],
        'resilience': [
            ('npl_coverage', 35, True),
            ('equity_assets', 30, True),
            ('credit_cost_std', 20, False),
            ('ldr', 15, False),
        ],
    },
    'SECURITIES': {
        'quality': [
            ('roe_avg3', 30, True),
            ('recurring_share', 35, True),
            ('fvtpl_equity', 35, False),
        ],
        'growth': [
            ('revenue_cagr5', 40, True),
            ('npat_cagr5', 40, True),
            ('margin_loans_cagr3', 20, True),
        ],
        'resilience': [
            ('margin_loans_equity', 35, False),
            ('debt_equity', 35, False),
            ('profit_drawdown5', 30, False),
        ],
    },
}

# --- Co quan tri tu dong (blueprint 8.5) ------------------------------------
# enabled=False: CHUA CO NGUON du lieu -> loai khoi mau so do phu. Neu de
# enabled=True ma khong co nguon, moi ma deu thieu 2/5 co, do phu 60% < 70%
# va chieu Quan tri cua TOAN BO universe thanh rong.
GOVERNANCE_FLAGS = {
    'dilution':          {'enabled': True,  'source': 'bctc'},
    'earnings_cash_gap': {'enabled': True,  'source': 'bctc'},
    'late_filing':       {'enabled': True,  'source': 'snapshot'},
    'warning_status':    {'enabled': False, 'source': 'chua co'},
    'qualified_opinion': {'enabled': False, 'source': 'chua co'},
}
DILUTION_STRONG = 0.10     # tang so CP binh quan/nam trong 3 nam
DILUTION_MILD = 0.05
PENALTY = {
    'dilution_strong': 20,
    'dilution_mild': 8,
    'earnings_cash_gap': 25,
    'late_filing': 10,
    'warning_status': 25,
    'qualified_opinion': 30,
}
FILING_LAG_DAYS = 45       # BCTC quy: han cong bo + do tre thuc te

# --- Veto (blueprint 8.7) ----------------------------------------------------
VETO_ENABLED = {
    'delisted': True,              # backend/data/delisted_tickers.txt
    'missing_two_quarters': True,  # tu snapshot
    'suspended_or_controlled': False,  # chua co nguon trang thai
    'adverse_opinion': False,          # chua co nguon y kien kiem toan
}
