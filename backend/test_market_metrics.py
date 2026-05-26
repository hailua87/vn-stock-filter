#!/usr/bin/env python3
"""
Test market_metrics module (beta + historical multiples) với synthetic data.
Tạo OHLCV cache giả lập + VN-Index để verify regression logic hoạt động.
"""
from __future__ import annotations
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

# Tạo synthetic OHLCV cache cho test
TEST_CACHE_DIR = Path('/tmp/test_market_metrics_cache')
TEST_VNINDEX_PATH = Path('/tmp/test_market_metrics_vnindex.parquet')

# Patch path BEFORE import
import scanner.market_metrics as mm
mm.OHLCV_CACHE_DIR = TEST_CACHE_DIR
mm.VNINDEX_CACHE = TEST_VNINDEX_PATH


def generate_synthetic_market(days: int = 800, seed: int = 42):
    """
    Sinh VN-Index synthetic và 3 stock với beta target khác nhau:
      - HIGH_BETA: target β ≈ 1.5
      - MID_BETA : target β ≈ 1.0
      - LOW_BETA : target β ≈ 0.5
    """
    np.random.seed(seed)

    # VN-Index: random walk với drift nhẹ
    dates = pd.date_range(end=datetime.now().date() - timedelta(days=1),
                          periods=days, freq='B')  # business days
    index_returns = np.random.normal(0.0003, 0.012, days)  # daily ~12% annual vol
    index_prices = 1000 * np.exp(np.cumsum(index_returns))

    vnindex_df = pd.DataFrame({'Date': dates, 'Close': index_prices})
    TEST_VNINDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    vnindex_df.to_parquet(TEST_VNINDEX_PATH, index=False)

    # Generate stocks với beta khác nhau
    TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for ticker, target_beta in [('HIGH_BETA', 1.5), ('MID_BETA', 1.0), ('LOW_BETA', 0.5)]:
        # Stock returns = α + β × market + ε
        idiosyncratic = np.random.normal(0, 0.015, days)  # 15% idio vol
        stock_returns = 0.0001 + target_beta * index_returns + idiosyncratic
        stock_prices = 30000 * np.exp(np.cumsum(stock_returns))  # bắt đầu 30k VND

        df = pd.DataFrame({
            'Date': dates,
            'Open': stock_prices * (1 + np.random.normal(0, 0.002, days)),
            'High': stock_prices * (1 + np.abs(np.random.normal(0, 0.005, days))),
            'Low': stock_prices * (1 - np.abs(np.random.normal(0, 0.005, days))),
            'Close': stock_prices,
            'Volume': np.random.randint(100_000, 5_000_000, days),
        })
        cache_file = TEST_CACHE_DIR / f'{ticker}_adj.parquet'
        df.to_parquet(cache_file, index=False)


def test_beta_calculation():
    """Verify beta regression recovers approximately the target beta."""
    print("=" * 70)
    print("TEST 1: BETA CALCULATION")
    print("=" * 70)

    cases = [
        ('HIGH_BETA', 1.5, (1.2, 1.8)),
        ('MID_BETA', 1.0, (0.8, 1.2)),
        ('LOW_BETA', 0.5, (0.3, 0.7)),
    ]

    all_passed = True
    for ticker, target, acceptable_range in cases:
        result = mm.calculate_beta(ticker, lookback_days=730)
        beta = result['beta_raw']  # raw, chưa Blume adjust
        passed = acceptable_range[0] <= beta <= acceptable_range[1]
        status = "✓" if passed else "✗"
        all_passed = all_passed and passed
        print(f"  {status} {ticker:<12} target={target:.2f}  recovered={beta:.3f}  "
              f"adj={result['beta_adjusted']:.3f}  R²={result['r_squared']:.2f}  "
              f"obs={result['observations']}")

    print(f"\n  {'PASS' if all_passed else 'FAIL'}: beta regression recovers target ±0.3\n")
    return all_passed


def test_beta_fallback():
    """Verify graceful fallback khi không có data."""
    print("=" * 70)
    print("TEST 2: BETA FALLBACK")
    print("=" * 70)

    result = mm.calculate_beta('NONEXISTENT_TICKER')
    expected_fallback = result['fallback'] and result['beta'] == 1.0
    status = "✓" if expected_fallback else "✗"
    print(f"  {status} Fallback: beta={result['beta']}, fallback={result['fallback']}, "
          f"method={result['method']}\n")
    return expected_fallback


def test_historical_multiples():
    """Test historical P/E và P/B calculation."""
    print("=" * 70)
    print("TEST 3: HISTORICAL MULTIPLES")
    print("=" * 70)

    # Mock fundamentals với 5 năm EPS và BVPS
    mock_fundamentals = {
        'ticker': 'MID_BETA',
        'ratio': [
            # vnstock returns latest first
            {'year': 2024, 'eps': 3000, 'bvps': 20000, 'pe': 10, 'pb': 1.5},
            {'year': 2023, 'eps': 2800, 'bvps': 18000, 'pe': 11, 'pb': 1.7},
            {'year': 2022, 'eps': 2500, 'bvps': 16000, 'pe': 12, 'pb': 1.9},
            {'year': 2021, 'eps': 2200, 'bvps': 14000, 'pe': 9, 'pb': 1.4},
            {'year': 2020, 'eps': 1800, 'bvps': 12500, 'pe': 8, 'pb': 1.2},
        ],
    }

    result = mm.calculate_historical_multiples('MID_BETA', mock_fundamentals)

    print(f"  observations: {result['observations']}")
    print(f"  P/E history ({len(result['pe_history'])} points):")
    for p in result['pe_history'][-5:]:
        print(f"    {p['period']:<10} price={p['price']:>10,.0f}  "
              f"eps={p['eps']:>6,.0f}  P/E={p['pe']:>5.1f}x")

    print(f"\n  P/E median 5Y : {result['pe_5y_median']}x  "
          f"[P25={result['pe_5y_p25']}, P75={result['pe_5y_p75']}]")
    print(f"  P/B median 5Y : {result['pb_5y_median']}x  "
          f"[P25={result['pb_5y_p25']}, P75={result['pb_5y_p75']}]")

    passed = (result['pe_5y_median'] is not None
              and result['pb_5y_median'] is not None
              and result['observations'] >= 3)
    status = "✓" if passed else "✗"
    print(f"\n  {status} {'PASS' if passed else 'FAIL'}: computed real multiples (not proxy)\n")
    return passed


def test_enrich_integration():
    """Test enrich_with_market_metrics tích hợp end-to-end."""
    print("=" * 70)
    print("TEST 4: ENRICH FUNDAMENTALS WITH MARKET METRICS")
    print("=" * 70)

    raw = {
        'ticker': 'HIGH_BETA',
        'current_price': 35000,
        'overview': {'industry': 'Banking'},
        'ratio': [
            {'year': 2024, 'eps': 3000, 'bvps': 20000, 'roe': 18, 'pe': 10, 'pb': 1.5},
            {'year': 2023, 'eps': 2800, 'bvps': 18000, 'roe': 17},
            {'year': 2022, 'eps': 2500, 'bvps': 16000, 'roe': 16},
            {'year': 2021, 'eps': 2200, 'bvps': 14000, 'roe': 16},
            {'year': 2020, 'eps': 1800, 'bvps': 12500, 'roe': 15},
        ],
    }

    enriched = mm.enrich_with_market_metrics('HIGH_BETA', raw)

    has_beta = 'beta_info' in enriched and not enriched['beta_info']['fallback']
    has_hist = 'historical_multiples' in enriched and not enriched['historical_multiples']['fallback']

    status1 = "✓" if has_beta else "✗"
    status2 = "✓" if has_hist else "✗"

    print(f"  {status1} Beta added: {enriched['beta_info']['beta']:.3f} "
          f"(method={enriched['beta_info']['method']})")
    print(f"  {status2} Historical multiples: P/E median = {enriched['historical_multiples']['pe_5y_median']}, "
          f"P/B median = {enriched['historical_multiples']['pb_5y_median']}")

    passed = has_beta and has_hist
    print(f"\n  {'PASS' if passed else 'FAIL'}: enrichment works end-to-end\n")
    return passed


def cleanup():
    """Xóa test cache."""
    if TEST_CACHE_DIR.exists():
        shutil.rmtree(TEST_CACHE_DIR)
    if TEST_VNINDEX_PATH.exists():
        TEST_VNINDEX_PATH.unlink()


if __name__ == '__main__':
    print("\nGenerating synthetic market data...")
    generate_synthetic_market(days=600)
    print("✓ Synthetic data created\n")

    results = []
    results.append(('Beta calculation', test_beta_calculation()))
    results.append(('Beta fallback', test_beta_fallback()))
    results.append(('Historical multiples', test_historical_multiples()))
    results.append(('Enrich integration', test_enrich_integration()))

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        all_pass = all_pass and passed

    cleanup()
    sys.exit(0 if all_pass else 1)
