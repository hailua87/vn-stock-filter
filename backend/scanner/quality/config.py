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
# v3 D17 (2026-09-22): diem 3 chieu la PERCENTILE trong nhom nen trung vi ~50;
# nguong cu 60/60/50 tu dong dua ~60% ma vao "Can xem lai" (chay that 100 ma:
# 55 REV, trung vi Chat luong 49). Nay "Can xem lai" nghia la nhom duoi cung
# (percentile < 30 / < 25). Quan tri la thang tuyet doi (100 - diem phat): < 30
# tuong duong tong phat > 70, vd pha loang manh + lech dong tien + cong bo cham.
REVIEW_BELOW = {'governance': 30, 'quality': 30, 'resilience': 25}
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
ACTIVE_MODELS = {'NON_FINANCIAL', 'BANK', 'SECURITIES', 'REAL_ESTATE'}

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
    # Ngan hang. Hai chi tieu ve chat luong tai san — ty le no xau va bao phu
    # no xau — DA GO ngay 24/09/2026 (D24): khong nguon nao co. Da khao sat
    # vnstock/VCI (bang ratio dung o 2018), vnstock/KBS (32 chi tieu, khong cai
    # nao ve no xau) va TCBS (co du lieu nhung la API noi bo). Trong so cua
    # chung chia lai cho cac chi tieu con lai, giu nguyen thu tu uu tien.
    #
    # He qua phai noi ra tren man hinh: chong chiu cua ngan hang o day do bang
    # VON va THANH KHOAN, khong do chat luong tai san. Xem BANK_NOT_EVALUATED.
    'BANK': {
        'quality': [
            ('roa_avg3', 30, True),
            ('roe_avg3', 20, True),
            ('nim_std', 25, False),
            ('cost_income', 25, False),
        ],
        'growth': [
            ('toi_cagr5', 30, True),
            ('pbt_cagr5', 30, True),
            ('loans_cagr5', 20, True),
            ('nonint_income_cagr3', 20, True),
        ],
        'resilience': [
            ('equity_assets', 45, True),
            ('credit_cost_std', 30, False),
            ('ldr', 25, False),
        ],
    },
    # Chu dau tu bat dong san. Blueprint §8.4 khong khai bo chi tieu cho nhom
    # nay; thiet ke 23/09/2026 va ghi nguoc lai vao §8.4.
    #
    # Ba khac biet voi NON_FINANCIAL, moi cai dan toi mot lua chon cu the:
    #  - Loi nhuan loi lom theo chu ky ban giao -> moi trung binh lay 5 nam.
    #  - EBITDA nhay theo nam ban giao nen net_debt_ebitda vo nghia -> dung
    #    debt_equity, mau so la von chu, on dinh qua chu ky.
    #
    # Chieu Tang truong chi co BA chi tieu chu khong phai bon: da thu them
    # "nguoi mua tra tien truoc / doanh thu" va BO, vi no xep NVL (ma kiet que
    # nhat ro) len dau. Xem metrics.real_estate de biet so do va ba mau so da
    # thu. Ba chi tieu dung con hon bon chi tieu co mot cai lat nguoc.
    'REAL_ESTATE': {
        'quality': [
            ('roe_avg5', 25, True),
            ('gross_margin_avg5', 25, True),
            ('cash_conversion5', 25, True),
            ('inventory_turnover', 25, True),
        ],
        'growth': [
            ('revenue_cagr5', 35, True),
            ('npat_cagr5', 35, True),
            ('revenue_up_years5', 30, True),
        ],
        'resilience': [
            ('debt_equity', 35, False),
            ('interest_coverage', 25, True),
            ('current_ratio', 15, True),
            ('profit_drawdown5', 25, False),
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
GOVERNANCE_FLAGS = {
    'dilution':          {'enabled': True,  'source': 'bctc'},
    'earnings_cash_gap': {'enabled': True,  'source': 'bctc'},
    'late_filing':       {'enabled': True,  'source': 'snapshot'},
}

# Hai co da GO ngay 23/09/2026 (§14.2 chot). Chung tung nam trong
# GOVERNANCE_FLAGS voi enabled=False, tuc khong bao gio bat, nhung giao dien
# van mang nhan cua chung — noi voi nguoi doc rang diem Quan tri co xet hai
# yeu to nay, trong khi khong.
#
# Da khao sat 23/09/2026: vnstock khong co; TCBS co getListAuditFirm nhung chi
# cho TEN cong ty kiem toan va nam, KHONG co y kien kiem toan; getTickerOverview
# khong co truong canh bao/kiem soat. Trang thai canh bao duoc cong bo dang
# tin/su kien chu khong phai truong co cau truc.
#
# Khai o day de giao dien noi duoc "chua xet" thay vi im lang. Co nguon that
# thi dua nguoc lai GOVERNANCE_FLAGS.
# Chuoi hien THANG len man hinh nen co dau — cung quy uoc voi ly do veto.
# Chi tieu cua rieng mo hinh BANK da can nhac va khong do duoc (D24).
# Giao dien hien "Chua xet" cho nhom ngan hang, giong cach lam voi §14.2.
BANK_NOT_EVALUATED = {
    'npl_ratio': 'tỷ lệ nợ xấu',
    'npl_coverage': 'bao phủ nợ xấu',
}

GOVERNANCE_NOT_EVALUATED = {
    'warning_status': 'diện cảnh báo / kiểm soát của sở giao dịch',
    'qualified_opinion': 'ý kiến kiểm toán ngoại trừ',
}
DILUTION_STRONG = 0.10     # tang so CP binh quan/nam trong 3 nam
DILUTION_MILD = 0.05
PENALTY = {
    'dilution_strong': 20,
    'dilution_mild': 8,
    'earnings_cash_gap': 25,
    'late_filing': 10,
}
FILING_LAG_DAYS = 45       # BCTC quy: han cong bo + do tre thuc te

# --- Veto (blueprint 8.7) ----------------------------------------------------
VETO_ENABLED = {
    'delisted': True,              # backend/data/delisted_tickers.txt
    'missing_two_quarters': True,  # tu snapshot
}

# Hai veto da GO cung luc voi hai co tren, cung mot ly do: khong co nguon
# (§14.2). Ghi lai day de khong ai tuong la quen.
VETO_NOT_EVALUATED = {
    'suspended_or_controlled': 'bị kiểm soát, hạn chế hoặc đình chỉ giao dịch',
    'adverse_opinion': 'ý kiến kiểm toán trái ngược hoặc từ chối',
}
