#!/usr/bin/env python3
"""
Test offline integration với mock fundamentals format giống vnstock 4.x.
Chạy trước khi deploy để verify normalizer + engine hoạt động đúng.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.strategies.valuation import value_ticker


# Mock data theo format mà financial_fetcher.fetch_fundamentals() sẽ trả về.
# Cấu trúc: {'ticker', 'current_price', 'overview', 'balance_sheet', 'income',
#            'cash_flow', 'ratio'} với các statements là list of period records.

VIB_MOCK = {
    'ticker': 'VIB',
    'current_price': 18500,
    'fetched_at': '2026-05-26T10:00:00',
    'overview': {
        'ticker': 'VIB',
        'industry': 'Ngân hàng',
        'sector': 'Ngân hàng',
        'company_name': 'NH TMCP Quốc tế VN',
        'outstanding_share': 3_087_000_000,
        'foreign_percent': 0.20,
    },
    'balance_sheet': [
        # Latest first (2024)
        {
            'total_assets': 480000,
            'owner_s_equity': 38500,
            'loans_to_customers': 320000,
            'customer_deposits': 280000,
            'short_term_borrowings': 0,
            'long_term_borrowings': 0,
            'cash': 0,
            'outstanding_share': 3_087_000_000,
        },
    ],
    'income': [
        {'revenue': 22000, 'net_profit': 7680, 'attributable_to_parent_company': 7680,
         'operating_profit': 13500, 'net_interest_income': 17800,
         'interest_and_similar_income': 17800, 'profit_before_tax': 9600},
        {'revenue': 22000, 'net_profit': 10700, 'attributable_to_parent_company': 10700,
         'operating_profit': 14000, 'net_interest_income': 18000, 'interest_and_similar_income': 18000},
        {'revenue': 21000, 'net_profit': 10580, 'attributable_to_parent_company': 10580,
         'operating_profit': 14200, 'net_interest_income': 17500, 'interest_and_similar_income': 17500},
        {'revenue': 18000, 'net_profit': 8011, 'attributable_to_parent_company': 8011,
         'operating_profit': 11000, 'net_interest_income': 14000, 'interest_and_similar_income': 14000},
        {'revenue': 14000, 'net_profit': 5803, 'attributable_to_parent_company': 5803,
         'operating_profit': 8500, 'net_interest_income': 11000, 'interest_and_similar_income': 11000},
    ],
    'cash_flow': [
        {'net_cash_inflows_outflows_from_operating_activities': 12000,
         'purchase_of_fixed_assets': -500, 'depreciation_and_amortisation': 400},
    ],
    'ratio': [
        # Latest first - vnstock thường trả % dưới dạng số nguyên (21 = 21%)
        {'pe': 7.4, 'pb': 1.48, 'roe': 20.5, 'roa': 1.7, 'eps': 2487,
         'bvps': 12472, 'dividend_yield': 5.0, 'npl_ratio': 2.5, 'car': 12.2,
         'payout_ratio': 30.0},
        {'pe': 8.0, 'pb': 2.1, 'roe': 25.0, 'roa': 2.1, 'eps': 3470, 'bvps': 11400},
        {'pe': 9.5, 'pb': 2.8, 'roe': 30.0, 'roa': 2.5, 'eps': 3500, 'bvps': 10300},
        {'pe': 6.5, 'pb': 1.8, 'roe': 27.0, 'roa': 2.3, 'eps': 2680, 'bvps': 9100},
        {'pe': 5.5, 'pb': 1.5, 'roe': 24.0, 'roa': 2.0, 'eps': 1940, 'bvps': 8000},
    ],
}


DBC_MOCK = {
    'ticker': 'DBC',
    'current_price': 28800,
    'fetched_at': '2026-05-26T10:00:00',
    'overview': {
        'ticker': 'DBC',
        'industry': 'Thực phẩm và đồ uống',
        'sector': 'Sản xuất Thực phẩm',
        'outstanding_share': 242_000_000,
    },
    'balance_sheet': [
        {'total_assets': 13800, 'owner_s_equity': 4300, 'inventory_net': 4200,
         'fixed_assets': 5900, 'short_term_borrowings': 4800, 'long_term_borrowings': 2100,
         'cash': 500, 'outstanding_share': 242_000_000},
    ],
    'income': [
        {'revenue': 13500, 'net_profit': 770, 'attributable_to_parent_company': 770,
         'operating_profit': 850, 'profit_before_tax': 870},
        {'revenue': 11280, 'net_profit': 28, 'attributable_to_parent_company': 28,
         'operating_profit': 50},
        {'revenue': 11558, 'net_profit': -100, 'attributable_to_parent_company': -100,
         'operating_profit': -80},
        {'revenue': 10812, 'net_profit': 829, 'attributable_to_parent_company': 829,
         'operating_profit': 900},
        {'revenue': 10022, 'net_profit': 1400, 'attributable_to_parent_company': 1400,
         'operating_profit': 1500},
    ],
    'cash_flow': [
        {'net_cash_inflows_outflows_from_operating_activities': 1180,
         'purchase_of_fixed_assets': -680, 'depreciation_and_amortisation': 500},
    ],
    'ratio': [
        {'pe': 9.0, 'pb': 1.62, 'roe': 18.0, 'roa': 5.6, 'eps': 3182,
         'bvps': 17770, 'payout_ratio': 15.0, 'debt_to_equity': 1.60},
        {'pe': 30.0, 'pb': 1.4, 'roe': 0.8, 'roa': 0.2, 'eps': 116, 'bvps': 14500},
        {'pe': -1, 'pb': 1.3, 'roe': -2.5, 'roa': -0.7, 'eps': -413, 'bvps': 14000},
        {'pe': 8.0, 'pb': 1.8, 'roe': 21.0, 'roa': 6.0, 'eps': 3425, 'bvps': 13000},
        {'pe': 5.5, 'pb': 2.0, 'roe': 42.0, 'roa': 12.0, 'eps': 5785, 'bvps': 10500},
    ],
}


PAN_MOCK = {
    'ticker': 'PAN',
    'current_price': 24700,
    'fetched_at': '2026-05-26T10:00:00',
    'overview': {
        'ticker': 'PAN',
        'industry': 'Thực phẩm và đồ uống',
        'sector': 'Sản xuất Thực phẩm',
        'outstanding_share': 209_000_000,
    },
    'balance_sheet': [
        {'total_assets': 18500, 'owner_s_equity': 5100, 'minority_interests': 3200,
         'inventory_net': 3800, 'fixed_assets': 4500,
         'short_term_borrowings': 5100, 'long_term_borrowings': 1800,
         'cash': 1950, 'outstanding_share': 209_000_000},
    ],
    'income': [
        {'revenue': 16200, 'net_profit': 720, 'attributable_to_parent_company': 420,
         'operating_profit': 1070, 'gross_profit': 2800},
        {'revenue': 13200, 'net_profit': 820, 'attributable_to_parent_company': 460,
         'operating_profit': 1100},
        {'revenue': 13650, 'net_profit': 800, 'attributable_to_parent_company': 442,
         'operating_profit': 1050},
        {'revenue': 9080, 'net_profit': 552, 'attributable_to_parent_company': 280,
         'operating_profit': 700},
        {'revenue': 7905, 'net_profit': 348, 'attributable_to_parent_company': 165,
         'operating_profit': 450},
    ],
    'cash_flow': [
        {'net_cash_inflows_outflows_from_operating_activities': 1350,
         'purchase_of_fixed_assets': -750, 'depreciation_and_amortisation': 450},
    ],
    'ratio': [
        {'pe': 12.3, 'pb': 1.01, 'roe': 8.5, 'roa': 3.9, 'eps': 2010,
         'bvps': 24402, 'dividend_yield': 2.5, 'payout_ratio': 30.0,
         'debt_to_equity': 0.83},
        {'pe': 14.0, 'pb': 1.1, 'roe': 9.5, 'roa': 4.3, 'eps': 2200, 'bvps': 22500},
        {'pe': 11.0, 'pb': 0.95, 'roe': 9.2, 'roa': 4.0, 'eps': 2115, 'bvps': 21800},
        {'pe': 10.5, 'pb': 0.85, 'roe': 7.5, 'roa': 3.2, 'eps': 1340, 'bvps': 19000},
        {'pe': 13.0, 'pb': 0.90, 'roe': 5.5, 'roa': 2.5, 'eps': 790, 'bvps': 17500},
    ],
}


MOCK_DATA = {'VIB': VIB_MOCK, 'PAN': PAN_MOCK, 'DBC': DBC_MOCK}


if __name__ == '__main__':
    print("=" * 75)
    print("OFFLINE INTEGRATION TEST — vnstock format → valuation engine")
    print("=" * 75)

    for ticker, mock in MOCK_DATA.items():
        print(f"\n{'─' * 75}")
        print(f"  ▶ {ticker}")
        print(f"{'─' * 75}")

        # enrich_market_metrics=False vì sandbox không có OHLCV cache
        report = value_ticker(ticker, raw_fundamentals=mock,
                              enrich_market_metrics=False)
        if report is None:
            print(f"  ❌ FAILED — engine returned None")
            continue

        d = report.to_dict()
        print(f"  Industry        : {d['industry']} (source: {d['industry_source']})")
        print(f"  Current price   : {d['current_price']:>10,.0f} VND")
        print(f"  Fair value      : {d['fair_value']:>10,.0f} VND  [{d['fair_value_low']:,.0f} - {d['fair_value_high']:,.0f}]")
        print(f"  Upside          : {d['upside_pct']:>+9.1f}%")
        print(f"  Verdict         : {d['verdict']}")
        print(f"  Confidence      : {d['confidence']:>10.0f}%")
        print(f"  Methods used    : {', '.join(d['methods_used'])}")

        print(f"\n  Method details:")
        for m in d['method_details']:
            print(f"    • {m['method']:<28} w={m['weight']:>3.0f}%  "
                  f"fair={m['fair_value']:>8,.0f}  upside={m['upside_pct']:>+5.1f}%  conf={m['confidence']:>3.0f}%")

        if d['warnings']:
            print(f"\n  ⚠️  Warnings ({len(d['warnings'])}):")
            for w in d['warnings']:
                print(f"    • {w}")

    print(f"\n{'=' * 75}")
    print("All tests completed.")
